import datetime
import requests

from . import cols_tools
from .models import Perform, Segment, Strava_user
from .vars import f_debug_trace

################################################
#   Retourne  la liste des segments pertinents
################################################

def segment_explorer(myRectangle, access_token, strava_id, strava_user_id):
    """Importe les segments réellement parcourus dans une activité Strava.

    ``myRectangle`` est conservé dans la signature pour compatibilité avec les
    anciens appelants, mais il n'est plus utilisé. L'endpoint d'activité
    retourne directement les efforts de segment associés à cette activité.
    """
    del myRectangle

    activity_url = f"https://www.strava.com/api/v3/activities/{strava_id}"
    headers = {"Authorization": f"Bearer {access_token}"}

    try:
        response = requests.get(
            activity_url,
            headers=headers,
            params={"include_all_efforts": "true"},
            timeout=15,
        )
        activity_response = response.json()
    except (requests.RequestException, ValueError) as error:
        f_debug_trace("segments_tools.py", "segment_explorer", f"Erreur API Strava: {error}")
        return 0

    if response.status_code == 401 and cols_tools.refresh_access_token(strava_user_id):
        refreshed_user = Strava_user.objects.filter(strava_user_id=strava_user_id).first()
        if refreshed_user and refreshed_user.access_token:
            headers["Authorization"] = f"Bearer {refreshed_user.access_token}"
            try:
                response = requests.get(
                    activity_url,
                    headers=headers,
                    params={"include_all_efforts": "true"},
                    timeout=15,
                )
                activity_response = response.json()
            except (requests.RequestException, ValueError) as error:
                f_debug_trace("segments_tools.py", "segment_explorer", f"Erreur API Strava après renouvellement: {error}")
                return 0

    if response.status_code != 200:
        f_debug_trace(
            "segments_tools.py",
            "segment_explorer",
            f"Erreur API Strava ({response.status_code}): {activity_response}",
        )
        return 0

    segment_efforts = activity_response.get("segment_efforts") if isinstance(activity_response, dict) else None
    if segment_efforts is None:
        # Compatibilité avec une réponse de test/ancienne intégration.
        segment_efforts = activity_response.get("segments") if isinstance(activity_response, dict) else None
    if not isinstance(segment_efforts, list):
        f_debug_trace(
            "segments_tools.py",
            "segment_explorer",
            f"Réponse Strava sans segment_efforts: {activity_response}",
        )
        return 0

    ret = 0
    
    for effort in segment_efforts:
        oneSegment = effort.get("segment", effort) if isinstance(effort, dict) else {}
        try:
            segment_strava_id = oneSegment["id"]
            nameSegment = oneSegment["name"]
            avg_grade = float(oneSegment.get("average_grade", oneSegment.get("avg_grade", 0)))
            elev_difference = oneSegment.get("elev_difference")
            if elev_difference is None:
                elev_difference = abs(
                    float(oneSegment.get("elevation_high", 0))
                    - float(oneSegment.get("elevation_low", 0))
                )
            distance = float(oneSegment["distance"]) / 1000
        except (KeyError, TypeError, ValueError):
            f_debug_trace("segments_tools.py", "segment_explorer", f"Segment Strava invalide: {oneSegment}")
            continue

        normal_power = None
        segment_id = 0  # computed
        ### f_debug_trace("segment_tools.py","segment_explorer",nameSegment + " distance = " + str(distance) + " avg_grade = " + str(avg_grade))                        
        ### Eligible ou Non        
        if distance >= 3 and avg_grade >= 5:
            # DB update
            segment_list = Segment.objects.all().filter(strava_segment_id=segment_strava_id)
            if len(segment_list) == 1:
                # UPDATE
                for db_segment in segment_list:
                    segment_id = db_segment.segment_id
            else:
                # INSERT                                
                segment = Segment(strava_segment_id=segment_strava_id, activity_type="riding", segment_name=nameSegment, slope=avg_grade, lenght=distance, ascent=elev_difference, power=normal_power)
                segment.save()
                # Find the new key
                segment_list = Segment.objects.all().filter(strava_segment_id=segment_strava_id)
                if len(segment_list) == 1:
                    for db_segment in segment_list:
                        segment_id = db_segment.segment_id

            # Performances
            payment = save_segment_perf(segment_id, segment_strava_id, access_token, elev_difference, strava_user_id)

            if payment == 0:
                break

            ret = ret + 1                    
    return ret

###############################################
#   Retourne  les chronos sur un segment
###############################################

def save_segment_perf(segment_id, segment_strava_id, access_token, elev_difference, strava_user_id):
        
    param = {'segment_id': segment_strava_id}

    myDate = datetime.datetime.now().isoformat()

    performance_url = "https://www.strava.com/api/v3/segment_efforts?segment_id=" + str(segment_strava_id)
    performance_url = performance_url + "&access_token=" + str(access_token)
    performance_url = performance_url + "&start_date_local=" + "2010-10-01T00:00:30+01:00"
    performance_url = performance_url + "&end_date_local=" + str(myDate)
    performance_url = performance_url + "&per_page=200"
        
    performanceResponse = requests.get(performance_url, params=param).json()

    ret = 0        

    try:
        if performanceResponse['message'] == "Payment Required":
            ### f_debug_trace("segments_tools","save_segment_perf","Payment Required")
            return ret
    except:
        ### f_debug_trace("segments_tools","save_segment_perf","Payment OK")
        ret = 1

    ret = 1        
                            
    for onePerf in performanceResponse:
        
        fc_avg = 0
        fc_max = 0
        power = 0
        idPerf = onePerf["id"]
        temps = onePerf["elapsed_time"]
        myDate = onePerf["start_date"]
        
        try:
            fc_avg = onePerf["average_heartrate"]	
        except:            
            ret = 2

        try:
            fc_max = onePerf["max_heartrate"]	            
        except:                        
            ret = 3
                                         				        
        vam = int(3600*elev_difference/temps)

        try:
            power =  onePerf["average_watts"]
        except:            
            ret = 4    

        # DB Insert New One          
        perf_list = Perform.objects.all().filter(strava_perf_id = idPerf).all()
        if len(perf_list) == 0 :
            myPerf = Perform( strava_perf_id = idPerf, segment_id = segment_id, perf_date = myDate, perf_chrono = temps, perf_vam = vam, perf_fc = fc_avg, perf_fcmax = fc_max, strava_user_id = strava_user_id,perf_power = power)
            myPerf.save()
                                        
    return ret

def compute_all_vam(listPerform): 
    nb_vam = dict()
    sum_vam = dict()
    avg_vam = dict()
 
    for onePerf in listPerform:
        datestr = str(onePerf.perf_date)   
        datestrmore = datestr[0:7]
        nb_vam[datestrmore]=nb_vam.get(datestrmore, 0) + 1
        sum_vam[datestrmore]=sum_vam.get(datestrmore,0)+onePerf.perf_vam
        avg_vam[datestrmore]=int(sum_vam[datestrmore]/nb_vam[datestrmore])           
    return avg_vam