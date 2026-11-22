import datetime

from django.shortcuts import render

from .elevation import get_elevation_profile
from .forms import CoordinatesForm
from .sun import daily_sunshine_details, timezone_at


def _format_sunshine_time(instant):
    return instant.strftime('%H:%M') if instant else 'Aucun'


def coordinates_view(request):
    context = {'latitude': None, 'longitude': None}
    if request.GET:
        form = CoordinatesForm(request.GET)
        try:
            context['zoom'] = int(request.GET.get('zoom', 11))
        except ValueError:
            context['zoom'] = 11
        if form.is_valid():
            latitude = form.cleaned_data['latitude']
            longitude = form.cleaned_data['longitude']
            context['latitude'] = latitude
            context['longitude'] = longitude

            horizon_profile, error = get_elevation_profile(latitude, longitude)
            if error:
                context['elevation_error'] = error
            else:
                current_year = datetime.date.today().year
                time_zone = timezone_at(latitude, longitude)
                if time_zone is None:
                    context['elevation_error'] = "Impossible de déterminer le fuseau horaire de ce lieu."
                    context['form'] = form
                    return render(request, 'coordinates/form.html', context)

                daily_results = daily_sunshine_details(
                    latitude,
                    longitude,
                    current_year,
                    horizon_profile,
                    time_zone,
                )
                context['sunshine_results'] = [
                    {
                        'date': day.isoformat(),
                        'minutes': int(duration.total_seconds() // 60),
                    }
                    for day, duration, _, _ in daily_results
                ]
                shortest_day = min(daily_results, key=lambda result: result[1])
                longest_day = max(daily_results, key=lambda result: result[1])
                current_day = datetime.date.today()
                today_result = next(
                    result for result in daily_results if result[0] == current_day
                )
                context['sunshine_extremes'] = [
                    {
                        'label': label,
                        'css_class': css_class,
                        'date': day.strftime('%d/%m'),
                        'start': _format_sunshine_time(first_sunshine),
                        'end': _format_sunshine_time(last_sunshine),
                        'duration': f'{int(duration.total_seconds() // 3600)} h '
                        f'{int((duration.total_seconds() // 60) % 60):02d} min',
                    }
                    for label, css_class, (day, duration, first_sunshine, last_sunshine) in (
                        ('Jour J', 'current-day', today_result),
                        ('Jour le plus court', 'shortest-day', shortest_day),
                        ('Jour le plus long', 'longest-day', longest_day),
                    )
                ]
    else:
        form = CoordinatesForm()

    context['form'] = form
    return render(request, 'coordinates/form.html', context)
