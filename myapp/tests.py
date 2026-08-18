from datetime import datetime, timezone as dt_timezone
from types import SimpleNamespace
from unittest.mock import patch

from django.template.loader import render_to_string
from django.test import SimpleTestCase, TestCase
from django.test.client import RequestFactory
from django.urls import reverse

from myapp import col_dbtools, views


class ConnectedMapRedirectTests(SimpleTestCase):
    def test_mobile_team_template_links_user_name(self):
        class DummyActivity:
            strava_user_id = 123
            pk = 1
            act_id = 1
            act_start_date = '2024-01-01'

            def get_strava_user_name(self):
                return 'Alice Example'

            def get_user_acronyme(self):
                return 'AE'

            def get_act_dist_km(self):
                return 12.5

        request = RequestFactory().get('/m_team/')
        html = render_to_string('m_activity_team.html', {'m_activity_team': [DummyActivity()]}, request=request)

        self.assertIn('/strava_user/123', html)
        self.assertIn('Alice Example', html)

    def setUp(self):
        self.factory = RequestFactory()

    def test_connected_map_redirects_to_user_detail_after_sync(self):
        class DummyUser:
            def __init__(self):
                self.social_auth = SimpleNamespace(
                    get=lambda provider: SimpleNamespace(
                        extra_data={
                            'token_type': 'Bearer',
                            'access_token': 'token',
                            'refresh_token': 'refresh',
                            'expires': 123,
                        }
                    )
                )

            def __str__(self):
                return 'alice'

        class FakeStravaUser:
            objects = SimpleNamespace(
                all=lambda: SimpleNamespace(filter=lambda **kwargs: SimpleNamespace(count=lambda: 0))
            )

            def __init__(self, *args, **kwargs):
                pass

            def save(self):
                return None

        class FakeUserVar:
            objects = SimpleNamespace(filter=lambda **kwargs: SimpleNamespace(count=lambda: 0))

            def __init__(self, *args, **kwargs):
                pass

            def save(self):
                return None

        class FakeActivity:
            objects = SimpleNamespace(
                filter=lambda **kwargs: SimpleNamespace(aggregate=lambda *args, **kwargs: {'act_start_date__max': None})
            )

        request = self.factory.get('/connected/')
        request.user = DummyUser()
        request.session = {}

        with patch.object(views, 'Strava_user', FakeStravaUser), \
             patch.object(views, 'User_var', FakeUserVar), \
             patch.object(views, 'Activity', FakeActivity), \
             patch.object(views, 'get_strava_user_id', return_value=42), \
             patch.object(views, 'update_user_var'), \
             patch.object(views, 'compute_all_month_stat'), \
             patch.object(views, 'set_col_count_list_this_year'), \
             patch.object(views.requests, 'get', return_value=SimpleNamespace(json=lambda: [])):
            response = views.connected_map(request)

        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, reverse('strava_user-detail', kwargs={'strava_user_id': 42}))

    def test_user_detail_uses_mobile_template_for_mobile_requests(self):
        class DummyQuerySet(list):
            def order_by(self, *args, **kwargs):
                return self

        request = self.factory.get('/strava_user/42')
        captured = {}

        def fake_render(request_obj, template_name, context):
            captured['template_name'] = template_name
            return SimpleNamespace(status_code=200)

        with patch.object(views, 'is_mobile_user_agent', return_value=True), \
             patch.object(views, 'render', side_effect=fake_render), \
             patch.object(views.User_dashboard.objects, 'filter', return_value=DummyQuerySet()), \
             patch.object(views.Strava_user.objects, 'filter', return_value=DummyQuerySet()), \
             patch.object(views.Activity.objects, 'filter', return_value=DummyQuerySet()), \
             patch.object(views.Col_counter.objects, 'filter', return_value=DummyQuerySet()):
            views.fUserDetail(request, strava_user_id=42)

        self.assertEqual(captured['template_name'], 'm_user_detail.html')

    def test_user_detail_exposes_last_ten_power_average(self):
        class DummyQuerySet(list):
            def order_by(self, *args, **kwargs):
                return self

        request = self.factory.get('/strava_user/42')
        captured = {}

        def fake_render(request_obj, template_name, context):
            captured['context'] = context
            return SimpleNamespace(status_code=200)

        activities = [
            SimpleNamespace(act_id=1, act_normal_power=180, act_start_date='2024-01-01'),
            SimpleNamespace(act_id=2, act_normal_power=220, act_start_date='2024-01-02'),
        ]

        with patch.object(views, 'is_mobile_user_agent', return_value=False), \
             patch.object(views, 'render', side_effect=fake_render), \
             patch.object(views.User_dashboard.objects, 'filter', return_value=DummyQuerySet([SimpleNamespace(set_bike_year_km=lambda: None, set_run_year_km=lambda: None, set_col_count=lambda: None, set_col2000_count=lambda: None)])), \
             patch.object(views.Strava_user.objects, 'filter', return_value=DummyQuerySet([SimpleNamespace(get_strava_user_name='Alice')])), \
             patch.object(views.Activity.objects, 'filter', return_value=DummyQuerySet(activities)), \
             patch.object(views.Col_counter.objects, 'filter', return_value=DummyQuerySet()):
            views.fUserDetail(request, strava_user_id=42)

        self.assertEqual(captured['context']['last_ten_power_avg'], 200)
        expected = {
            datetime.now().year: None,
            datetime.now().year - 1: None,
            datetime.now().year - 2: 200.0,
        }
        self.assertEqual(captured['context']['year_power_avgs'], expected)

    def test_user_detail_exposes_three_year_power_average(self):
        class DummyQuerySet(list):
            def order_by(self, *args, **kwargs):
                return self

        request = self.factory.get('/strava_user/42')
        captured = {}

        def fake_render(request_obj, template_name, context):
            captured['context'] = context
            return SimpleNamespace(status_code=200)

        activities = [
            SimpleNamespace(act_id=1, act_normal_power=180, act_start_date=datetime(2024, 1, 1, tzinfo=dt_timezone.utc)),
            SimpleNamespace(act_id=2, act_normal_power=220, act_start_date=datetime(2025, 1, 1, tzinfo=dt_timezone.utc)),
            SimpleNamespace(act_id=3, act_normal_power=260, act_start_date=datetime(2026, 1, 1, tzinfo=dt_timezone.utc)),
            SimpleNamespace(act_id=4, act_normal_power=300, act_start_date=datetime(2023, 1, 1, tzinfo=dt_timezone.utc)),
        ]

        with patch.object(views, 'is_mobile_user_agent', return_value=False), \
             patch.object(views, 'render', side_effect=fake_render), \
             patch.object(views.User_dashboard.objects, 'filter', return_value=DummyQuerySet([SimpleNamespace(set_bike_year_km=lambda: None, set_run_year_km=lambda: None, set_col_count=lambda: None, set_col2000_count=lambda: None)])), \
             patch.object(views.Strava_user.objects, 'filter', return_value=DummyQuerySet([SimpleNamespace(get_strava_user_name='Alice')])), \
             patch.object(views.Activity.objects, 'filter', return_value=DummyQuerySet(activities)), \
             patch.object(views.Col_counter.objects, 'filter', return_value=DummyQuerySet()):
            views.fUserDetail(request, strava_user_id=42)

        expected = {
            datetime.now().year: 260.0,
            datetime.now().year - 1: 220.0,
            datetime.now().year - 2: 180.0,
        }
        self.assertEqual(captured['context']['year_power_avgs'], expected)

