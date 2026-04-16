from django.http import HttpResponse
from django.views import generic
from django.shortcuts import render, get_object_or_404
import folium
import requests
import pandas as pd
import polyline
from .forms import ColForm
from .models import Activity, Activity_info, Col_perform, Month_stat, Perform, Region, Segment, User_dashboard, User_var
from .models import Col, Country
from .models import Col_counter
from .models import Strava_user
from .cols_tools import *
from .col_dbtools import *
from .graph import *
from .segments_tools import compute_all_vam, segment_explorer
from .vars import get_map_center
from django.db.models import Max
from django.shortcuts import render , redirect
from django.contrib.auth.models import User
from social_django.models import UserSocialAuth
from .myfunctions import *


def is_mobile_user_agent(request):
    """Return True when the request looks like it's coming from a mobile device.

    If django-user-agents is installed and enabled, use the provided parser (more accurate).
    Otherwise fallback to a basic UA substring check.
    """

    # Prefer django-user-agents when available (more reliable than simple substring checks)
    ua = getattr(request, "user_agent", None)
    if ua is not None:
        return ua.is_mobile or ua.is_tablet

    ua_string = request.META.get("HTTP_USER_AGENT", "").lower()
    return any(tok in ua_string for tok in ("mobile", "android", "iphone", "ipad", "phone", "blackberry", "windows phone"))


class MobileTemplateMixin:
    """Mixin to automatically pick mobile templates and context keys.

    - If the request is from a mobile user-agent (or force_mobile is set), it will look for a template
      with the same name prefixed by "m_".
    - It also exposes a mobile context key (prefixed with "m_") so existing mobile templates that
      expect e.g. "m_activity_list" can keep working.
    """

    mobile_prefix = "m_"
    force_mobile = False

    def is_mobile(self):
        if getattr(self, "force_mobile", False):
            return True
        if self.kwargs.get("force_mobile"):
            return True
        return is_mobile_user_agent(self.request)

    def _mobile_template_name(self, template_name):
        if "/" in template_name:
            head, tail = template_name.rsplit("/", 1)
            return f"{head}/{self.mobile_prefix}{tail}"
        return f"{self.mobile_prefix}{template_name}"

    def get_template_names(self):
        names = super().get_template_names()
        if self.is_mobile():
            mobile_names = [self._mobile_template_name(name) for name in names]
            # fallback to desktop templates if mobile template isn't found
            return mobile_names + names
        return names

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        if self.is_mobile() and getattr(self, "context_object_name", None):
            mobile_key = f"m_{self.context_object_name}"
            context.setdefault(mobile_key, context.get(self.context_object_name))
        return context


#####################################################################
#   Index View All devices                                          #
#####################################################################

def mainIndexView(request,user):
    ### f_debug_trace("views.py","base_map",SQLITE_PATH)    
    conn = create_connection(SQLITE_PATH)

    user_agent = request.META['HTTP_USER_AGENT']

    print('----------------------------------------------')
    print(user_agent)
    print('----------------------------------------------')
        
    my_strava_user_id = get_strava_user_id(request,user)
    nom_prenom = get_user_names(user)

    ### f_debug_trace("views.py","base_map/nom_prenom",nom_prenom)    
                                                
    # Make your map object
    view_region_info =  get_user_data_values(my_strava_user_id)            
    continent = "EUROPE"
    if view_region_info[0] == "AR":
        continent = "SOUTHAMERICA"
    main_map = folium.Map(location=get_map_center(continent), zoom_start = 6, tiles='CartoDB voyager')  # Create base map
    feature_group_Road = folium.FeatureGroup(name="Route").add_to(main_map)    
    feature_group_Piste = folium.FeatureGroup(name="Piste").add_to(main_map)    
    feature_group_Sentier = folium.FeatureGroup(name="Sentier").add_to(main_map)    
    folium.LayerControl().add_to(main_map)
                                    
    # Les cols passés    
    colOK = cols_effectue(conn,my_strava_user_id )    
    listeOK = []
    for oneCol in colOK:        
        listeOK.append(oneCol[3])   # col_code
        
    # Tous les cols                
    myColsList =  select_all_cols(conn,view_region_info)
                
    # Plot Cols onto Folium Map
    for oneCol in myColsList:
        myCol = PointCol()
        myCol.setPoint(oneCol)
        location = [myCol.lat,myCol.lon]
        colColor = "red"
        if myCol.col_code in listeOK :
            colColor = "green"

        # Surface
        if  myCol.col_type == "R":            
            folium.Marker(location, popup=myCol.name+" ("+str(myCol.alt)+"m)",icon=folium.Icon(color=colColor, icon="flag")).add_to(feature_group_Road)        
        if  myCol.col_type == "P":            
            folium.Marker(location, popup=myCol.name+" ("+str(myCol.alt)+"m)",icon=folium.Icon(color=colColor, icon="flag")).add_to(feature_group_Piste)        
        if  myCol.col_type == "S":            
            folium.Marker(location, popup=myCol.name+" ("+str(myCol.alt)+"m)",icon=folium.Icon(color=colColor, icon="flag")).add_to(feature_group_Sentier)        
        
    
    main_map_html = main_map._repr_html_() # Get HTML for website

    context = {
        "main_map":main_map_html,
        "user_infos":nom_prenom
    }

    return context

###################################################################
#   PC Index View                                                 #
###################################################################

