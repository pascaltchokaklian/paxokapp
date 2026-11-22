from django.urls import path

from . import views


app_name = 'portal'

urlpatterns = [
    path('', views.home, name='home'),
    path('activities/', views.all_activities, name='all_activities'),
    path('activities/statistiques/', views.monthly_statistics, name='monthly_statistics'),
    path('activities/dashboard/', views.dashboard, name='dashboard'),
    path('activities/puissances/', views.power_records, name='power_records'),
    path('activities/dashboard/segments/<int:segment_id>/', views.segment_history, name='segment_history'),
    path('activities/<int:strava_id>/export/', views.activity_export_text, name='activity_export_text'),
    path('activities/<int:strava_id>/', views.activity_detail, name='activity_detail'),
    path('cols/<str:col_code>/activities/', views.col_activities, name='col_activities'),
    path('cols/<str:col_code>/carte/', views.col_map, name='col_map'),
    path('vue/departement/', views.save_view_region, name='save_view_region'),
    path('map-tiles/<int:zoom>/<int:x>/<int:y>.png', views.map_tile, name='map_tile'),
    path('connected/', views.strava_connected, name='strava_connected'),
    path('strava/sync/', views.sync_strava, name='sync_strava'),
    path('applications/', views.applications, name='applications'),
]
