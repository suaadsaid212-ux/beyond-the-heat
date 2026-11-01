"""NASA FIRMS area API with safe credentials and reproducible observations."""
from datetime import date, datetime, timedelta, timezone
from io import BytesIO, StringIO
import json
import math
from urllib.parse import quote

import pandas as pd
import requests

BASE_URL = 'https://firms.modaps.eosdis.nasa.gov'
AREA_DOCS = BASE_URL + '/api/area/'
AVAILABILITY_DOCS = BASE_URL + '/api/data_availability/'
FAQ = 'https://www.earthdata.nasa.gov/data/tools/firms/faq'
SOURCES = {
    'VIIRS_NOAA20_NRT': 'VIIRS NOAA 20: recent observations',
    'VIIRS_NOAA21_NRT': 'VIIRS NOAA 21: recent observations',
    'MODIS_NRT': 'MODIS: recent observations',
    'VIIRS_NOAA20_SP': 'VIIRS NOAA 20: standard processing',
    'VIIRS_NOAA21_SP': 'VIIRS NOAA 21: standard processing',
    'MODIS_SP': 'MODIS: standard processing',
}
MAX_RESPONSE_BYTES = 20 * 1024 * 1024
ATTRIBUTION = ('NASA FIRMS, part of NASA EOSDIS: MODIS and VIIRS active fire '
               'and thermal anomaly observations. Retain the source product and version.')


class FIRMSError(RuntimeError):
    """A user safe error without a credential bearing request URL."""


def _csv_request(map_key, path_template, required):
    if not isinstance(map_key, str) or not map_key.strip():
        raise FIRMSError('Configure FIRMS_MAP_KEY in Streamlit Secrets first.')
    key = map_key.strip()
    url = BASE_URL + path_template.replace('[MAP_KEY]', quote(key, safe=''))
    response = None
    try:
        response = requests.get(url, timeout=(10, 35), stream=True, allow_redirects=False)
        if response.status_code in (401, 403):
            raise FIRMSError('NASA FIRMS rejected the MAP key. Check FIRMS_MAP_KEY in Streamlit Secrets.')
        if response.status_code == 429:
            raise FIRMSError('NASA FIRMS transaction limit reached. Wait before trying again.')
        if response.status_code != 200:
            raise FIRMSError(f'NASA FIRMS returned HTTP {response.status_code}. Check product availability and try again later.')
        chunks, size = [], 0
        for chunk in response.iter_content(chunk_size=65536):
            size += len(chunk)
            if size > MAX_RESPONSE_BYTES:
                raise FIRMSError('This response is too large. Choose a smaller area or fewer days.')
            chunks.append(chunk)
        text = b''.join(chunks).decode('utf-8-sig')
    except requests.RequestException:
        raise FIRMSError('NASA FIRMS could not be reached. Please try again later.') from None
    except UnicodeError:
        raise FIRMSError('NASA FIRMS returned an unreadable response.') from None
    finally:
        if response is not None:
            response.close()
    # Some provider errors use HTTP 200. Do not expose their raw message or URL.
    if key in text:
        raise FIRMSError('NASA FIRMS did not return a usable data response. Check the MAP key and query.')
    first = text.lstrip().splitlines()[0].lower() if text.strip() else ''
    if ('invalid' in first and any(word in first for word in ('map_key', 'map key', 'mapkey'))):
        raise FIRMSError('NASA FIRMS rejected the MAP key. Check FIRMS_MAP_KEY in Streamlit Secrets.')
    try:
        raw = pd.read_csv(StringIO(text), dtype=str)
    except (pd.errors.ParserError, pd.errors.EmptyDataError, ValueError):
        raise FIRMSError('NASA FIRMS did not return a data CSV. Check the product, dates and key.') from None
    if not set(required).issubset(raw.columns):
        raise FIRMSError('NASA FIRMS did not return the expected data columns. Check the product, dates and key.')
    return raw


def _source(source):
    if source not in SOURCES:
        raise ValueError('Choose one of the supported NASA FIRMS products.')
    return source


def data_availability(map_key, source='VIIRS_NOAA20_NRT'):
    source = _source(source)
    return _csv_request(map_key, f'/api/data_availability/csv/[MAP_KEY]/{source}',
                        ['data_id', 'min_date', 'max_date'])


def _validated_query(source, bbox, days, start_date):
    _source(source)
    if not isinstance(days, int) or isinstance(days, bool) or not 1 <= days <= 5:
        raise ValueError('The FIRMS Area API supports 1 to 5 days per query.')
    try:
        coordinates = tuple(float(value) for value in bbox)
    except (TypeError, ValueError):
        raise ValueError('Enter four numeric bounding box coordinates.') from None
    if len(coordinates) != 4 or not all(math.isfinite(value) for value in coordinates):
        raise ValueError('Enter four finite bounding box coordinates.')
    west, south, east, north = coordinates
    if not (-180 <= west < east <= 180 and -90 <= south < north <= 90):
        raise ValueError('Use west < east and south < north within valid longitude and latitude bounds. Split areas crossing the date line into separate queries.')
    start = None
    if start_date is not None:
        try:
            start = date.fromisoformat(str(start_date))
        except ValueError:
            raise ValueError('Start date must use YYYY-MM-DD.') from None
        if start + timedelta(days=days - 1) > datetime.now(timezone.utc).date():
            raise ValueError('Choose an observation period ending no later than today in UTC.')
    return coordinates, start


