import datetime
from datetime import date
import os

# Chemin du répertoire que vous souhaitez explorer
chemin = './backup'

# Obtenir la liste de tous les fichiers et dossiers
contenu = os.listdir(chemin)

# Afficher le contenu
for element in contenu:
    annee=element[0:4]
    mois=element[4:6]
    jour=element[6:8]
        
    myDate = datetime.date(int(annee),int(mois),int(jour)) 
    aujourdhui = date.today()
    diff = (aujourdhui - myDate).days
        
    if diff>30:
        print(element)
        print(diff)
        os.remove(chemin+'/'+element)