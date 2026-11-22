import math
import time

import requests
from django.conf import settings
from django.http import Http404, HttpResponse
from django.shortcuts import redirect, render
from django.utils import timezone


from .map_data import get_activity_details, get_col_activities, get_map_cols


def home(request):
    strava_user_id = request.session.get('strava_user_id')
    cols = get_map_cols(strava_user_id)
    passed_cols = [col for col in cols if col['passed']]
    passed_cols.sort(
        key=lambda col: (
            -col['col_count'],
            (col['name'] or '').casefold(),
        )
    )
    passed_count = len(passed_cols)
    greeting_name = ''
    if request.user.is_authenticated:
        greeting_name = (
            request.user.get_full_name().strip()
            or request.user.get_username()
        )

    return render(
        request,
        'portal/map.html',
        {
            'cols': cols,
            'cols_count': len(cols),
            'passed_count': passed_count,
            'passed_cols': passed_cols,
            'current_year': timezone.localdate().year,
            'personalized': strava_user_id is not None,
            'greeting_name': greeting_name,
            'strava_auth_configured': bool(
                settings.SOCIAL_AUTH_STRAVA_KEY
                and settings.SOCIAL_AUTH_STRAVA_SECRET
            ),
        },
    )


def strava_connected(request):
    if not request.user.is_authenticated:
        request.session.pop('strava_user_id', None)
        return redirect('portal:home')

    social_auth = request.user.social_auth.filter(provider='strava').first()
    try:
        strava_user_id = int(social_auth.uid)
    except (AttributeError, TypeError, ValueError):
        request.session.pop('strava_user_id', None)
        return redirect('portal:home')

    request.session['strava_user_id'] = strava_user_id
    return redirect('portal:home')


def applications(request):
    greeting_name = ''
    if request.user.is_authenticated:
        greeting_name = (
            request.user.get_full_name().strip()
            or request.user.get_username()
        )

    return render(
        request,
        'portal/applications.html',
        {
            'personalized': request.session.get('strava_user_id') is not None,
            'greeting_name': greeting_name,
        },
    )


def col_activities(request, col_code):
    strava_user_id = request.session.get('strava_user_id')
    col, activities = get_col_activities(col_code, strava_user_id)
    if col is None:
        raise Http404('Col not found')

    return render(
        request,
        'portal/col_activities.html',
        {
            'col': col,
            'activities': activities,
            'personalized': strava_user_id is not None,
            'greeting_name': request.user.get_full_name().strip()
            or request.user.get_username()
            if request.user.is_authenticated
            else '',
            'strava_auth_configured': bool(
                settings.SOCIAL_AUTH_STRAVA_KEY
                and settings.SOCIAL_AUTH_STRAVA_SECRET
            ),
        },
    )


def _activity_altitude_profile(strava_id, access_token):
    if not access_token:
        return [], [], None

    try:
        response = requests.get(
            f'https://www.strava.com/api/v3/activities/{strava_id}/streams',
            headers={'Authorization': f'Bearer {access_token}'},
            params={'keys': 'distance,altitude', 'key_by_type': 'true'},
            timeout=10,
        )
        response.raise_for_status()
        streams = response.json()
    except (requests.RequestException, ValueError):
        return [], [], None

    distances = streams.get('distance', {}).get('data', [])
    altitudes = streams.get('altitude', {}).get('data', [])
    raw_points = []
    for distance, altitude in zip(distances, altitudes):
        try:
            distance = float(distance)
            altitude = float(altitude)
        except (TypeError, ValueError):
            continue
        if math.isfinite(distance) and math.isfinite(altitude):
            raw_points.append((distance, altitude))
    if len(raw_points) < 2:
        return [], [], None
    raw_points.sort(key=lambda point: point[0])

    step = max(1, math.ceil((len(raw_points) - 1) / 239))
    sampled = raw_points[::step]
    if sampled[-1] != raw_points[-1]:
        sampled.append(raw_points[-1])

    minimum_altitude = min(point[1] for point in sampled)
    maximum_altitude = max(point[1] for point in sampled)
    altitude_range = maximum_altitude - minimum_altitude or 1
    total_distance = raw_points[-1][0] or 1
    profile_points = []
    for distance, altitude in sampled:
        profile_points.append(
            {
                'x': round(48 + 904 * distance / total_distance, 2),
                'y': round(266 - 224 * (altitude - minimum_altitude) / altitude_range, 2),
            }
        )

    profile_areas = []
    for index, (start, end) in enumerate(zip(sampled, sampled[1:])):
        start_point = profile_points[index]
        end_point = profile_points[index + 1]
        distance_delta = end[0] - start[0]
        altitude_delta = end[1] - start[1]
        profile_areas.append(
            {
                'points': (
                    f"{start_point['x']},266 "
                    f"{start_point['x']},{start_point['y']} "
                    f"{end_point['x']},{end_point['y']} "
                    f"{end_point['x']},266"
                ),
                'climb': distance_delta > 0 and altitude_delta / distance_delta > 0.04,
            }
        )

    return profile_points, profile_areas, (
        round(minimum_altitude),
        round(maximum_altitude),
    )


