from copy import deepcopy
from io import BytesIO
from pathlib import Path
import json
import zipfile

import pandas as pd
import pytest
import requests

from src import openaq


@pytest.fixture
def station():
    return {
        'id': 123, 'name': 'Test station', 'locality': 'Test locality',
        'country': {'code': 'GB'}, 'provider': {'name': 'Original provider'},
        'owner': {'name': 'Original owner'}, 'isMobile': False, 'isMonitor': True,
        'coordinates': {'latitude': 51.5, 'longitude': -0.1},
        'datetimeLast': {'utc': '2020-01-01T00:00:00Z'},
        'sensors': [{'id': 73, 'parameter': {'name': 'pm25', 'displayName': 'PM2.5',
                                           'units': 'µg/m³'}}],
        'licenses': [{'name': 'Test licence', 'dateFrom': '2019-01-01',
                      'dateTo': None, 'attribution': {'name': 'Original owner'}}],
    }


def reply(payload=None, status=200):
    class Response:
        status_code = status

        def json(self):
            return payload
    return Response()


def reading(sensor=73, value=0, location=123):
    return {'sensorsId': sensor, 'locationsId': location, 'value': value,
            'datetime': {'utc': '2020-01-01T00:00:00Z',
                         'local': '2020-01-01T00:00:00+00:00'},
            'coordinates': {'latitude': 51.51, 'longitude': -0.12}}


def test_authenticated_search_retains_query_without_secret(monkeypatch, station):
    calls = []

    def request(url, **kwargs):
        calls.append((url, kwargs))
        return reply({'results': [station], 'meta': {'page': 2, 'found': '>50'}})
    monkeypatch.setattr(openaq.requests, 'get', request)
    result = openaq.search_locations('private-test-value', iso='gb', page=2)
    assert calls[0][0] == 'https://api.openaq.org/v3/locations'
    assert calls[0][1]['headers']['X-API-Key'] == 'private-test-value'
    assert calls[0][1]['params'] == {'iso': 'GB', 'limit': 50, 'page': 2}
    assert 'private-test-value' not in json.dumps(result)
    assert result['query']['page'] == 2


@pytest.mark.parametrize('kwargs', [
    {'iso': 'Oman'}, {'iso': 'GB', 'page': 0}, {'iso': 'GB', 'limit': 1001},
    {'coordinates': (91, 0)}, {'coordinates': (0, 0), 'radius_m': 25001},
    {'coordinates': (0, 0), 'iso': 'OM'}, {'coordinates': (float('nan'), 0)},
])
def test_invalid_query_does_not_call_provider(monkeypatch, kwargs):
    def unexpected(*args, **kwargs):
        raise AssertionError('Invalid input must not reach OpenAQ')
    monkeypatch.setattr(openaq.requests, 'get', unexpected)
    with pytest.raises(ValueError):
        openaq.search_locations('test', **kwargs)


@pytest.mark.parametrize('status', [401, 403, 429, 502])
def test_provider_errors_are_safe(monkeypatch, status):
    monkeypatch.setattr(openaq.requests, 'get', lambda *a, **k: reply(status=status))
    with pytest.raises(openaq.OpenAQError) as caught:
        openaq.search_locations('private-test-value', iso='GB')
    assert 'private-test-value' not in str(caught.value)


def test_network_errors_do_not_expose_raw_exception(monkeypatch):
    def timeout(*args, **kwargs):
        raise requests.Timeout('A raw request containing private-test-value')
    monkeypatch.setattr(openaq.requests, 'get', timeout)
    with pytest.raises(openaq.OpenAQError) as caught:
        openaq.search_locations('private-test-value', iso='GB')
    assert 'private-test-value' not in str(caught.value)


def test_units_zero_missing_values_and_timestamps_are_preserved(monkeypatch, station):
    data = {'results': [reading(), reading(99, None), reading(73, -0.2)]}
    monkeypatch.setattr(openaq.requests, 'get', lambda *a, **k: reply(data))
    frame = openaq.fetch_latest('test', station)
    assert frame.iloc[0]['value'] == 0
    assert frame.iloc[0]['units'] == 'µg/m³'
    assert frame.iloc[0]['parameter'] == 'PM2.5'
    assert frame.iloc[0]['provider'] == 'Original provider'
    assert frame.iloc[0]['age_hours_at_retrieval'] > 24
    assert pd.isna(frame.iloc[1]['value'])
    assert pd.isna(frame.iloc[1]['units'])
    assert frame.iloc[2]['value'] == -0.2
    assert set(frame.columns) == set(openaq.LATEST_COLUMNS)


def test_mobile_station_does_not_substitute_first_coordinates(monkeypatch, station):
    station['isMobile'] = True
    row = reading()
    row['coordinates'] = None
    monkeypatch.setattr(openaq.requests, 'get', lambda *a, **k: reply({'results': [row]}))
    frame = openaq.fetch_latest('test', station)
    assert pd.isna(frame.iloc[0]['latitude'])
    assert pd.isna(frame.iloc[0]['longitude'])


