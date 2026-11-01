"""OpenAQ v3 observations with explicit units, timestamps and source metadata."""
from datetime import datetime, timezone
from io import BytesIO
import json
import math
import re

import pandas as pd
import requests

BASE_URL = 'https://api.openaq.org/v3'
TIMEOUT = 18
LATEST_COLUMNS = [
    'location_id', 'station', 'sensor_id', 'parameter', 'units', 'value',
    'observed_at_utc', 'observed_at_local', 'age_hours_at_retrieval',
    'latitude', 'longitude', 'reported_country', 'reported_locality',
    'provider', 'owner', 'is_mobile', 'is_reference_monitor',
    'retrieved_at_utc', 'source_url', 'licenses_json',
]
LOCATION_COLUMNS = [
    'location_id', 'station', 'reported_country', 'reported_locality',
    'latitude', 'longitude', 'provider', 'owner', 'is_mobile',
    'is_reference_monitor', 'last_reported_utc', 'parameters',
    'licenses_json', 'source_url',
]


class OpenAQError(RuntimeError):
    """A safe message that never includes a credential or raw request headers."""


def _request(api_key, path, params=None):
    if not isinstance(api_key, str) or not api_key.strip():
        raise OpenAQError('Configure OPENAQ_API_KEY in Streamlit Secrets first.')
    try:
        response = requests.get(
            BASE_URL + path, params=params,
            headers={'X-API-Key': api_key.strip(), 'Accept': 'application/json'},
            timeout=TIMEOUT,
        )
    except requests.RequestException:
        raise OpenAQError('OpenAQ could not be reached. Please try again later.') from None
    if response.status_code in (401, 403):
        raise OpenAQError('OpenAQ rejected this key. Check the key in Streamlit Secrets.')
    if response.status_code == 429:
        raise OpenAQError('OpenAQ rate limit reached. Wait before trying again.')
    if response.status_code == 404:
        raise OpenAQError('This station is no longer available from OpenAQ.')
    if response.status_code != 200:
        raise OpenAQError(f'OpenAQ returned HTTP {response.status_code}. Please try again later.')
    try:
        payload = response.json()
    except ValueError:
        raise OpenAQError('OpenAQ returned an unreadable response.') from None
    if (not isinstance(payload, dict) or not isinstance(payload.get('results'), list)
            or not all(isinstance(row, dict) for row in payload['results'])):
        raise OpenAQError('OpenAQ returned an unexpected response format.')
    return payload


def search_locations(api_key, *, iso=None, coordinates=None, radius_m=25000,
                     page=1, limit=50):
    """Return one explicit results page, never a claimed complete country census."""
    if not isinstance(page, int) or isinstance(page, bool) or page < 1:
        raise ValueError('Page must be a positive integer.')
    if not isinstance(limit, int) or isinstance(limit, bool) or not 1 <= limit <= 1000:
        raise ValueError('Results per page must be between 1 and 1000.')
    params = {'page': page, 'limit': limit}
    if coordinates is not None:
        if iso is not None:
            raise ValueError('Choose either a country or coordinates.')
        if len(coordinates) != 2:
            raise ValueError('Supply latitude and longitude.')
        latitude, longitude = coordinates
        if (not math.isfinite(latitude) or not math.isfinite(longitude)
                or not -90 <= latitude <= 90 or not -180 <= longitude <= 180):
            raise ValueError('Latitude or longitude is invalid.')
        if not isinstance(radius_m, int) or not 1 <= radius_m <= 25000:
            raise ValueError('Search radius must be between 1 and 25000 metres.')
        params.update(coordinates=f'{latitude:.4f},{longitude:.4f}', radius=radius_m)
    else:
        country = str(iso or '').strip().upper()
        if not re.fullmatch(r'[A-Z]{2}', country):
            raise ValueError('Enter a two letter country code, such as OM, GB or US.')
        params['iso'] = country
    result = _request(api_key, '/locations', params)
    result['query'] = params
    result['retrieved_at_utc'] = datetime.now(timezone.utc).isoformat()
    return result


def locations_frame(locations):
    rows = []
    for item in locations:
        coordinates = item.get('coordinates') or {}
        sensors = item.get('sensors') or []
        rows.append({
            'location_id': item.get('id'), 'station': item.get('name'),
            'reported_country': (item.get('country') or {}).get('code'),
            'reported_locality': item.get('locality'),
            'latitude': coordinates.get('latitude'),
            'longitude': coordinates.get('longitude'),
            'provider': (item.get('provider') or {}).get('name'),
            'owner': (item.get('owner') or {}).get('name'),
            'is_mobile': item.get('isMobile'),
            'is_reference_monitor': item.get('isMonitor'),
            'last_reported_utc': (item.get('datetimeLast') or {}).get('utc'),
            'parameters': ', '.join(sorted({
                (s.get('parameter') or {}).get('displayName')
                or (s.get('parameter') or {}).get('name') or 'Unknown'
                for s in sensors
            })),
            'licenses_json': json.dumps(item.get('licenses') or [], ensure_ascii=False),
            'source_url': f"{BASE_URL}/locations/{item.get('id')}",
        })
    return pd.DataFrame(rows, columns=LOCATION_COLUMNS)


