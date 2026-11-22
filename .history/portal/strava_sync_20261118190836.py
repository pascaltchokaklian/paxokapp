import logging
import sqlite3
import time

import requests
from django.conf import settings
from social_django.utils import load_strategy

from .map_data import _parse_database_datetime


logger = logging.getLogger(__name__)

ACTIVITIES_URL = 'https://www.strava.com/api/v3/athlete/activities'
ONE_DAY_SECONDS = 86400


def _access_token(social_auth):
    if float(social_auth.extra_data.get('expires', 0)) <= time.time() + 60:
        social_auth.refresh_token(load_strategy())
        social_auth.refresh_from_db()
    return social_auth.extra_data['access_token']


def _latest_start_timestamp(connection, strava_user_id):
    row = connection.execute(
        'SELECT MAX(act_start_date) FROM myapp_activity WHERE strava_user_id = ?',
        (strava_user_id,),
    ).fetchone()
    parsed = _parse_database_datetime(row[0])
    return int(parsed.timestamp()) if parsed else None


def _store_new_activity(connection, strava_user_id, activity):
    strava_id = int(activity['id'])
    exists = connection.execute(
        'SELECT 1 FROM myapp_activity WHERE strava_id = ?',
        (strava_id,),
    ).fetchone()
    if exists:
        return False

    connection.execute(
        'INSERT INTO myapp_activity (strava_user_id, strava_id, act_name, act_start_date, '
        'act_dist, act_den, act_type, act_time, act_power, act_status, act_normal_power, act_trainer) '
        'VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)',
        (
            strava_user_id,
            strava_id,
            activity.get('name'),
            activity.get('start_date'),
            activity.get('distance'),
            activity.get('total_elevation_gain'),
            activity.get('sport_type'),
            activity.get('moving_time'),
            activity.get('average_watts'),
            1,
            activity.get('weighted_average_watts'),
            1 if activity.get('trainer') else 0,
        ),
    )
    return True


def sync_strava_activities(social_auth):
    strava_user_id = int(social_auth.uid)
    headers = {'Authorization': f'Bearer {_access_token(social_auth)}'}
    connection = sqlite3.connect(settings.CENTCOLS_DB_PATH)
    try:
        params = {'per_page': 200}
        latest = _latest_start_timestamp(connection, strava_user_id)
        if latest is not None:
            params['after'] = latest - ONE_DAY_SECONDS

        response = requests.get(ACTIVITIES_URL, headers=headers, params=params, timeout=15)
        response.raise_for_status()
        added = 0
        for activity in response.json():
            if _store_new_activity(connection, strava_user_id, activity):
                added += 1
        connection.commit()
    finally:
        connection.close()
    return added
