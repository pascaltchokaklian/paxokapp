import hashlib
import colorsys

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

def premieres_lettres(chaine):
    mots = chaine.split('-')
    return ''.join(mot[0] for mot in mots if mot)

def couleur_depuis_mot(mot):
    """
    Retourne une couleur RGB (format matplotlib : valeurs entre 0 et 1)
    basée de manière stable sur un mot.
    """
    # Hash stable
    h = int(hashlib.md5(mot.encode("utf-8")).hexdigest(), 16)

    # Teinte basée sur le hash (0 → 1)
    hue = (h % 360) / 360.0

    # Paramètres ajustables
    saturation = 0.65
    value = 0.85

    r, g, b = colorsys.hsv_to_rgb(hue, saturation, value)
    return (r, g, b)

