import datetime
import warnings
from unittest.mock import Mock, patch
from zoneinfo import ZoneInfo

import requests
from django.core.cache import cache
from django.test import TestCase

from .elevation import (
    OPEN_METEO_ELEVATION_URL,
    OPEN_TOPO_DATA_ELEVATION_URL,
    get_elevation_profile,
)
from .sun import daily_sunshine, sunshine_details_for_date, sunshine_duration_for_date, timezone_at


class ElevationProfileTests(TestCase):
    def setUp(self):
        cache.clear()

    @patch('coordinates.elevation.requests.get')
    def test_fetches_horizon_elevations_from_open_meteo(self, mock_get):
        response = Mock()
        response.json.return_value = {'elevation': [100.0] * 5}
        mock_get.return_value = response

        profile, error = get_elevation_profile(
            48.8566,
            2.3522,
            radius_km=1,
            n_azimuths=2,
            n_distances=2,
        )

        self.assertIsNone(error)
        self.assertEqual(profile, {0.0: 0.0, 180.0: 0.0})
        mock_get.assert_called_once()
        self.assertEqual(mock_get.call_args.args[0], OPEN_METEO_ELEVATION_URL)
        self.assertEqual(mock_get.call_args.kwargs['timeout'], 15)
        self.assertEqual(mock_get.call_args.kwargs['params']['latitude'].count(','), 4)
        self.assertEqual(mock_get.call_args.kwargs['params']['longitude'].count(','), 4)

    @patch('coordinates.elevation.time.sleep')
    @patch('coordinates.elevation.requests.get')
    def test_returns_an_error_when_elevation_service_is_unavailable(self, mock_get, mock_sleep):
        mock_get.side_effect = requests.ConnectionError()

        profile, error = get_elevation_profile(
            48.8566,
            2.3522,
            radius_km=1,
            n_azimuths=2,
            n_distances=2,
        )

        self.assertIsNone(profile)
        self.assertEqual(
            error,
            "Impossible de récupérer les données de relief (service d'altitude indisponible).",
        )

    @patch('coordinates.elevation.time.sleep')
    @patch('coordinates.elevation.requests.get')
    def test_retries_a_transient_elevation_service_failure(self, mock_get, mock_sleep):
        failed_response = Mock()
        failed_response.status_code = 503
        retry_error = requests.HTTPError(response=failed_response)
        successful_response = Mock()
        successful_response.json.return_value = {'elevation': [100.0] * 5}
        mock_get.side_effect = [retry_error, successful_response]

        profile, error = get_elevation_profile(
            48.8566,
            2.3522,
            radius_km=1,
            n_azimuths=2,
            n_distances=2,
        )

        self.assertIsNone(error)
        self.assertEqual(profile, {0.0: 0.0, 180.0: 0.0})
        self.assertEqual(mock_get.call_count, 2)
        mock_sleep.assert_called_once_with(1)

    @patch('coordinates.elevation.time.sleep')
    @patch('coordinates.elevation.requests.get')
    def test_uses_fallback_when_open_meteo_remains_unavailable(self, mock_get, mock_sleep):
        fallback_response = Mock()
        fallback_response.json.return_value = {
            'results': [{'elevation': 100.0} for _ in range(5)],
        }
        mock_get.side_effect = [
            requests.ConnectionError(),
            requests.ConnectionError(),
            requests.ConnectionError(),
            fallback_response,
        ]

        profile, error = get_elevation_profile(
            48.8566,
            2.3522,
            radius_km=1,
            n_azimuths=2,
            n_distances=2,
        )

        self.assertIsNone(error)
        self.assertEqual(profile, {0.0: 0.0, 180.0: 0.0})
        self.assertEqual(mock_get.call_args.args[0], OPEN_TOPO_DATA_ELEVATION_URL)


