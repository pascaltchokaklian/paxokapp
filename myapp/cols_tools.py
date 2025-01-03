from numpy import sin, cos, arccos, pi, round
import numpy as N
import requests
from .models import Strava_user
from .vars import  f_debug_trace, get_app_client_id, get_app_client_secret
import warnings

warnings.filterwarnings('ignore', message='Unverified HTTPS request')

####################################################

class PointGPS:
    "Definition d'un point geometrique"
    def __init__(self):
        self.lat = 0
        self.lon = 0

####################################################

GPSPointsList = list[PointGPS] 

####################################################

class PointCol(PointGPS):
    "Definition d'un point col geometrique"
    def __init__(self):
        self.lat = 0
        self.lon = 0
        self.alt = 0
        self.name = "colName"
        self.col_code = "-"
        self.col_type = "-"

    def setPoint(self,PointGPS):        
        self.lat = PointGPS.lat
        self.lon = PointGPS.lon
        self.alt = PointGPS.alt
        self.name = PointGPS.name
        self.col_code = PointGPS.col_code
        self.col_type = PointGPS.col_type

####################################################        

ColsList = list[PointCol]        

####################################################

def rad2deg(radians):
    degrees = radians * 180 / pi
    return degrees

####################################################

def deg2rad(degrees):
    radians = degrees * pi / 180
    return radians

####################################################

def getDistanceBetween2Points(p1:PointGPS, p2:PointGPS):
    calcDistance = 0           
    calcDistance = getDistanceBetweenPoints(p1.lat,p1.lon,p2.lat,p2.lon,'kilometers')    
    return calcDistance

####################################################

def getDistanceBetweenPoints(latitude1, longitude1, latitude2, longitude2, unit = 'miles'):
            
    theta = longitude1 - longitude2    
    distance = 60 * 1.1515 * rad2deg(
        arccos(
            (sin(deg2rad(latitude1)) * sin(deg2rad(latitude2))) + 
            (cos(deg2rad(latitude1)) * cos(deg2rad(latitude2)) * cos(deg2rad(theta)))
        )
    )

    # print(">>>> Distance = ",distance)
     
    if unit == 'miles':
        return round(distance, 2)
    if unit == 'kilometers':
        return round(distance * 1.609344, 5)        

####################################################

def getColsVisited(colsList: ColsList, pointsList: GPSPointsList):
    visitedColList = []
    for onePoint in pointsList:
        myGPSPoint = PointGPS()
        myGPSPoint.lat = onePoint[0]
        myGPSPoint.lon = onePoint[1]
        laList = getColsVisitedList(colsList,myGPSPoint)
        visitedColList = visitedColList + laList
    
    visitedColList = N.unique(visitedColList) 

    return visitedColList

####################################################

def getColsVisitedList(colsList: ColsList, onePoint: PointGPS ):
    visitedList = []
    for oneCol in colsList:        
        myColPoint = PointCol()
        myColPoint.lat = oneCol.lat
        myColPoint.lon = oneCol.lon
        myColPoint.name = oneCol.name
        myColPoint.col_code = oneCol.col_code        
        distance = getDistanceBetween2Points(myColPoint,onePoint)                
        if distance < 0.250:         
            visitedList.append(myColPoint.col_code)                            

        ########################################################################
        #   if oneCol.col_code == "FR-06-0963b":
        #       print("------------------------------->",oneCol.name,distance  )                        
        ########################################################################    


    return visitedList

####################################################

def getListColsUniques(colsList: ColsList):
    colsList = N.unique(colsList) 
    return colsList

####################################################
    
def map_center(listePoint= PointGPS() ):                
        for unElt in listePoint:
            sum_x = 0.0
            sum_y = 0.0
            i = 0               
            for unPt in unElt:
                i=i+1
                sum_x = sum_x + unPt[0]
                sum_y = sum_y + unPt[1]
        if i > 0:                 
            sum_x = sum_x/i                                                      
            sum_y = sum_y/i                                                      
        
        return [sum_x,sum_y]

def get_map_rectangle(listePoint= PointGPS() ):        
        for unElt in listePoint:
            min_x = 200.0
            min_y = 200.0
            max_x = -200.0
            max_y = -200.0
                       
            for unPt in unElt:   

                if unPt[0] > max_x:
                    max_x = unPt[0]
                if unPt[1] > max_y:
                    max_y = unPt[1]

                if unPt[0] < min_x:
                    min_x = unPt[0]
                if unPt[1] < min_y:
                    min_y = unPt[1]                    
        
        return [min_x,min_y,max_x,max_y]

def map_zoom(centrerPoint, listePoint= PointGPS() ):        
        distMax = 0.0            
        myZoom = 10
        theCenter = PointGPS()
        theCenter.lat = centrerPoint[0]            
        theCenter.lon = centrerPoint[1]        
        for unElt in listePoint:
            distMax = 0.0            
            for unPt in unElt:                                            
                unPoint = PointGPS()
                unPoint.lat = unPt[0]
                unPoint.lon = unPt[1]                          
                d = getDistanceBetween2Points(theCenter,unPoint)                                
                if d>distMax:
                    distMax = d
        myZoom = 13-distMax/10 
        if myZoom < 0 :
            myZoom=1
        
        return int(myZoom)

#########################################################

def refresh_access_token(strava_user):
    """ Refresh du token strava 
    
    Parametres :
    client_Strava: une liste avec les informations du client strava
    
    Retourne :
    bool: Refresh token réussie ou non
    """

    refresh_token = ""
    myUser_unique = Strava_user.objects.all().filter(strava_user = strava_user)
    for oneOk in myUser_unique:
            myUser = oneOk            
            refresh_token = myUser.refresh_token                        
            
    payload_refresh = {
        'client_id': {get_app_client_id()},
        'client_secret': {get_app_client_secret()},
        'refresh_token': {refresh_token},
        'grant_type': "refresh_token",
        'f': 'json'
    }
        
    try:
        auth_url = "https://www.strava.com/oauth/token"
        print("-------------------------------------")
        print(auth_url)
        print("-------------------------------------")
        res = requests.post(auth_url, data=payload_refresh, verify=False)                

        myUser.access_token = res.json()['access_token']
        myUser.expire_at = res.json()['expires_at']
        myUser.save()
        
    except:
        f_debug_trace("col_tools.py","refresh_access_token","Refresh Token Error")
        return False
    
    return True

#####################################################
#   month = 202311
#   days_list = [20231102, 20231105, 20210712]
#   Return: 2
#####################################################

def get_dayson_in_month(month,days_list):    
    nb_count = 0
    for oneDay in days_list:                
        if (month == oneDay [:6]):            
            nb_count +=1                
    return nb_count
