from django.db import models


class UserViewRegion(models.Model):
    strava_user_id = models.BigIntegerField(unique=True)
    country_code = models.CharField(max_length=3)
    region_code = models.CharField(max_length=10)
    updated_at = models.DateTimeField(auto_now=True)


class SegmentEffort(models.Model):
    effort_id = models.BigIntegerField(unique=True)
    strava_user_id = models.BigIntegerField(db_index=True)
    strava_activity_id = models.BigIntegerField(db_index=True)
    segment_id = models.BigIntegerField(db_index=True)
    segment_name = models.CharField(max_length=255)
    start_date = models.DateTimeField()
    elapsed_time = models.PositiveIntegerField()
    vam = models.IntegerField(null=True, blank=True)

    class Meta:
        ordering = ['start_date', 'effort_id']