def fetch_latest(api_key, location):
    """Join readings to sensor metadata by ID; never guess or convert units."""
    location_id = location.get('id')
    if not isinstance(location_id, int) or isinstance(location_id, bool) or location_id < 1:
        raise ValueError('A valid OpenAQ station ID is required.')
    source_url = f'{BASE_URL}/locations/{location_id}/latest'
    # Page through this station only. Each additional page requires a full page.
    readings = []
    page_size = 1000
    for page in range(1, 11):
        payload = _request(api_key, f'/locations/{location_id}/latest',
                           {'limit': page_size, 'page': page})
        batch = payload['results']
        readings.extend(batch)
        if len(batch) < page_size:
            break
    else:
        raise OpenAQError('The station returned too many readings for one snapshot.')
    sensors = {sensor['id']: sensor for sensor in location.get('sensors') or []
               if sensor.get('id') is not None}
    retrieved = datetime.now(timezone.utc)
    rows = []
    for reading in readings:
        if reading.get('locationsId') not in (None, location_id):
            raise OpenAQError('OpenAQ returned a reading for a different station.')
        sensor_id = reading.get('sensorsId')
        parameter = (sensors.get(sensor_id) or {}).get('parameter') or {}
        timestamp = reading.get('datetime') or {}
        observed = pd.to_datetime(timestamp.get('utc'), errors='coerce', utc=True)
        age = None if pd.isna(observed) else (retrieved - observed).total_seconds() / 3600
        # Mobile locations use the reading's position, not the station's first point.
        coordinates = reading.get('coordinates') or {}
        if not location.get('isMobile'):
            coordinates = coordinates or location.get('coordinates') or {}
        rows.append({
            'location_id': location_id, 'station': location.get('name'),
            'sensor_id': sensor_id,
            'parameter': parameter.get('displayName') or parameter.get('name'),
            'units': parameter.get('units'), 'value': reading.get('value'),
            'observed_at_utc': timestamp.get('utc'),
            'observed_at_local': timestamp.get('local'),
            'age_hours_at_retrieval': age,
            'latitude': coordinates.get('latitude'),
            'longitude': coordinates.get('longitude'),
            'reported_country': (location.get('country') or {}).get('code'),
            'reported_locality': location.get('locality'),
            'provider': (location.get('provider') or {}).get('name'),
            'owner': (location.get('owner') or {}).get('name'),
            'is_mobile': location.get('isMobile'),
            'is_reference_monitor': location.get('isMonitor'),
            'retrieved_at_utc': retrieved.isoformat(), 'source_url': source_url,
            'licenses_json': json.dumps(location.get('licenses') or [], ensure_ascii=False),
        })
    frame = pd.DataFrame(rows, columns=LATEST_COLUMNS)
    frame['value'] = pd.to_numeric(frame['value'], errors='coerce')
    return frame


def snapshot_excel(readings, station, query):
    """Keep source attribution, licence periods and query provenance in exports."""
    output = BytesIO()
    notes = {
        'source': 'OpenAQ API v3 and the named original data provider',
        'content': 'Latest available sensor observations, not necessarily current conditions',
        'units': 'Original reported units; no conversion or AQI calculation',
        'country': 'Country and locality are provider reported metadata, not independently verified',
        'model': 'Context only; observations are not included automatically in EMNRI',
        'query_json': json.dumps(query, ensure_ascii=False),
        'source_url': f"{BASE_URL}/locations/{station['id']}/latest",
    }
    licences = pd.json_normalize(station.get('licenses') or [])
    if licences.empty:
        licences = pd.DataFrame({'note': ['The provider supplied no licence metadata. Verify reuse terms.']})
    with pd.ExcelWriter(output, engine='xlsxwriter', engine_kwargs={
            'options': {'strings_to_formulas': False, 'strings_to_urls': False}}) as writer:
        readings.to_excel(writer, index=False, sheet_name='Latest observations')
        locations_frame([station]).to_excel(writer, index=False, sheet_name='Station metadata')
        licences.to_excel(writer, index=False, sheet_name='Source licences')
        pd.DataFrame(notes.items(), columns=['field', 'value']).to_excel(
            writer, index=False, sheet_name='Provenance')
        for sheet in writer.sheets.values():
            sheet.freeze_panes(1, 0)
            sheet.set_column(0, 25, 23)
    return output.getvalue()
