import datetime
from multiprocessing import context
from django import template
from django.template.defaultfilters import stringfilter

register = template.Library()

def the_month(str_value):
    return str_value[-2:]

def the_year(str_value):
    return str_value[:4]

### First Strava Year ###

@register.filter
def get_first_year(allitems):
    for i in allitems:
        print(the_year(i[0]))
        break
    return int(the_year(i[0]))

### Current Year ###
def get_current_year():
    currentDateTime = datetime.datetime.now()
    date = currentDateTime.date()
    year = date.strftime("%Y")    
    return int(year)

### Year Loop
@register.filter
def get_all_year(yfirst):
    ly = []
    all = get_current_year()-yfirst 
    i = 0
    while i<=all:        
        year=yfirst+i 
        ly.append(year)        
        i+=1
    return ly

### Month Loop
@register.filter
def get_all_monthes(m):
    lm = []    
    i = 0
    while i<12:        
        i+=1
        if i>9:
            lm.append(str(i))
        else:
            istr = "0"+str(i)
            lm.append(str(istr))

    return lm

### Get VAM Value 
@register.filter
def get_vam(cle,liste):        
    return liste.get(cle,"")

### Rebuiding the key
@register.filter
def makekey(arg1, arg2):    
    return str(arg1) +"-"+ str(arg2)