class DailySunshineTests(TestCase):
    def test_night_filter_preserves_daily_results(self):
        horizon = {index * 10.0: (index % 5) * 3.0 - 4.0 for index in range(36)}
        cases = [
            (48.8566, 2.3522, datetime.date(2026, 3, 29), 'Europe/Paris'),
            (48.8566, 2.3522, datetime.date(2026, 10, 25), 'Europe/Paris'),
            (69.65, 18.96, datetime.date(2026, 6, 21), 'Europe/Oslo'),
            (69.65, 18.96, datetime.date(2026, 12, 21), 'Europe/Oslo'),
            (-33.87, 151.21, datetime.date(2026, 12, 21), 'Australia/Sydney'),
            (0.0, -179.9, datetime.date(2026, 1, 1), 'Pacific/Honolulu'),
        ]
        for latitude, longitude, day, zone in cases:
            with self.subTest(latitude=latitude, longitude=longitude, day=day):
                args = (latitude, longitude, day, horizon, ZoneInfo(zone))
                with patch('coordinates.sun._may_be_sunny', return_value=True):
                    expected = sunshine_details_for_date(*args)
                self.assertEqual(sunshine_details_for_date(*args), expected)

    @patch('coordinates.sun._solar_position', return_value=(180.0, 10.0))
    def test_night_filter_avoids_unnecessary_solar_calculations(self, mock_position):
        sunshine_details_for_date(
            48.8566, 2.3522, datetime.date(2026, 6, 21), {0.0: 0.0},
        )
        self.assertLess(mock_position.call_count, 288)

    @patch('coordinates.sun.sunshine_details_for_date')
    def test_returns_one_duration_for_every_day_of_the_year(self, mock_duration):
        mock_duration.return_value = (datetime.timedelta(hours=8), None, None)

        results = daily_sunshine(48.8566, 2.3522, 2025, {0.0: 0.0})

        self.assertEqual(len(results), 365)
        self.assertEqual(results[0][0], datetime.date(2025, 1, 1))
        self.assertEqual(results[-1][0], datetime.date(2025, 12, 31))
        self.assertEqual(mock_duration.call_count, 365)

    def test_finds_the_local_timezone_at_the_selected_coordinates(self):
        self.assertEqual(timezone_at(48.8566, 2.3522).key, 'Europe/Paris')

    def test_suppresses_only_the_known_pysolar_leap_second_warning(self):
        horizon_profile = {index * 10.0: 0.0 for index in range(36)}
        with warnings.catch_warnings(record=True) as caught_warnings:
            warnings.simplefilter('always')
            sunshine_duration_for_date(
                48.8566,
                2.3522,
                datetime.date(2026, 9, 14),
                horizon_profile,
                step_minutes=1440,
            )

        self.assertEqual(caught_warnings, [])


class SunshineChartViewTests(TestCase):
    @patch('coordinates.views.daily_sunshine_details')
    @patch('coordinates.views.timezone_at')
    @patch('coordinates.views.get_elevation_profile')
    def test_renders_daily_data_and_summary_days(
        self,
        mock_profile,
        mock_timezone,
        mock_daily_sunshine,
    ):
        mock_profile.return_value = ({0.0: 0.0}, None)
        mock_timezone.return_value = ZoneInfo('Europe/Paris')
        today = datetime.date.today()
        mock_daily_sunshine.return_value = [
            (
                today,
                datetime.timedelta(hours=8, minutes=5),
                datetime.datetime(today.year, today.month, today.day, 8, 5, tzinfo=ZoneInfo('Europe/Paris')),
                datetime.datetime(today.year, today.month, today.day, 16, 10, tzinfo=ZoneInfo('Europe/Paris')),
            ),
        ]

        response = self.client.get(
            '/xokamap/',
            {'latitude': '48.8566', 'longitude': '2.3522'},
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'class="page-header"')
        self.assertContains(response, 'src="/static/coordinates/images/xokamap-header.jpg"')
        self.assertContains(response, 'id="sunshine-chart"')
        self.assertContains(response, f'"date": "{today.isoformat()}"')
        self.assertContains(response, '"minutes": 485')
        self.assertContains(response, 'Jour J')
        self.assertContains(response, 'Jour le plus court')
        self.assertContains(response, 'Jour le plus long')
        self.assertContains(response, 'class="current-day"')
        self.assertContains(response, 'class="shortest-day"')
        self.assertContains(response, 'class="longest-day"')
        self.assertNotContains(response, '<h3>Jours extrêmes</h3>')
        self.assertContains(response, 'id="processing"')
        self.assertContains(response, 'class="sun-loader"')
        self.assertContains(response, 'aria-label="Calcul en cours"')
        self.assertContains(response, 'id="current-location"')
        self.assertContains(response, 'id="location-error"')
        self.assertContains(response, 'navigator.geolocation.getCurrentPosition')
        self.assertContains(response, 'window.isSecureContext')
        self.assertContains(response, "Calcul de l'ensoleillement en cours...")
        self.assertContains(response, 'data-label="Début ☀"')
        self.assertContains(response, '08:05')
        self.assertContains(response, '16:10')