def base_map(request, force_mobile=False):
    user = request.user  # Pulls in the Strava User data

    # user = "tpascal"

    f_debug_trace("views.py","base_map","user = "+str(user))

    if str(user) != 'AnonymousUser':
        context = mainIndexView(request, user)
    else:
        context = {"Strava User": "Not Connected"}

    template = "m_index.html" if force_mobile or is_mobile_user_agent(request) else "index.html"
    return render(request, template, context)


###################################################################
#   Connected Map
###################################################################

def connected_map(request):
        
    # Make your map object    
    main_map = folium.Map(location=get_map_center("EUROPE"), zoom_start = 6, tiles='CartoDB voyager') # Create base map 
    user = request.user # Pulls in the Strava User data                
    ### f_debug_trace("views.py","connected_map","user = "+str(user))
    get_strava_user_id(request,user)
    strava_login = user.social_auth.get(provider='strava') # Strava login             
                
    token_type = strava_login.extra_data['token_type'] 
    access_token = strava_login.extra_data['access_token'] # Strava Access token
    refresh_token = strava_login.extra_data['refresh_token'] # Strava Refresh token
    expires = strava_login.extra_data['expires'] 
                
    activites_url = "https://www.strava.com/api/v3/athlete/activities"
    
    myUser_sq = Strava_user.objects.all().filter(strava_user = user)

    if myUser_sq.count() == 0:
        myUser = Strava_user()        
        myUser.last_name = user
        myUser.first_name = user
        myUser.token_type = token_type
        myUser.access_token = access_token
        myUser.refresh_token = refresh_token
        myUser.strava_user = user
        myUser.expire_at = expires
        myUser.strava_user_id = get_strava_user_id(request,user)
        myUser.save()
        ### f_debug_trace("views.py","connected_map","New User = "+ str(user))
        
    else:
        for oneOk in myUser_sq:
            myUser = oneOk
            myUser.access_token = access_token
            myUser.refresh_token = refresh_token
            myUser.expire_at = expires
            myUser.save()            

    
    my_strava_user_id = get_strava_user_id(request,user)
    my_user_var_sq = User_var.objects.filter(strava_user_id = my_strava_user_id)
    
    if my_user_var_sq.count() == 0:
        my_user_var = User_var()
        my_user_var.strava_user_id = my_strava_user_id
        my_user_var.last_update = datetime.datetime.today().timestamp()
        my_user_var.save() 
                
    # Get activity data
    header = {'Authorization': 'Bearer ' + str(access_token)}
    
    activity_df_list = []

    select_max_act_date = Activity.objects.filter(strava_user_id=my_strava_user_id).aggregate(Max('act_start_date'))
    
    ze_date = select_max_act_date["act_start_date__max"]    

    if ze_date == None: 
        ### First pass, no data in activity
        ########################
        #   Last 100 activities
        ########################

        for n in range(1):  # Change this to be higher if you have more than 100 activities
            param = {'per_page': 100, 'page': n + 1}
            activities_json = requests.get(activites_url, headers=header, params=param).json()
            if not activities_json:
                break

    else:
        ze_epoc = int(ze_date.timestamp())
        un_d_epoc = 86400
        un_jour_avant = ze_epoc - un_d_epoc        
        #un_jour_avant = 1693224000
        param = {'after': un_jour_avant , "per_page": 200}
        activities_json = requests.get(activites_url, headers=header, params=param).json()
                                
    activity_df_list.append(pd.json_normalize(activities_json))
    
    # Get Polyline Data
    activities_df = pd.concat(activity_df_list)        

    if len(activities_df)>0: 
    
        activities_df = activities_df.dropna(subset=['map.summary_polyline'])
        
        activities_df['polylines'] = activities_df['map.summary_polyline'].apply(polyline.decode)
        
        ### f_debug_trace("views.py","connected_map",SQLITE_PATH)    
        conn = create_connection(SQLITE_PATH)        
        myColsList =  select_all_cols(conn,"00")        
                
        for ligne in range(len(activities_df)):
            trainer = activities_df['trainer'][ligne]   ### 1 if HomeTrainer        
            AllVisitedCols = []
            myGPSPoints = []        
            strava_id = int(activities_df['id'][ligne])        
            activity_name = activities_df['name'][ligne]              
            act_start_date = activities_df['start_date'][ligne]      
            act_start_date10 = act_start_date[:10]
            act_dist = activities_df['distance'][ligne]      
            act_den = activities_df['total_elevation_gain'][ligne]          
            sport_type = activities_df['sport_type'][ligne]
            act_time = int(activities_df['moving_time'][ligne])
            try:
                act_power = activities_df['average_watts'][ligne]
            except:
                act_power=0

            try: 
                act_noral_power = int(activities_df['weighted_average_watts'][ligne])
            except:
                act_noral_power=0                                
                        
            act_status = 1
            strava_user_id = get_strava_user_id(request,user)
            
            ########## Delete / Insert ###############
            # insert activities and col for each one
            ##########################################

            delete_activity(conn,strava_id)
            delete_col_perform(conn,strava_id)
            delete_activity_info(conn,strava_id)

            act_trainer = 0
            if trainer == 1:
                act_trainer = 1
                        
            insert_activity(conn,strava_user_id,strava_id,activity_name,act_start_date, act_dist, act_den,sport_type,act_time,act_power,act_status,act_noral_power, act_trainer)                

            #####################
            #  Activity infos   #             
            #####################

            if sport_type == "Ride":
                        
                my_Activity_info1 = Activity_info()
                my_Activity_info1.strava_id = strava_id
                my_Activity_info1.info_txt = get_last_activity_more_than(strava_user_id,act_dist,act_start_date10)           
                my_Activity_info1.save()

                my_Activity_info2 = Activity_info()
                my_Activity_info2.strava_id = strava_id
                my_Activity_info2.info_txt = get_last_activity_den_than(strava_user_id,act_den,act_start_date10)               
                my_Activity_info2.save()

                my_Activity_info3 = Activity_info()
                my_Activity_info3.strava_id = strava_id
                my_Activity_info3.info_txt = get_last_speed_activity(strava_user_id,act_dist,act_time,act_start_date10)    
                my_Activity_info3.save()
                                    
            for pl in activities_df['polylines'][ligne]:
                if len(pl) > 0: 
                    myPoint = PointGPS()                
                    myPoint = pl                
                    myGPSPoints.append(myPoint)

            FilteredColList = getFilterdColList(myColsList,myGPSPoints)                     
        
            returnList = getColsVisited(FilteredColList,myGPSPoints)       
            
            for ligne in returnList:                
                AllVisitedCols.append(ligne)            
                    
            insert_col_perform(conn,strava_id, AllVisitedCols)
            compute_cols_by_act(conn,my_strava_user_id,strava_id)

            #############################
            ### Treatement des segments
            #############################
            
            # Recherche des Segments
            ### f_debug_trace("views.py","connected_map","Activity Segemnts Performance, strava_id ="+str(strava_id)) 
            myRectangle = get_map_rectangle(activities_df['polylines'])
            segment_explorer(myRectangle, access_token, strava_id, my_strava_user_id)

        ### End Treatement des segments
                        
        # Plot Polylines onto Folium Map
        i=0
        for pl in activities_df['polylines']:
                       
            if len(pl) > 0: # Ignore polylines with length zero (Thanks Joukesmink for the tip)                                                                                                    
                
                lst = activities_df['sport_type']
                sport_type = lst[i]
                               
                i+=1
                myColor = "Green"
               
                match sport_type:
                    case "Ride":
                        myColor = "Blue"
                    case "Run":
                        myColor = "Red"                                         
                    case "Swim":
                        myColor = "Orange"                                                                 
                    case "Snowshoe":
                        myColor = "Maroon"                                                                                         
                    case _:   
                        f_debug_trace("views.py","connected_map","Activity Type = "+ sport_type) 
                
                folium.PolyLine(locations=pl, color=myColor).add_to(main_map)                
            
    # Return HTML version of map
    main_map_html = main_map._repr_html_() # Get HTML for website
    context = {
        "main_map":main_map_html
    }

    update_user_var(request.session.get("strava_user_id"),"","",datetime.datetime.now().timestamp())

    # Statistiques Mensuelles     
    compute_all_month_stat(my_strava_user_id)
    # Liste des Cols des l'année
    set_col_count_list_this_year(my_strava_user_id)
                    
    return render(request, 'index.html', context)