def test_foreign_station_reading_is_rejected(monkeypatch, station):
    monkeypatch.setattr(openaq.requests, 'get',
                        lambda *a, **k: reply({'results': [reading(location=456)]}))
    with pytest.raises(openaq.OpenAQError, match='different station'):
        openaq.fetch_latest('test', station)


def test_latest_pagination_is_not_silently_truncated(monkeypatch, station):
    requested = []

    def request(*args, **kwargs):
        page = kwargs['params']['page']
        requested.append(page)
        return reply({'results': [reading()] * (1000 if page == 1 else 1)})
    monkeypatch.setattr(openaq.requests, 'get', request)
    assert len(openaq.fetch_latest('test', station)) == 1001
    assert requested == [1, 2]


def test_empty_snapshots_keep_schema(monkeypatch, station):
    monkeypatch.setattr(openaq.requests, 'get', lambda *a, **k: reply({'results': []}))
    frame = openaq.fetch_latest('test', station)
    assert frame.empty
    assert list(frame.columns) == openaq.LATEST_COLUMNS


def test_workbook_keeps_provenance_without_evaluating_source_text(monkeypatch, station):
    station['name'] = '=1+1'
    monkeypatch.setattr(openaq.requests, 'get',
                        lambda *a, **k: reply({'results': [reading()]}))
    frame = openaq.fetch_latest('test', station)
    workbook = openaq.snapshot_excel(frame, station, {'iso': 'GB', 'page': 1})
    with zipfile.ZipFile(BytesIO(workbook)) as archive:
        names = archive.read('xl/workbook.xml').decode()
        assert all(name in names for name in ['Latest observations', 'Station metadata',
                                              'Source licences', 'Provenance'])
        text = archive.read('xl/sharedStrings.xml').decode()
        assert '=1+1' in text
        assert 'Original provider' in text
        assert 'Test licence' in text
        assert 'source_url' in text
        for name in archive.namelist():
            if name.startswith('xl/worksheets/'):
                assert '<f>' not in archive.read(name).decode()


def _panel():
    from src.air_quality import render_air_quality
    render_air_quality()


def test_panel_clears_previous_data_on_empty_search(monkeypatch, station):
    from streamlit.testing.v1 import AppTest
    from src import air_quality
    monkeypatch.setattr(air_quality, '_configured_key', lambda: 'test')
    searches = []

    def search(*args, **kwargs):
        searches.append(1)
        return {'results': [deepcopy(station)] if len(searches) == 1 else [],
                'query': {'page': 1, 'limit': 50, 'iso': 'GB'},
                'retrieved_at_utc': '2026-11-01T00:00:00+00:00'}
    monkeypatch.setattr(air_quality, 'search_locations', search)
    monkeypatch.setattr(air_quality, 'fetch_latest',
                        lambda *a, **k: pd.DataFrame(columns=openaq.LATEST_COLUMNS))
    app = AppTest.from_function(_panel, default_timeout=20).run()
    assert not app.exception
    next(b for b in app.button if b.label == 'Find air quality stations').click().run()
    assert not app.exception
    assert len(app.dataframe) == 1
    next(b for b in app.button if b.label == 'Fetch latest air quality readings').click().run()
    assert not app.exception
    assert any('no latest readings' in item.value for item in app.info)
    next(b for b in app.button if b.label == 'Find air quality stations').click().run()
    assert not app.exception
    assert not app.dataframe
    assert any('No stations' in item.value for item in app.info)


def test_full_app_runs_with_openaq_unconfigured(monkeypatch):
    from streamlit.testing.v1 import AppTest
    from src import air_quality, exports
    monkeypatch.setattr(air_quality, '_configured_key', lambda: '')
    monkeypatch.setattr(exports, 'figure_png', lambda *a, **k: b'png-test')
    app = AppTest.from_file(Path(__file__).resolve().parents[1] / 'app.py', default_timeout=45).run()
    assert not app.exception
    assert any('To enable OpenAQ' in item.value for item in app.info)


def test_panel_renders_observations_chart_exports_and_licences(monkeypatch, station):
    from streamlit.testing.v1 import AppTest
    from src import air_quality
    monkeypatch.setattr(openaq.requests, 'get',
                        lambda *a, **k: reply({'results': [reading()]}))
    frame = openaq.fetch_latest('test', station)
    monkeypatch.setattr(air_quality, '_configured_key', lambda: 'test')
    monkeypatch.setattr(air_quality, 'search_locations', lambda *a, **k: {
        'results': [station], 'query': {'page': 1, 'limit': 50, 'iso': 'GB'},
        'retrieved_at_utc': '2026-11-01T00:00:00+00:00'})
    monkeypatch.setattr(air_quality, 'fetch_latest', lambda *a, **k: frame)
    app = AppTest.from_function(_panel, default_timeout=20).run()
    next(b for b in app.button if b.label == 'Find air quality stations').click().run()
    next(b for b in app.button if b.label == 'Fetch latest air quality readings').click().run()
    assert not app.exception
    assert len(app.dataframe) == 3
    assert len(app.get('plotly_chart')) == 1
    assert len(app.get('download_button')) == 3
    assert any('more than 24 hours old' in item.value for item in app.warning)
