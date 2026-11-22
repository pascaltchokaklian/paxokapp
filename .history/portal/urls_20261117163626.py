from django.urls import path

from . import views


app_name = 'portal'

urlpatterns = [
    path('', views.home, name='home'),
    path('connected/', views.strava_connected, name='strava_connected'),
    path('applications/', views.applications, name='applications'),
]
