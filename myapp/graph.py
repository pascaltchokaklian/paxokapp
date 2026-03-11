import matplotlib.pyplot as plt
import base64
from io import BytesIO
import heapq

from myapp.myfunctions import couleur_depuis_mot

def top_10_biggest(numbers):
    return heapq.nlargest(10, numbers)

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