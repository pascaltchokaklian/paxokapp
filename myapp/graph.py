import math
from matplotlib.pylab import cos, radians, sin
import matplotlib.pyplot as plt
import base64
from io import BytesIO
import heapq

from myapp.myfunctions import couleur_depuis_mot

def top_10_biggest(numbers):
    return heapq.nlargest(10, numbers)

def haversine_distance(lat1, lon1, lat2, lon2):
    """
    Calcule la distance en km entre deux points GPS en utilisant la formule Haversine
    """
    lat1, lon1, lat2, lon2 = map(radians, [lat1, lon1, lat2, lon2])
    
    dlat = lat2 - lat1
    dlon = lon2 - lon1
    a = math.sin(dlat/2)**2 + math.cos(lat1) * math.cos(lat2) * math.sin(dlon/2)**2
    c = 2 * math.asin(math.sqrt(a))
    r = 6371  # Rayon terrestre en km
    
    return c * r

def get_altitude_profile_graph(decoded_polyline, total_elevation=None, total_distance=None):
    """
    Crée un graphique de profil d'altitudes à partir d'une polyline décodée
    decoded_polyline: liste de tuples (lat, lon) ou (lat, lon, elevation)
    total_elevation: dénivelé total en mètres (optionnel)
    total_distance: distance totale en km (optionnel)
    """
    
    if not decoded_polyline or len(decoded_polyline) == 0:
        return None
        
    plt.switch_backend('AGG')
    fig, ax = plt.subplots(figsize=(12, 5))  # Réduit de (14,6) à (12,5)
    
    distances = [0]  # Distance cumulée
    elevations = []
    
    total_dist = 0
    has_elevation_data = False
    
    # Vérifier si les points ont les altitudes (tuples de 3 éléments)
    if len(decoded_polyline[0]) >= 3:
        has_elevation_data = True
    
    # Extraire les altitudes et calculer les distances cumulées
    for i, point in enumerate(decoded_polyline):
        if len(point) >= 3:
            elevation = point[2]
        else:
            # Pas d'altitude disponible dans la polyline
            elevation = 0
        
        elevations.append(elevation)
        
        if i > 0:
            prev_point = decoded_polyline[i-1]
            lat1, lon1 = prev_point[0], prev_point[1]
            lat2, lon2 = point[0], point[1]
            
            dist = haversine_distance(lat1, lon1, lat2, lon2)
            total_dist += dist
            distances.append(total_dist)
        elif i == 0 and len(decoded_polyline) > 1:
            distances.append(0)
    
    # Créer le graphique
    if len(distances) > 1:
        # S'assurer que les listes ont la même taille
        min_len = min(len(distances), len(elevations))
        distances = distances[:min_len]
        elevations = elevations[:min_len]
        
        if has_elevation_data and any(e != 0 for e in elevations):
            # Sous-échantillonnage pour optimiser les performances
            max_points = 1000
            if len(distances) > max_points:
                step = len(distances) // max_points
                distances_sampled = distances[::step]
                elevations_sampled = elevations[::step]
                # S'assurer que le dernier point est inclus
                if distances[-1] != distances_sampled[-1]:
                    distances_sampled.append(distances[-1])
                    elevations_sampled.append(elevations[-1])
            else:
                distances_sampled = distances
                elevations_sampled = elevations
            
            # Données d'altitude disponibles
            try:
                # Tracer la ligne en noir ou gris
                ax.plot(distances_sampled, elevations_sampled, color='black', linewidth=1.5)
                
                # Grouper les segments par couleur pour optimiser
                current_color = None
                start_idx = 0
                
                for i in range(1, len(distances_sampled)):
                    dist_diff = distances_sampled[i] - distances_sampled[i-1]
                    elev_diff = elevations_sampled[i] - elevations_sampled[i-1]
                    slope = elev_diff / dist_diff if dist_diff > 0 else 0
                    
                    color = 'red' if slope > 0.001 else 'steelblue'
                    
                    if color != current_color:
                        # Fin de la plage précédente
                        if current_color is not None:
                            ax.fill_between(distances_sampled[start_idx:i], 
                                           elevations_sampled[start_idx:i], 
                                           0, color=current_color, alpha=0.7)
                        # Début de nouvelle plage
                        current_color = color
                        start_idx = i-1
                
                # Dernière plage
                if current_color is not None:
                    ax.fill_between(distances_sampled[start_idx:], 
                                   elevations_sampled[start_idx:], 
                                   0, color=current_color, alpha=0.7)
                
                ax.set_ylabel('Altitude (m)', fontsize=12)
            except Exception as e:
                print(f"Error in altitude graph: {e}")
                # En cas d'erreur, revenir au graphique simple
                ax.plot(distances, elevations, color='steelblue', linewidth=2.5)
                ax.fill_between(distances, elevations, alpha=0.3, color='steelblue')
                ax.set_ylabel('Altitude (m)', fontsize=12)
        else:
            # Pas de données d'altitude précises, créer un graphique avec le dénivelé total
            if total_elevation and total_elevation > 0:
                # Créer un profil approximatif basé sur le dénivelé total
                avg_gradient = total_elevation / total_dist if total_dist > 0 else 0
                approx_elevations = [i * avg_gradient for i in range(len(distances))]
                ax.plot(distances, approx_elevations, color='lightblue', linewidth=2, linestyle='--', label='Profil estimé')
                ax.fill_between(distances, approx_elevations, alpha=0.2, color='lightblue')
                ax.set_ylabel('Altitude (m - estimée)', fontsize=12)
                ax.legend()
            else:
                # Afficher simplement la distance
                ax.plot(distances, [0] * len(distances), color='gray', linewidth=1)
                ax.set_ylabel('Distance (km)', fontsize=12)
        
        ax.set_xlabel('Distance (km)', fontsize=12)
        ax.set_title('Profil d\'altitudes', fontsize=14, fontweight='bold')
        ax.grid(True, alpha=0.3)
        fig.tight_layout()
        
        # Sauvegarder le graphique en base64
        buffer = BytesIO()
        fig.savefig(buffer, format='png')
        buffer.seek(0)
        image_png = buffer.getvalue()
        graph = base64.b64encode(image_png)
        graph = graph.decode('utf-8')
        buffer.close()
        
        plt.close(fig)
        return graph
    
    plt.close(fig)
    return None





