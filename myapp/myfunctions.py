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
    basée de manière stable sur un mot avec une bonne distinction visuelle.
    """

    # Palette de couleurs bien espacées pour les utilisateurs (HSV format)
    # Chaque couleur est séparée d'environ 60 degrés en teinte

    palette_colors = [
        (0.0, 0.85, 0.95),    # Rouge vif
        (0.15, 0.85, 0.95),   # Jaune-orange
        (0.30, 0.85, 0.95),   # Jaune        
        (0.60, 0.85, 0.95),   # Cyan
        (0.75, 0.85, 0.95),   # Bleu
        (0.90, 0.85, 0.95),   # Magenta
        (0.05, 0.70, 0.90),   # Rouge-orange foncé
        (0.20, 0.70, 0.90),   # Vert foncé
        (0.35, 0.70, 0.90),   # Bleu-vert foncé
        (0.50, 0.70, 0.90),   # Bleu foncé
        (0.65, 0.70, 0.90),   # Violet foncé
        (0.80, 0.70, 0.90),   # Rose foncé
        (0.45, 0.85, 0.95),   # Vert citron
    ]
   
    # Hash stable du mot
    h = int(hashlib.md5(mot.encode("utf-8")).hexdigest(), 16)
   
    # Sélectionner une couleur de la palette basée sur le hash
    index = h % len(palette_colors)
    hue, saturation, value = palette_colors[index]   
    r, g, b = colorsys.hsv_to_rgb(hue, saturation, value)

    return (r, g, b)

