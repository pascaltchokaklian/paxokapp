from django.db import models
from .vars import display_year_month

# Create your models here.

class Country(models.Model):			
	country_code = models.CharField(max_length=3, primary_key=True)
	country_name = models.CharField(max_length=50)
	country_lat = models.FloatField(null=True)
	country_lon = models.FloatField(null=True)
	code_100cols = models.CharField(max_length=3, null = True)

class Region(models.Model):			
	region_id = models.IntegerField(auto_created=True,  primary_key=True)
	region_name = models.CharField(max_length=50)
	region_code = models.CharField(max_length=50,null=True, default="")
	country_code = models.CharField(max_length=3, null=False, default="")	
	region_lat = models.FloatField(null=True)
	region_lon = models.FloatField(null=True)	
	
class Col(models.Model):		
	col_id = models.IntegerField(auto_created=True,  primary_key=True)
	col_name = models.CharField(max_length=200)
	col_code = models.CharField(max_length=20, null=True, unique=True)
	col_alt = models.IntegerField(null=True)	
	col_lat = models.FloatField(null=True)
	col_lon = models.FloatField(null=True)
	col_type = models.CharField(max_length=10, null= True)	

	def get_activities_passed(self):
		sc = self.col_code		
		q1 = Col_perform.objects.filter(col_code=sc)		
		return q1
	
class Activity(models.Model):
	act_id = models.IntegerField(null=False, primary_key=True)	
	strava_id = models.IntegerField(null=False, default=0)	
	strava_user_id	= models.IntegerField(null=False)	
	act_name = models.CharField(max_length=200, null=True, default="")
	act_start_date = models.DateTimeField(null=False)
	act_dist = models.FloatField(null=True)
	act_den =  models.IntegerField(null=True)
	act_type = models.CharField(max_length=10, null= True)
	act_time = models.IntegerField(null=True)	
	act_power = models.IntegerField(null=True)
	act_status = models.IntegerField(null=True)

	def get_act_dist_km(self):
		return self.act_dist/1000
	
	def get_col_passed(self):
		sc = self.strava_id		
		q1 = Col_perform.objects.filter(strava_id=sc)
		return q1
						
class Col_perform(models.Model):
	col_perf_id = models.IntegerField(auto_created=True,  primary_key=True)
	col_code = models.CharField(max_length=20, null=False, default="-" )
	strava_id = models.IntegerField(null=False)	### id activity

	class Meta:
		ordering = ['-strava_id']

	def get_col_name(self):		
		sc = self.col_code
		q1 = Col.objects.filter(col_code=sc)		
		return q1[0].col_name
	
	def get_col_id(self):		
		sc = self.col_code
		q1 = Col.objects.filter(col_code=sc)		
		return q1[0].col_id
			
class Col_counter(models.Model):
	col_count_id = models.IntegerField(auto_created=True,  primary_key=True)
	col_code = models.CharField(max_length=20, default="-")
	strava_user_id	= models.IntegerField(null=False)
	col_count = models.IntegerField(null=False)	
	year_col_count = models.IntegerField(null=False, default=0)	
	last_passage_date = models.DateTimeField(null=True)
	last_act_id = models.IntegerField(null=True)

	def get_col_name(self):		
		sc = self.col_code
		q1 = Col.objects.filter(col_code=sc)		
		return q1[0].col_name
	
	def get_col_id(self):		
		sc = self.col_code
		q1 = Col.objects.filter(col_code=sc)				
		return q1[0].col_id
	
	def get_col_alt(self):		
		sc = self.col_code
		q1 = Col.objects.filter(col_code=sc)		
		return q1[0].col_alt
		
	def get_country_name(self):		
		sc = self.col_code[0:2]			
		q1 = Country.objects.filter(code_100cols=sc)		
		return q1[0].country_name
	
	def get_region_name(self):		
		sc = self.col_code[0:2]				
		q1 = Country.objects.filter(code_100cols=sc)				
		country_code = q1[0].country_code		
		rc = self.col_code[3:5]
		#TODO
		if country_code == "ARG":
			rc = self.col_code[3:4]
		q2 = Region.objects.filter(country_code=country_code).filter(region_code=rc)
		region_name = "Not Found"
		for one in q2:
			region_name = one.region_name
		return region_name
	
	def get_country_region_code(self):		
		sc = self.col_code[0:5]						
		return sc
								
class Strava_user(models.Model):	
	id = models.IntegerField(auto_created=True,  primary_key=True)
	strava_user_id = models.IntegerField(null=True)
	strava_user = models.CharField(max_length=100, default="-") 
	first_name = models.CharField(max_length=100, default="-")
	last_name = models.CharField(max_length=100, default="-")
	token_type = models.CharField(max_length=100, default="-")
	access_token = models.CharField(max_length=100, default="-")
	refresh_token = models.CharField(max_length=100, default="-")
	expire_at = models.IntegerField(null=True)
	city = models.CharField(max_length=50, null=True)
	country = models.CharField(max_length=50, null=True)
	sex = models.CharField(max_length=100, null=True)

