from datetime import datetime
import sqlite3
import io

conn = sqlite3.connect('db.sqlite3')  

mynow = str(datetime.now())
#print(mynow)

filename = mynow[0:4]+mynow[5:7]+mynow[8:10]+".sql"
 #print(filename)

# Open() function  

with io.open(filename,'w',encoding='UTF-8') as p:  
    # iterdump() function
    for line in conn.iterdump():           
        p.write('%s\n' % line)
     
    print(' Backup performed successfully!')
print(' Data Saved as backupdatabase_dump.sql')
 
conn.close()