def fetch_hotspots(map_key, *, source='VIIRS_NOAA20_NRT',
                   bbox=(52., 16., 60.1, 26.5), days=1, start_date=None):
    """Retrieve one product and preserve raw attributes, including zero detections."""
    coordinates, start = _validated_query(source, bbox, days, start_date)
    area = ','.join(format(value, '.6f').rstrip('0').rstrip('.') for value in coordinates)
    template = f'/api/area/csv/[MAP_KEY]/{source}/{area}/{days}'
    if start is not None:
        template += '/' + start.isoformat()
    raw = _csv_request(map_key, template, ['latitude', 'longitude', 'acq_date', 'acq_time'])
    retrieved = datetime.now(timezone.utc).isoformat()
    query = {
        'source': source, 'bbox_west_south_east_north': list(coordinates),
        'days': days, 'date_mode': 'explicit_start' if start is not None else 'latest_days',
        'start_date_utc': start.isoformat() if start is not None else None,
        'end_date_utc': (start + timedelta(days=days - 1)).isoformat() if start is not None else None,
        'request_template': BASE_URL + template,
        'retrieved_at_utc': retrieved, 'source_url': AREA_DOCS,
    }
    normalized = raw.copy()
    normalized['latitude_numeric'] = pd.to_numeric(raw['latitude'], errors='coerce')
    normalized['longitude_numeric'] = pd.to_numeric(raw['longitude'], errors='coerce')
    normalized['coordinate_valid'] = (normalized['latitude_numeric'].between(-90, 90)
                                      & normalized['longitude_numeric'].between(-180, 180))
    west, south, east, north = coordinates
    normalized['within_query_bbox'] = (normalized['latitude_numeric'].between(south, north)
                                       & normalized['longitude_numeric'].between(west, east))
    times = raw['acq_time'].astype('string').str.strip()
    times = times.where(times.str.fullmatch(r'\d{1,4}', na=False)).str.zfill(4)
    observed = pd.to_datetime(raw['acq_date'].astype('string') + ' ' + times,
                              format='%Y-%m-%d %H%M', errors='coerce', utc=True)
    normalized['observed_at_utc'] = observed.dt.strftime('%Y-%m-%dT%H:%M:%SZ')
    normalized['frp_mw'] = pd.to_numeric(raw.get('frp', pd.Series(index=raw.index, dtype=str)),
                                         errors='coerce')
    normalized['source_product'] = source
    normalized['retrieved_at_utc'] = retrieved
    normalized['source_url'] = AREA_DOCS
    normalized['confidence_meaning'] = ('MODIS detection confidence, percent' if source.startswith('MODIS')
                                        else 'VIIRS detection confidence: l=low, n=nominal, h=high')
    return {'raw': raw, 'observations': normalized, 'query': query}


def hotspot_figures(observations, source):
    """Figures use all observations and label counts as detections, not fire events."""
    import plotly.express as px
    figures = {}
    valid = observations[observations['coordinate_valid'] & observations['within_query_bbox']].copy()
    if not valid.empty:
        hover = [field for field in ['observed_at_utc', 'confidence', 'frp_mw', 'satellite']
                 if field in valid]
        figure = px.scatter(valid, x='longitude_numeric', y='latitude_numeric', hover_data=hover,
                            color='confidence' if 'confidence' in valid else None,
                            labels={'longitude_numeric': 'Longitude (degrees east)',
                                    'latitude_numeric': 'Latitude (degrees north)'},
                            title=f'Satellite thermal detections | {source}')
        figure.update_yaxes(scaleanchor='x', scaleratio=1)
        figures['Hotspot coordinates'] = figure
    dates = pd.to_datetime(observations['observed_at_utc'], errors='coerce', utc=True)
    if dates.notna().any():
        counts = dates.dropna().dt.strftime('%Y-%m-%d').value_counts().sort_index()
        counts = counts.rename_axis('UTC observation date').reset_index(name='Satellite detections')
        figures['Detections by date'] = px.bar(counts, x='UTC observation date', y='Satellite detections',
                                               title=f'Detection records by observation date | {source}')
    return figures


def hotspot_excel(snapshot):
    output = BytesIO()
    notes = {
        'attribution': ATTRIBUTION, 'documentation': AREA_DOCS, 'interpretation': FAQ,
        'query_json': json.dumps(snapshot['query'], ensure_ascii=False),
        'count_meaning': 'Detected thermal pixels, not unique fires, burned area or confirmed wildfires',
        'confidence': 'VIIRS uses l/n/h categories; MODIS uses percentages. These are not interchangeable.',
        'frp': 'Fire radiative power is in megawatts (MW), not energy or burned area.',
        'brightness': 'Brightness temperatures are in kelvins, not local air temperature.',
        'sampling': 'Missing detections can reflect cloud, overpass timing, sensor limitations or outages.',
        'model': 'Context only; these observations do not automatically change EMNRI.',
        'processing': 'NRT products are provisional; use standard processing when appropriate for research.',
    }
    with pd.ExcelWriter(output, engine='xlsxwriter', engine_kwargs={
            'options': {'strings_to_formulas': False, 'strings_to_urls': False}}) as writer:
        snapshot['observations'].to_excel(writer, sheet_name='Thermal detections', index=False)
        snapshot['raw'].to_excel(writer, sheet_name='Original NASA fields', index=False)
        pd.DataFrame(notes.items(), columns=['field', 'value']).to_excel(
            writer, sheet_name='Provenance and units', index=False)
        for sheet in writer.sheets.values():
            sheet.freeze_panes(1, 0)
            sheet.set_column(0, 30, 23)
    return output.getvalue()
