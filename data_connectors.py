"""Optional external research data connectors. No fabricated fallback observations."""
from io import StringIO
import requests
import pandas as pd
import xml.etree.ElementTree as ET

TIMEOUT = 18

def open_meteo_history(latitude: float, longitude: float, start: str, end: str) -> pd.DataFrame:
    """Retrieve daily historical weather from Open-Meteo ERA5 archive."""
    response = requests.get('https://archive-api.open-meteo.com/v1/archive', params={
        'latitude': latitude, 'longitude': longitude, 'start_date': start,
        'end_date': end, 'daily': 'temperature_2m_max,temperature_2m_mean,precipitation_sum',
        'timezone': 'UTC'}, timeout=TIMEOUT)
    response.raise_for_status()
    data = response.json()
    if 'daily' not in data:
        raise ValueError(data.get('reason', 'No historical daily weather returned'))
    return pd.DataFrame(data['daily']).rename(columns={'time': 'date'})


def google_trends_rss(country: str = 'US') -> pd.DataFrame:
    """Retrieve current trending searches RSS, not topic-specific interest-over-time."""
    response = requests.get('https://trends.google.com/trending/rss',
                            params={'geo': country.upper()}, timeout=TIMEOUT,
                            headers={'User-Agent': 'BeyondTheHeatResearch/0.5 (academic research)'})
    response.raise_for_status()
    root = ET.fromstring(response.content)
    rows = []
    for item in root.findall('.//channel/item'):
        rows.append({'title': item.findtext('title'), 'published': item.findtext('pubDate'),
                     'link': item.findtext('link'), 'country': country.upper(),
                     'approx_traffic': next((el.text for el in item if el.tag.endswith('approx_traffic')), None)})
    return pd.DataFrame(rows, columns=['title','published','link','country','approx_traffic'])


def parse_trends_csv(uploaded) -> pd.DataFrame:
    """Read a Google Trends chart CSV including its optional explanatory header lines."""
    text = uploaded.getvalue().decode('utf-8-sig')
    lines = text.splitlines()
    first = next((i for i, line in enumerate(lines) if line.lower().startswith(('day,','week,','month,','date,','year,'))), None)
    if first is None:
        raise ValueError('Could not find a dated Google Trends CSV header. Export Interest over time as CSV.')
    df = pd.read_csv(StringIO('\n'.join(lines[first:])))
    df.rename(columns={df.columns[0]: 'date'}, inplace=True)
    return df
