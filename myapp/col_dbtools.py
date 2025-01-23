import datetime
import sqlite3
import time

from aifc import Error

from myapp import cols_tools
from refactor.settings import SQLITE_PATH
from .models import Activity, Activity_info, Col, Col_counter as cc, Col_perform as cp, Country, Month_stat, Region, Strava_user, User_dashboard, User_var
from django.utils import timezone
from .vars import f_debug_col, f_debug_trace
from django.contrib.auth.models import User

#############################################################################

def create_connection(db_file):
    """ create a database connection to the SQLite database
        specified by the db_file
    :param db_file: database file
    :return: Connection object or None
    """
    conn = None
    try:
        conn = sqlite3.connect(db_file)
    except Error as e:
        print(e)

    return conn

#############################################################################

def select_all_cols(conn, region_info):
    """
    Query all rows in the tasks table
    :param conn: the Connection object
    :return:
    """
    cur = conn.cursor()
    
    if region_info == "00":
        codeSql = "SELECT col_name,col_alt,col_lat,col_lon,col_code,col_type FROM myapp_col"
    else:
        country = region_info[0][0:2]
        departement = region_info[1]
        codeSql = "SELECT col_name,col_alt,col_lat,col_lon,col_code,col_type FROM myapp_col WHERE col_code like '%"+ country + "-"+ departement +"%'"
        
    cur.execute(codeSql)

    rows = cur.fetchall()
    
    myListeCols = []

    # col indexes
    col_name = 0
    col_alt = 1
    col_lat = 2 
    col_lon = 3
    col_code = 4
    col_type = 5

    for row in rows :                                      
        myCol = cols_tools.PointCol()
        myCol.name = row[col_name]
        myCol.alt = row[col_alt]
        myCol.lat = row[col_lat]        
        myCol.lon = row[col_lon]        
        myCol.col_code = row[col_code]
        myCol.col_type = row[col_type]        
        myListeCols.append(myCol)
                    
    return myListeCols    

#############################################################################
    
def insert_activity (conn, strava_user_id, strava_id, act_name, act_start_date, act_dist, act_den, act_type, act_time, act_power, act_status):
    try:
        cur = conn.cursor()
        sql = "INSERT INTO myapp_activity (strava_user_id, strava_id, act_name, act_start_date, act_dist, act_den, act_type, act_time, act_power, act_status) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)"
        value = (strava_user_id, strava_id, act_name, act_start_date, act_dist, act_den, act_type, act_time, act_power, act_status)
        
        cur.execute(sql, value)
        conn.commit()
        #print("Enregistrement inséré avec succès dans la table Activity")                
    except sqlite3.Error as error:
        print("Erreur lors de l'insertion dans la table Activity", error)
        
#############################################################################
#                               Delete                                      #    
#############################################################################        

def delete_activity(conn, strava_id):
    cur = conn.cursor()
    sql = 'DELETE FROM myapp_activity WHERE strava_id=?'    
    cur.execute(sql, (strava_id,))
    conn.commit()

def delete_col_perform(conn, strava_id):
    cur = conn.cursor()
    sql = 'DELETE FROM myapp_col_perform WHERE strava_id=?'    
    cur.execute(sql, (strava_id,))
    conn.commit()

def delete_activity_info(conn, strava_id):
    cur = conn.cursor()
    sql = 'DELETE FROM myapp_activity_info WHERE strava_id=?'    
    cur.execute(sql, (strava_id,))
    conn.commit()    

#############################################################################
    
def insert_col_perform(conn,act_id,rows):
    cur = conn.cursor()
    for row in rows :                 
        sql = "INSERT INTO myapp_col_perform (strava_id,col_code) VALUES (?, ?)"    
        value = (act_id, row)
        cur.execute(sql, value)
    conn.commit()      

#############################################################################

