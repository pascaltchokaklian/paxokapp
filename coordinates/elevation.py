"""Horizon profile computation using elevation samples around a point."""
import math
import time

import requests
from django.core.cache import cache

OPEN_METEO_ELEVATION_URL = 'https://api.open-meteo.com/v1/elevation'
OPEN_TOPO_DATA_ELEVATION_URL = 'https://api.opentopodata.org/v1/aster30m'
EARTH_RADIUS_KM = 6371.0
REQUEST_TIMEOUT_SECONDS = 15
ELEVATION_BATCH_SIZE = 100
MAX_ELEVATION_REQUEST_ATTEMPTS = 3
ELEVATION_RETRY_DELAY_SECONDS = 1


def _destination_point(lat, lon, bearing_deg, distance_km):
    """Compute the lat/lon reached from (lat, lon) travelling distance_km along bearing_deg."""
    lat1 = math.radians(lat)
    lon1 = math.radians(lon)
    bearing = math.radians(bearing_deg)
    angular_distance = distance_km / EARTH_RADIUS_KM

    lat2 = math.asin(
        math.sin(lat1) * math.cos(angular_distance)
        + math.cos(lat1) * math.sin(angular_distance) * math.cos(bearing)
    )
    lon2 = lon1 + math.atan2(
        math.sin(bearing) * math.sin(angular_distance) * math.cos(lat1),
        math.cos(angular_distance) - math.sin(lat1) * math.sin(lat2),
    )
    return math.degrees(lat2), math.degrees(lon2)


def _fetch_elevations(locations):
    """Fetch elevations from Open-Meteo in bounded batches of coordinates."""
    elevations = []
    for start in range(0, len(locations), ELEVATION_BATCH_SIZE):
        batch = locations[start:start + ELEVATION_BATCH_SIZE]
        request_params = {
            'latitude': ','.join(str(location['latitude']) for location in batch),
            'longitude': ','.join(str(location['longitude']) for location in batch),
        }
        for attempt in range(MAX_ELEVATION_REQUEST_ATTEMPTS):
            try:
                response = requests.get(
                    OPEN_METEO_ELEVATION_URL,
                    params=request_params,
                    timeout=REQUEST_TIMEOUT_SECONDS,
                )
                response.raise_for_status()
                batch_elevations = response.json()['elevation']
                break
            except requests.RequestException as error:
                status_code = error.response.status_code if error.response is not None else None
                is_transient = status_code is None or status_code == 429 or status_code >= 500
                if not is_transient or attempt == MAX_ELEVATION_REQUEST_ATTEMPTS - 1:
                    batch_elevations = _fetch_open_topo_data_elevations(batch)
                    break
                time.sleep(ELEVATION_RETRY_DELAY_SECONDS * (attempt + 1))
        if (
            not isinstance(batch_elevations, list)
            or len(batch_elevations) != len(batch)
            or any(isinstance(value, bool) or not isinstance(value, (int, float)) for value in batch_elevations)
        ):
            raise ValueError('Invalid elevation response')
        elevations.extend(batch_elevations)
    return elevations


def _fetch_open_topo_data_elevations(locations):
    """Fetch a batch of elevations from the fallback OpenTopoData provider."""
    response = requests.get(
        OPEN_TOPO_DATA_ELEVATION_URL,
        params={
            'locations': '|'.join(
                f"{location['latitude']},{location['longitude']}" for location in locations
            ),
        },
        timeout=REQUEST_TIMEOUT_SECONDS,
    )
    response.raise_for_status()
    results = response.json()['results']
    elevations = [result['elevation'] for result in results]
    if (
        len(elevations) != len(locations)
        or any(isinstance(value, bool) or not isinstance(value, (int, float)) for value in elevations)
    ):
        raise ValueError('Invalid fallback elevation response')
    return elevations


def get_elevation_profile(lat, lon, radius_km=40, n_azimuths=36, n_distances=16):
    """Return (horizon_profile, error).

    horizon_profile maps azimuth in degrees (0, 10, 20, ...) to the maximum
    horizon elevation angle in degrees observed around the point, based on
    terrain elevation samples fetched from the Open-Meteo elevation API.
    On failure, horizon_profile is None and error contains a user-facing message.
    """
    cache_key = f'horizon_profile:{round(lat, 4)}:{round(lon, 4)}:{radius_km}:{n_azimuths}:{n_distances}'
    cached = cache.get(cache_key)
    if cached is not None:
        return cached, None

    azimuths = [i * (360 / n_azimuths) for i in range(n_azimuths)]
    # Nearby terrain (a ridge a few hundred metres away) has much more impact on the
    # horizon angle than distant terrain, so samples are denser close to the point
    # (quadratic spacing) rather than evenly spaced, which would miss close ridges.
    distances = [radius_km * ((i + 1) / n_distances) ** 2 for i in range(n_distances)]

    locations = [{'latitude': lat, 'longitude': lon}]
    sample_points = []
    for azimuth in azimuths:
        for distance in distances:
            sample_lat, sample_lon = _destination_point(lat, lon, azimuth, distance)
            sample_points.append((azimuth, distance))
            locations.append({'latitude': sample_lat, 'longitude': sample_lon})

    try:
        elevations = _fetch_elevations(locations)
    except (requests.RequestException, ValueError, KeyError, TypeError):
        return None, "Impossible de récupérer les données de relief (service d'altitude indisponible)."

    origin_elevation = elevations[0]
    horizon_profile = {azimuth: -90.0 for azimuth in azimuths}
    for (azimuth, distance_km), elevation in zip(sample_points, elevations[1:]):
        elevation_diff = elevation - origin_elevation
        distance_m = distance_km * 1000
        angle = math.degrees(math.atan2(elevation_diff, distance_m))
        if angle > horizon_profile[azimuth]:
            horizon_profile[azimuth] = angle

    cache.set(cache_key, horizon_profile, timeout=3600)
    return horizon_profile, None