def _get_social_access_token(social_auth):
    extra_data = dict(social_auth.extra_data or {})
    access_token = extra_data.get('access_token')
    refresh_token = extra_data.get('refresh_token')
    try:
        expires_at = int(extra_data.get('expires_at') or extra_data.get('expires') or 0)
    except (TypeError, ValueError):
        expires_at = 0
    if not expires_at:
        try:
            expires_at = int(extra_data.get('auth_time') or 0) + int(
                extra_data.get('expires_in') or 0
            )
        except (TypeError, ValueError):
            expires_at = 0
    if (
        not refresh_token
        or not settings.SOCIAL_AUTH_STRAVA_KEY
        or not settings.SOCIAL_AUTH_STRAVA_SECRET
        or expires_at > int(time.time()) + 60
    ):
        return access_token

    try:
        response = requests.post(
            'https://www.strava.com/oauth/token',
            data={
                'client_id': settings.SOCIAL_AUTH_STRAVA_KEY,
                'client_secret': settings.SOCIAL_AUTH_STRAVA_SECRET,
                'grant_type': 'refresh_token',
                'refresh_token': refresh_token,
            },
            timeout=10,
        )
        response.raise_for_status()
        refreshed_tokens = response.json()
    except (requests.RequestException, ValueError, TypeError):
        return access_token

    new_access_token = refreshed_tokens.get('access_token')
    if not new_access_token:
        return access_token

    extra_data['access_token'] = new_access_token
    if refreshed_tokens.get('refresh_token'):
        extra_data['refresh_token'] = refreshed_tokens['refresh_token']
    if refreshed_tokens.get('expires_at'):
        extra_data['expires_at'] = refreshed_tokens['expires_at']
    if refreshed_tokens.get('expires_in'):
        extra_data['expires_in'] = refreshed_tokens['expires_in']
    extra_data['auth_time'] = int(time.time())
    social_auth.extra_data = extra_data
    social_auth.save(update_fields=['extra_data'])
    return new_access_token


def activity_detail(request, strava_id):
    strava_user_id = request.session.get('strava_user_id')
    activity = get_activity_details(strava_id, strava_user_id)
    if activity is None:
        raise Http404('Activity not found')

    social_auth = None
    if request.user.is_authenticated:
        social_auth = request.user.social_auth.filter(provider='strava').first()
    access_token = _get_social_access_token(social_auth) if social_auth else None
    profile_points, profile_areas, altitude_bounds = _activity_altitude_profile(
        strava_id,
        access_token,
    )

    greeting_name = ''
    if request.user.is_authenticated:
        greeting_name = (
            request.user.get_full_name().strip()
            or request.user.get_username()
        )

    return render(
        request,
        'portal/activity_detail.html',
        {
            'activity': activity,
            'profile_points': profile_points,
            'profile_areas': profile_areas,
            'altitude_bounds': altitude_bounds,
            'personalized': True,
            'greeting_name': greeting_name,
            'strava_auth_configured': bool(
                settings.SOCIAL_AUTH_STRAVA_KEY
                and settings.SOCIAL_AUTH_STRAVA_SECRET
            ),
        },
    )


def activity_export_text(request, strava_id):
    strava_user_id = request.session.get('strava_user_id')
    activity = get_activity_details(strava_id, strava_user_id)
    if activity is None:
        raise Http404('Activity not found')

    start_date = activity['start_date']
    lines = [
        f"Activité: {activity['name']}",
        f"Date: {start_date.strftime('%d/%m/%Y %H:%M') if start_date else ''}",
        f"Distance: {activity['distance_km']:.2f} km" if activity['distance_km'] is not None else 'Distance: ',
        f"Dénivelé: {activity['elevation_gain_m']} m" if activity['elevation_gain_m'] is not None else 'Dénivelé: ',
        f"Durée: {activity['duration'] or ''}",
        f"Nombre de cols passés: {len(activity['cols'])}",
        '',
    ]
    lines.extend(
        f"{col['name']} - {col['altitude']} m [{col['col_count']}]"
        for col in activity['cols']
    )

    response = HttpResponse(
        '\n'.join(lines) + '\n',
        content_type='text/plain; charset=utf-8',
    )
    response['Content-Disposition'] = f'attachment; filename="activite-{strava_id}.txt"'
    return response