def compute_cols_by_act( conn, my_strava_user_id,myActivity_id):

    f_debug_trace("col_dbtools.py","compute_cols_by_act","Begin")  
                                
    perf = cp.objects.filter(strava_id=myActivity_id).values_list("col_code", flat=True)
                        
    for colCode in perf:        
        
        nbPassage = getActivitiesByCol(conn,my_strava_user_id,colCode)        
                
        exists = cc.objects.filter(col_code=colCode).filter(strava_user_id=my_strava_user_id).count()
                
        if exists==0:
            new_cc = cc()
            new_cc.col_code=colCode
            new_cc.col_count=1
            new_cc.strava_user_id=my_strava_user_id
            new_cc.save()            
            f_debug_trace("col_dbtools.py","compute_cols_by_act","Nouveau col: " + new_cc.get_col_name())            
            ### log new col
            my_Activity_info = Activity_info()
            my_Activity_info.strava_id = myActivity_id
            my_Activity_info.info_txt = "Nouveau col: " + new_cc.get_col_name()
            my_Activity_info.save()
        else:
            my_cc = cc.objects.filter(col_code=colCode, strava_user_id=my_strava_user_id)            
            upd_cc = my_cc[0]
            upd_cc.col_count=nbPassage
            upd_cc.save()
            f_debug_trace("col_dbtools.py","compute_cols_by_act","Col Franchis: " + upd_cc.get_col_name()+'('+str(nbPassage)+')')            

        lact = Activity.objects.filter(strava_id=myActivity_id)
        for act in lact:
            act.act_status = 1
            act.save()
                                           
def cols_effectue(conn, suid):

    cur = conn.cursor()
    cur.execute("select col_name, col_alt, col_count, C.col_code from myapp_col C , myapp_col_counter CC where C.col_code = CC.col_code and CC.strava_user_id = " + str(suid)+ " order by CC.col_count desc")
    rows = cur.fetchall()

    return rows

def getCol(conn,col_id):
    cur = conn.cursor()
    cur.execute("SELECT col_name,col_alt,col_lat,col_lon,col_code FROM myapp_col WHERE col_id = "+str(col_id))
    
    rows = cur.fetchall()
    
    myListeCols = []

    # col indexes
    col_name = 0
    col_alt = 1
    col_lat = 2 
    col_lon = 3
    col_code = 4

    for row in rows :                               
        myCol = cols_tools.PointCol()
        myCol.name = row[col_name]
        myCol.alt = row[col_alt]
        myCol.lat = row[col_lat]        
        myCol.lon = row[col_lon]        
        myCol.col_code = row[col_code]
        myListeCols.append(myCol)
                    
    return myListeCols   

###########################################################################################################

def getColByActivity(conn,strava_id):
    cur = conn.cursor()    
    cur.execute("select col_name,col_alt,col_lat,col_lon,P.col_code from myapp_col_perform P, myapp_col C where P.col_code = C.col_code and strava_id = "+str(strava_id))
        
    rows = cur.fetchall()
    
    myListeCols = []
    
    # col indexes
    col_name = 0
    col_alt = 1
    col_lat = 2 
    col_lon = 3
    col_code = 4

    for row in rows :                               
        myCol = cols_tools.PointCol()
        myCol.name = row[col_name]
        myCol.alt = row[col_alt]
        myCol.lat = row[col_lat]        
        myCol.lon = row[col_lon]        
        myCol.col_code = row[col_code]
        myListeCols.append(myCol)

        #print( myCol.name )
                    
    return myListeCols   
            
###########################################################################################################

def getActivitiesByCol(conn, strava_user_id, col_code):                
    cur = conn.cursor()        
    sqlExec = "select act_id from myapp_activity A, myapp_col_perform P where strava_user_id = "+strava_user_id+" and A.strava_id = P.strava_id and col_code = '"+col_code+"'"
        
    cur.execute(sqlExec)    
    rows = cur.fetchall()    
    myListActivities = 0
        
    for row in rows :                        
        #TODO -        
        myListActivities = myListActivities+1
                                    
    return myListActivities   

