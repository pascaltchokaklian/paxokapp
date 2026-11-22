import logging
import math
import sqlite3
import time
from datetime import datetime

from django.conf import settings


logger = logging.getLogger(__name__)

REGION_NAME_FALLBACKS = {
    ('ARG', 'J'): 'San Juan',
    ('FRA', '01'): 'Ain',
    ('FRA', '88'): 'Vosges',
}


ACTIVITY_TYPE_LABELS = {
    'Ride': 'Vélo',
    'VirtualRide': 'Vélo virtuel',
    'EBikeRide': 'Vélo électrique',
    'Run': 'Course à pied',
    'Walk': 'Marche',
    'Hike': 'Randonnée',
    'WeightTraining': 'Musculation',
    'Workout': 'Entraînement',
    'Swim': 'Natation',
}


def _parse_database_datetime(value):
    if not value:
        return None
    try:
        return datetime.fromisoformat(str(value).replace('Z', '+00:00'))
    except ValueError:
        return None


def get_map_cols(strava_user_id=None):
    database_path = settings.CENTCOLS_DB_PATH
    if not database_path.is_file():
        raise FileNotFoundError(
            f'Cent Cols database was not found: {database_path}'
        )

    database_uri = f'{database_path.as_uri()}?mode=ro'
    connection = sqlite3.connect(database_uri, uri=True)
    connection.row_factory = sqlite3.Row
    try:
        country_rows = connection.execute(
            '''
            SELECT country_code, country_name, code_100cols
            FROM myapp_country
            '''
        ).fetchall()
        region_rows = connection.execute(
            '''
            SELECT country_code, region_code, region_name
            FROM myapp_region
            '''
        ).fetchall()
        rows = connection.execute(
            '''
            SELECT
                col.col_code,
                col.col_name,
                col.col_alt,
                col.col_lat,
                col.col_lon,
                col.col_type,
                COALESCE(counter.col_count, 0) AS col_count,
                COALESCE(counter.year_col_count, 0) AS year_col_count,
                counter.last_passage_date
            FROM myapp_col AS col
            LEFT JOIN (
                SELECT
                    col_code,
                    MAX(col_count) AS col_count,
                    MAX(year_col_count) AS year_col_count,
                    MAX(last_passage_date) AS last_passage_date
                FROM myapp_col_counter
                WHERE strava_user_id = ?
                GROUP BY col_code
            ) AS counter ON counter.col_code = col.col_code
            WHERE col.col_lat IS NOT NULL
                AND col.col_lon IS NOT NULL
            ORDER BY col.col_name
            ''',
            (strava_user_id,),
        ).fetchall()
    finally:
        connection.close()

    countries = {
        row['code_100cols'].strip().upper(): row
        for row in country_rows
        if row['code_100cols']
    }
    regions = {
        (row['country_code'].strip().upper(), row['region_code'].strip().upper()): row
        for row in region_rows
        if row['country_code'] and row['region_code']
    }

    cols = []
    for row in rows:
        try:
            latitude = float(row['col_lat'])
            longitude = float(row['col_lon'])
        except (TypeError, ValueError):
            logger.warning(
                'Skipping col with invalid coordinates: %s',
                row['col_code'],
            )
            continue

        if not -90 <= latitude <= 90 or not -180 <= longitude <= 180:
            logger.warning(
                'Skipping col with out-of-range coordinates: %s',
                row['col_code'],
            )
            continue

        code_parts = [
            part
            for part in (row['col_code'] or '').strip().upper().replace(' ', '-').split('-')
            if part
        ]
        country_prefix = code_parts[0][:2] if code_parts else ''
        country = countries.get(country_prefix)
        country_code = country['country_code'] if country else country_prefix
        country_name = country['country_name'] if country else country_prefix
        department_code = code_parts[1] if len(code_parts) > 1 else ''
        region = regions.get((country_code.upper(), department_code))

        cols.append(
            {
                'code': row['col_code'],
                'name': row['col_name'],
                'altitude': row['col_alt'],
                'latitude': latitude,
                'longitude': longitude,
                'type': row['col_type'],
                'col_count': row['col_count'],
                'year_col_count': row['year_col_count'],
                'last_passage_date': _parse_database_datetime(
                    row['last_passage_date']
                ),
                'passed': row['col_count'] > 0,
                'country_code': country_code,
                'country_name': country_name,
                'department_code': department_code,
                'department_name': (
                    region['region_name']
                    if region
                    else REGION_NAME_FALLBACKS.get(
                        (country_code.upper(), department_code),
                        department_code or 'Non renseigné',
                    )
                ),
            }
        )

    return cols


def get_user_view_region(strava_user_id):
    if strava_user_id is None:
        return None
    connection = _legacy_connection()
    try:
        row = connection.execute(
            'SELECT view_country_code, view_region_code FROM myapp_user_var WHERE strava_user_id = ?',
            (strava_user_id,),
        ).fetchone()
    finally:
        connection.close()
    if row is None:
        return None
    return {'country_code': row['view_country_code'], 'region_code': row['view_region_code']}


