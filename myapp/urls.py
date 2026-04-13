from django import views
from django.urls import path, include

from .views import *
from django.contrib.staticfiles.urls import staticfiles_urlpatterns


urlpatterns = [
    path('', base_map, name='Base Map View'),    
    path('oauth/', include('social_django.urls', namespace='social')),     
    path('connected/', connected_map, name='Connect Map View'),                                       
    path('index/',base_map,name='index'),
    path('col_map/<str:col_id>', col_map, name = 'Col Map View'),
    path('act_map/<int:act_id>', act_map, name = 'Activity Map View'),          
    ###    
    path('activity', ActivityListView.as_view(), name='activity'),        
    path('activity/<pk>', ActivityDetailView.as_view(), name="activity-detail"),            
    path('activity/<int:act_id>/export-txt/', export_activity_text, name='activity-export-txt'),
    path('activity/<int:act_id>/<int:col_id>/', col_map_by_act,name = "act-col"),
    path('team', ActivityTeamView.as_view(), name='team'),        
    ###             
    path('cols_list/<str:pk>/', fColsListView,name='cols_list'),
    path('cols_list/<int:col_id>/', ColsDetailView.as_view(),name = "col-detail"),           
    path('cols/', ColsListView.as_view(), name='cols'),    
    path('cols/<pk>/', ColsDetailView.as_view(), name = "col-detail"),                           
    path('cols/<int:col_id>/<int:act_id>/', act_map_by_col, name = "col-act"),                           
    ###        
    path('colsok/', ColsOkListView.as_view(), name='colsok'),                           
    path('colsok/<pk>/', ColsDetailView.as_view(),name = "col-detail"),           
    path('colsok/<int:col_id>/<int:act_id>/', act_map_by_col, name = "col-act"),                                      
    ### SEGMENTS
    path('dashboard/', User_dashboardView.as_view(), name='userdashboard'),            
    path('segment/',SegmentListView.as_view(), name='segment'),
    path('perform/',PerformListView.as_view(), name = 'perform'),
    path('perform/<int:segment_id>',fSegmentHistoView, name = 'perform_histo'),     
    ### VAM
    path('vamyear/',fVamYearView, name = 'vamyear'),         
    path('stat_list/',StatListView.as_view(), name = 'stat_list'),         
    ### Users
    path('strava_user/<int:strava_user_id>',fUserDetail,name='strava_user-detail'),
    ###
    path('calendar/',MonthStatListView.as_view(), name = 'calendar'),     
    ### Puissances
    path('puissances/',puissancesView, name = 'puissances'),     
    ### FORM
    path('new_col/',new_col_form, name='new_col'),       
    ### m_pages (mobile shortcuts)
    path('m_index/', base_map, {'force_mobile': True}, name='m_index'),
    path('m_activity/', ActivityListView.as_view(force_mobile=True), name='m_activity'),                      
    path('m_activity/<pk>', ActivityDetailView.as_view(force_mobile=True), name="activity-detail"),            
    path('m_activity/<int:act_id>/map', m_act_map, name='activity-map'),            
    path('m_cols/', ColsListView.as_view(force_mobile=True), name='m_cols'),
    path('m_cols/<pk>/', ColsDetailView.as_view(), name = "col-detail"),                           
    path('m_colsok/', ColsOkListView.as_view(force_mobile=True), name='m_colsok'),                           
    path('m_colsok/<pk>/', ColsDetailView.as_view(),name = "col-detail"),        
    path('m_team/', ActivityTeamView.as_view(force_mobile=True), name='m_team'),
    path('m_team/activity/<pk>', ActivityDetailView.as_view(), name="activity-detail"),     
    path('m_stat_list/', StatListView.as_view(force_mobile=True), name = 'm_stat_list'),     
    path('m_perform_list/', PerformListView.as_view(force_mobile=True), name = 'm_perform_list'),     
    path('m_perform/<int:segment_id>',fSegmentHistoView, name = 'm_perform_histo'),

]

urlpatterns += staticfiles_urlpatterns()