##########################################################################################################

def recompute_activity(strava_id, activities_df, strava_user):        
    f_debug_trace("col_dbtools.py","recompute_activity",SQLITE_PATH)    
    conn = create_connection(SQLITE_PATH)

    AllVisitedCols = []
    allCols = []
    myColsList = []
    myGPSPoints = []

    allCols=  select_all_cols(conn,"00")            
    
    for oneCol in allCols:               
        myCol = cols_tools.PointCol()
        myCol.setPoint(oneCol)        
        myColsList.append(myCol)
    
    for pl in activities_df['polylines']:
            if len(pl) > 0:                 
                for onePoint in pl:                    
                    myGPSPoints.append(onePoint)
    
    returnList = cols_tools.getColsVisited(myColsList,myGPSPoints)           
                    
    for ligne in returnList:                
        AllVisitedCols.append(ligne)            

    delete_col_perform(conn,strava_id)                
    insert_col_perform(conn,strava_id, AllVisitedCols)
    compute_cols_by_act(conn,strava_user,strava_id)  
    
    return 0
        
###########################################################################################################

def get_country_region(code_paysregion):    
    ### TODO PT 
    lPaysA = []    
    lPaysA.append("FR")
    lPaysA.append("IT")    
    codePays = code_paysregion[0:2] 
    if codePays in lPaysA:
        country = code_paysregion[0:2]+"A"
    else:
        country = code_paysregion[0:2]    

    region = code_paysregion[3:5]

    if f_debug_col():
        f_debug_trace("col_dbtools.py","country",country)
        f_debug_trace("col_dbtools.py","region",region)
        
    country_region = []
    country_region.append(country)
    country_region.append(region)    
    return country_region

###########################################################################################################

def get_country_from_code(code):        
    ### TODO PT 
    if code == "AR":
        code = "ARG"        
    return Country.objects.get(pk=code).country_name

###########################################################################################################

def get_region_from_code(codepays,coderegion):        
    ### TODO PT 
    if codepays == "AR":
        codepays = "ARG"                
    ret = "not found"
    lr = Region.objects.filter(country_code=codepays).filter(region_code=coderegion)
    for one_region in lr:
        ret =  one_region.region_name
    return ret

###########################################################################################################
    
def update_user_var(strava_user_id, country_code, region_code,now):        
    my_user_var_sq = User_var.objects.all().filter(strava_user_id = strava_user_id)

    for oneOk in my_user_var_sq:
            myUser_var = oneOk            
            if len(country_code):
                myUser_var.view_country_code = country_code
                myUser_var.view_region_code = region_code            
            if now > 0:
                myUser_var.last_update = now
            myUser_var.save()
           
###########################################################################################################            

def get_user_data_values(strava_user_id):        
    my_user_var_sq = User_var.objects.filter(strava_user_id = strava_user_id)        
    view_country_code = "FRA"
    view_region_code = "06"    
    for oneOk in my_user_var_sq:            
            myUser_var = oneOk
            view_country_code = myUser_var.view_country_code                                                           
            view_region_code = myUser_var.view_region_code                                                                                               
            last_update = myUser_var.last_update
    values_info = [view_country_code,view_region_code,last_update]     

    f_debug_trace('col_dbtools.py','get_user_data_values',values_info)

    return values_info

###########################################################################################################

def get_user_names(user):
    qs_user= User.objects.filter(username=user).values()
    myret = "Unknown User"
    for oneOk in qs_user:
        myret = oneOk["first_name"] +" " + oneOk["last_name"]                
    return myret

###########################################################################################################

