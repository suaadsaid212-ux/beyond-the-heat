"""Prepare official Google Trends keyword links and truthful CSV chart data."""
from datetime import date, datetime, timezone
from urllib.parse import urlencode

import pandas as pd

REGIONS = {'Oman': 'OM', 'Worldwide': '', 'United States': 'US', 'United Kingdom': 'GB',
           'Russia': 'RU', 'United Arab Emirates': 'AE', 'Saudi Arabia': 'SA',
           'India': 'IN', 'France': 'FR', 'Germany': 'DE', 'Australia': 'AU',
           'Canada': 'CA', 'Brazil': 'BR'}


def prepare_keyword_search(text, region, start, end):
    terms, seen = [], set()
    for line in str(text or '').splitlines():
        term = ' '.join(line.split())
        if not term:
            continue
        if ',' in term or len(term) > 100:
            raise ValueError('Enter one keyword or phrase per line, without commas, using up to 100 characters each.')
        if term.casefold() not in seen:
            terms.append(term)
            seen.add(term.casefold())
    if not 1 <= len(terms) <= 5:
        raise ValueError('Enter between one and five keywords or phrases, one per line.')
    if region not in REGIONS:
        raise ValueError('Choose an available Google Trends region.')
    try:
        first, last = date.fromisoformat(str(start)), date.fromisoformat(str(end))
    except (ValueError, TypeError):
        raise ValueError('Choose valid Google Trends start and end dates.') from None
    if first < date(2004, 1, 1) or last > datetime.now(timezone.utc).date() or first > last:
        raise ValueError('Choose an ordered date range between January 2004 and today.')
    params = {'hl': 'en', 'q': ','.join(terms), 'date': f'{first.isoformat()} {last.isoformat()}'}
    if REGIONS[region]:
        params['geo'] = REGIONS[region]
    return {'terms': terms, 'region': region, 'geo': REGIONS[region],
            'start_date': first.isoformat(), 'end_date': last.isoformat(),
            'url': 'https://trends.google.com/trends/explore?'+urlencode(params),
            'prepared_at_utc': datetime.now(timezone.utc).isoformat(),
            'status': 'Official search link prepared; keyword data not fetched by the app'}


def chart_values(frame):
    """Keep suppressed and missing values as chart gaps, with no imputation."""
    if 'date' not in frame or len(frame.columns) < 2:
        raise ValueError('Import an Interest over time CSV with dates and at least one keyword column.')
    chart = pd.DataFrame(index=frame['date'].astype(str))
    suppressed = 0
    for column in frame.columns[1:]:
        raw = frame[column].astype(str).str.strip()
        suppressed += int(raw.eq('<1').sum())
        values = pd.to_numeric(raw.replace({'<1': None, '': None, 'nan': None}), errors='coerce')
        invalid = values.notna() & ~values.between(0, 100)
        unknown = values.isna() & ~raw.isin(['<1', '', 'nan', 'N/A', 'NA'])
        if invalid.any() or unknown.any():
            raise ValueError('Keyword interest values must be from 0 to 100, blank, or the reported <1 marker.')
        chart[column] = values.to_numpy()
    if not chart.notna().any().any():
        raise ValueError('This CSV contains no numeric keyword observations to chart. Original rows can still be inspected.')
    chart.index.name = 'date'
    return chart, suppressed


def keyword_claim_query(search):
    region = search['region']
    return search['terms'][0] + ('' if region == 'Worldwide' else ' '+region)
