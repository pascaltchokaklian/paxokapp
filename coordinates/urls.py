from django.urls import path

from . import views

urlpatterns = [
    path('', views.coordinates_view, name='coordinates_form'),
]
