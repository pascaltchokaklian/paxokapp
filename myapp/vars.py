from refactor.settings import APP_CLIENT_ID, COLOMARS, COUNTRY, DEPARTEMENT, LEVEL_COL_DEBUG, SALTA, SOCIAL_AUTH_STRAVA_SECRET

MONTHES = ["Janvier","Février","Mars","Avril","Mai","Juin","Juillet","Août","Septembre","Octobre","Novembre","Décembre"]

def f_debug_col():
    ret = False
    if LEVEL_COL_DEBUG > 0:
        ret = True
    return ret    

def f_debug_trace(classe,function,value):      
    print("[Debug] >>> Class: ", classe, " >>> function: ",function, " >>> ",str(value))

def get_app_client_secret():
    return SOCIAL_AUTH_STRAVA_SECRET   

def get_app_client_id():
    return APP_CLIENT_ID

def get_map_center(continent):        
    ret = COLOMARS
    if continent == "SOUTHAMERICA":
        ret = SALTA        
    return ret

def get_default_departement():    
    return DEPARTEMENT

def get_default_country():    
    return COUNTRY

def display_year_month(month):
    ret = "not found"
    if month > 0 and month < 13:
        ret = MONTHES[month-1]
    else:
        f_debug_trace("vars.py","display_year_month","not found:"+str(month))        
        ret = "not found"
    return ret