def index(request):

    """View function for home page of site."""

    # Generate counts of some of the main objects
    num_cols = Col.objects.all().count()
    num_cols06 = Col.objects.all().count()

    context = {
        'Nombre de Cols': num_cols,
        'Nombre de Cols (AM)': num_cols06,
    }
    
    # Render the HTML template index.html with the data in the context variable
    return render(request, 'm_index.html', context)

def perf(request):
                   
    return render(request, 'performances.html')

def col_map(request, col_id):

    f_debug_trace("views.py","col_map",SQLITE_PATH)    
    conn = create_connection(SQLITE_PATH)        
    
    myColsList =  getCol(conn,col_id)     
        
    for oneCol in myColsList:
        myCol = PointCol()
        myCol.setPoint(oneCol)
        col_location = [myCol.lat,myCol.lon]
        colColor = "blue"
        map = folium.Map(col_location, zoom_start=15, tiles='CartoDB voyager')
        myPopup = myCol.name+" ("+str(myCol.alt)+"m)"
        folium.Marker(col_location, popup=myPopup,icon=folium.Icon(color=colColor, icon="flag")).add_to(map)      

    map_html = map._repr_html_()
    
    context = {
        "main_map": map_html,
        "col_id" : col_id,        
    }
        
    return render(request, 'index.html', context)

