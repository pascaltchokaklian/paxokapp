from django.db import models


class UserViewRegion(models.Model):
    strava_user_id = models.BigIntegerField(unique=True)
    country_code = models.CharField(max_length=3)
    region_code = models.CharField(max_length=10)
    updated_at = models.DateTimeField(auto_now=True)
