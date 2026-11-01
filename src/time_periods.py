"""Explicit date precision, inclusive periods and descriptive cohort summaries."""
from calendar import monthrange
from datetime import date, datetime, timezone
import re

import pandas as pd

FREQUENCIES = {'Daily': 'D', 'Weekly': 'W-SUN', 'Monthly': 'M'}


def date_bounds(start, end):
    try:
        first = start.date() if isinstance(start, datetime) else date.fromisoformat(str(start))
        last = end.date() if isinstance(end, datetime) else date.fromisoformat(str(end))
    except (ValueError, TypeError):
        raise ValueError('Choose valid start and end dates.') from None
    if first > last:
        raise ValueError('The start date must be on or before the end date.')
    if first.year < 1900 or last.year > 2100:
        raise ValueError('Choose dates between 1900 and 2100.')
    return first, last


def publication_span(value):
    """Return the entire stated date span without inventing daily precision."""
    value = str(value or '').strip()
    try:
        if re.fullmatch(r'\d{4}', value):
            year = int(value)
            return date(year, 1, 1), date(year, 12, 31)
        if re.fullmatch(r'\d{4}-\d{2}', value):
            year, month = map(int, value.split('-'))
            return date(year, month, 1), date(year, month, monthrange(year, month)[1])
        if re.fullmatch(r'\d{4}-\d{2}-\d{2}', value):
            day = date.fromisoformat(value)
            return day, day
        if re.match(r'^\d{4}-\d{2}-\d{2}[T ]', value):
            stamp = datetime.fromisoformat(value.replace('Z', '+00:00'))
            if stamp.tzinfo is not None:
                stamp = stamp.astimezone(timezone.utc)
            return stamp.date(), stamp.date()
    except (TypeError, ValueError, OverflowError):
        pass
    return None


def publication_in_period(value, start, end):
    span = publication_span(value)
    return bool(span and start <= span[0] and span[1] <= end)


def record_dates(frame):
    values = frame.get('date', pd.Series('', index=frame.index))
    # A year or month cannot enter a day or week bin without an explicit date.
    days = values.map(publication_span).map(lambda span: span[0] if span and span[0] == span[1] else None)
    return pd.to_datetime(days, errors='coerce', utc=True)


def filter_period(frame, start, end):
    first, last = date_bounds(start, end)
    dates = record_dates(frame)
    selected = dates.between(pd.Timestamp(first, tz='UTC'), pd.Timestamp(last, tz='UTC'))
    return frame.loc[selected].copy()


def period_summary(frame, frequency='Monthly', by_topic=False):
    if frequency not in FREQUENCIES:
        raise ValueError('Choose daily, weekly or monthly aggregation.')
    groups = ['period_start'] + (['topic'] if by_topic and 'topic' in frame else [])
    columns = [*groups, 'period_end', 'records', 'mean_emnri', 'mean_political_framing', 'mean_claim_reliability']
    dates = record_dates(frame)
    tmp = frame.loc[dates.notna()].copy()
    if tmp.empty:
        return pd.DataFrame(columns=columns)
    periods = dates.loc[dates.notna()].dt.tz_localize(None).dt.to_period(FREQUENCIES[frequency])
    tmp['period_start'] = periods.dt.start_time.dt.date
    tmp['period_end'] = periods.dt.end_time.dt.date
    summary = tmp.groupby(groups, dropna=False, as_index=False).agg(
        period_end=('period_end', 'first'), records=('emnri', 'size'),
        mean_emnri=('emnri', 'mean'), mean_political_framing=('political_framing', 'mean'),
        mean_claim_reliability=('claim_reliability', 'mean'))
    return summary[columns].sort_values(groups).reset_index(drop=True)


def compare_periods(frame, first_start, first_end, second_start, second_end):
    first_start, first_end = date_bounds(first_start, first_end)
    second_start, second_end = date_bounds(second_start, second_end)
    if first_end >= second_start:
        raise ValueError('The first period must end before the second period starts. Overlapping periods cannot be compared here.')
    rows = []
    for name, start, end in [('First period', first_start, first_end), ('Second period', second_start, second_end)]:
        subset = filter_period(frame, start, end)
        rows.append({'period': name, 'start_date': start.isoformat(), 'end_date': end.isoformat(),
                     'calendar_days': (end-start).days+1, 'records': len(subset),
                     'mean_emnri': subset['emnri'].mean(),
                     'mean_political_framing': subset['political_framing'].mean(),
                     'mean_claim_reliability': subset['claim_reliability'].mean()})
    return pd.DataFrame(rows)
