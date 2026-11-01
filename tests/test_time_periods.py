from datetime import date
from io import BytesIO
import json
import zipfile

import pandas as pd
import pytest

from src.evidence import capture_claim, document_from_result
from src.exports import excel_bytes
from src.scoring import FIELDS, Weights, score_records
from src import source_search
from src.time_periods import (
    compare_periods, date_bounds, filter_period, period_summary, publication_in_period,
    publication_span, record_dates,
)


def sample():
    return pd.DataFrame({
        'date': ['2026-01-01', '2026-01-02T23:59:00Z', '2026-01-03', '2026-01-04', '', '2026-01'],
        'emnri': [10., 30., 50., 70., 90., 90.],
        'political_framing': [.1, .3, .5, .7, .9, .9],
        'claim_reliability': [.9, .7, .5, .3, .1, .1],
    })


@pytest.mark.parametrize('value,expected', [
    ('2024', (date(2024, 1, 1), date(2024, 12, 31))),
    ('2024-02', (date(2024, 2, 1), date(2024, 2, 29))),
    ('2026-01-02', (date(2026, 1, 2), date(2026, 1, 2))),
    ('2026-01-02T00:30:00+04:00', (date(2026, 1, 1), date(2026, 1, 1))),
    ('2026-02-30', None), ('2026-13', None), ('', None), ('unknown', None),
])
def test_publication_precision_and_utc_dates(value, expected):
    assert publication_span(value) == expected


def test_partial_dates_require_entire_span_inside_search_period():
    assert publication_in_period('2024', date(2024, 1, 1), date(2024, 12, 31))
    assert not publication_in_period('2024', date(2024, 6, 1), date(2024, 12, 31))
    assert publication_in_period('2024-02', date(2024, 2, 1), date(2024, 2, 29))
    assert not publication_in_period('2024-02', date(2024, 2, 10), date(2024, 2, 29))


@pytest.mark.parametrize('start,end', [('2026-01-03', '2026-01-02'),
    (None, '2026-01-02'), ('not a date', '2026-01-02'), ('1800-01-01', '2026-01-02')])
def test_invalid_or_reversed_periods_are_rejected(start, end):
    with pytest.raises(ValueError):
        date_bounds(start, end)


def test_claim_filter_includes_end_of_last_day_and_rejects_unknown_dates():
    result = filter_period(sample(), '2026-01-01', '2026-01-02')
    assert list(result['emnri']) == [10., 30.]
    assert record_dates(sample()).isna().sum() == 2
    assert record_dates(pd.DataFrame({'date': ['', None, '2026']})).isna().all()
    assert record_dates(pd.DataFrame({'other': [1, 2]})).isna().all()


def test_period_summaries_do_not_impute_unknown_or_missing_months():
    frame = sample()
    monthly = period_summary(frame, 'Monthly')
    assert len(monthly) == 1
    assert monthly.iloc[0]['records'] == 4
    assert monthly.iloc[0]['mean_emnri'] == 40.
    assert monthly.iloc[0]['period_start'] == date(2026, 1, 1)
    assert monthly.iloc[0]['period_end'] == date(2026, 1, 31)
    assert period_summary(frame, 'Weekly').iloc[0]['period_start'] == date(2025, 12, 29)
    assert len(period_summary(frame, 'Daily')) == 4
    assert period_summary(frame.iloc[4:]).empty


def test_period_comparisons_are_disjoint_and_empty_period_is_missing():
    compared = compare_periods(sample(), '2026-01-01', '2026-01-02', '2026-01-03', '2026-01-04')
    assert list(compared['records']) == [2, 2]
    assert list(compared['mean_emnri']) == [20., 60.]
    assert list(compared['calendar_days']) == [2, 2]
    empty = compare_periods(sample(), '2025-01-01', '2025-12-31', '2026-01-01', '2026-01-04')
    assert empty.iloc[0]['records'] == 0
    assert pd.isna(empty.iloc[0]['mean_emnri'])
    with pytest.raises(ValueError, match='Overlapping'):
        compare_periods(sample(), '2026-01-01', '2026-01-03', '2026-01-03', '2026-01-04')


def response(data):
    class Response:
        status_code = 200

        def iter_content(self, size):
            yield data

        def close(self):
            pass
    return Response()


def test_news_custom_period_filters_provider_dates_and_keeps_search_provenance(monkeypatch):
    calls = []
    items = ''.join(f'<item><title>Heat report {day}</title><link>https://example.org/{index}</link><pubDate>{day}</pubDate></item>'
                    for index, day in enumerate(['Tue, 01 Oct 2024 00:00:00 GMT',
                        'Thu, 31 Oct 2024 23:59:00 GMT', 'Fri, 01 Nov 2024 00:00:00 GMT', 'unknown']))

    def get(url, **kwargs):
        calls.append(kwargs['params'])
        return response(('<rss><channel>'+items+'</channel></rss>').encode())
    monkeypatch.setattr(source_search.requests, 'get', get)
    found = source_search.search_sources('heat', start_date='2024-10-01', end_date='2024-10-31')
    assert len(found['results']) == 2
    assert 'after:2024-09-30 before:2024-11-01' in calls[0]['q']
    assert 'when:' not in calls[0]['q']
    assert found['start_date'] == '2024-10-01'
    assert found['results'][0]['search_end_date'] == '2024-10-31'