class ColCounterTotalsTests(TestCase):
    def setUp(self):
        self.factory = RequestFactory()

    def test_compute_cols_by_act_rebuilds_all_user_totals(self):
        activity_1_id = 2001
        activity_2_id = 2002
        user_id = 42

        activity_1 = col_dbtools.Activity.objects.create(
            act_id=activity_1_id,
            strava_id=activity_1_id,
            strava_user_id=user_id,
            act_name='A1',
            act_start_date=datetime(2024, 1, 1, tzinfo=dt_timezone.utc),
            act_status=0,
        )
        col_dbtools.Activity.objects.create(
            act_id=activity_2_id,
            strava_id=activity_2_id,
            strava_user_id=user_id,
            act_name='A2',
            act_start_date=datetime(2024, 1, 2, tzinfo=dt_timezone.utc),
            act_status=0,
        )

        col_dbtools.cp.objects.create(strava_id=activity_1_id, col_code='FR-06-0001')
        col_dbtools.cp.objects.create(strava_id=activity_2_id, col_code='FR-06-0001')
        col_dbtools.cp.objects.create(strava_id=activity_2_id, col_code='FR-06-0002')

        col_dbtools.cc.objects.create(col_code='FR-06-0001', strava_user_id=user_id, col_count=0)
        col_dbtools.cc.objects.create(col_code='FR-06-0002', strava_user_id=user_id, col_count=0)

        col_dbtools.compute_cols_by_act(None, user_id, activity_1_id)

        self.assertEqual(
            col_dbtools.cc.objects.get(col_code='FR-06-0001', strava_user_id=user_id).col_count,
            2,
        )
        self.assertEqual(
            col_dbtools.cc.objects.get(col_code='FR-06-0002', strava_user_id=user_id).col_count,
            1,
        )
        activity_1.refresh_from_db()
        self.assertEqual(activity_1.act_status, 1)

    def test_rebuild_user_col_counters_recomputes_total_from_full_history(self):
        user_id = 77
        activity_1_id = 3001
        activity_2_id = 3002

        col_dbtools.Activity.objects.create(
            act_id=activity_1_id,
            strava_id=activity_1_id,
            strava_user_id=user_id,
            act_name='A1',
            act_start_date=datetime(2026, 1, 1, tzinfo=dt_timezone.utc),
            act_status=0,
        )
        col_dbtools.Activity.objects.create(
            act_id=activity_2_id,
            strava_id=activity_2_id,
            strava_user_id=user_id,
            act_name='A2',
            act_start_date=datetime(2026, 1, 2, tzinfo=dt_timezone.utc),
            act_status=0,
        )

        col_dbtools.cp.objects.create(strava_id=activity_1_id, col_code='FR-06-0530')
        col_dbtools.cp.objects.create(strava_id=activity_2_id, col_code='FR-06-0530')
        col_dbtools.cp.objects.create(strava_id=activity_2_id, col_code='FR-06-0002')

        col_dbtools.cc.objects.create(col_code='FR-06-0530', strava_user_id=user_id, col_count=1)
        col_dbtools.cc.objects.create(col_code='FR-06-0002', strava_user_id=user_id, col_count=1)

        col_dbtools.rebuild_user_col_counters(user_id)

        self.assertEqual(
            col_dbtools.cc.objects.get(col_code='FR-06-0530', strava_user_id=user_id).col_count,
            2,
        )
        self.assertEqual(
            col_dbtools.cc.objects.get(col_code='FR-06-0002', strava_user_id=user_id).col_count,
            1,
        )

    def test_set_col_count_list_this_year_accepts_int_user_id(self):
        user_id = 88
        activity_1_id = 4001
        activity_2_id = 4002

        col_dbtools.Activity.objects.create(
            act_id=activity_1_id,
            strava_id=activity_1_id,
            strava_user_id=user_id,
            act_name='A1',
            act_start_date=datetime(2026, 1, 10, tzinfo=dt_timezone.utc),
            act_status=1,
        )
        col_dbtools.Activity.objects.create(
            act_id=activity_2_id,
            strava_id=activity_2_id,
            strava_user_id=user_id,
            act_name='A2',
            act_start_date=datetime(2026, 2, 20, tzinfo=dt_timezone.utc),
            act_status=1,
        )

        col_dbtools.cp.objects.create(strava_id=activity_1_id, col_code='FR-06-0530')
        col_dbtools.cp.objects.create(strava_id=activity_1_id, col_code='FR-06-0002')
        col_dbtools.cp.objects.create(strava_id=activity_2_id, col_code='FR-06-0530')

        col_dbtools.cc.objects.create(col_code='FR-06-0530', strava_user_id=user_id, col_count=1, year_col_count=0)
        col_dbtools.cc.objects.create(col_code='FR-06-0002', strava_user_id=user_id, col_count=1, year_col_count=0)

        result = col_dbtools.set_col_count_list_this_year(user_id)

        self.assertEqual(result, 1)
        self.assertEqual(
            col_dbtools.cc.objects.get(col_code='FR-06-0530', strava_user_id=user_id).year_col_count,
            2,
        )
        self.assertEqual(
            col_dbtools.cc.objects.get(col_code='FR-06-0002', strava_user_id=user_id).year_col_count,
            1,
        )

    def test_colsok_map_colors_by_col_count_not_altitude(self):
        request = self.factory.get('/colsok_map/')
        request.session = {'strava_user_id': 42}

        class DummyColCounter:
            def __init__(self, col_count, col_alt):
                self.col_count = col_count
                self._col_alt = col_alt

            def get_col_lat(self):
                return 45.0

            def get_col_lon(self):
                return 3.0

            def get_col_name(self):
                return 'Mon col'

            def get_col_alt(self):
                return self._col_alt

        captured = []

        def fake_circle_marker(*args, **kwargs):
            captured.append(kwargs.get('fill_color'))
            return SimpleNamespace(add_to=lambda _: None)

        class DummyColQuerySet(list):
            def order_by(self, *args, **kwargs):
                return self

        with patch.object(views.Col_counter.objects, 'filter', return_value=DummyColQuerySet([DummyColCounter(col_count=2, col_alt=3500)])), \
             patch.object(views, 'is_mobile_user_agent', return_value=False), \
             patch.object(views, 'render', return_value=SimpleNamespace(status_code=200)), \
             patch.object(views.folium, 'Map', return_value=SimpleNamespace(_repr_html_=lambda: '<div>map</div>')), \
             patch.object(views, 'MarkerCluster', return_value=SimpleNamespace(add_to=lambda map_obj: map_obj)), \
             patch.object(views.folium, 'CircleMarker', side_effect=fake_circle_marker):
            views.colsok_map(request)

        self.assertEqual(captured, ['#d89538'])