import datetime
from django.http import HttpResponse
from django.views import generic
from django.shortcuts import render, get_object_or_404
import folium
from folium.plugins import MarkerCluster
import requests
import pandas as pd
import polyline
from .forms import ColForm
from .models import Activity, Activity_info, Col_perform, Month_stat, Perform, Region, Segment, User_dashboard, User_var, User_weight
from .models import Col, Country
from .models import Col_counter
from .models import Strava_user
from .cols_tools import *
from .col_dbtools import *
from .graph import *
from .segments_tools import compute_all_vam, segment_explorer
from .vars import get_map_center, f_debug_trace
from django.db.models import Max
from django.shortcuts import render , redirect
from django.urls import reverse
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


def compute_climb_segments(altitude_data, distance_data, watts_data=None, interval_m=100, min_gradient=4.0):
    """
    Calcule la pente tous les `interval_m` mètres.
    Retourne la liste des segments en montée avec pente > min_gradient%.
    Retourne aussi le total de km en montée, la pente moyenne et la puissance moyenne.
    """
    if not altitude_data or not distance_data or len(altitude_data) < 2:
        return [], 0, None, None

    segments = []
    total_climb_dist = 0.0
    weighted_gradient_sum = 0.0
    climb_watts_sum = 0.0
    climb_watts_count = 0

    dist_start = distance_data[0]
    alt_start = altitude_data[0]
    i = 1

    while i < len(distance_data):
        # Avancer jusqu'à avoir parcouru interval_m mètres
        i_seg_start = i - 1
        while i < len(distance_data) and (distance_data[i] - dist_start) < interval_m:
            i += 1

        if i >= len(distance_data):
            break

        dist_end = distance_data[i]
        alt_end = altitude_data[i]
        delta_dist = dist_end - dist_start  # en mètres

        if delta_dist > 0:
            gradient = ((alt_end - alt_start) / delta_dist) * 100  # en %
            if gradient > min_gradient:
                seg = {
                    'dist_start': round(dist_start / 1000, 2),
                    'dist_end': round(dist_end / 1000, 2),
                    'gradient': round(gradient, 1),
                }
                segments.append(seg)
                total_climb_dist += delta_dist
                weighted_gradient_sum += gradient * delta_dist
                if watts_data:
                    for j in range(i_seg_start, min(i + 1, len(watts_data))):
                        w = watts_data[j]
                        if w and w > 0:
                            climb_watts_sum += w
                            climb_watts_count += 1

        dist_start = dist_end
        alt_start = alt_end

    total_climb_km = round(total_climb_dist / 1000, 2) if total_climb_dist > 0 else None
    avg_gradient = round(weighted_gradient_sum / total_climb_dist, 1) if total_climb_dist > 0 else None
    avg_power = round(climb_watts_sum / climb_watts_count) if climb_watts_count > 0 else None

    return segments, total_climb_km, avg_gradient, avg_power


def _interpolate_value_at_distance(distance_data, value_data, target_distance, start_index=1):
    """Interpole linéairement une valeur (altitude, FC, etc.) pour une distance cible."""
    if not distance_data or not value_data or len(distance_data) < 2:
        return None, start_index

    i = max(1, start_index)
    n = min(len(distance_data), len(value_data))
    while i < n and distance_data[i] < target_distance:
        i += 1

    if i >= n:
        i = n - 1

    d1 = distance_data[i - 1]
    d2 = distance_data[i]
    v1 = value_data[i - 1]
    v2 = value_data[i]

    if d2 == d1:
        return v2, i

    ratio = (target_distance - d1) / (d2 - d1)
    interpolated = v1 + (v2 - v1) * ratio
    return interpolated, i