def act_map(request, act_id):
    
    my_strava_user = request.session.get("strava_user")    
    my_strava_user_id = get_strava_user_id(request,my_strava_user)
    
    ###f_debug_trace("col_tools.py","act_map","user : "+my_strava_user)
    
    refresh_access_token(my_strava_user)

    user = str(request.user) # Pulls in the Strava User data                
    ### f_debug_trace("views.py","act_map","user = "+user)
    get_strava_user_id(request,user)

    myActivity_sq = Activity.objects.all().filter(act_id = act_id)    
    access_token = "notFound"
                   
    userList = Strava_user.objects.all().filter(strava_user = user)
    for userOne in userList:
            myUser = userOne
            access_token = myUser.access_token                

    ### f_debug_trace("views.py","act_map","access_token = "+access_token)     
           
    for myActivity in myActivity_sq:            
            strava_id =  myActivity.strava_id
            act_statut = myActivity.act_status
            team_strava_user_id = myActivity.strava_user_id
            f_debug_trace("views.py","strava_user_id = ",my_strava_user_id)                 
                        
    if str(my_strava_user_id) != str(team_strava_user_id):
        ### See activity from an other
        ### f_debug_trace("views.py","### See activity from an other",team_strava_user_id)     
        return HttpResponse('')
        
        
    activites_url = "https://www.strava.com/api/v3//activities/"+str(strava_id)
    
    # Get activity data
    header = {'Authorization': 'Bearer ' + str(access_token)}            
    param = {'id': strava_id}
    
    activities_json = requests.get(activites_url, headers=header, params=param).json()
    activity_df_list = []
       
    activity_df_list.append(pd.json_normalize(activities_json))
    
    # Get Polyline Data
    activities_df = pd.concat(activity_df_list)        
        
    activities_df = activities_df.dropna(subset=['map.summary_polyline'])
    
    activities_df['polylines'] = activities_df['map.summary_polyline'].apply(polyline.decode)
    
    # Centrage de la carte                       
    centrer_point = map_center(activities_df['polylines'])           

    # Recherche des Segments
    myRectangle = get_map_rectangle(activities_df['polylines'])
    segment_explorer(myRectangle, access_token, strava_id, my_strava_user_id)
                             
    # Zoom
    ### f_debug_trace("col_tools.py","act_map","Call map_zoom ")
    map_zoom = cols_tools.map_zoom(centrer_point,activities_df['polylines'])    
    ### f_debug_trace("col_tools.py","act_map","After map_zoo")
    
    map = folium.Map(location=centrer_point, zoom_start=map_zoom, tiles='CartoDB voyager')
                                                   
    # kw = {
    #   "color": "blue",
    #   "line_cap": "round",
    #   "fill": True,
    #   "fill_color": "red",
    #   "weight": 5,
    #   "popup": "Mon rectangle",
    #   "tooltip": "<strong>Click me!</strong>",
    #   }        
    
    #folium.Rectangle(bounds=[[myRectangle[0],myRectangle[1]],[myRectangle[2],myRectangle[3]]],line_join="round",dash_array="5, 5",**kw,).add_to(map)

    ###############################################
    #   Plot Polylines onto Folium Map
    ###############################################

    myGPSPoints = []
    
    for pl in activities_df['polylines']:
        if len(pl) > 0: # Ignore polylines with length zero (Thanks Joukesmink for the tip)
            folium.PolyLine(locations=pl, color='red').add_to(map)                
            myPoint = PointGPS()                
            myPoint = pl                            
            myGPSPoints.append(myPoint)


    ## Col Display
    ### f_debug_trace("views.py","act_map",SQLITE_PATH)    
    conn = create_connection(SQLITE_PATH)        
    
    myColsList =  getColByActivity(conn,strava_id)     
        
    for oneCol in myColsList:
        myCol = PointCol()
        myCol.setPoint(oneCol)
        col_location = [myCol.lat,myCol.lon]
        colColor = "blue"        
        mypopup = myCol.name+" ("+str(myCol.alt)+"m)"
        folium.Marker(col_location, popup=mypopup,icon=folium.Icon(color=colColor, icon="flag")).add_to(map)      
        ##### Count Update #####
                   
            
    # Return HTML version of map
    map_html = map._repr_html_() # Get HTML for website
    
    context = {
        "main_map":map_html        
    }

    strava_user = get_strava_user_id(request,my_strava_user)

    ## Check col passed new
    if act_statut == 0:
        recompute_activity(strava_id, activities_df,strava_user)
                                           
    return render(request,"base_map.html", context)


def act_map_by_col(request,col_id,act_id):      
    return  act_map(request, act_id)

def col_map_by_act(request,act_id,col_id):    
    return  col_map(request, col_id)

##########################################################################

def fActivitiesListView(request, col_code):        
    strava_user_id = request.session.get('strava_user_id') 
    listActivities = Activity.objects.filter(strava_user_id=strava_user_id)
    listActivitiesPassed = Col_perform.objects.filter(col_code = col_code)

    return listActivities
    
##########################################################################    

def fUserDetail(request,**kwargs):        
    template = "user_detail.html"      

    strava_user_id = kwargs['strava_user_id']

    mydashBoard = User_dashboard.objects.filter(strava_user_id = strava_user_id)
    for onDS in mydashBoard:
        onDS.set_bike_year_km()
        onDS.set_run_year_km()
        onDS.set_col_count()
        onDS.set_col2000_count()
    
    theUser =Strava_user.objects.filter(strava_user_id=strava_user_id)
    listActivities = Activity.objects.filter(strava_user_id=strava_user_id).order_by('-act_start_date')[:10]
    listColsOk = Col_counter.objects.filter(strava_user_id=strava_user_id).order_by("-col_count")[:10]                                                                   
            
    return render (request,template, {'Strava_User':theUser, 'listAct': listActivities, 'ColsOk': listColsOk})

#########################################################################################  

def fColsListView(request,**kwargs):        

    template = 'm_col_list.html' if is_mobile_user_agent(request) else 'cols_list.html'
    
    listeCols = Col.objects.filter(col_code__icontains=code_paysregion).order_by("col_alt")
    country_region = get_country_region(code_paysregion)           
    country_name = get_country_from_code(country_region[0])    
    region_name = get_region_from_code(country_region[0],country_region[1])
    update_user_var(request.session.get("strava_user_id"),country_region[0],country_region[1],0)
            
    return render (request, template, {'col_list':listeCols , 'country':country_name , 'region':region_name })
    
