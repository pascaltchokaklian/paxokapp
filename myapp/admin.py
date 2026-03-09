from django.contrib import admin
from .models import Activity

# Register your models here.

@admin.register(Activity)
class ActivityAdmin(admin.ModelAdmin):
    list_display = (
        'act_id', 'act_name', 'act_start_date', 'act_dist',
        'act_den', 'act_normal_power', 'act_type', 'act_trainer'
    )
    list_filter = ('act_type', 'act_trainer')
    search_fields = ('act_name',)
