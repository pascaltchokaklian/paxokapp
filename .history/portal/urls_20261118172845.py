from django.urls import path

from . import views


app_name = 'portal'

urlpatterns = [
    path('', views.home, name='home'),
    path('cols/<str:col_code>/activities/', views.col_activities, name='col_activities'),
    path('connected/', views.strava_connected, name='strava_connected'),
    path('applications/', views.applications, name='applications'),
]