class Segment(models.Model):	
	segment_id = models.IntegerField(auto_created=True,  primary_key=True)
	strava_segment_id= models.IntegerField(null=True)
	activity_type = models.CharField(max_length=20, default="-")
	segment_name = models.CharField(max_length=100, default="-")
	slope =  models.FloatField(null=True)
	lenght = models.FloatField(null=True)
	ascent = models.FloatField(null=True)

class Perform(models.Model):
	perform_id = models.IntegerField(auto_created=True,  primary_key=True)
	strava_perf_id = models.IntegerField(null=True)
	segment_id = models.IntegerField(null=False)		
	strava_user_id = models.IntegerField(null=True)
	perf_date = models.DateTimeField(null=False)
	perf_chrono = models.IntegerField(null=False)
	perf_vam = models.IntegerField(null=False)
	perf_fc = models.IntegerField(null=False)
	perf_fcmax = models.IntegerField(null=False)

	def get_segment_name(self):		
		sid = self.segment_id
		q1 = Segment.objects.filter(segment_id=sid)		
		return q1[0].segment_name
	
	def get_segment_length(self):		
		sid = self.segment_id
		q1 = Segment.objects.filter(segment_id=sid)		
		return q1[0].lenght
	
	def get_segment_slope(self):		
		sid = self.segment_id
		q1 = Segment.objects.filter(segment_id=sid)		
		return q1[0].slope	
		
	def get_chrono_str(self):		
		secondes = self.perf_chrono
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

class User_var(models.Model):				
	id = models.IntegerField(auto_created=True,  primary_key=True)			
	strava_user_id = models.IntegerField(null=True)
	view_country_code = models.CharField(max_length=20, default="FRA")
	view_region_code = models.CharField(max_length=20, default="06")
	last_update = models.IntegerField(null=True)

class User_dashboard(models.Model):			
	id = models.IntegerField(auto_created=True,  primary_key=True)		
	strava_user_id = models.IntegerField(null=True)
	col_count = models.IntegerField(null=True)
	col2000_count = models.IntegerField(null=True)
	bike_year_km  = models.IntegerField(null=True)
	run_year_km  = models.IntegerField(null=True)

	def set_col_count(self):	
		nbCols = Col_counter.objects.filter(strava_user_id=self.strava_user_id).count()				
		# DB save		
		self.col_count = nbCols
		self.save()
		return nbCols
	
	def set_col2000_count(self):	
		## All Col Counter 		
		lcc = Col_counter.objects.filter(strava_user_id=self.strava_user_id)
		listeCC = []
		for one_cc in lcc:
			listeCC.append(one_cc.col_code)

		## All 2000  Cols
		q2000 = Col.objects.filter(col_alt__gt=1999)			
		liste2000 = []
		for one2000 in q2000:
			liste2000.append(one2000.col_code)

		### Intersection:
		passed2000 = [value for value in liste2000 if value in listeCC]    	
		nbCols2000 = len(passed2000)
		
		# DB save
		self.col2000_count = nbCols2000
		self.save()
		return nbCols2000
	
	def set_bike_year_km(self):	
		## All Activities 		
		
		lActivity = Activity.objects.filter(strava_user_id=self.strava_user_id).filter(act_start_date__gt="2024-01-01").filter(act_type="Ride")		
		distance_BY = 0		
		for one_act in lActivity:			
			distance_BY = distance_BY + one_act.act_dist/1000			
		
		self.bike_year_km = int(distance_BY)
		self.save()
				
		return self.bike_year_km
	
	def set_run_year_km(self):	
		## All Activities 		
		
		lActivity = Activity.objects.filter(strava_user_id=self.strava_user_id).filter(act_start_date__gt="2024-01-01").filter(act_type="Run")				
		distance_RY = 0
		for one_act in lActivity:
			distance_RY = distance_RY + one_act.act_dist/1000
					
		self.run_year_km = int(distance_RY)
		self.save()
				
		return self.run_year_km
	
class Month_stat(models.Model):					
	month_stat_id = models.IntegerField(auto_created=True,  primary_key=True)
	strava_user_id = models.IntegerField(null=True)
	yearmonth = models.CharField(max_length=6, default="190000")
	days_on = models.IntegerField(null=True)
	bike_km = models.IntegerField(null=True)
	bike_ascent = models.IntegerField(null=True)
	bike_time = models.IntegerField(null=True)
	col_count = models.IntegerField(null=True)
	col2000_count = models.IntegerField(null=True)
	top_alt_col = models.IntegerField(null=True)
	
	def yearmonth_html(self):
		annee = self.yearmonth[0:4]
		mois = int(self.yearmonth[4:])		
		mois_str = display_year_month(mois) 
		return  mois_str + " " + annee
	
	def get_chrono_str(self):		
		secondes = self.bike_time
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
		hms = sHeure+"h"+sMinutes
		return hms		
	
class Activity_info(models.Model):
	act_info_id = models.IntegerField(auto_created=True,  primary_key=True)
	act_id = models.IntegerField(null=True)
	info_txt = models.CharField(max_length=100, default="***")


	