def save_user_view_region(strava_user_id, country_code, region_code):
    connection = sqlite3.connect(settings.CENTCOLS_DB_PATH)
    try:
        updated = connection.execute(
            'UPDATE myapp_user_var SET view_country_code = ?, view_region_code = ?, last_update = ? '
            'WHERE strava_user_id = ?',
            (country_code, region_code, int(time.time()), strava_user_id),
        ).rowcount
        if not updated:
            connection.execute(
                'INSERT INTO myapp_user_var (strava_user_id, view_country_code, view_region_code, last_update) '
                'VALUES (?, ?, ?, ?)',
                (strava_user_id, country_code, region_code, int(time.time())),
            )
        connection.commit()
    finally:
        connection.close()


def _activity_summary(row):
    duration_seconds = row['act_time']
    duration = None
    if duration_seconds is not None:
        total_minutes = int(duration_seconds) // 60
        hours, minutes = divmod(total_minutes, 60)
        duration = f'{hours} h {minutes:02} min' if hours else f'{minutes} min'

    distance = row['act_dist']
    return {
        'strava_id': row['strava_id'],
        'name': row['act_name'] or 'Activité sans titre',
        'start_date': _parse_database_datetime(row['act_start_date']),
        'type': ACTIVITY_TYPE_LABELS.get(row['act_type'], row['act_type'] or ''),
        'distance_km': float(distance) / 1000 if distance is not None else None,
        'elevation_gain_m': row['act_den'],
        'normalized_power_w': row['act_normal_power'],
        'duration': duration,
    }


def _format_chrono(seconds):
    hours, remainder = divmod(int(seconds), 3600)
    minutes, secs = divmod(remainder, 60)
    return f'{hours}:{minutes:02d}:{secs:02d}'


def _legacy_connection():
    database_path = settings.CENTCOLS_DB_PATH
    if not database_path.is_file():
        raise FileNotFoundError(
            f'Cent Cols database was not found: {database_path}'
        )
    connection = sqlite3.connect(f'{database_path.as_uri()}?mode=ro', uri=True)
    connection.row_factory = sqlite3.Row
    return connection


def get_activity_info(strava_id):
    connection = _legacy_connection()
    try:
        rows = connection.execute(
            'SELECT info_txt FROM myapp_activity_info WHERE strava_id = ? ORDER BY act_info_id',
            (strava_id,),
        ).fetchall()
    finally:
        connection.close()
    return [row['info_txt'] for row in rows]


def get_activity_performances(strava_id, strava_user_id):
    if strava_user_id is None:
        return []

    connection = _legacy_connection()
    try:
        activity = connection.execute(
            'SELECT substr(act_start_date, 1, 10) AS day FROM myapp_activity WHERE strava_id = ? AND strava_user_id = ?',
            (strava_id, strava_user_id),
        ).fetchone()
        if activity is None or not activity['day']:
            return []
        # Comme l'ancienne appli : les performances du jour de l'activite
        efforts = connection.execute(
            '''
            SELECT perform.segment_id, perform.perf_chrono, perform.perf_vam, segment.segment_name
            FROM myapp_perform AS perform
            INNER JOIN myapp_segment AS segment ON segment.segment_id = perform.segment_id
            WHERE perform.strava_user_id = ? AND date(perform.perf_date) = ?
            ORDER BY perform.perf_date
            ''',
            (strava_user_id, activity['day']),
        ).fetchall()
        performances = []
        for effort in efforts:
            total, faster = connection.execute(
                'SELECT COUNT(*), COALESCE(SUM(perf_chrono < ?), 0) FROM myapp_perform '
                'WHERE strava_user_id = ? AND segment_id = ?',
                (effort['perf_chrono'], strava_user_id, effort['segment_id']),
            ).fetchone()
            place = faster + 1
            performances.append({
                'name': effort['segment_name'],
                'chrono': _format_chrono(effort['perf_chrono']),
                'vam': f"{effort['perf_vam']} m/h",
                'place': f'{place}/{total}',
                'percent': int(100 * place / total),
            })
    finally:
        connection.close()
    return performances


def get_col_activities(col_code, strava_user_id):
    database_path = settings.CENTCOLS_DB_PATH
    if not database_path.is_file():
        raise FileNotFoundError(
            f'Cent Cols database was not found: {database_path}'
        )

    database_uri = f'{database_path.as_uri()}?mode=ro'
    connection = sqlite3.connect(database_uri, uri=True)
    connection.row_factory = sqlite3.Row
    try:
        col_row = connection.execute(
            'SELECT col_code, col_name FROM myapp_col WHERE col_code = ?',
            (col_code,),
        ).fetchone()
        if not col_row:
            return None, []

        activity_rows = []
        if strava_user_id is not None:
            activity_rows = connection.execute(
                '''
                SELECT DISTINCT
                    activity.strava_id,
                    activity.act_name,
                    activity.act_start_date,
                    activity.act_type,
                    activity.act_dist,
                    activity.act_den,
                    activity.act_power,
                    activity.act_normal_power,
                    activity.act_time
                FROM myapp_col_perform AS passage
                INNER JOIN myapp_activity AS activity
                    ON activity.strava_id = passage.strava_id
                WHERE passage.col_code = ?
                    AND activity.strava_user_id = ?
                ORDER BY activity.act_start_date DESC, activity.strava_id DESC
                ''',
                (col_code, strava_user_id),
            ).fetchall()
    finally:
        connection.close()

    activities = [_activity_summary(row) for row in activity_rows]

    return dict(col_row), activities