##########################################################################    
#                               Liste des cols                           #
##########################################################################    

class ColsListView(MobileTemplateMixin, generic.ListView):    

    model = Col
    context_object_name = 'col_list'   # your own name for the list as a template    
    template_name = "col_list.html"    # Specify your own template name/location

    def get_queryset(self):        
        return Col.objects.all().order_by("col_alt")
        
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['countries'] = Country.objects.all().order_by("country_name")
        context['regions'] = Region.objects.all().order_by("region_code")          
        return context
    
##########################################################################   
#                               Cols Franchis                            #
##########################################################################   

### Vue PC ###              

class ColsOkListView(MobileTemplateMixin, generic.ListView):        

    model = Col
    context_object_name = 'col_counter_list'              # your own name for the list as a template    
    template_name = "col_counter_list.html"                 # Specify your own template name/location
    
    def get_queryset(self):            
        strava_user_id = self.request.session.get('strava_user_id')    
        ### f_debug_trace("views.py","ColsOkListView","strava_user_id = "+str(strava_user_id))
        qsOk = Col_counter.objects.filter(strava_user_id=strava_user_id).order_by("-col_count")                                                                   
        return qsOk
    
    def get_context_data(self, **kwargs):
        context = super(ColsOkListView, self).get_context_data(**kwargs)
        currentDateTime = datetime.datetime.now()
        date = currentDateTime.date()
        year = date.strftime("%Y")        
        context['annee'] = str(year)
        return context

#########################################################################   
#                       Carte des Cols Franchis                         #
#########################################################################   

def colsok_map(request):
    """Affiche une carte avec les cols franchis en bleu"""
    strava_user_id = request.session.get('strava_user_id')
    
    # Récupérer tous les cols franchis de l'utilisateur
    cols_franchis = Col_counter.objects.filter(strava_user_id=strava_user_id)
    
    # Initialiser la carte avec un centre par défaut
    map_center = [45.5, 5.0]  # Centre en France par défaut
    colsok_map = folium.Map(location=map_center, zoom_start=6, tiles='CartoDB voyager')
    
    # Ajouter un marqueur pour chaque col franchi
    for col_counter in cols_franchis:
        col_lat = col_counter.get_col_lat()
        col_lon = col_counter.get_col_lon()
        col_name = col_counter.get_col_name()
        col_alt = col_counter.get_col_alt()
        
        # Vérifier que les coordonnées existent
        if col_lat and col_lon:
            location = [col_lat, col_lon]
            popup_text = f"{col_name} ({col_alt}m)"
            folium.Marker(
                location,
                popup=popup_text,
                tooltip=col_name,
                icon=folium.Icon(color="blue", icon="flag")
            ).add_to(colsok_map)
    
    colsok_map_html = colsok_map._repr_html_()
    
    # Déterminer le template à utiliser selon le user-agent
    is_mobile = is_mobile_user_agent(request)
    template = "m_col_map.html" if is_mobile else "col_map.html"
    
    context = {
        "colsok_map": colsok_map_html,
        "col_count": cols_franchis.count()
    }
    
    return render(request, template, context)

                    
#########################################################################   
#                       Liste des activités                             #
#########################################################################   

### Vue PC ###              

class ActivityListView(MobileTemplateMixin, generic.ListView):        
    model = Activity
    context_object_name = 'activity_list'   # your own name for the list as a template variable    
    template_name = "activity_list.html"    # Specify your own template name/location

    def get_queryset(self):                
        strava_user_id = self.request.session.get('strava_user_id')    
        ### f_debug_trace("views.py","ActivityListView",Activity.objects.count())
        return Activity.objects.filter(strava_user_id=strava_user_id).order_by("-act_start_date")

    
#############################################################################################
#                                          L'Equipe                                         #
#############################################################################################

### Vue PC ###              

class ActivityTeamView(MobileTemplateMixin, generic.ListView):        
    model = Activity
    context_object_name = 'activity_team'   # your own name for the list as a template variable    
    template_name = "activity_team.html"    # Specify your own template name/location

    def get_queryset(self):                        
        ### f_debug_trace("views.py","ActivityTeamView",Activity.objects.count())
        nbcount = 100
        strava_user_id = self.request.session.get('strava_user_id') 
        if strava_user_id == None:
            nbcount=0
        return Activity.objects.order_by("-act_start_date")[:nbcount]

#############################################################################################
    
