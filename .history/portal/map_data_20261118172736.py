import logging
import sqlite3
from datetime import datetime

from django.conf import settings


logger = logging.getLogger(__name__)

REGION_NAME_FALLBACKS = {
    ('ARG', 'J'): 'San Juan',
    ('FRA', '01'): 'Ain',
    ('FRA', '88'): 'Vosges',
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
                SELECT
                    activity.strava_id,
                    activity.act_name,
                    activity.act_start_date,
                    activity.act_dist,
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

    activities = []
    for row in activity_rows:
        duration_seconds = row['act_time']
        duration = None
        if duration_seconds is not None:
            total_minutes = int(duration_seconds) // 60
            hours, minutes = divmod(total_minutes, 60)
            duration = f'{hours} h {minutes:02} min' if hours else f'{minutes} min'

        distance = row['act_dist']
        activities.append(
            {
                'strava_id': row['strava_id'],
                'name': row['act_name'] or 'Activité sans titre',
                'start_date': _parse_database_datetime(row['act_start_date']),
                'distance_km': float(distance) / 1000 if distance is not None else None,
                'duration': duration,
            }
        )

    return dict(col_row), activities