def get_graph():
    buffer = BytesIO()
    plt.savefig(buffer, format= 'png')
    buffer.seek(0)
    image_png = buffer.getvalue()
    graph = base64.b64encode(image_png)   
    graph = graph.decode('utf-8')    
    buffer.close()
    return graph

### get_plot

def get_plot(x,y,n):

    tsize=len(x)     
    top10Km = top_10_biggest(x)
    top10Watt = top_10_biggest(y)

    plt.switch_backend('AGG')    
    plt.figure(figsize=(15,8))
    plt.title('Mes Puissances')

    mycolor = []
    
    # Last 10 rides    
    for indice in range(len(x)):                
        if indice> tsize-10:
            mycolor.append('green')
        else:
            mycolor.append('blue')                

    plt.scatter(x, y, color=mycolor)
                
    for i, txt in enumerate(n):

        # text sur les 10 dernieres
        if i>tsize-10:
            plt.annotate(txt, (x[i], y[i]))

        # text sur les meilleures puissances         

        mySize = len(top10Watt)
        
        if mySize>10:
            mySize=10

        if y[i] >= top10Watt[mySize-1]:
            plt.annotate(txt, (x[i], y[i]))

        # text sur les plus longues        
        if x[i] >= top10Km[mySize-1]:
            plt.annotate(txt, (x[i], y[i]))            
    
    plt.xlabel('Distance (Km)')
    plt.ylabel('Puissance (Watt)') 
    plt.tight_layout()
    graph = get_graph()

    return graph

### get_plot_all

def get_plot_all(x,y,n):
                     
    plt.switch_backend('AGG')    
    plt.figure(figsize=(15,8))
    plt.title('Puissances Equipe vélo')            

    # determine a color for each point based on the user name
    colors = []    
    for name in n:
        colors.append(couleur_depuis_mot(name))            

    plt.scatter(x, y, color=colors)

    # build a legend mapping each unique name to its color
    unique = {}
    for name, color in zip(n, colors):
        if name not in unique:
            unique[name] = color

    if unique:
        from matplotlib.lines import Line2D
        handles = [Line2D([0],[0], marker='o', color='w', markerfacecolor=c, markersize=8)
                   for c in unique.values()]
        labels = list(unique.keys())
        # place legend below the axes, spanning the width
        plt.legend(handles, labels, title='Utilisateur', loc='upper center',
                   bbox_to_anchor=(0.5, -0.15), ncol=min(5, len(labels)))

    # annotations removed; colors are explained by legend
    plt.xlabel('Distance (Km)')
    plt.ylabel('Puissance (Watt)') 
    plt.tight_layout()

    graph = get_graph()

    return graph