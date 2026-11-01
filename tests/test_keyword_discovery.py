from datetime import date
from io import BytesIO
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

import pandas as pd
import pytest

from src.data_connectors import parse_trends_csv
from src.trends_search import chart_values, keyword_claim_query, prepare_keyword_search


def test_keyword_link_preserves_terms_country_dates_and_unicode():
    result = prepare_keyword_search('heat stress\nموجة حر\nHeat stress', 'Oman', '2024-01-01', '2024-12-31')
    params = parse_qs(urlsplit(result['url']).query)
    assert result['terms'] == ['heat stress', 'موجة حر']
    assert params == {'hl': ['en'], 'q': ['heat stress,موجة حر'],
                      'date': ['2024-01-01 2024-12-31'], 'geo': ['OM']}
    assert 'not fetched' in result['status']
    assert keyword_claim_query(result) == 'heat stress Oman'
    worldwide = prepare_keyword_search('water & health', 'Worldwide', '2024-01-01', '2024-12-31')
    assert 'geo' not in parse_qs(urlsplit(worldwide['url']).query)
    assert parse_qs(urlsplit(worldwide['url']).query)['q'] == ['water & health']
    assert keyword_claim_query(worldwide) == 'water & health'


@pytest.mark.parametrize('text,region,start,end', [
    ('', 'Oman', '2024-01-01', '2024-12-31'),
    ('one,two', 'Oman', '2024-01-01', '2024-12-31'),
    ('a\nb\nc\nd\ne\nf', 'Oman', '2024-01-01', '2024-12-31'),
    ('a'*101, 'Oman', '2024-01-01', '2024-12-31'),
    ('heat', 'Unknown', '2024-01-01', '2024-12-31'),
    ('heat', 'Oman', '2024-12-31', '2024-01-01'),
    ('heat', 'Oman', '2003-12-01', '2024-01-01'),
    ('heat', 'Oman', '2024-01-01', '2099-01-01'),
])
def test_invalid_keyword_search_is_rejected(text, region, start, end):
    with pytest.raises(ValueError):
        prepare_keyword_search(text, region, start, end)


def test_csv_preserves_suppressed_values_and_chart_never_imputes_them():
    raw = b'Category: All categories\n\nWeek,heat stress: (Oman)\n2024-01-01,100\n2024-01-08,<1\n2024-01-15,0\n'
    frame = parse_trends_csv(BytesIO(raw))
    assert list(frame.iloc[:, 1]) == ['100', '<1', '0']
    chart, suppressed = chart_values(frame)
    assert suppressed == 1
    assert chart.iloc[0, 0] == 100
    assert pd.isna(chart.iloc[1, 0])
    assert chart.iloc[2, 0] == 0
    assert '<1' in frame.to_csv(index=False)


@pytest.mark.parametrize('text', ['Region,heat\nOman,100\n', 'Day,heat\n', 'Day\n2024-01-01\n'])
def test_non_time_series_or_empty_csv_is_rejected(text):
    with pytest.raises(ValueError):
        parse_trends_csv(BytesIO(text.encode()))


@pytest.mark.parametrize('values', [['101'], ['-1'], ['unknown'], ['<1', '']])
def test_invalid_or_entirely_suppressed_chart_has_no_fake_observations(values):
    frame = pd.DataFrame({'date': ['2024-01-01']*len(values), 'heat': values})
    with pytest.raises(ValueError):
        chart_values(frame)


def search_snapshot(query):
    from test_source_search import result_record
    return {'results': [result_record()], 'query': query, 'provider': 'Test news index',
            'retrieved_at': '2026-11-01T00:00:00Z'}


def test_keyword_bar_opens_find_claims_searches_once_and_saves_source_passage(monkeypatch):
    from streamlit.testing.v1 import AppTest
    from src import source_workspace
    calls = []

    def search(query, *args):
        calls.append(query)
        return search_snapshot(query)
    monkeypatch.setattr(source_workspace, '_search', search)
    app = AppTest.from_file(Path(__file__).resolve().parents[1]/'app.py', default_timeout=30).run()
    app.switch_page('views/environment.py').run()
    next(item for item in app.text_input if item.label == 'Find claims by keyword').set_value('heat stress Oman')
    next(item for item in app.button if item.label == 'Find claims').click().run()
    assert not app.exception
    assert calls == ['heat stress Oman']
    assert next(item for item in app.text_input if item.label == 'Keywords to find claims').value == 'heat stress Oman'
    assert any('Candidate statement to inspect' in item.value for item in app.markdown)
    # Acknowledge the destination after st.switch_page so later AppTest widget
    # events use the destination page hash, as the browser navigation does.
    app.switch_page('views/source_search.py').run()
    next(item for item in app.button if item.label == 'Capture a claim from this result').click().run()
    assert not app.exception
    next(item for item in app.button if item.label == 'Save claim and source link').click().run()
    assert not app.exception and len(app.session_state['claim_corpus']) == 1
    assert app.session_state['claim_corpus'][0]['source_url'] == 'https://example.org/article'
    assert app.session_state['claim_corpus'][0]['review_status'] == 'Unreviewed'
    assert calls == ['heat stress Oman']


def test_preparing_trends_keywords_does_not_fetch_data_and_can_find_news_claims(monkeypatch):
    from streamlit.testing.v1 import AppTest
    from src import source_workspace, trends_workspace
    calls = []

    def unexpected(*args, **kwargs):
        pytest.fail('Preparing a Trends link must not fetch RSS or claim keyword data')
    monkeypatch.setattr(trends_workspace, 'google_trends_rss', unexpected)
    monkeypatch.setattr(source_workspace, '_search', lambda query, *args: calls.append(query) or search_snapshot(query))
    app = AppTest.from_file(Path(__file__).resolve().parents[1]/'app.py', default_timeout=30).run()
    app.switch_page('views/environment.py').run()
    next(item for item in app.text_area if item.label == 'Google Trends keywords, one per line').set_value('heat stress\nموجة حر')
    next(item for item in app.date_input if item.label == 'Keyword interest start date').set_value(date(2024, 1, 1))
    next(item for item in app.date_input if item.label == 'Keyword interest end date').set_value(date(2024, 12, 31))
    next(item for item in app.button if item.label == 'Prepare Google Trends keyword search').click().run()
    assert not app.exception and not calls
    assert app.session_state['trends_keyword_search']['terms'] == ['heat stress', 'موجة حر']
    assert any('have not been fetched automatically' in item.value for item in app.info)
    next(item for item in app.button if item.label == 'Find news claims using the first keyword').click().run()
    assert not app.exception and calls == ['heat stress Oman']


def test_public_url_capture_form_is_inside_reader_tab(monkeypatch):
    from hashlib import sha256
    from streamlit.testing.v1 import AppTest
    from src import source_workspace
    from test_source_search import _workspace
    text = 'Heat research requires documented evidence and careful assessment of the exact claim under review.'
    monkeypatch.setattr(source_workspace, 'read_source', lambda url: {
        'url': url, 'text': text, 'text_kind': 'Original source text', 'text_sha256': sha256(text.encode()).hexdigest(),
        'retrieved_at': '2026-11-01T00:00:00Z', 'partial': False})
    app = AppTest.from_function(_workspace, default_timeout=20).run()
    next(item for item in app.text_input if item.label == 'Public source URL').set_value('https://example.org/report')
    next(item for item in app.button if item.label == 'Read this public source').click().run()
    assert not app.exception
    assert not app.tabs[0].text_area
    assert any(item.label == 'Source passage to retain' for item in app.tabs[1].text_area)
    assert not app.tabs[2].text_area
