import logging
import sqlite3
import time
from collections import Counter
from datetime import datetime, timezone
from math import acos, cos, degrees, radians, sin
from zoneinfo import ZoneInfo

import requests
from django.conf import settings
from django.utils.dateparse import parse_datetime
from social_django.utils import load_strategy

from .map_data import _parse_database_datetime


logger = logging.getLogger(__name__)

ACTIVITIES_URL = 'https://www.strava.com/api/v3/athlete/activities'
ACTIVITY_URL = 'https://www.strava.com/api/v3/activities/{}'
SEGMENT_EFFORTS_URL = 'https://www.strava.com/api/v3/segment_efforts'
MIN_SEGMENT_DISTANCE_M = 3000
MIN_SEGMENT_GRADE = 5
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


def _decode_polyline(encoded):
    points = []
    index = lat = lng = 0
    while index < len(encoded):
        deltas = []
        for _ in range(2):
            shift = result = 0
            while True:
                byte = ord(encoded[index]) - 63
                index += 1
                result |= (byte & 0x1F) << shift
                shift += 5
                if byte < 0x20:
                    break
            deltas.append(~(result >> 1) if result & 1 else result >> 1)
        lat += deltas[0]
        lng += deltas[1]
        points.append((lat / 1e5, lng / 1e5))
    return points


def _distance_km(lat1, lon1, lat2, lon2):
    cos_value = sin(radians(lat1)) * sin(radians(lat2)) + cos(radians(lat1)) * cos(radians(lat2)) * cos(radians(lon1 - lon2))
    cos_value = max(-1.0, min(1.0, cos_value))
    return 60 * 1.1515 * degrees(acos(cos_value)) * 1.609344


def _load_cols(connection):
    return connection.execute(
        'SELECT col_code, col_lat, col_lon FROM myapp_col '
        'WHERE col_lat IS NOT NULL AND col_lon IS NOT NULL'
    ).fetchall()


def _visited_col_codes(cols, points):
    if not points:
        return set()
    min_lat = min(lat for lat, _ in points)
    max_lat = max(lat for lat, _ in points)
    min_lon = min(lon for _, lon in points)
    max_lon = max(lon for _, lon in points)
    candidates = [
        (code, col_lat, col_lon)
        for code, col_lat, col_lon in cols
        if min_lat <= col_lat <= max_lat and min_lon <= col_lon <= max_lon
    ]

    visited = set()
    for lat, lon in points:
        for code, col_lat, col_lon in candidates:
            if _distance_km(col_lat, col_lon, lat, lon) < 0.250:
                visited.add(code)
    return visited


def _has_col_perform(connection, strava_id):
    return connection.execute(
        'SELECT 1 FROM myapp_col_perform WHERE strava_id = ? LIMIT 1',
        (strava_id,),
    ).fetchone() is not None


def _store_col_perform(connection, strava_id, col_code):
    connection.execute(
        'INSERT INTO myapp_col_perform (strava_id, col_code) SELECT ?, ? '
        'WHERE NOT EXISTS (SELECT 1 FROM myapp_col_perform WHERE strava_id = ? AND col_code = ?)',
        (strava_id, col_code, strava_id, col_code),
    )


def _paris_midnight_utc(date_text):
    local = datetime.strptime(date_text[:10], '%Y-%m-%d').replace(tzinfo=ZoneInfo('Europe/Paris'))
    return local.astimezone(timezone.utc).strftime('%Y-%m-%d %H:%M:%S')


def _rebuild_col_counters(connection, strava_user_id):
    rows = connection.execute(
        'SELECT DISTINCT cp.col_code, cp.strava_id, a.act_start_date FROM myapp_col_perform cp '
        'JOIN myapp_activity a ON a.strava_id = cp.strava_id '
        'WHERE a.strava_user_id = ?',
        (strava_user_id,),
    ).fetchall()
    year_start = f'{datetime.now().year}-01-01'

    totals = Counter()
    year_totals = Counter()
    last_dates = {}
    for code, _, start_date in rows:
        totals[code] += 1
        if start_date > year_start:
            year_totals[code] += 1
        if code not in last_dates or start_date > last_dates[code]:
            last_dates[code] = start_date

    existing = {
        code for (code,) in connection.execute(
            'SELECT col_code FROM myapp_col_counter WHERE strava_user_id = ?',
            (strava_user_id,),
        )
    }

    for code in set(totals) | existing:
        count = totals.get(code, 0)
        year_count = year_totals.get(code, 0)
        last_date = _paris_midnight_utc(last_dates[code]) if code in last_dates else None
        if code in existing:
            connection.execute(
                'UPDATE myapp_col_counter SET col_count = ?, year_col_count = ?, '
                'last_passage_date = COALESCE(?, last_passage_date) '
                'WHERE strava_user_id = ? AND col_code = ?',
                (count, year_count, last_date, strava_user_id, code),
            )
        else:
            connection.execute(
                'INSERT INTO myapp_col_counter (col_code, strava_user_id, col_count, year_col_count, last_passage_date) '
                'VALUES (?, ?, ?, ?, ?)',
                (code, strava_user_id, count, year_count, last_date),
            )