def test_crossref_custom_period_and_ambiguous_date_boundaries(monkeypatch):
    calls = []
    items = [{'title': ['Heat study'], 'URL': f'https://doi.org/10.test/{index}',
              'published': {'date-parts': [parts]}}
             for index, parts in enumerate([[2024], [2024, 2], [2024, 2, 29], [2024, 3, 1]])]

    def get(url, **kwargs):
        calls.append(kwargs['params'])
        return response(json.dumps({'message': {'items': items}}).encode())
    monkeypatch.setattr(source_search.requests, 'get', get)
    found = source_search.search_sources('heat', provider=source_search.PROVIDERS[1],
                                         start_date='2024-02-01', end_date='2024-02-29')
    assert [item['published_at'] for item in found['results']] == ['2024-02', '2024-02-29']
    assert calls[0]['filter'] == 'from-pub-date:2024-02-01,until-pub-date:2024-02-29'


def test_researcher_entered_publication_date_needs_evidence_and_never_uses_retrieval():
    document = document_from_result({'title': 'Heat research in this region.', 'excerpt_kind': 'Research title only',
        'url': 'https://example.org/report', 'published_at': '2024',
        'retrieved_at': '2026-11-01T00:00:00Z', 'search_start_date': '2024-01-01', 'search_end_date': '2024-12-31'})
    uncoded = capture_claim(document, document['text'], document['text'])
    assert uncoded['date'] == ''
    with pytest.raises(ValueError, match='Document where'):
        capture_claim(document, document['text'], document['text'], publication_date=date(2024, 2, 1))
    entered = capture_claim(document, document['text'], document['text'],
                             publication_date=date(2024, 2, 1), date_evidence='Report title page')
    assert entered['date'] == '2024-02-01' and entered['published_at'] == '2024'
    assert entered['date_basis'] == 'Researcher supplied source publication date'
    assert entered['search_start_date'] == '2024-01-01'
    assert all(entered[field] is None for field in FIELDS)


def test_period_exports_include_metadata_and_separate_sheets():
    frame = sample()
    weights = Weights()
    comparison = compare_periods(frame, '2026-01-01', '2026-01-02', '2026-01-03', '2026-01-04')
    workbook = excel_bytes(frame, weights, provenance={'analysis_period_start': '2026-01-01', 'period_endpoints': 'inclusive'},
                            time_summary=period_summary(frame), time_comparison=comparison)
    with zipfile.ZipFile(BytesIO(workbook)) as archive:
        xml = archive.read('xl/workbook.xml').decode()
        assert 'Period summary' in xml and 'Period comparison' in xml
        assert 'analysis_period_start' in archive.read('xl/sharedStrings.xml').decode()


def _time_panel():
    import pandas as pd
    import streamlit as st
    from src.period_workspace import select_analysis_period, render_time_analysis
    frame = pd.DataFrame({'date': ['2026-01-01', '2026-01-02', '2026-01-03', '2026-01-04', ''],
        'emnri': [10., 30., 50., 70., 90.], 'political_framing': [.1, .3, .5, .7, .9],
        'claim_reliability': [.9, .7, .5, .3, .1]})
    filtered, settings, frequency = select_analysis_period(frame)
    st.metric('Selected records', len(filtered))
    render_time_analysis(filtered, frequency, {})


def test_date_filter_and_period_comparison_ui():
    from streamlit.testing.v1 import AppTest
    app = AppTest.from_function(_time_panel, default_timeout=20).run()
    assert not app.exception and app.metric[0].value == '5'
    next(item for item in app.button if item.label == 'Compare selected periods').click().run()
    assert not app.exception
    assert app.metric[1].value == '+40.00'
    app.checkbox[0].check().run()
    next(item for item in app.date_input if item.label == 'Analysis start date').set_value(date(2026, 1, 2))
    next(item for item in app.date_input if item.label == 'Analysis end date').set_value(date(2026, 1, 3))
    app.run()
    assert not app.exception and app.metric[0].value == '2'
    assert any('1 records without a complete date excluded' in item.value for item in app.caption)


def test_custom_search_dates_reach_provider_from_ui(monkeypatch):
    from streamlit.testing.v1 import AppTest
    from src import source_workspace
    from test_source_search import _workspace
    received = []

    def search(*args):
        received.append(args)
        return {'results': [], 'query': args[0], 'provider': args[1], 'retrieved_at': '2026-11-01',
                'start_date': args[-2].isoformat(), 'end_date': args[-1].isoformat()}
    monkeypatch.setattr(source_workspace, '_search', search)
    app = AppTest.from_function(_workspace, default_timeout=20).run()
    next(item for item in app.selectbox if item.label == 'Publication period').select('Custom dates').run()
    next(item for item in app.text_input if item.label == 'Search topic, claim or organisation').set_value('heat')
    next(item for item in app.date_input if item.label == 'Source publication start date').set_value(date(2024, 1, 1))
    next(item for item in app.date_input if item.label == 'Source publication end date').set_value(date(2024, 12, 31))
    next(item for item in app.button if item.label == 'Search sources now').click().run()
    assert not app.exception
    assert received[0][-2:] == (date(2024, 1, 1), date(2024, 12, 31))
