import datetime
import requests

from .models import Perform, Segment
from .vars import f_debug_trace

################################################
#   Retourne  la liste des segments pertinents
################################################

def segment_explorer(myRectangle, access_token, strava_id, strava_user_id):
            
    header = {'Authorization': 'Bearer ' + str(access_token)}            
    param = {'id': strava_id, 'min_cat' : 3 }

    segments_url = "https://www.strava.com/api/v3/segments/explore?bounds="+str(myRectangle[0])+","+str(myRectangle[1])+","+str(myRectangle[2])+","+str(myRectangle[3])
    segments_url = segments_url + "&activity_type=riding"
    segments_url = segments_url + "&access_token="+ str(access_token)

    ExplorerResponse = requests.get(segments_url, headers=header, params=param).json()

    ret = 0
    
    for oneSegment in ExplorerResponse['segments']:
        
        strava_id = oneSegment["id"]
        nameSegment = oneSegment["name"]
        
        avg_grade = oneSegment["avg_grade"]
        normal_power = oneSegment["avg_grade"]
        elev_difference = oneSegment["elev_difference"]
        distance = oneSegment["distance"]/1000
        segment_id = 0 # compuuted
        ### f_debug_trace("segment_tools.py","segment_explorer",nameSegment + " distance = " + str(distance) + " avg_grade = " + str(avg_grade))                        
        ### Eligible ou Non        
        if distance >= 3 and avg_grade >= 5:                    
            # DB update
            segment_list = Segment.objects.all().filter(strava_segment_id = strava_id)
            if len(segment_list) == 1 :
                # UPDATE
                for oneSegment in segment_list:                                        
                    segment_id = oneSegment.segment_id
            else:
                # INSERT                                
                segment = Segment(strava_segment_id=strava_id,activity_type="riding", segment_name=nameSegment, slope=avg_grade,lenght=distance,ascent=elev_difference,power=normal_power)
                segment.save()
                # Find the new key
                segment_list = Segment.objects.all().filter(strava_segment_id = strava_id)
                if len(segment_list) ==1 :                
                    for oneSegment in segment_list:                        
                        segment_id = oneSegment.segment_id

            #Performances
            payment = save_segment_perf(segment_id, strava_id, access_token, elev_difference,strava_user_id)

            if payment == 0:
                break

            ret = ret + 1                    
    return ret

###############################################
#   Retourne  les chronos sur un segment
###############################################

def save_segment_perf(segment_id, segment_strava_id, access_token, elev_difference, strava_user_id):
        
    param = {'segment_id': segment_strava_id}
    header = {'Authorization': 'Bearer ' + str(access_token)} 
    
    myDate = datetime.datetime.now().isoformat()

    performance_url = "https://www.strava.com/api/v3/segment_efforts?segment_id="+ str (segment_strava_id)
    performance_url = performance_url + "&start_date_local="+"2010-10-01T00:00:30+01:00"
    performance_url = performance_url + "&end_date_local="+str(myDate)    
    performance_url = performance_url + "&per_page=200"
    performance_url = performance_url + "&access_token="+ str(access_token)
        
    performanceResponse = requests.get(performance_url, headers=header, params=param).json()

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
            myPerf = Perform( strava_perf_id = idPerf, segment_id = segment_id, perf_date = myDate, perf_chrono = temps, perf_vam = vam, perf_fc = fc_avg, perf_fcmax = fc_max, strava_user_id = strava_user_id,power = power)
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