class ActivityDetailView(MobileTemplateMixin, generic.DetailView):                       
    model = Activity        
    context_object_name = 'activity-detail'   # your own name for the list as a template variable    
    template_name = "activity_detail.html"    # Specify your own template name/location   

    def get_template_names(self):
        """Sélectionne le bon template selon si c'est une requête mobile"""
        request_path = self.request.path
        if '/m_activity/' in request_path:
            return ['m_activity_detail.html']
        return ['activity_detail.html']
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        activity = self.get_object()
        
        # Vérifier si c'est une requête mobile
        is_mobile = '/m_activity/' in self.request.path
        
        if is_mobile:
            try:
                user = self.request.user
                if str(user) != 'AnonymousUser':
                    # Récupérer le token Strava
                    user_list = Strava_user.objects.all().filter(strava_user=user)
                    if user_list:
                        access_token = user_list[0].access_token
                        header = {'Authorization': f'Bearer {access_token}'}
                        
                        # Récupérer les données de l'activité depuis Strava
                        activites_url = f"https://www.strava.com/api/v3/activities/{activity.strava_id}"
                        activities_json = requests.get(activites_url, headers=header).json()
                        
                        # Essayer d'abord la polyline détaillée (avec altitudes)
                        polyline_data = None
                        if 'map' in activities_json:
                            # Préférer la polyline détaillée qui contient les altitudes
                            if 'polyline_detailed' in activities_json['map'] and activities_json['map']['polyline_detailed']:
                                polyline_data = activities_json['map']['polyline_detailed']
                            elif 'summary_polyline' in activities_json['map']:
                                polyline_data = activities_json['map']['summary_polyline']
                        
                        if polyline_data:
                            decoded_polyline = polyline.decode(polyline_data)
                            
                            # Essayer de récupérer les altitudes via l'API streams
                            try:
                                streams_url = f"https://www.strava.com/api/v3/activities/{activity.strava_id}/streams"
                                streams_params = {'keys': 'latlng,altitude,distance', 'key_by_type': 'true'}
                                streams_json = requests.get(streams_url, headers=header, params=streams_params).json()
                                
                                if 'altitude' in streams_json and 'latlng' in streams_json:
                                    altitude_data = streams_json.get('altitude', {}).get('data', [])
                                    latlng_data = streams_json.get('latlng', {}).get('data', [])
                                    
                                    # Combiner les données : ajouter l'altitude à chaque point
                                    if altitude_data and latlng_data:
                                        decoded_polyline_with_alt = [
                                            (point[0], point[1], altitude_data[i] if i < len(altitude_data) else 0)
                                            for i, point in enumerate(latlng_data)
                                        ]
                                        decoded_polyline = decoded_polyline_with_alt
                            except Exception as e:
                                f_debug_trace("views.py", "ActivityDetailView.streams", f"Streams API error: {str(e)}")
                                pass
                            
                            # Générer le graphique d'altitude
                            altitude_graph = get_altitude_profile_graph(
                                decoded_polyline, 
                                total_elevation=activity.act_den,
                                total_distance=activity.get_act_dist_km()
                            )
                            if altitude_graph:
                                context['altitude_graph'] = altitude_graph
            except Exception as e:
                f_debug_trace("views.py", "ActivityDetailView.get_context_data", f"Error: {str(e)}")
                pass
        
        return context   


def export_activity_text(request, act_id):
    activity = get_object_or_404(Activity, act_id=act_id)
    lines = []
    lines.append(f"Activité: {activity.act_name or ''}")
    lines.append(f"Date: {activity.act_start_date.strftime('%d-%m-%Y %H:%M') if activity.act_start_date else ''}")
    lines.append(f"Strava ID: {activity.strava_id}")
    lines.append(f"Type: {activity.act_type or ''}")
    if activity.act_dist:
        lines.append(f"Distance: {activity.get_act_dist_km():.2f} km")
    else:
        lines.append("Distance: -")
    lines.append(f"Dénivelé: {activity.act_den or 0} m")
    ratio = activity.get_den_dist_ratio()
    lines.append(f"Ratio Dén./Dist.: {ratio if ratio is not None else '-'}")
    lines.append(f"Puissance normale: {activity.act_normal_power if activity.act_normal_power else '-'}")
    lines.append(f"Trainer: {'Oui' if activity.act_trainer == 1 else 'Non'}")
    lines.append("")
    lines.append("Infos:")
    info_items = activity.get_info_txt()
    if info_items:
        for info in info_items:
            lines.append(f"- {info.info_txt}")
    else:
        lines.append("- Aucune information disponible")
    perf_items = activity.get_performances()
    if perf_items:
        lines.append("")
        lines.append("Performances:")
        for perf in perf_items:
            lines.append(f"- {perf.nomSegment} | chrono {perf.chrono} | vam {perf.vam} | place {perf.place} | {perf.percent}%")
    col_items = activity.get_col_passed()
    if col_items:
        lines.append("")
        lines.append("Cols passés:")
        for col in col_items:
            lines.append(f"- {col.get_col_name()} ({col.col_code}) [{col.get_col_count()}]")
    
    # Section des nouveaux cols à la fin
    col_items = activity.get_col_passed()
    if col_items:
        lines.append("")
        lines.append("Déclaration 100 Cols:")
        for col in col_items:
            col_alt = col.get_col_alt() or "-"
            col_date = activity.act_start_date.strftime("%d-%m-%Y") if activity.act_start_date else "-"
            lines.append(f"{col.col_code};{col.get_col_name()};{col_alt};{col_date}")
    
    content = "\n".join(lines)
    response = HttpResponse(content, content_type='text/plain; charset=utf-8')
    response['Content-Disposition'] = f'attachment; filename="activity_{activity.act_id}.txt"'
    return response
                                                                            