def compute_slope_watts_hr_histogram_data(altitude_data, distance_data, watts_data=None, heartrate_data=None, interval_m=100):
    """Prépare les données pour 3 histogrammes: FC moyenne par tranche de watts selon la pente."""
    if not altitude_data or not distance_data:
        return {}

    n = min(len(altitude_data), len(distance_data))
    if n < 2:
        return {}

    altitude_data = altitude_data[:n]
    distance_data = distance_data[:n]

    watts_n = min(len(watts_data), n) if watts_data else 0
    hr_n = min(len(heartrate_data), n) if heartrate_data else 0
    if watts_n == 0 or hr_n == 0:
        return {}

    zones = {
        'lt4': {},
        '4to8': {},
        'gt8': {},
    }

    total_distance = distance_data[-1]
    segment_count = int(total_distance // interval_m)
    if segment_count <= 0:
        return {}

    idx_start = 1
    idx_end = 1

    for segment_index in range(segment_count):
        start_m = segment_index * interval_m
        end_m = (segment_index + 1) * interval_m

        alt_start, idx_start = _interpolate_value_at_distance(distance_data, altitude_data, start_m, idx_start)
        alt_end, idx_end = _interpolate_value_at_distance(distance_data, altitude_data, end_m, idx_end)

        if alt_start is None or alt_end is None:
            continue

        slope = ((alt_end - alt_start) / float(interval_m)) * 100.0

        if slope < 4.0:
            zone_key = 'lt4'
        elif slope <= 8.0:
            zone_key = '4to8'
        else:
            zone_key = 'gt8'

        power_values = []
        hr_values = []
        max_samples = min(watts_n, hr_n)
        for i in range(max_samples):
            dist_i = distance_data[i]
            if start_m <= dist_i < end_m:
                watts = watts_data[i]
                hr = heartrate_data[i]
                if watts and watts > 0 and hr and hr > 0:
                    power_values.append(watts)
                    hr_values.append(hr)

        if not power_values or not hr_values:
            continue

        avg_power = sum(power_values) / len(power_values)
        avg_hr = sum(hr_values) / len(hr_values)
        if avg_power <= 120:
            continue
        watts_bin = int(avg_power // 10) * 10
        zones[zone_key].setdefault(watts_bin, []).append(avg_hr)

    histogram_data = {}
    for zone_key, bins in zones.items():
        points = []
        for watts_bin in sorted(bins.keys()):
            hr_list = bins[watts_bin]
            if hr_list:
                points.append({
                    'watts_bin': watts_bin,
                    'avg_hr': round(sum(hr_list) / len(hr_list), 1),
                })
        histogram_data[zone_key] = points

    return histogram_data


def build_strava_description(conn, strava_id, climb_total_km=None, climb_avg_gradient=None, climb_avg_power=None):
    cols = getColByActivity(conn, strava_id)

    description = ""

    # Km en montée, pente et puissance moyenne (calculés depuis les streams)
    if climb_total_km and climb_avg_gradient:
        line = f"Montée : {climb_total_km} km — pente moy. {climb_avg_gradient} %"
        if climb_avg_power:
            line += f" — puissance moy. {climb_avg_power} W"
        description += line + "\n\n"

    if not cols:
        description += "Cols passés : aucun col identifié"
        return description[:1000]

    description += "Cols passés durant cette activité:\n"
    
    cols_list = []
    for col in cols:
        col_name = col.name        
        col_alt = ' - '
        if col.alt:
            col_alt = str(col.alt)            
        cols_list.append(col_name + ' [' + col_alt + ']')
        
    description += "\n".join(cols_list)
                
    return description[:1000]


def update_strava_activity_description(access_token, strava_id, description):
    if not access_token or not description:
        return False

    activities_url = f"https://www.strava.com/api/v3/activities/{strava_id}"
    headers = {'Authorization': f'Bearer {access_token}'}
    payload = {'description': description}

    try:
        res = requests.put(activities_url, headers=headers, data=payload)
        if res.status_code != 200:
            f_debug_trace("views.py", "update_strava_activity_description", f"status={res.status_code} body={res.text}")
            return False
        return True
    except Exception as e:
        f_debug_trace("views.py", "update_strava_activity_description", str(e))
        return False


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
    # Carte avec uniquement OpenStreetMap (OSM Standard)
    main_map = folium.Map(location=get_map_center(continent), zoom_start=6, tiles='OpenStreetMap')
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
    main_map = folium.Map(location=get_map_center("EUROPE"), zoom_start = 6, tiles='OpenStreetMap') # Create base map 
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
    activities_summary = []

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

            # Récupérer les streams pour calculer les segments de montée réels
            climb_total_km = None
            climb_avg_gradient = None
            climb_avg_power = None
            try:
                streams_url = f"https://www.strava.com/api/v3/activities/{strava_id}/streams"
                streams_params = {'keys': 'altitude,distance,watts', 'key_by_type': 'true'}
                streams_json = requests.get(streams_url, headers={'Authorization': f'Bearer {access_token}'}, params=streams_params).json()
                if 'altitude' in streams_json and 'distance' in streams_json:
                    altitude_data = streams_json['altitude']['data']
                    distance_data = streams_json['distance']['data']
                    watts_data = streams_json.get('watts', {}).get('data', []) or None
                    _, climb_total_km, climb_avg_gradient, climb_avg_power = compute_climb_segments(altitude_data, distance_data, watts_data)
            except Exception as e:
                f_debug_trace("views.py", "connected_map.streams", str(e))

            activities_summary.append({
                'name': activity_name,
                'date': act_start_date[:10],
                'dist_km': round(act_dist / 1000, 1) if act_dist else None,
                'den': int(act_den) if act_den else None,
                'climb_total_km': climb_total_km,
                'climb_avg_gradient': climb_avg_gradient,
                'cols': list(AllVisitedCols),
            })

            description = build_strava_description(conn, strava_id, climb_total_km, climb_avg_gradient, climb_avg_power)
            update_strava_activity_description(access_token, strava_id, description)

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
        "main_map":main_map_html,
        "activities_summary": activities_summary,
    }

    update_user_var(request.session.get("strava_user_id"),"","",datetime.datetime.now().timestamp())

    # Statistiques Mensuelles     
    compute_all_month_stat(my_strava_user_id)
    # Liste des Cols des l'année
    set_col_count_list_this_year(my_strava_user_id)

    return redirect('strava_user-detail', strava_user_id=my_strava_user_id)


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
        map = folium.Map(col_location, zoom_start=15, tiles='OpenStreetMap')
        myPopup = myCol.name+" ("+str(myCol.alt)+"m)"
        folium.Marker(col_location, popup=myPopup,icon=folium.Icon(color=colColor, icon="flag")).add_to(map)      

    map_html = map._repr_html_()
    
    context = {
        "main_map": map_html,
        "col_id" : col_id,        
    }
        
    return render(request, 'index.html', context)

def act_map(request, act_id):
    try:
        my_strava_user = request.session.get("strava_user")    
        my_strava_user_id = get_strava_user_id(request,my_strava_user)
        
        refresh_access_token(my_strava_user)

        user = str(request.user)
        get_strava_user_id(request,user)

        # Initialiser les variables
        myActivity_sq = Activity.objects.all().filter(act_id=act_id)
        
        if not myActivity_sq.exists():
            return HttpResponse('Activité non trouvée', status=404)
        
        myActivity = myActivity_sq.first()
        strava_id = myActivity.strava_id
        act_statut = myActivity.act_status
        team_strava_user_id = myActivity.strava_user_id
                        
        if str(my_strava_user_id) != str(team_strava_user_id):
            return HttpResponse('Accès non autorisé', status=403)
        
        # Récupérer le token
        access_token = None
        userList = Strava_user.objects.filter(strava_user=user)
        if userList.exists():
            access_token = userList.first().access_token
        
        if not access_token or access_token == "notFound":
            f_debug_trace("views.py", "act_map", "Token non disponible")
            map = folium.Map(location=[45.5, 5.0], zoom_start=6, tiles='OpenStreetMap')
            context = {"main_map": map._repr_html_()}
            return render(request, "base_map.html", context)
        
        # Récupérer les données de l'activité avec gestion d'erreur
        activites_url = f"https://www.strava.com/api/v3/activities/{strava_id}"
        header = {'Authorization': f'Bearer {access_token}'}
        
        try:
            response = requests.get(activites_url, headers=header, timeout=10)
            response.raise_for_status()
            activities_json = response.json()
        except (requests.RequestException, ValueError) as e:
            f_debug_trace("views.py", "act_map", f"Erreur API Strava: {str(e)}")
            map = folium.Map(location=[45.5, 5.0], zoom_start=6, tiles='OpenStreetMap')
            context = {"main_map": map._repr_html_()}
            return render(request, "base_map.html", context)
        
        # Vérifier que la polyline existe
        if 'map' not in activities_json or 'summary_polyline' not in activities_json.get('map', {}):
            f_debug_trace("views.py", "act_map", "Pas de polyline disponible")
            map = folium.Map(location=[45.5, 5.0], zoom_start=6, tiles='OpenStreetMap')
            context = {"main_map": map._repr_html_()}
            return render(request, "base_map.html", context)
        
        # Décoder la polyline
        try:
            polyline_data = activities_json['map']['summary_polyline']
            decoded_polyline = polyline.decode(polyline_data)
            
            if not decoded_polyline or len(decoded_polyline) == 0:
                f_debug_trace("views.py", "act_map", "Polyline vide après décodage")
                map = folium.Map(location=[45.5, 5.0], zoom_start=6, tiles='OpenStreetMap')
                context = {"main_map": map._repr_html_()}
                return render(request, "base_map.html", context)
            
            # Créer la carte
            centrer_point = [sum(p[0] for p in decoded_polyline) / len(decoded_polyline),
                            sum(p[1] for p in decoded_polyline) / len(decoded_polyline)]
            map = folium.Map(location=centrer_point, zoom_start=9, tiles='OpenStreetMap')
            
            # Ajouter la polyline
            folium.PolyLine(locations=decoded_polyline, color='red').add_to(map)
            
            # Ajouter les cols (sans appel bloquant à segment_explorer)
            conn = create_connection(SQLITE_PATH)
            myColsList = getColByActivity(conn, strava_id)
            
            for oneCol in myColsList:
                myCol = PointCol()
                myCol.setPoint(oneCol)
                col_location = [myCol.lat, myCol.lon]
                colColor = "blue"
                mypopup = myCol.name + " (" + str(myCol.alt) + "m)"
                folium.Marker(col_location, popup=mypopup, 
                            icon=folium.Icon(color=colColor, icon="flag")).add_to(map)
            
            # Appeler segment_explorer en arrière-plan (non-bloquant)
            try:
                myRectangle = get_map_rectangle([decoded_polyline])
                # Exécuter segment_explorer sans bloquer (si possible, utiliser Celery)
                segment_explorer(myRectangle, access_token, strava_id, my_strava_user_id)
            except Exception as e:
                f_debug_trace("views.py", "act_map", f"Erreur segment_explorer: {str(e)}")
                pass  # Continuer même si segment_explorer échoue
            
            # Recompute activity si nécessaire
            if act_statut == 0:
                try:
                    recompute_activity(strava_id, None, my_strava_user_id)
                except Exception as e:
                    f_debug_trace("views.py", "act_map", f"Erreur recompute_activity: {str(e)}")
                    pass
            
            map_html = map._repr_html_()
            context = {"main_map": map_html}
            return render(request, "base_map.html", context)
            
        except Exception as e:
            f_debug_trace("views.py", "act_map", f"Erreur polyline: {str(e)}")
            map = folium.Map(location=[45.5, 5.0], zoom_start=6, tiles='OpenStreetMap')
            context = {"main_map": map._repr_html_()}
            return render(request, "base_map.html", context)
    
    except Exception as e:
        f_debug_trace("views.py", "act_map", f"Erreur générale: {str(e)}")
        map = folium.Map(location=[45.5, 5.0], zoom_start=6, tiles='OpenStreetMap')
        context = {"main_map": map._repr_html_()}
        return render(request, "base_map.html", context)


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
    template = "m_user_detail.html" if is_mobile_user_agent(request) else "user_detail.html"      

    strava_user_id = kwargs['strava_user_id']

    mydashBoard = User_dashboard.objects.filter(strava_user_id = strava_user_id)
    all_activities = list(Activity.objects.filter(strava_user_id=strava_user_id).order_by('-act_start_date'))
    last_activities = all_activities[:10]
    power_values = [activity.act_normal_power for activity in last_activities if activity.act_normal_power not in (None, 0)]
    last_ten_power_avg = round(sum(power_values) / len(power_values), 1) if power_values else None

    current_year = datetime.datetime.now().year
    year_power_avgs = {}
    for year in (current_year, current_year - 1, current_year - 2):
        year_values = []
        for activity in all_activities:
            if activity.act_normal_power in (None, 0):
                continue

            act_date = activity.act_start_date
            if act_date is None:
                continue

            if isinstance(act_date, str):
                try:
                    act_date = datetime.datetime.fromisoformat(act_date.replace('Z', '+00:00'))
                except ValueError:
                    continue

            act_year = getattr(act_date, 'year', None)
            if act_year == year:
                year_values.append(activity.act_normal_power)

        year_power_avgs[year] = round(sum(year_values) / len(year_values), 1) if year_values else None
    for onDS in mydashBoard:
        onDS.set_bike_year_km()
        onDS.set_run_year_km()
        onDS.set_col_count()
        onDS.set_col2000_count()
    
    theUser =Strava_user.objects.filter(strava_user_id=strava_user_id)
    listActivities = Activity.objects.filter(strava_user_id=strava_user_id).order_by('-act_start_date')[:10]
    listColsOk = Col_counter.objects.filter(strava_user_id=strava_user_id).order_by("-col_count")[:10]                                                                   
            
    return render (request,template, {
        'Strava_User': theUser,
        'listAct': listActivities,
        'ColsOk': listColsOk,
        'last_ten_power_avg': last_ten_power_avg,
        'year_power_avgs': year_power_avgs,
    })

#########################################################################################  

def fColsListView(request,**kwargs):        

    template = 'm_col_list.html' if is_mobile_user_agent(request) else 'cols_list.html'
    
    code_paysregion = kwargs.get('pk', kwargs.get('code_paysregion', ''))
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
        context['show_recalc_progress'] = self.request.GET.get('recalc') == '1'
        return context

#########################################################################   
#                       Carte des Cols Franchis                         #
#########################################################################   

def get_col_count_color(col_count):
    """Retourne une palette de 6 nuances, du plus clair au rouge pour les plus visités."""
    palette = [
        "#ddb571",
        "#d89538",
        "#d8781d",
        "#c85a1a",
        "#b33d14",
        "#7d0000",
    ]
    thresholds = [1, 2, 5, 10, 20, float('inf')]
    for index, limit in enumerate(thresholds):
        if col_count <= limit:
            return palette[index]
    return palette[-1]


def colsok_map(request):
    """Affiche une carte avec les cols franchis colorés selon le nombre d'ascensions."""
    strava_user_id = request.session.get('strava_user_id')
    
    # Récupérer tous les cols franchis de l'utilisateur
    cols_franchis = Col_counter.objects.filter(strava_user_id=strava_user_id).order_by('col_code')
    
    # Initialiser la carte avec un centre par défaut
    map_center = [45.5, 5.0]  # Centre en France par défaut
    colsok_map = folium.Map(location=map_center, zoom_start=6, tiles='OpenStreetMap')
    
    # Créer un cluster pour grouper les marqueurs proches
    marker_cluster = MarkerCluster().add_to(colsok_map)
    
    # Ajouter un marqueur pour chaque col franchi
    for col_counter in cols_franchis:
        col_lat = col_counter.get_col_lat()
        col_lon = col_counter.get_col_lon()
        col_name = col_counter.get_col_name()
        col_alt = col_counter.get_col_alt()
        col_count = getattr(col_counter, 'col_count', 0) or 0
        
        # Vérifier que les coordonnées existent
        if col_lat and col_lon and col_alt:
            location = [col_lat, col_lon]
            popup_text = f"{col_name} ({col_alt}m) [{col_count}x]"
            color = get_col_count_color(col_count)
            
            folium.CircleMarker(
                location,
                radius=8,
                popup=popup_text,
                tooltip=f"{col_name} ({col_count}x)",
                color=color,
                fill=True,
                fill_color=color,
                fill_opacity=0.9,
            ).add_to(marker_cluster)
    
    colsok_map_html = colsok_map._repr_html_()
    
    # Déterminer le template à utiliser selon le user-agent
    is_mobile = is_mobile_user_agent(request)
    template = "m_col_map.html" if is_mobile else "col_map.html"
    
    try:
        col_count = cols_franchis.count()
    except TypeError:
        col_count = len(cols_franchis)

    context = {
        "colsok_map": colsok_map_html,
        "col_count": col_count
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
        queryset = Activity.objects.filter(strava_user_id=strava_user_id).order_by("-act_start_date")
        
        # Filtre par date de début
        date_from = self.request.GET.get('date_from')
        if date_from:
            try:
                from datetime import datetime, time
                date_from_obj = datetime.strptime(date_from, '%Y-%m-%d').replace(hour=0, minute=0, second=0)
                queryset = queryset.filter(act_start_date__gte=date_from_obj)
                f_debug_trace("views.py", "ActivityListView", f"Filtre date_from: {date_from_obj}")
            except (ValueError, Exception) as e:
                f_debug_trace("views.py", "ActivityListView", f"Erreur date_from: {str(e)}")
                pass
        
        # Filtre par date de fin
        date_to = self.request.GET.get('date_to')
        if date_to:
            try:
                from datetime import datetime, time
                date_to_obj = datetime.strptime(date_to, '%Y-%m-%d').replace(hour=23, minute=59, second=59)
                queryset = queryset.filter(act_start_date__lte=date_to_obj)
                f_debug_trace("views.py", "ActivityListView", f"Filtre date_to: {date_to_obj}")
            except (ValueError, Exception) as e:
                f_debug_trace("views.py", "ActivityListView", f"Erreur date_to: {str(e)}")
                pass
        
        # Filtre par nom de l'activité
        activity_name = self.request.GET.get('activity_name')
        if activity_name:
            queryset = queryset.filter(act_name__icontains=activity_name)
            f_debug_trace("views.py", "ActivityListView", f"Filtre activity_name: {activity_name}")
        
        return queryset
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        # Passer les paramètres de filtre au template
        context['date_from'] = self.request.GET.get('date_from', '')
        context['date_to'] = self.request.GET.get('date_to', '')
        context['activity_name'] = self.request.GET.get('activity_name', '')
        return context

    
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
        
        # Générer le graphique d'altitude si l'utilisateur est connecté
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
                            streams_params = {'keys': 'latlng,altitude,distance,watts,heartrate', 'key_by_type': 'true'}
                            streams_json = requests.get(streams_url, headers=header, params=streams_params).json()
                            
                            if 'altitude' in streams_json and 'latlng' in streams_json:
                                altitude_data = streams_json.get('altitude', {}).get('data', [])
                                latlng_data = streams_json.get('latlng', {}).get('data', [])
                                distance_data = streams_json.get('distance', {}).get('data', [])
                                watts_data = streams_json.get('watts', {}).get('data', [])
                                heartrate_data = streams_json.get('heartrate', {}).get('data', [])

                                # Combiner les données : ajouter l'altitude à chaque point
                                if altitude_data and latlng_data:
                                    decoded_polyline_with_alt = [
                                        (point[0], point[1], altitude_data[i] if i < len(altitude_data) else 0)
                                        for i, point in enumerate(latlng_data)
                                    ]
                                    decoded_polyline = decoded_polyline_with_alt

                                # Calculer les segments en montée tous les 100m
                                if altitude_data and distance_data:
                                    climb_segs, climb_km, avg_grad, avg_power = compute_climb_segments(altitude_data, distance_data, watts_data or None)
                                    context['climb_segments'] = climb_segs
                                    context['climb_total_km'] = climb_km
                                    context['climb_avg_gradient'] = avg_grad
                                    context['climb_avg_power'] = avg_power

                                    hist_data = compute_slope_watts_hr_histogram_data(
                                        altitude_data,
                                        distance_data,
                                        watts_data or None,
                                        heartrate_data or None,
                                        interval_m=100,
                                    )
                                    zone_specs = [
                                        ('lt4', 'Pente < 4 %'),
                                        ('4to8', 'Pente 4 a 8 %'),
                                        ('gt8', 'Pente > 8 %'),
                                    ]
                                    slope_zone_histograms = []
                                    for zone_key, zone_title in zone_specs:
                                        zone_points = hist_data.get(zone_key, [])
                                        graph = get_watts_hr_histogram(zone_points, zone_title)
                                        slope_zone_histograms.append({
                                            'title': zone_title,
                                            'graph': graph,
                                            'points': zone_points,
                                        })
                                    context['slope_zone_histograms'] = slope_zone_histograms
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


def recalculate_activity_cols(request, act_id):
    """Réinitialise le calcul des cols pour une activité."""
    try:
        activity = get_object_or_404(Activity, act_id=act_id)
        
        # Vérifier que c'est l'utilisateur de l'activité
        strava_user_id = request.session.get('strava_user_id')
        if str(strava_user_id) != str(activity.strava_user_id):
            return HttpResponse('Accès non autorisé', status=403)
        
        user = request.user
        
        # Récupérer le token Strava
        user_list = Strava_user.objects.filter(strava_user=user)
        if not user_list.exists():
            f_debug_trace("views.py", "recalculate_activity_cols", "Token Strava non trouvé")
            activity.act_status = 0
            activity.save()
            return redirect('activity-detail', pk=act_id)
        
        access_token = user_list.first().access_token
        
        if not access_token or access_token == "notFound":
            f_debug_trace("views.py", "recalculate_activity_cols", "Token invalide")
            activity.act_status = 0
            activity.save()
            return redirect('activity-detail', pk=act_id)
        
        # Récupérer les données de l'activité depuis Strava
        strava_id = activity.strava_id
        activites_url = f"https://www.strava.com/api/v3/activities/{strava_id}"
        header = {'Authorization': f'Bearer {access_token}'}
        
        try:
            response = requests.get(activites_url, headers=header, timeout=10)
            response.raise_for_status()
            activities_json = response.json()
            
            # Vérifier que la polyline existe
            if 'map' in activities_json and 'summary_polyline' in activities_json.get('map', {}):
                polyline_data = activities_json['map']['summary_polyline']
                decoded_polyline = polyline.decode(polyline_data)
                
                if decoded_polyline and len(decoded_polyline) > 0:
                    # Créer un DataFrame avec les données
                    activities_df = pd.DataFrame({
                        'polylines': [decoded_polyline]
                    })
                    
                    # Lancer le recalcul
                    recompute_activity(strava_id, activities_df, strava_user_id)
                    f_debug_trace("views.py", "recalculate_activity_cols", f"Recalcul lancé avec succès pour {strava_id}")
        except Exception as e:
            f_debug_trace("views.py", "recalculate_activity_cols", f"Erreur lors du recalcul: {str(e)}")
        
        # Passer le status à 1 pour marquer le calcul comme fait
        activity.act_status = 1
        activity.save()
        
        return redirect(f"{reverse('colsok')}?recalc=1")
    except Exception as e:
        f_debug_trace("views.py", "recalculate_activity_cols", f"Erreur générale: {str(e)}")
        return HttpResponse('Erreur lors du recalcul', status=500)

                                                                            
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
    QueryPower = Activity.objects.filter(act_normal_power__gte=1, strava_user_id=strava_user_id)
    x = []
    y = []
    n = []
    normal_missing = not QueryPower.exists()
    weight = get_user_weight(strava_user_id)
    for oneActivity in QueryPower:
        power_value = oneActivity.act_normal_power
        if power_value and oneActivity.act_dist:
            activity_weight = get_user_weight(strava_user_id, oneActivity.act_start_date) or weight
            if activity_weight and activity_weight > 0:
                x.append(oneActivity.act_dist/1000)
                y.append(round(power_value / activity_weight, 2))
                n.append(oneActivity.act_name)
    chart = get_plot(x,y,n, title='Mes Puissances', ylabel='Puissance (W/kg)')
    # If there are activities but none with normalized power, show a warning in template
    normal_missing = normal_missing and len(x) == 0
    weight_missing = bool(QueryPower.exists() and not weight)

    # Puissances All
    QueryAllPower = Activity.objects.filter(act_normal_power__gte=1).exclude(act_show_power=0).filter(act_type='Ride').exclude(act_trainer=1)
    all_users = sorted({
        oneActivity.get_user_acronyme()
        for oneActivity in QueryAllPower
        if oneActivity.act_normal_power != '' and oneActivity.act_dist != ''
    })

    selected_users = request.GET.getlist('users')
    filter_submitted = request.GET.get('filter_users') == '1'

    # Par defaut, afficher tout le monde. Si le filtre est soumis sans case cochee, afficher vide.
    if not filter_submitted:
        selected_users = all_users

    x = []
    y = []
    n = []
    team_weight_missing = False
    team_weight_found = False
    team_activity_found = False

    for oneActivity in QueryAllPower:
        if oneActivity.act_normal_power != '' and oneActivity.act_dist != '':
            user_acronym = oneActivity.get_user_acronyme()
            if user_acronym in selected_users:
                team_activity_found = True
                activity_weight = get_user_weight(oneActivity.strava_user_id)
                if activity_weight and activity_weight > 0:
                    x.append(oneActivity.act_dist/1000)
                    y.append(round(oneActivity.act_normal_power / activity_weight, 2))
                    n.append(user_acronym)
                    team_weight_found = True
                else:
                    team_weight_missing = True

    if team_activity_found and not team_weight_found:
        team_weight_missing = True

    chartAll = get_plot_all(x, y, n)

    return render(request, template, {
        'chart': chart,
        'chartAll': chartAll,
        'all_users': all_users,
        'selected_users': selected_users,
        'weight_missing': weight_missing,
        'normal_missing': normal_missing,
        'team_weight_missing': team_weight_missing,
    })

########################################################################################################
#                                   Helper functions                                                   #
########################################################################################################

def get_user_weight(strava_user_id, activity_date=None):
    """Return the most recent user weight, optionally on or before a specific activity date."""
    if not strava_user_id:
        return None
    query = User_weight.objects.filter(strava_user_id=strava_user_id)
    if activity_date is not None:
        query = query.filter(weight_date__lte=activity_date)
    weight_entry = query.order_by('-weight_date').first()
    return float(weight_entry.weight) if weight_entry else None

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

    perf = [
        {'year': year, 'chrono': chrono, 'chrono_str': chrono_str}
        for year, chrono, chrono_str in zip(l_annee, l_chrono, s_chrono)
    ]
    perf_graph = [
        {'year': item['year'], 'chrono': item['chrono']}
        for item in perf
    ]
    return render(request, template, {
        'seg_name': segment_name,
        'strava_segment_id': strava_segment_id,
        'perf': perf,
        'perf_graph': perf_graph,
    })

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
    
    map = folium.Map(location=centrer_point, zoom_start=map_zoom, tiles='OpenStreetMap')

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