def compute_all_month_stat(my_user_id: int):

    monthKeyList = []
    dayList = []
    bikeKm = {}
    bikeAscent = {}
    bikeTime = {}
    colsCount = {}    
    cols2000Count = {}
    topAlt = {}
                        
    millisecBegin = int(time.time() * 1000)        
    activities = Activity.objects.filter(strava_user_id = my_user_id)
    for oneActivity in activities:
        if oneActivity.act_type == "Run" or oneActivity.act_type == "Ride" or oneActivity.act_type == "Hike":            
            formatedDate = oneActivity.act_start_date.strftime("%Y%m")
            formatedDay = oneActivity.act_start_date.strftime("%Y%m%d")            
                        
            if formatedDay not in dayList: 
                dayList.append(formatedDay) 
            
            if formatedDate not in monthKeyList: 
                monthKeyList.append(formatedDate)                 

            if oneActivity.act_type == "Ride":                                
                if formatedDate in bikeKm: 
                    km = bikeKm[formatedDate] + round(oneActivity.act_dist/1000)
                    ascent = bikeAscent[formatedDate] + round(oneActivity.act_den)
                    thetime  = bikeTime[formatedDate] + oneActivity.act_time
                    bikeKm[formatedDate]= km 
                    bikeAscent[formatedDate] = ascent
                    bikeTime[formatedDate] = thetime                
                else:
                    bikeKm[formatedDate] = round(oneActivity.act_dist/1000)
                    bikeAscent[formatedDate] = round(oneActivity.act_den)
                    bikeTime[formatedDate] = oneActivity.act_time

            ### Et les Cols

            colsList = cp.objects.filter(strava_id = oneActivity.strava_id)                        
            for uncol in colsList:                
                detailListCol = Col.objects.filter(col_code = uncol.col_code)                                
                for leCol in detailListCol: 

                    altitude = leCol.col_alt

                    if formatedDate in colsCount:
                        colsCount[formatedDate] = colsCount[formatedDate] + 1                                                
                    else:
                        colsCount[formatedDate] = 1                        

                    if altitude >= 2000:                        
                        if formatedDate in cols2000Count:
                            cols2000Count[formatedDate] = cols2000Count[formatedDate] + 1
                        else:
                            cols2000Count[formatedDate] = 1

                    if formatedDate in topAlt:
                        if altitude > topAlt[formatedDate]:
                            topAlt[formatedDate] = altitude
                    else:
                        topAlt[formatedDate] = altitude                                
                            
    ### Pascours des listes construites
    myKm = 0
    myAsc = 0
    thetime = 0   
    nbc = 0         
    nb2000 = 0
    top = 0

                                                       
    for uniqueKey in monthKeyList:        
        if uniqueKey in  bikeKm:
            myKm = bikeKm[uniqueKey]
            myAsc = bikeAscent[uniqueKey]
            thetime = bikeTime[uniqueKey]                                    

        if uniqueKey in colsCount:            
            nbc = colsCount[uniqueKey]            
        
        if uniqueKey in cols2000Count:
            nb2000 = cols2000Count[uniqueKey]

        if uniqueKey in topAlt:
            top = topAlt[uniqueKey] 

        compute_month_stat(my_user_id,uniqueKey,dayList,myKm,myAsc,thetime,nbc,nb2000,top)

        myKm = 0
        myAsc = 0
        thetime = 0   
        nbc = 0         
        nb2000 = 0
        top = 0
                    
    millisecEnd = int(time.time() * 1000)

    f_debug_trace("col_db_tools.py","compute_all_month_stat",str(millisecEnd-millisecBegin)+" ms")
    
    return 1

###########################################################################################################

