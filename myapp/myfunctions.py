def get_pr_by_year(listePerformance):                     
    all=[]
    bestYear=[]
    for onePerf in listePerformance:        
        my_year=onePerf.perf_date.year        
        myChrono = onePerf.perf_chrono
        all.append([my_year,myChrono])            
    
    return all

def get_chrono_str(myTime):				
		secondes = myTime
		sHeure = "0"
		sMinutes  = "00"
		sSecondes = "00"		
		heures = int(secondes/3600)
		if heures>0:
			sHeure = str(heures)
			secondes = secondes - heures*3600
		minutes = int(secondes/60)		
		if minutes>0:			
			sMinutes = "{:02d}".format(minutes)	 		
			secondes = secondes - minutes*60
		sSecondes = "{:02d}".format(secondes)	 		
		hms = sHeure+":"+sMinutes+":"+sSecondes
		return hms		



