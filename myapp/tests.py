from types import SimpleNamespace
from unittest.mock import patch

from django.test import SimpleTestCase
from django.test.client import RequestFactory
from django.urls import reverse

from myapp import views


class ConnectedMapRedirectTests(SimpleTestCase):
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