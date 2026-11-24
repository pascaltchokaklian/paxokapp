"""Sunshine duration calculation accounting for the surrounding terrain horizon."""
import datetime
import math
import warnings
from zoneinfo import ZoneInfo

import pysolar
from pysolar.solar import get_position
from timezonefinder import TimezoneFinder

STEP_MINUTES_DEFAULT = 5
TIMEZONE_FINDER = TimezoneFinder()

# These calculations use scalar datetimes; NumPy's scalar operations are slower.
pysolar.use_math()


def _solar_position(lat, lon, moment):
    """Return the solar azimuth and altitude without Pysolar's stale leap-second warning."""
    with warnings.catch_warnings():
        warnings.filterwarnings(
            'ignore',
            message=r'Leap seconds for year .* are not available for the installed version of pysolar',
            category=UserWarning,
            module=r'pysolar\.solartime',
        )
        return get_position(lat, lon, moment)


def _may_be_sunny(lat, lon, moment):
    """Conservatively rule out times when the sun is well below the horizon."""
    utc_hour = moment.hour + moment.minute / 60 + moment.second / 3600
    mean_hour_angle = ((utc_hour - 12) * 15 + lon + 180) % 360 - 180
    # Allow 45 minutes for the equation of time and a generous declination bound.
    closest_hour_angle = max(0, abs(mean_hour_angle) - 11.25)
    latitude = math.radians(lat)
    horizontal = math.cos(latitude) * math.cos(math.radians(closest_hour_angle))
    max_sine_altitude = (
        abs(math.sin(latitude)) * math.sin(math.radians(24))
        + (horizontal if horizontal >= 0 else horizontal * math.cos(math.radians(24)))
    )
    return max_sine_altitude >= math.sin(math.radians(-2))


def _horizon_angle_at(horizon_profile, azimuth):
    """Linearly interpolate the horizon angle at a given azimuth between the two nearest sampled bins."""
    bins = sorted(horizon_profile.keys())
    n = len(bins)
    step = 360 / n
    lower_index = int(azimuth // step) % n
    upper_index = (lower_index + 1) % n
    lower_azimuth = bins[lower_index]
    fraction = (azimuth - lower_azimuth) / step if azimuth >= lower_azimuth else (azimuth + 360 - lower_azimuth) / step
    lower_angle = horizon_profile[bins[lower_index]]
    upper_angle = horizon_profile[bins[upper_index]]
    return lower_angle + (upper_angle - lower_angle) * fraction


def timezone_at(lat, lon):
    """Return the IANA timezone at a geographical coordinate, if available."""
    timezone_name = TIMEZONE_FINDER.timezone_at(lat=lat, lng=lon)
    return ZoneInfo(timezone_name) if timezone_name else None


def sunshine_details_for_date(
    lat,
    lon,
    date,
    horizon_profile,
    time_zone=datetime.timezone.utc,
    step_minutes=STEP_MINUTES_DEFAULT,
):
    """Return effective duration and first/last sunshine instants for a local date."""
    day_start = datetime.datetime(date.year, date.month, date.day, tzinfo=time_zone)
    next_day_start = day_start + datetime.timedelta(days=1)
    day_start_utc = day_start.astimezone(datetime.timezone.utc)
    day_end_utc = next_day_start.astimezone(datetime.timezone.utc)
    visible_minutes = 0
    first_sunshine = None
    last_sunshine = None
    minutes_in_day = int((day_end_utc - day_start_utc).total_seconds() // 60)
    for minute in range(0, minutes_in_day, step_minutes):
        moment = day_start_utc + datetime.timedelta(minutes=minute)
        if not _may_be_sunny(lat, lon, moment):
            continue
        azimuth, altitude = _solar_position(lat, lon, moment)
        if altitude <= 0:
            continue
        horizon_angle = _horizon_angle_at(horizon_profile, azimuth % 360)
        if altitude > horizon_angle:
            visible_minutes += step_minutes
            if first_sunshine is None:
                first_sunshine = moment.astimezone(time_zone)
            last_sunshine = (moment + datetime.timedelta(minutes=step_minutes)).astimezone(time_zone)
    return datetime.timedelta(minutes=visible_minutes), first_sunshine, last_sunshine


def sunshine_duration_for_date(
    lat,
    lon,
    date,
    horizon_profile,
    time_zone=datetime.timezone.utc,
    step_minutes=STEP_MINUTES_DEFAULT,
):
    """Return effective sunshine duration for a local date, accounting for terrain."""
    duration, _, _ = sunshine_details_for_date(
        lat,
        lon,
        date,
        horizon_profile,
        time_zone,
        step_minutes,
    )
    return duration


def monthly_sunshine(lat, lon, year, horizon_profile, step_minutes=STEP_MINUTES_DEFAULT):
    """Return a list of (date, duration) for the first day of each month of the given year."""
    results = []
    for month in range(1, 13):
        first_of_month = datetime.date(year, month, 1)
        duration = sunshine_duration_for_date(lat, lon, first_of_month, horizon_profile, step_minutes)
        results.append((first_of_month, duration))
    return results


def daily_sunshine_details(
    lat,
    lon,
    year,
    horizon_profile,
    time_zone,
    step_minutes=STEP_MINUTES_DEFAULT,
):
    """Return daily duration and first/last sunshine instants for every local day in year."""
    first_day = datetime.date(year, 1, 1)
    last_day = datetime.date(year + 1, 1, 1)
    results = []
    for offset in range((last_day - first_day).days):
        day = first_day + datetime.timedelta(days=offset)
        duration, first_sunshine, last_sunshine = sunshine_details_for_date(
            lat,
            lon,
            day,
            horizon_profile,
            time_zone,
            step_minutes,
        )
        results.append((day, duration, first_sunshine, last_sunshine))
    return results


def daily_sunshine(
    lat,
    lon,
    year,
    horizon_profile,
    time_zone=datetime.timezone.utc,
    step_minutes=STEP_MINUTES_DEFAULT,
):
    """Return a list of (date, duration) for every day in year."""
    return [
        (day, duration)
        for day, duration, _, _ in daily_sunshine_details(
            lat,
            lon,
            year,
            horizon_profile,
            time_zone,
            step_minutes,
        )
    ]


def format_duration(duration):
    """Format a timedelta as 'Xh YYmin'."""
    total_minutes = int(duration.total_seconds() // 60)
    hours, minutes = divmod(total_minutes, 60)
    return f'{hours}h {minutes:02d}min'
