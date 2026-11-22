from django.conf import settings
from django.shortcuts import redirect, render


from .map_data import get_map_cols


def home(request):
    strava_user_id = request.session.get('strava_user_id')
    cols = get_map_cols(strava_user_id)
    passed_count = sum(col['passed'] for col in cols)
    return render(
        request,
        'portal/map.html',
        {
            'cols': cols,
            'cols_count': len(cols),
            'passed_count': passed_count,
            'personalized': strava_user_id is not None,
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
    return render(request, 'portal/applications.html')