def compute_month_stat(stravaUserId,yyyy_mm,formatedDay,bikeKm,BikeAsc, bikeTime,colsCount,cols2000Count,topAlt):
    
    nbDays0n = cols_tools.get_dayson_in_month (yyyy_mm,formatedDay)    
    myStat = Month_stat.objects.filter(strava_user_id = stravaUserId, yearmonth = yyyy_mm)
    
    if len(myStat) > 0:
        for omeLine in myStat:
            omeLine.bike_km = bikeKm
            omeLine.bike_ascent = BikeAsc
            omeLine.bike_time = bikeTime
            omeLine.col2000_count = cols2000Count
            omeLine.col_count = colsCount
            omeLine.top_alt_col = topAlt
            omeLine.days_on = nbDays0n        
            omeLine.save()
    else:
            newLine = Month_stat()
            newLine.strava_user_id = stravaUserId
            newLine.yearmonth = yyyy_mm 
            newLine.bike_km = bikeKm
            newLine.bike_ascent = BikeAsc
            newLine.bike_time = bikeTime
            newLine.col2000_count = cols2000Count
            newLine.col_count = colsCount
            newLine.top_alt_col = topAlt
            newLine.days_on = nbDays0n        
            newLine.save()
    
    return 0

#####################################################################################

def set_col_count_list_this_year(strava_user_id):

    millisecBegin = int(time.time() * 1000)        
    
    f_debug_trace("col_dbtools.py","set_col_count_list_this_year",SQLITE_PATH)    
    conn = create_connection(SQLITE_PATH)

    currentDateTime = datetime.datetime.now()
    
    date = currentDateTime.date()
    year = date.strftime("%Y")+'-01-01'        

    cur = conn.cursor()            

    sqlExec = "select count(*) as compteur, col_code from myapp_col_perform P, myapp_activity A where P.strava_id = A.strava_id	and strava_user_id = "+strava_user_id+" and act_start_date > '"+year+"' group by col_code"

    f_debug_trace('set_col_count_list_this_year',sqlExec,str(year))
    cur.execute(sqlExec)    

    myListCompte = cur.fetchall()    

    nombre_de_passages = {}
    for one_col_y in myListCompte:        
        nombre_de_passages[one_col_y[1]] = one_col_y[0]

    for oneCount in cc.objects.filter(strava_user_id=strava_user_id):
        oneCount.year_col_count = nombre_de_passages.get(oneCount.col_code, 0)                
        oneCount.save()
                                        
    millisecMid = int(time.time() * 1000)

    f_debug_trace("col_db_tools.py","set_col_count_list_this_year - part 1 ",str(millisecMid-millisecBegin)+" ms")

    ###

    sqlExec2 =  "select max(act_start_date),col_code, A.act_id from myapp_col_perform C, myapp_activity A where A.strava_id = C.strava_id and strava_user_id = "+strava_user_id+" group by col_code"
    cur.execute(sqlExec2)    

    myListPass = cur.fetchall()    
    
    last_passages = {}
    last_passages_id = {}

    for one_passage in myListPass:                                                        
        last_passages[one_passage[1]] = one_passage[0]  # act_start_date
        last_passages_id[one_passage[1]] = one_passage[2]  # id activity
    
    for oneCount in cc.objects.filter(strava_user_id=strava_user_id):                                        
        act_id = last_passages_id.get(oneCount.col_code, None)                                      
        date_time_str = last_passages.get(oneCount.col_code, None)                                      
        if date_time_str != None:                    
            date_str = date_time_str[0:10]                                        
            date_object = datetime.datetime.strptime(date_str, '%Y-%m-%d')
            my_datetime = timezone.make_aware(date_object, timezone.get_current_timezone())
            oneCount.last_passage_date = my_datetime
            oneCount.last_act_id = act_id
            oneCount.save()
                                        
    millisecend = int(time.time() * 1000)

    f_debug_trace("col_db_tools.py","set_col_count_list_this_year - part 2",str(millisecend-millisecMid)+" ms")
        
    return 1

#######################################################################

