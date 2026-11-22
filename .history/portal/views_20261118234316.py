import json
import math
import time

import requests
from django.conf import settings
import logging

from django.http import Http404, HttpResponse
from django.shortcuts import redirect, render
from django.utils import timezone
from django.views.decorators.http import require_POST

from .map_data import (
    get_activity_details,
    get_activity_info,
    get_activity_performances,
    get_all_activities,
    get_col_activities,
    get_map_cols,
    get_user_view_region,
    save_user_view_region,
)
from .strava_sync import sync_strava_activities


logger = logging.getLogger(__name__)


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
            'view_region': get_user_view_region(strava_user_id),
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


@require_POST
def save_view_region(request):
    strava_user_id = request.session.get('strava_user_id')
    if strava_user_id is None:
        return HttpResponse(status=403)
    try:
        payload = json.loads(request.body or b'{}')
    except ValueError:
        return HttpResponse(status=400)
    if not isinstance(payload, dict):
        return HttpResponse(status=400)

    country_code = str(payload.get('country_code', '')).strip().upper()
    region_code = str(payload.get('region_code', '')).strip().upper()
    if not country_code or not region_code:
        return HttpResponse(status=400)

    save_user_view_region(strava_user_id, country_code, region_code)
    return HttpResponse(status=204)


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


@require_POST
def sync_strava(request):
    social_auth = None
    if request.user.is_authenticated:
        social_auth = request.user.social_auth.filter(provider='strava').first()

    if social_auth is None:
        return redirect('portal:home')

    try:
        sync_strava_activities(social_auth)
    except Exception:
        logger.exception('Synchronisation Strava echouee')

    if request.POST.get('next') == 'activities':
        return redirect('portal:all_activities')
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


def all_activities(request):
    strava_user_id = request.session.get('strava_user_id')
    greeting_name = ''
    if request.user.is_authenticated:
        greeting_name = (
            request.user.get_full_name().strip()
            or request.user.get_username()
        )

    return render(
        request,
        'portal/all_activities.html',
        {
            'activities': get_all_activities(strava_user_id),
            'personalized': strava_user_id is not None,
            'greeting_name': greeting_name,
            'strava_auth_configured': bool(
                settings.SOCIAL_AUTH_STRAVA_KEY
                and settings.SOCIAL_AUTH_STRAVA_SECRET
            ),
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


def col_map(request, col_code):
    strava_user_id = request.session.get('strava_user_id')
    col = next(
        (item for item in get_map_cols(strava_user_id) if item['code'] == col_code),
        None,
    )
    if col is None:
        raise Http404('Col not found')

    return render(
        request,
        'portal/col_map.html',
        {
            'col': col,
            'position': {'lat': col['latitude'], 'lon': col['longitude']},
        },
    )


def compute_climb_summary(altitude_data, distance_data, watts_data=None, interval_m=100, min_gradient=4.0):
    """Retourne (km en montée, pente moyenne %, puissance moyenne W) par tranches de interval_m."""
    if not altitude_data or not distance_data or len(altitude_data) < 2:
        return None, None, None

    total_climb_dist = 0.0
    weighted_gradient_sum = 0.0
    climb_watts_sum = 0.0
    climb_watts_count = 0

    dist_start = distance_data[0]
    alt_start = altitude_data[0]
    i = 1

    while i < len(distance_data):
        i_seg_start = i - 1
        while i < len(distance_data) and (distance_data[i] - dist_start) < interval_m:
            i += 1

        if i >= len(distance_data):
            break

        dist_end = distance_data[i]
        alt_end = altitude_data[i]
        delta_dist = dist_end - dist_start

        if delta_dist > 0:
            gradient = ((alt_end - alt_start) / delta_dist) * 100
            if gradient > min_gradient:
                total_climb_dist += delta_dist
                weighted_gradient_sum += gradient * delta_dist
                if watts_data:
                    for j in range(i_seg_start, min(i + 1, len(watts_data))):
                        watts = watts_data[j]
                        if watts and watts > 0:
                            climb_watts_sum += watts
                            climb_watts_count += 1

        dist_start = dist_end
        alt_start = alt_end

    if total_climb_dist <= 0:
        return None, None, None

    total_climb_km = round(total_climb_dist / 1000, 2)
    avg_gradient = round(weighted_gradient_sum / total_climb_dist, 1)
    avg_power = round(climb_watts_sum / climb_watts_count) if climb_watts_count else None
    return total_climb_km, avg_gradient, avg_power


def _fetch_activity_streams(strava_id, access_token):
    if not access_token:
        return {}

    try:
        response = requests.get(
            f'https://www.strava.com/api/v3/activities/{strava_id}/streams',
            headers={'Authorization': f'Bearer {access_token}'},
            params={'keys': 'distance,altitude,watts', 'key_by_type': 'true'},
            timeout=10,
        )
        response.raise_for_status()
        return response.json()
    except (requests.RequestException, ValueError):
        return {}


def _activity_climb_summary(streams):
    altitudes = streams.get('altitude', {}).get('data', [])
    distances = streams.get('distance', {}).get('data', [])
    watts = streams.get('watts', {}).get('data', []) or None
    return compute_climb_summary(altitudes, distances, watts)


def _activity_altitude_profile(streams):
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
        return [], [], [], None
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

    smoothed_points = []
    smoothing_radius = 2
    for index, point in enumerate(profile_points):
        window_start = max(0, index - smoothing_radius)
        window_end = min(len(profile_points), index + smoothing_radius + 1)
        average_y = sum(
            profile_points[window_index]['y']
            for window_index in range(window_start, window_end)
        ) / (window_end - window_start)
        smoothed_points.append({'x': point['x'], 'y': round(average_y, 2)})

    line_step = max(1, math.ceil((len(smoothed_points) - 1) / 119))
    profile_line_points = smoothed_points[::line_step]
    if profile_line_points[-1] != smoothed_points[-1]:
        profile_line_points.append(smoothed_points[-1])

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

    return profile_points, profile_areas, profile_line_points, (
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
    streams = _fetch_activity_streams(strava_id, access_token)
    profile_points, profile_areas, profile_line_points, altitude_bounds = _activity_altitude_profile(streams)
    climb_total_km, climb_avg_gradient, climb_avg_power = _activity_climb_summary(streams)
    activity_info = get_activity_info(strava_id)
    if access_token and strava_user_id is not None and not SegmentEffort.objects.filter(
        strava_user_id=strava_user_id, strava_activity_id=strava_id
    ).exists():
        try:
            import_segment_efforts(
                strava_user_id, strava_id, {'Authorization': f'Bearer {access_token}'}
            )
        except requests.RequestException:
            logger.warning('Segments non importes pour l activite %s', strava_id, exc_info=True)
    performances = get_activity_performances(strava_id, strava_user_id)
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
            'back_to_all': request.GET.get('from') == 'all',
            'profile_points': profile_points,
            'profile_areas': profile_areas,
            'altitude_bounds': altitude_bounds,
            'climb_total_km': climb_total_km,
            'climb_avg_gradient': climb_avg_gradient,
            'climb_avg_power': climb_avg_power,
            'activity_info': activity_info,
            'performances': performances,
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
