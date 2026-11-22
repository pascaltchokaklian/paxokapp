import sqlite3
import tempfile
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

from django.contrib.auth.models import User
from django.contrib.sessions.middleware import SessionMiddleware
from django.test import TestCase
from django.test import RequestFactory
from django.test.utils import override_settings
from django.urls import reverse

from .map_data import get_map_cols
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
                '''
            )
        finally:
            connection.close()

        settings_override = override_settings(CENTCOLS_DB_PATH=database_path)
        settings_override.enable()
        self.addCleanup(settings_override.disable)

    def test_public_home_shows_map_and_application_list_is_separate(self):
        response = self.client.get('/')

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.headers['X-Frame-Options'], 'SAMEORIGIN')
        self.assertContains(response, 'Les cols, en un coup d’œil')
        self.assertNotContains(response, 'En mode public')
        self.assertContains(response, 'id="country-filter"')
        self.assertContains(response, 'id="department-filter"')
        self.assertContains(response, 'id="passed-cols-tab"')
        self.assertContains(response, 'Connectez-vous à Strava pour afficher vos cols franchis.')
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
        self.assertContains(applications_response, 'Hello !')
        self.assertNotContains(applications_response, 'que fait-on aujourd’hui')
        self.assertNotContains(
            applications_response,
            'Retrouvez vos applications et lancez-les en un clic.',
        )
        self.assertContains(applications_response, 'id="weather-widget"')
        self.assertContains(applications_response, 'id="weather-note"')
        self.assertContains(applications_response, 'id="weather-osm-credit"')
        self.assertContains(applications_response, '/static/portal/weather.js')

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
        self.assertContains(response, 'data-col-code="FR-04-0001"')
        self.assertContains(response, 'data-col-code="FR-01-0003"')
        self.assertContains(response, 'id="passed-year-only"')
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
        self.assertContains(response, '<th scope="col">Nombre de passages</th>')
        self.assertContains(response, '14/06/2026', html=False)
        self.assertRegex(
            response.content.decode(),
            r'<td class="passed-number">\s*<span class="passed-cell-label">Nombre de passages</span>\s*<span>5</span>',
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