def get_last_activity_more_than(strava_user_id, distance, dateFrom):
        
    txt_ret = "*** RECORD *** Plus longue Sortie **** Bravo ***"

    for one_act in Activity.objects.filter(strava_user_id=strava_user_id).order_by("-act_start_date"):
        if one_act.act_type == "Ride":
            if one_act.act_dist > distance: 
                laDate1 = datetime.datetime.strptime(dateFrom, '%Y-%m-%d')
                laDateStr = one_act.act_start_date.strftime("%Y-%m-%d %H:%M:%S")            
                laDate2 = datetime.datetime.strptime(laDateStr, '%Y-%m-%d %H:%M:%S')            
                if laDate2 < laDate1:                
                    txt_ret = 'Plus longue sortie depuis "' + one_act.act_name + '" le '
                    txt_ret += str(one_act.act_start_date.day) + "/" + str(one_act.act_start_date.month) + "/" + str(one_act.act_start_date.year) + ' ( '
                    txt_ret += str(one_act.act_dist/1000) + ' Km )'

                    f_debug_trace("col_db_tools.py","get_last_activity_more_than",txt_ret) 
                
                    break

    return txt_ret

#######################################################################

def get_last_activity_den_than(strava_user_id, deniv,dateFrom):

    txt_ret = "*** RECORD *** Plus gros denivelé **** Bravo ***"

    for one_act in Activity.objects.filter(strava_user_id=strava_user_id).order_by("-act_start_date"):
        if one_act.act_type == "Ride":            
            if one_act.act_den > deniv: 
                laDate1 = datetime.datetime.strptime(dateFrom, '%Y-%m-%d')
                laDateStr = one_act.act_start_date.strftime("%Y-%m-%d %H:%M:%S")            
                laDate2 = datetime.datetime.strptime(laDateStr, '%Y-%m-%d %H:%M:%S')            
                if laDate2 < laDate1:                
                    txt_ret = 'Plus gros denivellé depuis "' + one_act.act_name + '" le '
                    txt_ret += str(one_act.act_start_date.day) + "/" + str(one_act.act_start_date.month) + "/" + str(one_act.act_start_date.year)+ ' ( '
                    txt_ret += str(one_act.act_den) + ' m )'

                    f_debug_trace("col_db_tools.py","get_last_activity_den_than",txt_ret) 
                
                    break

    return txt_ret

#######################################################################

def get_last_speed_activity( strava_user_id,distance,duree,dateFrom):

    vitesse = format(distance/duree*3.6,'.1f')
    txt_ret = str(vitesse) +" Km/h >>> " 
    txt_ret += "*** RECORD *** La plus rapide **** Bravo ***"
    for one_act in Activity.objects.filter(strava_user_id=strava_user_id).order_by("-act_start_date"):        
        if one_act.act_type == "Ride":            
            laDate1 = datetime.datetime.strptime(dateFrom, '%Y-%m-%d')
            laDateStr = one_act.act_start_date.strftime("%Y-%m-%d %H:%M:%S")            
            laDate2 = datetime.datetime.strptime(laDateStr, '%Y-%m-%d %H:%M:%S')            
            if laDate2 < laDate1:                
                if one_act.act_dist/one_act.act_time*3.6 > distance/duree*3.6: 
                    txt_ret = str(vitesse) +" Km/h - " 
                    txt_ret += 'La plus rapide depuis "' + one_act.act_name + '" le '
                    txt_ret += str(one_act.act_start_date.day) + "/" + str(one_act.act_start_date.month) + "/" + str(one_act.act_start_date.year)+ ' ( '
                    txt_ret += str(format(one_act.act_dist/one_act.act_time*3.6,'.1f')) + ' Km/h )'

                    f_debug_trace("col_db_tools.py","get_last_speed_activity",txt_ret) 
                
                    break
      
    return txt_ret


#####################################################

def all_users_stat():
    all_users = Strava_user.objects.values()
    for un_user in all_users:                
        strava_user_Id = un_user['strava_user_id']                        
        udsq = User_dashboard.objects.filter(strava_user_id=strava_user_Id)
        for i in udsq:
            print(i.col_count)
            print(i.col2000_count)
            print(i.bike_year_km)
            print(i.run_year_km)
    return all_users
