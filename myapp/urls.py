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
    ###
    path('calendar/',MonthStatListView.as_view(), name = 'calendar'),     
    ### Puissances
    path('puissances/',puissancesView, name = 'puissances'),     
    ### FORM
    path('new_col/',new_col_form, name='new_col'),       
    ### m_pages
    path('m_index/',mIndexView,name='m_index'),
    path('m_activity/',mActivityListView.as_view(), name='m_activity'),                      
    path('m_activity/<pk>', ActivityDetailView.as_view(), name="activity-detail"),            
    path('m_cols/', mColsListView.as_view(), name='m_cols'),
    path('m_cols/<pk>/', ColsDetailView.as_view(), name = "col-detail"),                           
    path('m_colsok/', mColsOkListView.as_view(), name='m_colsok'),                           
    path('m_colsok/<pk>/', ColsDetailView.as_view(),name = "col-detail"),        
    path('m_team/', mActivityTeamView.as_view(), name='m_team'),
    path('m_team/activity/<pk>', ActivityDetailView.as_view(), name="activity-detail"),     
    path('m_stat_list/',mStatListView.as_view(), name = 'm_stat_list'),     

]

urlpatterns += staticfiles_urlpatterns()