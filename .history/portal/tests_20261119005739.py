import sqlite3
import tempfile
from datetime import datetime
from io import StringIO
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

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
from .strava_sync import import_segment_efforts
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

    def test_public_home_shows_map_and_application_list_is_separate(self):
        response = self.client.get('/')

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.headers['X-Frame-Options'], 'SAMEORIGIN')
        self.assertNotContains(response, 'CARTE INTERACTIVE')
        self.assertNotContains(response, 'Les cols, en un coup d’œil')
        self.assertNotContains(response, 'En mode public')
        self.assertContains(response, 'id="country-filter"')
        self.assertContains(response, '/static/portal/map.js?v=16')
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
        self.assertContains(applications_response, '/static/portal/main.js?v=7')

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
        self.assertContains(response, 'data-col-code="FR-04-0001"')
        self.assertContains(response, 'data-col-code="FR-01-0003"')
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