def get_all_activities(strava_user_id):
    if strava_user_id is None:
        return []

    database_path = settings.CENTCOLS_DB_PATH
    if not database_path.is_file():
        raise FileNotFoundError(
            f'Cent Cols database was not found: {database_path}'
        )

    database_uri = f'{database_path.as_uri()}?mode=ro'
    connection = sqlite3.connect(database_uri, uri=True)
    connection.row_factory = sqlite3.Row
    try:
        activity_rows = connection.execute(
            '''
            SELECT strava_id, act_name, act_start_date, act_type, act_dist, act_den, act_power, act_normal_power, act_time
            FROM myapp_activity
            WHERE strava_user_id = ?
            ORDER BY act_start_date DESC, strava_id DESC
            ''',
            (strava_user_id,),
        ).fetchall()
    finally:
        connection.close()

    return [_activity_summary(row) for row in activity_rows]


def get_activity_details(strava_id, strava_user_id):
    if strava_user_id is None:
        return None

    database_path = settings.CENTCOLS_DB_PATH
    if not database_path.is_file():
        raise FileNotFoundError(
            f'Cent Cols database was not found: {database_path}'
        )

    database_uri = f'{database_path.as_uri()}?mode=ro'
    connection = sqlite3.connect(database_uri, uri=True)
    connection.row_factory = sqlite3.Row
    try:
        activity_row = connection.execute(
            '''
            SELECT
                strava_id,
                act_name,
                act_start_date,
                act_dist,
                act_time,
                act_den,
                act_power,
                act_normal_power
            FROM myapp_activity
            WHERE strava_id = ? AND strava_user_id = ?
            ''',
            (strava_id, strava_user_id),
        ).fetchone()
        if not activity_row:
            return None

        col_rows = connection.execute(
            '''
            SELECT DISTINCT
                col.col_code,
                col.col_name,
                col.col_alt,
                col.col_lat,
                col.col_lon,
                COALESCE(counter.col_count, 0) AS col_count
            FROM myapp_col_perform AS passage
            INNER JOIN myapp_col AS col ON col.col_code = passage.col_code
            LEFT JOIN (
                SELECT col_code, MAX(col_count) AS col_count
                FROM myapp_col_counter
                WHERE strava_user_id = ?
                GROUP BY col_code
            ) AS counter ON counter.col_code = col.col_code
            WHERE passage.strava_id = ?
            ORDER BY col.col_alt
            ''',
            (strava_user_id, strava_id),
        ).fetchall()
    finally:
        connection.close()

    cols = []
    seen_codes = set()
    physical_groups = []
    for row in col_rows:
        if row['col_code'] in seen_codes:
            continue
        seen_codes.add(row['col_code'])
        latitude, longitude, altitude = row['col_lat'], row['col_lon'], row['col_alt']
        if latitude is not None and longitude is not None and altitude is not None:
            is_same_physical = False
            for other_latitude, other_longitude, other_altitude in physical_groups:
                if abs(altitude - other_altitude) <= 20:
                    lat1, lon1, lat2, lon2 = map(
                        math.radians,
                        (latitude, longitude, other_latitude, other_longitude),
                    )
                    cosine = (
                        math.sin(lat1) * math.sin(lat2)
                        + math.cos(lat1)
                        * math.cos(lat2)
                        * math.cos(lon1 - lon2)
                    )
                    distance_km = 6371 * math.acos(max(-1, min(1, cosine)))
                    if distance_km <= 0.25:
                        is_same_physical = True
                        break
            if is_same_physical:
                continue
            physical_groups.append((latitude, longitude, altitude))

        cols.append(
            {
                'code': row['col_code'],
                'name': row['col_name'],
                'altitude': row['col_alt'],
                'latitude': latitude,
                'longitude': longitude,
                'col_count': row['col_count'],
            }
        )

    distance = activity_row['act_dist']
    duration_seconds = activity_row['act_time']
    distance_km = float(distance) / 1000 if distance is not None else None
    duration = None
    average_speed = None
    if duration_seconds is not None and duration_seconds > 0:
        total_minutes = int(duration_seconds) // 60
        hours, minutes = divmod(total_minutes, 60)
        duration = f'{hours} h {minutes:02} min' if hours else f'{minutes} min'
        if distance_km is not None:
            average_speed = distance_km / duration_seconds * 3600

    return {
        'strava_id': activity_row['strava_id'],
        'name': activity_row['act_name'] or 'Activité sans titre',
        'start_date': _parse_database_datetime(activity_row['act_start_date']),
        'distance_km': distance_km,
        'duration': duration,
        'average_speed_kmh': average_speed,
        'elevation_gain_m': activity_row['act_den'],
        'average_power_w': activity_row['act_power'],
        'normalized_power_w': activity_row['act_normal_power'],
        'cols': cols,
    }
