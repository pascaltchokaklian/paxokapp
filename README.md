# tchok.com

Portail responsive servi par Django, conçu pour regrouper plusieurs applications Python.

## Ajouter ou modifier une application

Ouvrez `portal/static/portal/apps.js` et modifiez `window.PORTAL_APPS`. Chaque entrée comporte :

- `id` : identifiant unique ;
- `name` : nom affiché ;
- `description` : résumé court ;
- `url` : adresse accessible depuis le navigateur ;
- `category` : catégorie affichée ;
- `icon` : texte court dans l’icône ;
- `image` (facultatif) : chemin d’une image dans les fichiers statiques, affichée à la place du texte ;
- `color` : `mint`, `peach`, `lavender`, `blue` ou `yellow`.

La page d’accueil affiche la carte des cols, filtrable par pays puis par département/région. La liste des applications est accessible sur `/applications/`; la fiche Cent Cols y renvoie vers cette même carte. Les deux autres entrées restent des exemples pointant vers `localhost:8502` et `8503`.

Le bandeau de la page Applications demande d’abord l’autorisation du navigateur pour utiliser la position de l’appareil. Les coordonnées sont envoyées à Open-Meteo pour la prévision et à Nominatim/OpenStreetMap pour afficher le nom du lieu; ce dernier est mémorisé dans l’onglet pendant 24 heures. Si l’autorisation est refusée ou indisponible, la météo utilise une localisation IP approximative : l’IP est transmise à `ipapi.co`, puis les coordonnées à Open-Meteo. Le widget crédite OpenStreetMap.

## Lancer le portail Django

XokaMap est accessible depuis le portail sur `/xokamap/`.

Dans Strava+, l’onglet Dashboard présente les cols franchis, les distances annuelles et les totaux vélo des 28 derniers jours, ainsi que les performances sur segments cyclistes. Les distances vélo utilisent les activités de type `Ride` comme dans l’application modèle. La liste est filtrable et triable ; chaque segment ouvre l’historique des meilleurs temps par année.

L’onglet Puissances affiche les puissances normalisées strictement positives des activités vélo enregistrées dans la base, sans recalcul ni import supplémentaire.

Créez un environnement virtuel, installez Django dedans, puis démarrez le portail sur le port 8080 :

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe manage.py migrate
.\.venv\Scripts\python.exe manage.py runserver 127.0.0.1:8080
```

Ouvrez ensuite <http://127.0.0.1:8080>.

Le serveur du portail lit la base Cent Cols en mode SQLite lecture seule. Par défaut, il utilise `C:\Users\pasca\Dev\python\centcols\paxokapp\db.sqlite3`. Pour sélectionner une autre copie, définissez `CENTCOLS_DB_PATH` avant de lancer Django.

La connexion Strava utilise OAuth. Définissez `STRAVA_CLIENT_ID` et `STRAVA_CLIENT_SECRET` dans l’environnement, puis appliquez les migrations Django. Déclarez cette URL de callback dans la configuration de l’application Strava : `http://127.0.0.1:8080/oauth/complete/strava/`. Après connexion, l’ID de l’athlète est enregistré en session et sert à afficher ses cols franchis en vert. Le portail demande uniquement l’accès `read` nécessaire à l’identification.

Pour un déploiement, définissez `DJANGO_SECRET_KEY`, `DJANGO_DEBUG=false` et `DJANGO_ALLOWED_HOSTS` dans l’environnement du serveur.

## Affichage intégré

Les applications sont chargées dans une iframe. Le portail autorise l’intégration de ses pages de même origine; les applications externes peuvent néanmoins interdire cet affichage avec leurs en-têtes `X-Frame-Options` ou `Content-Security-Policy`. Dans ce cas, le bouton « Ouvrir dans un nouvel onglet » reste disponible. Si le portail est servi en HTTPS, les applications intégrées doivent également être accessibles en HTTPS, car les navigateurs bloquent généralement le contenu HTTP mixte.

Le fond de carte utilise les tuiles d’[OpenStreetMap.de](https://www.openstreetmap.de/); une connexion internet est nécessaire.