class ColsDetailView(generic.DetailView):
	# specify the model to use            
    model = Col    
    context_object_name = 'col_detail'   # your own name for the list as a template variable    
    template_name = "col_detail.html"    # Specify your own template name/location   

    def get_context_data(self, **kwargs):
        ### Looking for activities on this col for the context user
        context = super(ColsDetailView, self).get_context_data(**kwargs)
        strava_user_id = self.request.session.get('strava_user_id')            
        le_col = context["object"]        
        ### f_debug_trace("views.py","le_col",le_col)    
        listColPerform = le_col.get_activities_passed()        
        ### f_debug_trace("views.py","listColPerform",listColPerform)    
        liste_activities = []        
        for cp in listColPerform:                                    
            pk_activity = cp.strava_id                        
            myActivities= Activity.objects.filter(strava_id = pk_activity)
            for lactivity in myActivities:                                
                print(lactivity.act_name)
                if int(strava_user_id) == int(lactivity.strava_user_id):
                    liste_activities.append(lactivity)                            
        context.update({'strava_user_id': strava_user_id})        
        context.update({'activities': liste_activities})        
        ### f_debug_trace("views.py","ColsDetailView",liste_activities)
        return context
    
       
class User_dashboardView(generic.ListView):	

    model = User_dashboard
    context_object_name = 'user_dashboard_list'               # your own name for the list as a template    
    template_name = "user_dashboard_list.html"      # Specify your own template name/location

    def get_queryset(self):                
        strava_user_id = self.request.session.get('strava_user_id')             
        # Delete/Insert        
        User_dashboard.objects.filter(strava_user_id=strava_user_id).delete()
        myUd = User_dashboard()
        myUd.strava_user_id = strava_user_id
        myUd.col_count = 0
        myUd.col2000_count = 0
        myUd.bike_year_km = 0        
        myUd.run_year_km = 0
        myUd.save()
        myQs = User_dashboard.objects.filter(strava_user_id=strava_user_id)
        return myQs
    
class PerformListView(MobileTemplateMixin, generic.ListView):
    model = Perform     
    context_object_name = 'perform_list'                # your own name for the list as a template    
    template_name = "perform_list.html"                 # Specify your own template name/location
    def get_queryset(self):                
        strava_user_id = self.request.session.get('strava_user_id')             
        perfList = Perform.objects.filter(strava_user_id=strava_user_id).order_by("-perf_date")
        return perfList

def m_perform_list(request):
    """Vue pour afficher la liste des performances en mode mobile"""
    strava_user_id = request.session.get('strava_user_id')             
    perfList = Perform.objects.filter(strava_user_id=strava_user_id).order_by("-perf_date")
    context = {
        'perform_list': perfList
    }
    return render(request, 'm_perform_list.html', context)
    
class SegmentListView(generic.ListView):        
    model = Segment   
    context_object_name = 'segment_list'               # your own name for the list as a template    
    template_name = "segment_list.html"      # Specify your own template name/location
    def get_queryset(self):                
        qsOk = Segment.objects.all()
        return qsOk           

class MonthStatListView(generic.ListView):        

    model = Month_stat
    context_object_name = 'month_stat_list'                 # your own name for the list as a template    
    template_name = "month_stat_list.html"                  # Specify your own template name/location

    def get_queryset(self):   
        strava_user_id = self.request.session.get('strava_user_id')             
        return Month_stat.objects.filter(strava_user_id=strava_user_id).order_by("-yearmonth")        
    
def new_col_form(request):
    if request.method  == 'POST':         
        form = ColForm(request.POST)
        if form.is_valid():        
            form.save()
            return redirect('../cols/')
        else:
            form = ColForm()
            return render(request , 'new_col.html' , {'form' : form})        
    else:                
        form = ColForm()
        return render(request , 'new_col.html' , {'form' : form})    
    
def get_strava_user_id(request,username):    
    ### f_debug_trace("views.py","get_strava_user_id","username = "+str(username))
    user_id = User.objects.get(username=username).pk        
    uid = UserSocialAuth.objects.get(user_id=user_id).uid        
    request.session['strava_user'] = str(username)
    request.session['strava_user_id'] = uid
    ### f_debug_trace("views.py","get_strava_user_id","strava_user_id = "+str(uid))
    
    return uid

def fVamYearView(request):
    template = 'vam.html'
    context_object_name = 'vamyear'     # your own name for the list as a template   
    template_name = "vam.html"          # Specify your own template name/location
    strava_user_id = request.session.get('strava_user_id')        
    listPerform = Perform.objects.filter(strava_user_id=strava_user_id).order_by('perf_date') 
    computed_vam = compute_all_vam(listPerform)
    if len(computed_vam)==0:
        currentDateTime = datetime.datetime.now()
        date = currentDateTime.date()
        year = date.strftime("%Y")
        strbegin = year+"-01"
        strend = year+"-12"
        computed_vam = {strbegin: 0, strend: 0}
    return render(request, template, {'context': computed_vam})    
    
########################################################################################################
#                                         Statistiques                                                 #
########################################################################################################

###     Vue PC

class StatListView(MobileTemplateMixin, generic.ListView):        
    model = User_dashboard   
    context_object_name = 'stat_list'               # your own name for the list as a template    
    template_name = "stat_list.html"                # Specify your own template name/location
    def get_queryset(self):                
        qsOk = User_dashboard.objects.all().order_by('-bike_year_km')                
        return qsOk           

########################################################################################################
#                                         Puissances                                                   #
########################################################################################################