def _local_segment_id(connection, segment):
    row = connection.execute(
        'SELECT segment_id FROM myapp_segment WHERE strava_segment_id = ?',
        (int(segment['id']),),
    ).fetchone()
    if row:
        return row[0]
    cursor = connection.execute(
        'INSERT INTO myapp_segment (strava_segment_id, activity_type, segment_name, slope, lenght, ascent) '
        'VALUES (?, ?, ?, ?, ?, ?)',
        (
            int(segment['id']),
            'riding',
            segment.get('name') or '-',
            segment['average_grade'],
            segment['distance'] / 1000,
            segment['elevation_high'] - segment['elevation_low'],
        ),
    )
    return cursor.lastrowid


def _store_segment_perform(connection, strava_user_id, segment_id, elevation_gain, effort):
    elapsed = int(effort.get('elapsed_time') or 0)
    if not elapsed:
        return
    exists = connection.execute(
        'SELECT 1 FROM myapp_perform WHERE strava_perf_id = ?',
        (int(effort['id']),),
    ).fetchone()
    if exists:
        return
    connection.execute(
        'INSERT INTO myapp_perform (strava_perf_id, segment_id, perf_date, perf_chrono, perf_vam, '
        'perf_fc, perf_fcmax, strava_user_id, perf_power) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)',
        (
            int(effort['id']),
            segment_id,
            parse_datetime(effort['start_date']).astimezone(timezone.utc).strftime('%Y-%m-%d %H:%M:%S'),
            elapsed,
            int(3600 * elevation_gain / elapsed),
            int(effort.get('average_heartrate') or 0),
            int(effort.get('max_heartrate') or 0),
            strava_user_id,
            effort.get('average_watts'),
        ),
    )


def _import_segment_history(connection, strava_user_id, segment_id, segment, headers):
    # Strava refuse cet historique sans abonnement : on garde alors le seul passage de l'activite
    try:
        response = requests.get(
            SEGMENT_EFFORTS_URL,
            headers=headers,
            params={'segment_id': segment['id'], 'per_page': 200},
            timeout=15,
        )
        response.raise_for_status()
    except requests.RequestException:
        logger.warning('Historique non importe pour le segment %s', segment['id'], exc_info=True)
        return
    elevation_gain = segment['elevation_high'] - segment['elevation_low']
    for effort in response.json():
        _store_segment_perform(connection, strava_user_id, segment_id, elevation_gain, effort)


def _import_activity_segments(connection, strava_user_id, strava_id, headers):
    response = requests.get(ACTIVITY_URL.format(strava_id), headers=headers, timeout=15)
    response.raise_for_status()
    for effort in response.json().get('segment_efforts') or []:
        segment = effort.get('segment') or {}
        # Memes criteres que l'ancienne appli : montees d'au moins 3 km a 5 % de moyenne
        if (segment.get('distance') or 0) < MIN_SEGMENT_DISTANCE_M:
            continue
        if (segment.get('average_grade') or 0) < MIN_SEGMENT_GRADE:
            continue
        if segment.get('elevation_high') is None or segment.get('elevation_low') is None:
            continue
        segment_id = _local_segment_id(connection, segment)
        has_history = connection.execute(
            'SELECT 1 FROM myapp_perform WHERE strava_user_id = ? AND segment_id = ? LIMIT 1',
            (strava_user_id, segment_id),
        ).fetchone()
        _store_segment_perform(
            connection, strava_user_id, segment_id,
            segment['elevation_high'] - segment['elevation_low'], effort,
        )
        if not has_history:
            _import_segment_history(connection, strava_user_id, segment_id, segment, headers)


def import_segment_efforts(strava_user_id, strava_id, headers):
    connection = sqlite3.connect(settings.CENTCOLS_DB_PATH)
    try:
        _import_activity_segments(connection, strava_user_id, strava_id, headers)
        connection.commit()
    finally:
        connection.close()


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
        activities = response.json()

        cols = _load_cols(connection)
        added = 0
        for activity in activities:
            if _store_new_activity(connection, strava_user_id, activity):
                added += 1
                try:
                    _import_activity_segments(connection, strava_user_id, int(activity['id']), headers)
                except requests.RequestException:
                    logger.warning('Segments non importes pour l activite %s', activity['id'], exc_info=True)
            strava_id = int(activity['id'])
            if _has_col_perform(connection, strava_id):
                continue
            encoded = (activity.get('map') or {}).get('summary_polyline') or ''
            points = _decode_polyline(encoded) if encoded else []
            for col_code in _visited_col_codes(cols, points):
                _store_col_perform(connection, strava_id, col_code)

        _rebuild_col_counters(connection, strava_user_id)
        connection.commit()
    finally:
        connection.close()
    return added
