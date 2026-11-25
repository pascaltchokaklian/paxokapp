import sqlite3
import tempfile
from datetime import datetime
from io import StringIO
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch
from urllib.parse import parse_qs, urlparse
from zoneinfo import ZoneInfo

import requests
from django.conf import settings
from django.contrib.auth.models import User
from django.contrib.sessions.middleware import SessionMiddleware
from django.core.management import call_command
from django.test import TestCase
from django.test import RequestFactory
from django.test.utils import override_settings
from django.urls import reverse
from social_django.models import UserSocialAuth

from .map_data import get_map_cols
from .strava_sync import import_segment_efforts, sync_strava_activities
from .views import strava_connected


class PortalMapTests(TestCase):
    def setUp(self):
        temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(temp_dir.cleanup)
        database_path = Path(temp_dir.name) / 'centcols.sqlite3'

        connection = sqlite3.connect(database_path)
        try:
            connection.executescript(
                '''
                CREATE TABLE myapp_col (
                    col_code TEXT,
                    col_name TEXT,
                    col_alt REAL,
                    col_lat REAL,
                    col_lon REAL,
                    col_type TEXT
                );
                CREATE TABLE myapp_col_counter (
                    strava_user_id INTEGER,
                    col_code TEXT,
                    col_count INTEGER,
                    year_col_count INTEGER,
                    last_passage_date TEXT
                );
                CREATE TABLE myapp_col_perform (
                    strava_id INTEGER,
                    col_code TEXT
                );
                CREATE TABLE myapp_activity (
                    act_id INTEGER,
                    strava_user_id INTEGER,
                    act_type TEXT,
                    act_dist REAL,
                    act_time INTEGER,
                    act_den INTEGER,
                    act_power INTEGER,
                    act_normal_power INTEGER,
                    act_name TEXT,
                    act_start_date TEXT,
                    strava_id INTEGER
                );
                CREATE TABLE myapp_country (
                    country_code TEXT,
                    country_name TEXT,
                    code_100cols TEXT
                );
                CREATE TABLE myapp_region (
                    country_code TEXT,
                    region_code TEXT,
                    region_name TEXT
                );
                INSERT INTO myapp_country VALUES
                    ('FRA', 'France', 'FR'),
                    ('ARG', 'Argentine', 'AR');
                INSERT INTO myapp_region VALUES
                    ('FRA', '04', 'Alpes de Haute-Provence'),
                    ('ARG', 'A', 'Salta');
                INSERT INTO myapp_col VALUES
                    ('FR-04-0001', 'Col témoin', 1200, 43.7, 7.2, 'R'),
                    ('FR-01-0003', 'Col de l’Ain', 800, 46, 5, 'R'),
                    ('AR-A-0001', 'Col argentin', 1500, -24, -65, 'S'),
                    ('FR-06-0002', 'Col invalide', 1400, 91, 7.2, 'P');
                INSERT INTO myapp_col_counter VALUES
                    (42, 'FR-04-0001', 5, 1, '2026-06-14 08:30:00'),
                    (42, 'FR-01-0003', 2, 3, '2026-07-01 09:00:00');
                INSERT INTO myapp_activity VALUES
                    (1, 42, 'Ride', 25000, 5400, 650, 180, 195, 'Sortie du dimanche', '2026-06-14 08:30:00', 7001),
                    (2, 99, 'Ride', 12000, 2700, 240, 150, 165, 'Activité autre compte', '2026-06-15 09:00:00', 7002),
                    (3, 42, 'Run', 8500, 1800, 310, 120, 130, 'Balade du col', '2026-05-10 10:00:00', 7003);
                INSERT INTO myapp_col_perform VALUES
                    (7001, 'FR-04-0001'),
                    (7002, 'FR-04-0001'),
                    (7003, 'FR-04-0001');
                CREATE TABLE myapp_activity_info (
                    act_info_id INTEGER,
                    strava_id INTEGER,
                    info_txt TEXT
                );
                INSERT INTO myapp_activity_info VALUES
                    (1, 7001, 'Plus longue sortie depuis "Test" le 14/06/2026 ( 25.0 Km )');
                CREATE TABLE myapp_segment (
                    segment_id INTEGER NOT NULL PRIMARY KEY,
                    strava_segment_id INTEGER,
                    activity_type TEXT NOT NULL,
                    segment_name TEXT NOT NULL,
                    slope REAL,
                    lenght REAL,
                    ascent NUMERIC,
                    power NUMERIC
                );
                CREATE TABLE myapp_perform (
                    perform_id INTEGER NOT NULL PRIMARY KEY,
                    strava_perf_id INTEGER,
                    segment_id INTEGER NOT NULL,
                    perf_date DATETIME NOT NULL,
                    perf_chrono INTEGER NOT NULL,
                    perf_vam INTEGER NOT NULL,
                    perf_fc INTEGER NOT NULL,
                    perf_fcmax INTEGER NOT NULL,
                    strava_user_id INTEGER,
                    perf_power INTEGER
                );
                CREATE TABLE myapp_user_var (
                    id INTEGER NOT NULL PRIMARY KEY,
                    strava_user_id INTEGER,
                    view_country_code TEXT NOT NULL,
                    view_region_code TEXT NOT NULL,
                    last_update INTEGER
                );
                '''
            )
        finally:
            connection.close()

        app_path = Path(temp_dir.name) / 'app.sqlite3'
        settings_override = override_settings(
            CENTCOLS_LEGACY_DB_PATH=database_path,
            CENTCOLS_DB_PATH=app_path,
        )
        settings_override.enable()
        self.addCleanup(settings_override.disable)
        call_command('import_legacy_data', stdout=StringIO())

    def test_power_page_shows_only_positive_cycling_power_for_own_activities(self):
        connection = sqlite3.connect(settings.CENTCOLS_DB_PATH)
        try:
            connection.executemany(
                'INSERT INTO myapp_activity (act_id, strava_user_id, act_type, act_normal_power, '
                'act_name, act_start_date, strava_id) VALUES (?, 42, ?, ?, ?, ?, ?)',
                [
                    (4, 'VirtualRide', 200, 'Vélo virtuel', '2026-04-01', 7004),
                    (5, 'MountainBikeRide', 210, 'VTT', '2026-03-01', 7005),
                    (6, 'GravelRide', 0, 'Gravel sans puissance', '2026-02-01', 7006),
                    (7, 'Ride', -5, 'Puissance négative', '2026-01-01', 7007),
                    (8, 'Ride', None, 'Puissance absente', '2025-12-01', 7008),
                ],
            )
            connection.commit()
        finally:
            connection.close()
        session = self.client.session
        session['strava_user_id'] = 42
        session.save()
        with patch('portal.views.requests.get') as fetch:
            page = self.client.get(reverse('portal:power_records'))
        fetch.assert_not_called()
        self.assertContains(page, 'Sortie du dimanche')
        self.assertContains(page, '195 W')
        self.assertContains(page, '<span class="power-date-full">14/06/2026</span>', html=True)
        self.assertContains(page, '<span class="power-date-short">14 juin</span>', html=True)
        self.assertNotContains(page, '180 W')
        self.assertContains(page, 'Vélo virtuel')
        self.assertContains(page, '200 W')
        self.assertContains(page, 'VTT')
        self.assertContains(page, '210 W')
        self.assertNotContains(page, 'Balade du col')
        self.assertNotContains(page, 'Gravel sans puissance')
        self.assertNotContains(page, 'Puissance négative')
        self.assertNotContains(page, 'Puissance absente')
        self.assertNotContains(page, 'Activité autre compte')
        self.assertNotContains(page, 'Importer les puissances')

    def test_power_page_empty_when_no_positive_cycling_power(self):
        connection = sqlite3.connect(settings.CENTCOLS_DB_PATH)
        try:
            connection.execute('UPDATE myapp_activity SET act_normal_power = 0 WHERE strava_id = 7001')
            connection.execute('UPDATE myapp_activity SET act_normal_power = NULL WHERE strava_id = 7003')
            connection.commit()
        finally:
            connection.close()
        session = self.client.session
        session['strava_user_id'] = 42
        session.save()
        page = self.client.get(reverse('portal:power_records'))
        self.assertContains(page, 'Aucune activité vélo avec une puissance normalisée positive.')
        self.assertNotContains(page, 'Sortie du dimanche')

    def test_power_page_requires_connection(self):
        page = self.client.get(reverse('portal:power_records'))
        self.assertContains(page, 'Connectez-vous à Strava')
        self.assertNotContains(page, 'Sortie du dimanche')

    def test_public_home_shows_map_and_application_list_is_separate(self):
        response = self.client.get('/')

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.headers['X-Frame-Options'], 'SAMEORIGIN')
        self.assertNotContains(response, 'CARTE INTERACTIVE')
        self.assertNotContains(response, 'Les cols, en un coup d’œil')
        self.assertNotContains(response, 'En mode public')
        self.assertContains(response, 'id="country-filter"')
        self.assertContains(
            response,
            'rel="icon" type="image/png" href="/static/portal/cent-cols-logo.png"',
        )
        self.assertContains(
            response,
            'rel="apple-touch-icon" href="/static/portal/cent-cols-logo.png"',
        )
        self.assertContains(response, '/static/portal/map.js?v=29')
        self.assertContains(response, '/static/portal/map.css?v=32')
        self.assertContains(response, 'id="department-filter"')
        self.assertContains(response, 'id="passed-cols-tab"')
        self.assertContains(response, 'id="monthly-col-stats-tab"')
        self.assertContains(response, 'Connectez-vous à Strava pour afficher vos cols franchis.')
        self.assertNotContains(response, 'id="passed-map"')
        self.assertContains(response, '/static/portal/map.js')

        applications_response = self.client.get('/applications/')
        self.assertEqual(applications_response.status_code, 200)
        self.assertContains(
            applications_response,
            '<title>tchok.com — Applications</title>',
            html=False,
        )
        self.assertNotContains(
            applications_response,
            'VOTRE ESPACE NUMÉRIQUE',
        )
        self.assertContains(applications_response, 'tchok.com')
        self.assertNotContains(applications_response, 'Vos outils, au même endroit.')
        self.assertNotContains(applications_response, 'que fait-on aujourd’hui')
        self.assertNotContains(
            applications_response,
            'Retrouvez vos applications et lancez-les en un clic.',
        )
        self.assertContains(applications_response, 'id="weather-widget"')
        self.assertContains(applications_response, 'id="weather-note"')
        self.assertContains(applications_response, 'id="weather-osm-credit"')
        self.assertContains(applications_response, '/static/portal/weather.js')
        self.assertContains(applications_response, '/static/portal/main.js?v=11')
        self.assertNotContains(applications_response, 'VOTRE BOÎTE À OUTILS')
        self.assertNotContains(applications_response, 'id="search"')
        self.assertNotContains(applications_response, 'Un espace, plusieurs outils.')
        self.assertNotContains(applications_response, 'href="#aide"')
        self.assertNotContains(applications_response, 'FAIT POUR SIMPLIFIER VOTRE QUOTIDIEN')
        self.assertNotContains(applications_response, 'footer-dot')
        self.assertContains(applications_response, 'id="apps-grid"')

    def test_map_status_is_red_for_anonymous_and_green_for_matching_user(self):
        anonymous_cols = get_map_cols()
        self.assertEqual(len(anonymous_cols), 3)
        self.assertTrue(all(not col['passed'] for col in anonymous_cols))
        cols_by_code = {col['code']: col for col in anonymous_cols}
        self.assertEqual(cols_by_code['FR-04-0001']['country_name'], 'France')
        self.assertEqual(
            cols_by_code['FR-04-0001']['department_name'],
            'Alpes de Haute-Provence',
        )
        self.assertEqual(cols_by_code['FR-01-0003']['department_name'], 'Ain')
        self.assertEqual(cols_by_code['AR-A-0001']['country_name'], 'Argentine')
        self.assertEqual(cols_by_code['AR-A-0001']['department_name'], 'Salta')

        connected_cols = get_map_cols(42)
        connected_by_code = {col['code']: col for col in connected_cols}
        self.assertTrue(connected_by_code['FR-04-0001']['passed'])
        self.assertTrue(connected_by_code['FR-01-0003']['passed'])
        self.assertFalse(connected_by_code['AR-A-0001']['passed'])
        self.assertEqual(connected_by_code['FR-04-0001']['col_count'], 5)
        self.assertEqual(connected_by_code['FR-04-0001']['year_col_count'], 1)
        self.assertEqual(
            connected_by_code['FR-04-0001']['last_passage_date'],
            datetime(2026, 6, 14, 8, 30),
        )

        session = self.client.session
        session['strava_user_id'] = 42
        session.save()
        response = self.client.get('/')
        self.assertContains(response, '"passed": true')
        self.assertContains(response, 'id="passed-visible-count">2</span> cols')
        self.assertContains(response, 'id="passed-map"')
        self.assertContains(response, 'id="passed-list-view" type="button" aria-controls="passed-list" aria-pressed="true"')
        self.assertContains(response, 'id="passed-map-panel" aria-label="Carte des cols franchis" hidden')
        self.assertContains(response, 'data-col-code="FR-04-0001"')
        self.assertContains(response, 'data-col-code="FR-01-0003"')
        self.assertContains(
            response,
            'data-country-code="FRA" data-department-code="04"',
        )
        self.assertContains(
            response,
            'data-country-code="FRA" data-department-code="01"',
        )
        self.assertContains(response, 'id="passed-year-only"')
        self.assertContains(response, '/cols/FR-04-0001/activities/')
        self.assertContains(response, 'id="passed-year-only" type="checkbox" autocomplete="off"')
        self.assertNotContains(response, 'id="passed-year-only" type="checkbox" checked')
        self.assertContains(response, 'Franchis en 2026')
        self.assertNotContains(response, 'id="passed-total-min"')
        self.assertNotContains(response, 'id="passed-year-min"')
        self.assertContains(response, 'data-col-count="5" data-year-count="1"')
        self.assertNotContains(response, '<th scope="col">Code</th>')
        for label in (
            'Nom',
            'Altitude',
            'Nombre de passages',
            'Passages 2026',
            'Dernier passage',
            'Pays',
            'Département',
        ):
            self.assertContains(response, f'class="passed-cell-label">{label}</span>')
        self.assertLess(
            response.content.index(b'data-col-code="FR-04-0001"'),
            response.content.index(b'data-col-code="FR-01-0003"'),
        )
        self.assertContains(
            response,
            '<th class="passed-number" scope="col">Nombre de passages</th>',
        )
        self.assertContains(response, '14/06/2026', html=False)
        self.assertRegex(
            response.content.decode(),
            r'<td class="passed-number">\s*<span class="passed-cell-label">Nombre de passages</span>\s*<span>5</span>',
        )
        self.assertEqual(
            response.context['monthly_col_statistics'],
            [
                {
                    'label': 'Juin 2026',
                    'crossings': 1,
                    'distinct_cols': 1,
                    'minimum_altitude': 1200,
                    'maximum_altitude': 1200,
                },
                {
                    'label': 'Mai 2026',
                    'crossings': 1,
                    'distinct_cols': 1,
                    'minimum_altitude': 1200,
                    'maximum_altitude': 1200,
                },
            ],
        )
        self.assertContains(
            response,
            '<span class="passed-cell-label">Nombre de cols franchis</span>',
        )
        self.assertContains(
            response,
            '<span class="passed-cell-label">Altitude maximale</span>',
        )

    @override_settings(SOCIAL_AUTH_STRAVA_KEY='client-id', SOCIAL_AUTH_STRAVA_SECRET='client-secret')
    def test_map_links_to_strava_oauth_when_configured(self):
        response = self.client.get('/')

        self.assertContains(
            response,
            reverse('social:begin', args=('strava',)),
        )
        self.assertContains(response, 'target="_top"')

    @override_settings(SOCIAL_AUTH_STRAVA_KEY='client-id', SOCIAL_AUTH_STRAVA_SECRET='client-secret')
    def test_strava_login_forms_open_in_top_level_window(self):
        form = (
            '<form class="map-strava-form" method="post" '
            f'action="{reverse("social:begin", args=("strava",))}" target="_top">'
        )
        for url in (
            reverse('portal:all_activities'),
            reverse('portal:monthly_statistics'),
            reverse('portal:dashboard'),
            reverse('portal:col_activities', args=['FR-04-0001']),
        ):
            with self.subTest(url=url):
                self.assertContains(self.client.get(url), form)

        session = self.client.session
        session['strava_user_id'] = 42
        session.save()
        self.assertContains(self.client.get(reverse('portal:activity_detail', args=[7001])), form)

    @override_settings(SOCIAL_AUTH_STRAVA_KEY='client-id', SOCIAL_AUTH_STRAVA_SECRET='client-secret')
    def test_strava_oauth_begin_redirects_to_provider(self):
        response = self.client.post(reverse('social:begin', args=('strava',)))

        self.assertEqual(response.status_code, 302)
        self.assertIn('www.strava.com/oauth/authorize', response['Location'])

    @override_settings(SOCIAL_AUTH_STRAVA_KEY='', SOCIAL_AUTH_STRAVA_SECRET='')
    def test_map_disables_strava_connection_without_credentials(self):
        response = self.client.get('/')

        self.assertContains(response, 'Se connecter à Strava')
        self.assertContains(response, 'disabled')
        self.assertNotContains(
            response,
            reverse('social:begin', args=('strava',)),
        )

    def test_connected_view_stores_strava_athlete_id_in_session(self):
        request = RequestFactory().get('/connected/')
        social_auth = Mock()
        social_auth.filter.return_value.first.return_value = SimpleNamespace(uid='42')
        request.user = SimpleNamespace(is_authenticated=True, social_auth=social_auth)
        SessionMiddleware(lambda current_request: None).process_request(request)

        response = strava_connected(request)

        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, '/')
        self.assertEqual(request.session['strava_user_id'], 42)

    def test_monthly_statistics_show_connected_cycling_totals(self):
        session = self.client.session
        session['strava_user_id'] = 42
        session.save()

        response = self.client.get(reverse('portal:monthly_statistics'))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Statistiques mensuelles vélo')
        self.assertNotContains(response, '<h1>Statistiques mensuelles vélo</h1>')
        self.assertNotContains(response, 'KM - Vélo')
        self.assertNotContains(response, 'Dénivelé - Vélo')
        self.assertNotContains(response, 'Temps - Vélo')
        self.assertContains(response, '<th class="passed-number" scope="col">Activités</th>')
        self.assertNotContains(response, 'Jours Activité')
        self.assertContains(response, 'Juin 2026')
        self.assertEqual(
            response.context['statistics'],
            [
                {
                    'label': 'Juin 2026',
                    'active_days': 1,
                    'distance_km': 25,
                    'elevation_m': 650,
                    'duration': '1h30',
                }
            ],
        )
        self.assertNotContains(response, 'Mai 2026')

    def test_yearly_cycling_statistics_count_activities_for_local_year_and_athlete(self):
        connection = sqlite3.connect(settings.CENTCOLS_DB_PATH)
        try:
            connection.executescript(
                '''
                INSERT INTO myapp_activity VALUES
                    (4, 42, 'Ride', 1000, 3600, 20, NULL, NULL, 'Avant nouvel an', '2025-12-31 22:59:59', 7004),
                    (5, 42, 'Ride', 2000, 3660, 100, NULL, NULL, 'Nouvel an local', '2025-12-31 23:00:00', 7005),
                    (6, 42, 'MountainBikeRide', 3000, 1200, 200, NULL, NULL, 'VTT', '2026-06-14 09:00:00', 7006),
                    (7, 42, 'VirtualRide', NULL, NULL, NULL, NULL, NULL, 'Sans données', '2026-06-14 10:00:00', 7007),
                    (8, 42, 'Ride', 100000, 3600, 5000, NULL, NULL, 'Futur', '2026-06-30 10:00:01', 7008),
                    (9, 42, 'Ride', 100000, 3600, 5000, NULL, NULL, 'Année suivante', '2027-01-01 10:00:00', 7009);
                '''
            )
            connection.commit()
        finally:
            connection.close()

        session = self.client.session
        session['strava_user_id'] = 42
        session.save()
        now = datetime(2026, 6, 30, 12, tzinfo=ZoneInfo('Europe/Paris'))
        with patch('portal.views.timezone.localtime', return_value=now):
            response = self.client.get(reverse('portal:yearly_cycling_statistics'))

        self.assertEqual(response.context['statistics'], {
            'activity_count': 4,
            'distance_km': 30,
            'elevation_m': 950,
            'duration': '2h51',
        })
        self.assertContains(response, 'Année vélo 2026')
        self.assertContains(response, '30 km')
        self.assertContains(response, '950 m')
        self.assertContains(response, '2h51')

    def test_yearly_cycling_statistics_empty_and_public_views(self):
        url = reverse('portal:yearly_cycling_statistics')
        response = self.client.get(url)
        self.assertContains(response, 'Connectez-vous à Strava')
        self.assertNotContains(response, 'performance-stats')
        self.assertNotContains(response, 'Les 5 sorties les plus longues')
        self.assertNotContains(response, 'Distance par mois')

        session = self.client.session
        session['strava_user_id'] = 123
        session.save()
        response = self.client.get(url)
        self.assertEqual(response.context['statistics'], {
            'activity_count': 0,
            'distance_km': 0,
            'elevation_m': 0,
            'duration': '0h00',
        })
        self.assertContains(response, 'Aucune sortie vélo avec une distance enregistrée cette année.')
        self.assertContains(response, 'Aucune sortie vélo avec un dénivelé enregistré cette année.')
        self.assertContains(response, 'Aucune sortie vélo avec une distance et une durée valides cette année.')
        self.assertTrue(all(item['distance_km'] == 0 and item['bar_width'] == 0
                            for item in response.context['monthly_distances'] + response.context['weekday_distances']))

        for name in ('all_activities', 'dashboard', 'power_records', 'monthly_statistics'):
            with self.subTest(page=name):
                self.assertContains(self.client.get(reverse(f'portal:{name}')), f'href="{url}"')

    def test_yearly_longest_cycling_activities_are_ranked_and_filtered(self):
        connection = sqlite3.connect(settings.CENTCOLS_DB_PATH)
        try:
            connection.executescript(
                '''
                INSERT INTO myapp_activity VALUES
                    (4, 42, 'Ride', 70000, 3600, 0, NULL, NULL, 'Nouvel an local', '2025-12-31 23:00:00', 7004),
                    (5, 42, 'MountainBikeRide', 60000, 3600, 0, NULL, NULL, 'VTT', '2026-03-01 10:00:00', 7005),
                    (6, 42, 'VirtualRide', 50000, 3600, 0, NULL, NULL, 'Vélo virtuel', '2026-04-01 10:00:00', 7006),
                    (7, 42, 'Ride', 40000, 3600, 0, NULL, NULL, 'Sortie moyenne', '2026-05-01 10:00:00', 7007),
                    (8, 42, 'Ride', 30000, 3600, 0, NULL, NULL, 'Cinquième sortie', '2026-06-01 10:00:00', 7008),
                    (9, 42, 'Ride', NULL, 3600, 0, NULL, NULL, 'Distance absente', '2026-06-02 10:00:00', 7009),
                    (10, 42, 'Ride', 999000, 3600, 0, NULL, NULL, 'Année précédente', '2025-12-31 22:59:59', 7010),
                    (11, 42, 'Ride', 999000, 3600, 0, NULL, NULL, 'Futur', '2026-07-01 10:00:00', 7011),
                    (12, 42, 'Run', 999000, 3600, 0, NULL, NULL, 'Course', '2026-06-01 10:00:00', 7012),
                    (13, 99, 'Ride', 999000, 3600, 0, NULL, NULL, 'Autre athlète', '2026-06-01 10:00:00', 7013);
                '''
            )
            connection.commit()
        finally:
            connection.close()

        session = self.client.session
        session['strava_user_id'] = 42
        session.save()
        now = datetime(2026, 6, 30, 12, tzinfo=ZoneInfo('Europe/Paris'))
        with patch('portal.views.timezone.now', return_value=now):
            response = self.client.get(reverse('portal:yearly_cycling_statistics'))

        self.assertEqual(
            [activity['name'] for activity in response.context['longest_activities']],
            ['Nouvel an local', 'VTT', 'Vélo virtuel', 'Sortie moyenne', 'Cinquième sortie'],
        )
        self.assertContains(response, '01/01/2026')
        self.assertContains(response, '70,0 km')
        self.assertContains(response, reverse('portal:activity_detail', args=[7004]))
        for excluded in ('Année précédente', 'Futur', 'Course', 'Autre athlète'):
            self.assertNotContains(response, excluded)

    def test_yearly_climbing_and_speed_rankings(self):
        connection = sqlite3.connect(settings.CENTCOLS_DB_PATH)
        try:
            connection.executescript(
                '''
                INSERT INTO myapp_activity VALUES
                    (4, 42, 'Ride', 60000, 3600, 300, NULL, NULL, 'Rapide', '2026-01-02 10:00:00', 7004),
                    (5, 42, 'MountainBikeRide', 50000, 3600, 1200, NULL, NULL, 'Montagne', '2026-02-02 10:00:00', 7005),
                    (6, 42, 'VirtualRide', 40000, 3600, 1100, NULL, NULL, 'Virtuelle', '2026-03-02 10:00:00', 7006),
                    (7, 42, 'Ride', 30000, 3600, 1000, NULL, NULL, 'Quatrième', '2026-04-02 10:00:00', 7007),
                    (8, 42, 'Ride', 20000, 3600, 900, NULL, NULL, 'Cinquième', '2026-05-02 10:00:00', 7008),
                    (9, 42, 'Ride', 10000, 3600, 800, NULL, NULL, 'Sixième', '2026-06-02 10:00:00', 7009),
                    (10, 42, 'Ride', 900000, 0, NULL, NULL, NULL, 'Durée zéro', '2026-06-03 10:00:00', 7010),
                    (11, 42, 'Ride', 900000, NULL, NULL, NULL, NULL, 'Durée absente', '2026-06-04 10:00:00', 7011),
                    (12, 42, 'Ride', NULL, 3600, NULL, NULL, NULL, 'Données absentes', '2026-06-05 10:00:00', 7012),
                    (13, 42, 'Ride', 900000, 3600, 9999, NULL, NULL, 'Année précédente', '2025-12-31 22:59:59', 7013),
                    (14, 42, 'Ride', 900000, 3600, 9999, NULL, NULL, 'Futur', '2026-07-01 10:00:00', 7014),
                    (15, 42, 'Run', 900000, 3600, 9999, NULL, NULL, 'Course', '2026-06-01 10:00:00', 7015),
                    (16, 99, 'Ride', 900000, 3600, 9999, NULL, NULL, 'Autre athlète', '2026-06-01 10:00:00', 7016);
                '''
            )
            connection.commit()
        finally:
            connection.close()

        session = self.client.session
        session['strava_user_id'] = 42
        session.save()
        now = datetime(2026, 6, 30, 12, tzinfo=ZoneInfo('Europe/Paris'))
        with patch('portal.views.timezone.now', return_value=now):
            response = self.client.get(reverse('portal:yearly_cycling_statistics'))

        climbing = response.context['climbing_activities']
        fastest = response.context['fastest_activities']
        self.assertEqual([activity['name'] for activity in climbing],
                         ['Montagne', 'Virtuelle', 'Quatrième', 'Cinquième', 'Sixième'])
        self.assertEqual([activity['name'] for activity in fastest],
                         ['Rapide', 'Montagne', 'Virtuelle', 'Quatrième', 'Cinquième'])
        self.assertEqual(fastest[0]['average_speed_kmh'], 60)
        self.assertContains(response, '<td class="yearly-desktop-column"><time datetime="2026-02-02">02/02/2026</time></td>', count=3, html=True)
        self.assertContains(response, '<td class="yearly-mobile-column"><time datetime="2026-02-02">02-02</time></td>', count=3, html=True)
        self.assertContains(response, '1200 m')
        self.assertContains(response, '60,0 km/h')
        self.assertContains(response, reverse('portal:activity_detail', args=[7005]))
        for excluded in ('Année précédente', 'Futur', 'Course', 'Autre athlète'):
            self.assertNotContains(response, excluded)

    def test_yearly_distance_charts_group_by_local_month_and_weekday(self):
        connection = sqlite3.connect(settings.CENTCOLS_DB_PATH)
        try:
            connection.executescript(
                '''
                INSERT INTO myapp_activity VALUES
                    (4, 42, 'Ride', 10000, 3600, 0, NULL, NULL, 'Nouvel an local', '2025-12-31 23:00:00', 7004),
                    (5, 42, 'GravelRide', 5000, 1800, 0, NULL, NULL, 'Avril local', '2026-03-31 22:30:00', 7005),
                    (6, 42, 'Ride', NULL, 3600, 0, NULL, NULL, 'Distance absente', '2026-04-01 10:00:00', 7006),
                    (7, 42, 'Ride', 100000, 3600, 0, NULL, NULL, 'Avant nouvel an', '2025-12-31 22:59:59', 7007),
                    (8, 42, 'Ride', 100000, 3600, 0, NULL, NULL, 'Futur', '2026-07-01 10:00:00', 7008),
                    (9, 42, 'Run', 100000, 3600, 0, NULL, NULL, 'Course', '2026-04-01 10:00:00', 7009),
                    (10, 99, 'Ride', 100000, 3600, 0, NULL, NULL, 'Autre athlète', '2026-04-01 10:00:00', 7010);
                '''
            )
            connection.commit()
        finally:
            connection.close()

        session = self.client.session
        session['strava_user_id'] = 42
        session.save()
        now = datetime(2026, 6, 30, 12, tzinfo=ZoneInfo('Europe/Paris'))
        with patch('portal.views.timezone.now', return_value=now):
            response = self.client.get(reverse('portal:yearly_cycling_statistics'))

        monthly = response.context['monthly_distances']
        weekdays = response.context['weekday_distances']
        self.assertEqual(len(monthly), 12)
        self.assertEqual(len(weekdays), 7)
        self.assertEqual([item['distance_km'] for item in monthly],
                         [10, 0, 0, 5, 0, 25, 0, 0, 0, 0, 0, 0])
        self.assertEqual([item['distance_km'] for item in weekdays], [0, 0, 5, 10, 0, 0, 25])
        self.assertEqual([monthly[index]['bar_width'] for index in (0, 3, 5)], [40, 20, 100])
        self.assertContains(response, 'Distance par mois')
        self.assertContains(response, 'Distance par jour de la semaine')
        self.assertContains(response, 'width: 40.0%')
        self.assertContains(response, '10,0 km')

    def test_dashboard_and_segment_history_use_only_current_athletes_data(self):
        connection = sqlite3.connect(settings.CENTCOLS_DB_PATH)
        try:
            connection.executescript(
                '''
                INSERT INTO myapp_col VALUES ('FR-05-0004', 'Col haut', 2100, 45, 6, 'R');
                INSERT INTO myapp_col_counter VALUES (42, 'FR-05-0004', 1, 1, NULL);
                INSERT INTO myapp_activity VALUES
                    (4, 42, 'Ride', 1000, 3600, 20, NULL, NULL, 'Nouvel an', '2025-12-31 23:00:00', 7004),
                    (5, 42, 'Ride', 2000, 3600, 100, NULL, NULL, 'Limite', '2026-06-02 10:00:00', 7005),
                    (6, 42, 'Ride', 100000, 3600, 5000, NULL, NULL, 'Futur', '2026-07-01 10:00:00', 7006),
                    (7, 42, 'VirtualRide', 50000, 3600, 500, NULL, NULL, 'Virtuel', '2026-06-15 10:00:00', 7007);
                INSERT INTO myapp_segment VALUES
                    (1, 111, 'riding', 'Montée témoin', 7.5, 3.4, 250, NULL),
                    (2, 222, 'running', 'Segment course', 4, 2, 80, NULL),
                    (3, 333, 'riding', 'Segment privé', 5, 3, 150, NULL);
                INSERT INTO myapp_perform VALUES
                    (1, 101, 1, '2026-06-14 08:30:00', 900, 1000, 150, 170, 42, 220),
                    (2, 102, 1, '2026-05-14 08:30:00', 800, 1100, 155, 175, 42, NULL),
                    (3, 103, 1, '2025-06-14 08:30:00', 1000, 900, 145, 165, 42, 200),
                    (4, 104, 2, '2026-06-14 08:30:00', 500, 700, 140, 160, 42, 180),
                    (5, 105, 3, '2026-06-14 08:30:00', 400, 800, 140, 160, 99, 180);
                '''
            )
            connection.commit()
        finally:
            connection.close()

        session = self.client.session
        session['strava_user_id'] = 42
        session.save()
        now = datetime(2026, 6, 30, 12, tzinfo=ZoneInfo('Europe/Paris'))
        with patch('portal.views.timezone.localtime', return_value=now):
            response = self.client.get(reverse('portal:dashboard'))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context['summary'], {
            'col_count': 3,
            'high_col_count': 1,
            'bike_year_km': 28,
            'run_year_km': 8,
            'bike_four_weeks_km': 27,
            'elevation_four_weeks': 750,
        })
        self.assertEqual(len(response.context['performances']), 3)
        self.assertContains(response, 'Montée témoin')
        self.assertNotContains(response, 'Segment course')
        self.assertNotContains(response, 'Segment privé')
        self.assertContains(response, reverse('portal:segment_history', args=[1]))

        history = self.client.get(reverse('portal:segment_history', args=[1]))
        self.assertEqual(history.status_code, 200)
        self.assertEqual(history.context['history'], [
            {'year': '2026', 'seconds': 800, 'chrono': '0:13:20'},
            {'year': '2025', 'seconds': 1000, 'chrono': '0:16:40'},
        ])
        self.assertContains(history, 'https://www.strava.com/segments/111')
        self.assertEqual(self.client.get(reverse('portal:segment_history', args=[3])).status_code, 404)

    def test_dashboard_requires_strava_session_for_personal_data(self):
        response = self.client.get(reverse('portal:dashboard'))
        self.assertContains(response, 'Connectez-vous à Strava')
        self.assertNotContains(response, 'Liste des performances')
        self.assertRedirects(
            self.client.get(reverse('portal:segment_history', args=[1])),
            reverse('portal:dashboard'),
        )

    def test_map_greets_connected_user_by_full_name(self):
        user = User.objects.create_user(
            username='strava-42',
            first_name='Aline',
            last_name='Cycliste',
        )
        self.client.force_login(user)
        session = self.client.session
        session['strava_user_id'] = 42
        session.save()

        response = self.client.get('/')

        self.assertContains(response, 'Hello Aline Cycliste')
        self.assertRegex(
            response.content.decode(),
            r'(?s)<div class="map-header-actions">.*?Hello Aline Cycliste.*?Mes applications',
        )

        applications_response = self.client.get('/applications/')
        self.assertContains(applications_response, 'id="embedded-greeting"')
        self.assertContains(applications_response, 'Hello Aline Cycliste')

    def test_col_activities_are_limited_to_connected_strava_user(self):
        session = self.client.session
        session['strava_user_id'] = 42
        session.save()

        response = self.client.get('/cols/FR-04-0001/activities/')

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Sortie du dimanche')
        self.assertContains(response, 'Balade du col')
        self.assertNotContains(response, 'Activité autre compte')
        self.assertContains(response, '/activities/7001/')
        self.assertNotContains(response, 'https://www.strava.com/activities/7001')

    @patch('portal.views.import_segment_efforts')
    @patch('portal.views.requests.get')
    def test_activity_opens_internal_detail_with_cols_and_altitude_profile(self, mock_get, mock_import):
        user = User.objects.create_user(username='strava-42')
        UserSocialAuth.objects.create(
            user=user,
            provider='strava',
            uid='42',
            extra_data={'access_token': 'test-token'},
        )
        self.client.force_login(user)
        session = self.client.session
        session['strava_user_id'] = 42
        session.save()

        mock_response = Mock()
        mock_response.raise_for_status.return_value = None
        mock_response.json.return_value = {
            'distance': {
                'data': [*range(0, 12000, 10), *range(12000, 0, -10)],
            },
            'altitude': {
                'data': [300 + index % 120 for index in range(2400)],
            },
            'latlng': {
                'data': [[43.7 + index * 0.0001, 7.2] for index in range(2400)],
            },
        }
        mock_get.return_value = mock_response

        response = self.client.get('/activities/7001/')

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Sortie du dimanche')
        self.assertContains(response, 'Nombre de cols passés: 1')
        self.assertContains(response, 'Col témoin')
        self.assertContains(response, 'Profil d’altitudes')
        self.assertContains(response, 'profile-area-climb')
        self.assertContains(response, 'id="activity-map"')
        self.assertLessEqual(len(response.context['route_points']), 601)
        self.assertEqual(response.context['route_points'][0], [43.7, 7.2])
        self.assertLessEqual(len(response.context['profile_points']), 240)
        profile_x = [point['x'] for point in response.context['profile_points']]
        self.assertEqual(profile_x, sorted(profile_x))
        self.assertNotContains(response, 'Puissance moyenne')
        self.assertNotContains(response, 'Puissance normalisée')
        self.assertNotContains(response, 'https://www.strava.com/activities/7001')
        mock_get.assert_called_once()
        mock_import.assert_not_called()

    @override_settings(
        SOCIAL_AUTH_STRAVA_KEY='client-id',
        SOCIAL_AUTH_STRAVA_SECRET='client-secret',
    )
    def test_activity_detail_refreshes_an_expired_strava_token(self):
        user = User.objects.create_user(username='strava-refresh')
        social_auth = UserSocialAuth.objects.create(
            user=user,
            provider='strava',
            uid='42',
            extra_data={
                'access_token': 'expired-token',
                'refresh_token': 'old-refresh-token',
                'expires_at': 1,
            },
        )
        self.client.force_login(user)
        session = self.client.session
        session['strava_user_id'] = 42
        session.save()

        refresh_response = Mock()
        refresh_response.raise_for_status.return_value = None
        refresh_response.json.return_value = {
            'access_token': 'fresh-token',
            'refresh_token': 'rotated-refresh-token',
            'expires_at': 4_000_000_000,
        }
        stream_response = Mock()
        stream_response.raise_for_status.return_value = None
        stream_response.json.return_value = {
            'distance': {'data': [0, 1000]},
            'altitude': {'data': [300, 450]},
        }

        with patch('portal.views.requests.post', return_value=refresh_response) as mock_post:
            with patch('portal.views.requests.get', return_value=stream_response) as mock_get:
                with patch('portal.views.import_segment_efforts'):
                    response = self.client.get('/activities/7001/')

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Profil d’altitudes')
        mock_post.assert_called_once()
        mock_get.assert_called_once_with(
            'https://www.strava.com/api/v3/activities/7001/streams',
            headers={'Authorization': 'Bearer fresh-token'},
            params={'keys': 'distance,altitude,watts,latlng', 'key_by_type': 'true'},
            timeout=10,
        )
        social_auth.refresh_from_db()
        self.assertEqual(social_auth.extra_data['access_token'], 'fresh-token')
        self.assertEqual(social_auth.extra_data['refresh_token'], 'rotated-refresh-token')

    @override_settings(
        SOCIAL_AUTH_STRAVA_KEY='client-id',
        SOCIAL_AUTH_STRAVA_SECRET='client-secret',
    )
    def test_activity_detail_does_not_refresh_a_valid_token(self):
        user = User.objects.create_user(username='strava-valid')
        UserSocialAuth.objects.create(
            user=user,
            provider='strava',
            uid='42',
            extra_data={
                'access_token': 'valid-token',
                'refresh_token': 'refresh-token',
                'auth_time': 4_000_000_000,
                'expires_in': 3600,
            },
        )
        self.client.force_login(user)
        session = self.client.session
        session['strava_user_id'] = 42
        session.save()

        stream_response = Mock()
        stream_response.raise_for_status.return_value = None
        stream_response.json.return_value = {
            'distance': {'data': [0, 1000]},
            'altitude': {'data': [300, 450]},
        }

        with patch('portal.views.requests.post') as mock_post:
            with patch('portal.views.requests.get', return_value=stream_response) as mock_get:
                response = self.client.get('/activities/7001/')

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Profil d’altitudes')
        mock_post.assert_not_called()
        self.assertEqual(
            mock_get.call_args.kwargs['headers'],
            {'Authorization': 'Bearer valid-token'},
        )

    def test_import_segment_efforts_keeps_only_long_climbs_and_loads_history(self):
        def segment(segment_id, distance, grade):
            return {
                'id': segment_id, 'name': f'Segment {segment_id}', 'distance': distance,
                'average_grade': grade, 'elevation_low': 100, 'elevation_high': 400,
            }

        activity_response = Mock()
        activity_response.raise_for_status.return_value = None
        activity_response.json.return_value = {'segment_efforts': [
            {'id': 1, 'elapsed_time': 1800, 'start_date': '2026-06-14T08:40:00Z', 'segment': segment(10, 5000, 6.0)},
            {'id': 2, 'elapsed_time': 300, 'start_date': '2026-06-14T09:40:00Z', 'segment': segment(11, 1000, 8.0)},
            {'id': 3, 'elapsed_time': 900, 'start_date': '2026-06-14T10:40:00Z', 'segment': segment(12, 6000, 2.0)},
        ]}
        history_response = Mock()
        history_response.raise_for_status.return_value = None
        history_response.json.return_value = [
            {'id': 1, 'elapsed_time': 1800, 'start_date': '2026-06-14T08:40:00Z', 'activity': {'id': 7001}},
            {'id': 4, 'elapsed_time': 1500, 'start_date': '2026-05-01T08:40:00Z', 'activity': {'id': 6000}},
        ]

        with patch('portal.strava_sync.requests.get', side_effect=[activity_response, history_response]):
            import_segment_efforts(42, 7001, {})

        connection = sqlite3.connect(settings.CENTCOLS_DB_PATH)
        try:
            segments = connection.execute('SELECT strava_segment_id, segment_name FROM myapp_segment').fetchall()
            performs = connection.execute(
                'SELECT strava_perf_id, perf_chrono, perf_vam FROM myapp_perform ORDER BY strava_perf_id'
            ).fetchall()
        finally:
            connection.close()
        self.assertEqual(segments, [(10, 'Segment 10')])
        self.assertEqual(performs, [(1, 1800, 600), (4, 1500, 720)])

    def test_sync_updates_only_new_activity_descriptions_with_distinct_totals(self):
        connection = sqlite3.connect(settings.CENTCOLS_DB_PATH)
        try:
            connection.execute('ALTER TABLE myapp_activity ADD COLUMN act_status INTEGER')
            connection.execute('ALTER TABLE myapp_activity ADD COLUMN act_trainer INTEGER')
            connection.commit()
        finally:
            connection.close()

        activity = {
            'id': 7004, 'name': 'Nouvelle sortie',
            'start_date': '2026-12-31T23:30:00Z', 'sport_type': 'Ride',
        }
        activities_response = Mock()
        activities_response.json.return_value = [activity, {'id': 7001}]
        detail_response = Mock()
        detail_response.json.return_value = {'description': '194 charge d’entraînement\n-- de COROS'}
        auth = SimpleNamespace(uid='42')
        now = datetime(2027, 1, 2, 12, tzinfo=ZoneInfo('Europe/Paris'))

        with patch('portal.strava_sync._access_token', return_value='token'), \
                patch('portal.strava_sync._import_activity_segments'), \
                patch('portal.strava_sync._visited_col_codes', return_value={'FR-04-0001', 'FR-01-0003'}), \
                patch('portal.strava_sync.django_timezone.localtime', return_value=now), \
                patch('portal.strava_sync.requests.get', side_effect=[
                    activities_response, detail_response, activities_response,
                ]), \
                patch('portal.strava_sync.requests.put') as update:
            self.assertEqual(sync_strava_activities(auth), 1)
            self.assertEqual(sync_strava_activities(auth), 0)

        update.assert_called_once_with(
            'https://www.strava.com/api/v3/activities/7004',
            headers={'Authorization': 'Bearer token'},
            data={'description': (
                '194 charge d’entraînement\n-- de COROS\n\n'
                '[Paxoka - cols franchis]\nCols distincts : 2\n'
                'Cols distincts en 2027 : 2'
            )},
            timeout=15,
        )

    def test_sync_failure_rolls_back_import_and_retry_does_not_duplicate_description(self):
        connection = sqlite3.connect(settings.CENTCOLS_DB_PATH)
        try:
            connection.execute('ALTER TABLE myapp_activity ADD COLUMN act_status INTEGER')
            connection.execute('ALTER TABLE myapp_activity ADD COLUMN act_trainer INTEGER')
            connection.commit()
        finally:
            connection.close()

        activity = {'id': 7004, 'start_date': '2027-01-01T10:00:00Z', 'sport_type': 'Ride'}
        activities_response = Mock()
        activities_response.json.return_value = [activity]
        detail_response = Mock()
        detail_response.json.side_effect = [
            {'description': (
                'Texte personnel\n\n[Paxoka - cols franchis]\nCols distincts : 10\n'
                'Cols distincts en 2026 : 5\n[/Paxoka]'
            )},
            {'description': (
                'Texte personnel\n\n[Paxoka - cols franchis]\nCols distincts : 10\n'
                'Cols distincts en 2026 : 5'
            )},
        ]
        failed_response = Mock()
        failed_response.raise_for_status.side_effect = requests.HTTPError('write failed')
        auth = SimpleNamespace(uid='42')
        now = datetime(2027, 1, 2, 12, tzinfo=ZoneInfo('Europe/Paris'))

        with patch('portal.strava_sync._access_token', return_value='token'), \
                patch('portal.strava_sync._import_activity_segments'), \
                patch('portal.strava_sync._visited_col_codes', return_value=set()), \
                patch('portal.strava_sync.django_timezone.localtime', return_value=now), \
                patch('portal.strava_sync.requests.get', side_effect=[
                    activities_response, detail_response, activities_response, detail_response,
                ]), \
                patch('portal.strava_sync.requests.put', side_effect=[failed_response, Mock()]) as update:
            with self.assertRaises(requests.HTTPError):
                sync_strava_activities(auth)
            connection = sqlite3.connect(settings.CENTCOLS_DB_PATH)
            try:
                self.assertIsNone(connection.execute(
                    'SELECT strava_id FROM myapp_activity WHERE strava_id = 7004'
                ).fetchone())
            finally:
                connection.close()
            self.assertEqual(sync_strava_activities(auth), 1)

        description = update.call_args.kwargs['data']['description']
        self.assertNotIn('[/Paxoka]', update.call_args_list[0].kwargs['data']['description'])
        self.assertEqual(description.count('[Paxoka - cols franchis]'), 1)
        self.assertIn('Texte personnel\n\n', description)
        self.assertIn('Cols distincts : 1\nCols distincts en 2027 : 0', description)
        self.assertNotIn('[/Paxoka]', description)

    @override_settings(SOCIAL_AUTH_STRAVA_KEY='client-id', SOCIAL_AUTH_STRAVA_SECRET='secret')
    def test_strava_reconnection_requests_activity_write_scope(self):
        response = self.client.post(reverse('social:begin', args=['strava']))

        self.assertEqual(response.status_code, 302)
        scope = parse_qs(urlparse(response['Location']).query)['scope'][0].split(',')
        self.assertIn('activity:write', scope)
        self.assertIn('activity:read_all', scope)

    @override_settings(SOCIAL_AUTH_STRAVA_KEY='client-id', SOCIAL_AUTH_STRAVA_SECRET='secret')
    def test_sync_error_is_shown_with_reconnect_option(self):
        user = User.objects.create_user(username='sync-error')
        UserSocialAuth.objects.create(user=user, provider='strava', uid='42')
        self.client.force_login(user)
        session = self.client.session
        session['strava_user_id'] = 42
        session.save()

        with patch('portal.views.sync_strava_activities', side_effect=requests.HTTPError('write failed')):
            response = self.client.post(reverse('portal:sync_strava'), follow=True)

        self.assertContains(response, 'La synchronisation Strava a échoué')
        self.assertContains(response, 'Reconnecter Strava')

    def test_activity_detail_shows_legacy_records_and_performances(self):
        connection = sqlite3.connect(settings.CENTCOLS_DB_PATH)
        try:
            connection.executescript(
                '''
                INSERT INTO myapp_segment (segment_id, strava_segment_id, activity_type, segment_name)
                VALUES (1, 10, 'riding', 'Montee test'), (2, 11, 'riding', 'Autre segment');
                INSERT INTO myapp_perform
                    (strava_perf_id, segment_id, perf_date, perf_chrono, perf_vam, perf_fc, perf_fcmax, strava_user_id)
                VALUES
                    (1, 1, '2026-06-14 08:40:00', 1990, 900, 0, 0, 42),
                    (2, 1, '2026-05-01 08:40:00', 1800, 1000, 0, 0, 42),
                    (3, 1, '2026-07-01 08:40:00', 2100, 800, 0, 0, 42),
                    (4, 2, '2026-06-14 08:50:00', 600, 500, 0, 0, 42),
                    (5, 1, '2026-06-14 09:00:00', 1500, 1200, 0, 0, 99);
                '''
            )
            connection.commit()
        finally:
            connection.close()
        session = self.client.session
        session['strava_user_id'] = 42
        session.save()

        response = self.client.get('/activities/7001/?from=all')

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Puissance moyenne')
        self.assertContains(response, '180 W')
        self.assertContains(response, 'Puissance normalisée')
        self.assertContains(response, '195 W')
        self.assertContains(response, 'Plus longue sortie depuis')
        self.assertEqual(
            [item['name'] for item in response.context['performances']],
            ['Montee test', 'Autre segment'],
        )
        first = response.context['performances'][0]
        self.assertEqual(first['chrono'], '0:33:10')
        self.assertEqual(first['vam'], '900 m/h')
        self.assertEqual(first['place'], '2/3')
        self.assertEqual(first['percent'], 66)
        self.assertContains(response, 'Autre segment')

        cols_view = self.client.get('/activities/7001/')
        self.assertNotContains(cols_view, 'Autre segment')
        self.assertNotContains(cols_view, 'Plus longue sortie depuis')
        self.assertNotContains(cols_view, 'Montées')

    def test_strava_activity_power_handles_zero_and_missing_values(self):
        connection = sqlite3.connect(settings.CENTCOLS_DB_PATH)
        try:
            connection.execute(
                'UPDATE myapp_activity SET act_power = 0, act_normal_power = NULL WHERE strava_id = 7001'
            )
            connection.commit()
        finally:
            connection.close()
        session = self.client.session
        session['strava_user_id'] = 42
        session.save()

        response = self.client.get('/activities/7001/?from=all')

        self.assertContains(response, 'Puissance moyenne')
        self.assertContains(response, '0 W')
        self.assertContains(
            response,
            '<span class="performance-stat-label">Puissance normalisée</span>'
            '<span class="performance-stat-value">—</span>',
            html=True,
        )

    def test_activity_detail_does_not_expose_another_users_activity(self):
        session = self.client.session
        session['strava_user_id'] = 42
        session.save()

        response = self.client.get('/activities/7002/')

        self.assertEqual(response.status_code, 404)

    def test_activity_text_export_downloads_cols_and_summary(self):
        session = self.client.session
        session['strava_user_id'] = 42
        session.save()

        response = self.client.get('/activities/7001/export/')

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response['Content-Type'], 'text/plain; charset=utf-8')
        self.assertIn('attachment; filename="activite-7001.txt"', response['Content-Disposition'])
        exported_text = response.content.decode('utf-8')
        self.assertIn('Activité: Sortie du dimanche', exported_text)
        self.assertIn('Col témoin - 1200.0 m [5]', exported_text)

    def test_saved_view_region_is_exposed_and_can_be_updated(self):
        connection = sqlite3.connect(settings.CENTCOLS_DB_PATH)
        try:
            connection.execute(
                "INSERT INTO myapp_user_var (strava_user_id, view_country_code, view_region_code) VALUES (42, 'FRA', '04')"
            )
            connection.commit()
        finally:
            connection.close()
        session = self.client.session
        session['strava_user_id'] = 42
        session.save()

        response = self.client.get('/')
        self.assertContains(response, 'id="view-region"')
        self.assertContains(response, '"region_code": "04"')

        response = self.client.post(
            '/vue/departement/',
            data='{"country_code": "FRA", "region_code": "01"}',
            content_type='application/json',
        )
        self.assertEqual(response.status_code, 204)

        response = self.client.get('/')
        self.assertContains(response, '"region_code": "01"')

    def test_col_activities_returns_not_found_for_unknown_col(self):
        session = self.client.session
        session['strava_user_id'] = 42
        session.save()

        response = self.client.get('/cols/NO-SUCH-COL/activities/')

        self.assertEqual(response.status_code, 404)