def puissancesView(request):
    template = 'puissances.html' 
    # Mes Puissances
    strava_user_id = request.session.get('strava_user_id')        
    QueryPower = Activity.objects.filter(act_normal_power__gte=1).exclude(act_show_power=0).filter(strava_user_id=strava_user_id)
    x = []
    y = []
    n = []
    for oneActivity in QueryPower:
        if oneActivity.act_normal_power!='' and oneActivity.act_dist!='':
            x.append(oneActivity.act_dist/1000)    
            y.append(oneActivity.act_normal_power)            
            n.append(oneActivity.act_name)
    chart = get_plot(x,y,n)

    # Puissances All
    QueryAllPower = Activity.objects.filter(act_normal_power__gte=1).exclude(act_show_power=0).filter(act_type='Ride').exclude(act_trainer=1)    
    x = []
    y = []
    n = []
    for oneActivity in QueryAllPower:
        if oneActivity.act_normal_power!='' and oneActivity.act_dist!='':
            x.append(oneActivity.act_dist/1000)    
            y.append(oneActivity.act_normal_power)            
            n.append(oneActivity.get_user_acronyme())                    
    chartAll = get_plot_all(x,y,n)

    return render (request, template, {'chart':chart ,'chartAll':chartAll})

########################################################################################################
#                                   Historique d'un Segment                                            #
########################################################################################################

def fSegmentHistoView(request,**kwargs):
    template = 'm_segment_histo.html' if is_mobile_user_agent(request) else 'segment_histo.html'
    strava_user_id = request.session.get('strava_user_id')        
    segment_id = kwargs['segment_id']        
    segment_name = 'Not Found'
    strava_segment_id = 0
    Qrysegment = Segment.objects.filter(segment_id=segment_id)
    ## Segment Name
    for one_segment in Qrysegment:
        segment_name =  one_segment.segment_name
        strava_segment_id = one_segment.strava_segment_id
    ## Perf list by year            
    QueryPerf = Perform.objects.filter(segment_id=segment_id).filter(strava_user_id=strava_user_id).order_by("-perf_date")        
    byYear = get_pr_by_year(QueryPerf)           
    l_annee = []
    l_chrono = []
    s_chrono = []
    for one in byYear:        
        if one[0] not in l_annee:                        
            l_annee.append(one[0])                
            l_chrono.append(one[1]) 
            s_chrono.append(get_chrono_str(one[1]))
        else:            
            annee_index = l_annee.index(one[0])            
            if one[1]<l_chrono[annee_index]:            
                l_annee[annee_index]=one[0]
                l_chrono[annee_index]=one[1]                                             
                s_chrono[annee_index]=get_chrono_str(one[1])

    zipped = zip(l_annee, s_chrono)        
    print("zipped")
    print(zipped)
    return render (request, template, {'seg_name': segment_name , 'strava_segment_id': strava_segment_id , 'perf': zipped} )

def m_act_map(request, act_id):
    """Vue pour afficher la carte d'une activité en mode mobile"""
    my_strava_user = request.session.get("strava_user")    
    my_strava_user_id = get_strava_user_id(request, my_strava_user)
    
    refresh_access_token(my_strava_user)

    user = str(request.user)
    get_strava_user_id(request, user)

    myActivity_sq = Activity.objects.all().filter(act_id=act_id)    
    access_token = "notFound"
                   
    userList = Strava_user.objects.all().filter(strava_user=user)
    for userOne in userList:
        myUser = userOne
        access_token = myUser.access_token

    for myActivity in myActivity_sq:            
        strava_id = myActivity.strava_id
        act_statut = myActivity.act_status
        team_strava_user_id = myActivity.strava_user_id
                        
    if str(my_strava_user_id) != str(team_strava_user_id):
        return HttpResponse('')
        
    activites_url = f"https://www.strava.com/api/v3/activities/{strava_id}"
    header = {'Authorization': f'Bearer {access_token}'}            
    param = {'id': strava_id}
    
    activities_json = requests.get(activites_url, headers=header, params=param).json()
    activity_df_list = [pd.json_normalize(activities_json)]
    
    activities_df = pd.concat(activity_df_list)        
    activities_df = activities_df.dropna(subset=['map.summary_polyline'])
    activities_df['polylines'] = activities_df['map.summary_polyline'].apply(polyline.decode)
    
    # Centrage et zoom de la carte
    centrer_point = map_center(activities_df['polylines'])           
    map_zoom = cols_tools.map_zoom(centrer_point, activities_df['polylines'])    
    
    map = folium.Map(location=centrer_point, zoom_start=map_zoom, tiles='CartoDB voyager')

    # Afficher la polyline
    myGPSPoints = []
    
    for pl in activities_df['polylines']:
        if len(pl) > 0:
            folium.PolyLine(locations=pl, color='red').add_to(map)                
            myPoint = PointGPS()                
            myPoint = pl                            
            myGPSPoints.append(myPoint)

    # Afficher les cols
    conn = create_connection(SQLITE_PATH)        
    myColsList = getColByActivity(conn, strava_id)     
        
    for oneCol in myColsList:
        myCol = PointCol()
        myCol.setPoint(oneCol)
        col_location = [myCol.lat, myCol.lon]
        colColor = "blue"        
        mypopup = myCol.name + " (" + str(myCol.alt) + "m)"
        folium.Marker(col_location, popup=mypopup, icon=folium.Icon(color=colColor, icon="flag")).add_to(map)      
                   
    # Return HTML version of map
    map_html = map._repr_html_()
    
    context = {
        "main_map": map_html,
        "activity": Activity.objects.get(act_id=act_id)
    }

    return render(request, "m_activity_map.html", context)


