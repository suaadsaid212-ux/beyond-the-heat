from io import BytesIO
import json
from pathlib import Path
import zipfile

import pandas as pd
import pytest
import requests

from src import firms

VIIRS_CSV = (
    'latitude,longitude,bright_ti4,scan,track,acq_date,acq_time,satellite,instrument,confidence,version,bright_ti5,frp,daynight\n'
    '23.5,58.4,320.5,0.4,0.4,2026-01-01,0004,N20,VIIRS,n,2.0NRT,290.1,0,N\n'
    '23.6,58.5,330.5,0.4,0.4,2026-01-01,19,N20,VIIRS,h,2.0NRT,292.1,8.5,N\n'
)
HEADER = VIIRS_CSV.splitlines()[0] + '\n'


def response(text=VIIRS_CSV, status=200):
    class Response:
        status_code = status
        closed = False

        def iter_content(self, chunk_size):
            data = text.encode('utf-8')
            for i in range(0, len(data), chunk_size):
                yield data[i:i+chunk_size]

        def close(self):
            self.closed = True
    return Response()


@pytest.fixture
def snapshot(monkeypatch):
    monkeypatch.setattr(firms.requests, 'get', lambda *a, **k: response())
    return firms.fetch_hotspots('private-test-value', start_date='2026-01-01')


def test_area_request_and_download_metadata_do_not_publish_key(monkeypatch):
    calls = []

    def request(url, **kwargs):
        calls.append((url, kwargs))
        return response()
    monkeypatch.setattr(firms.requests, 'get', request)
    result = firms.fetch_hotspots('private-test-value', bbox=(52, 16, 60.1, 26.5),
                                  days=2, start_date='2026-01-01')
    assert calls[0][0].endswith('/private-test-value/VIIRS_NOAA20_NRT/52,16,60.1,26.5/2/2026-01-01')
    assert calls[0][1]['allow_redirects'] is False
    assert 'private-test-value' not in json.dumps(result['query'])
    assert '[MAP_KEY]' in result['query']['request_template']
    assert result['query']['end_date_utc'] == '2026-01-02'
    assert 'private-test-value' not in result['observations'].to_csv(index=False)


def test_hhmm_leading_zeros_units_and_original_fields_are_preserved(snapshot):
    frame = snapshot['observations']
    assert snapshot['raw'].loc[0, 'acq_time'] == '0004'
    assert snapshot['raw'].loc[1, 'acq_time'] == '19'
    assert frame.loc[0, 'observed_at_utc'] == '2026-01-01T00:04:00Z'
    assert frame.loc[1, 'observed_at_utc'] == '2026-01-01T00:19:00Z'
    assert frame.loc[0, 'frp_mw'] == 0
    assert frame.loc[1, 'frp_mw'] == 8.5
    assert list(frame['confidence']) == ['n', 'h']
    assert frame['confidence_meaning'].str.contains('VIIRS').all()
    assert frame['within_query_bbox'].all()


@pytest.mark.parametrize('kwargs', [
    {'days': 0}, {'days': 6}, {'days': True}, {'source': 'UNKNOWN'},
    {'bbox': (60, 16, 52, 26)}, {'bbox': (52, 27, 60, 16)},
    {'bbox': (52, float('nan'), 60, 26)}, {'bbox': (52, 16, 190, 26)},
    {'start_date': '2099-01-01'}, {'start_date': '2026/01/01'},
])
def test_invalid_query_never_reaches_provider(monkeypatch, kwargs):
    def unexpected(*args, **kwargs):
        raise AssertionError('Invalid input must not use a NASA transaction')
    monkeypatch.setattr(firms.requests, 'get', unexpected)
    with pytest.raises(ValueError):
        firms.fetch_hotspots('test', **kwargs)


@pytest.mark.parametrize('text,status', [
    ('Invalid MAP_KEY', 200), ('<html>maintenance</html>', 200),
    ('', 403), ('', 429), ('', 503), ('private-test-value', 200),
])
def test_provider_errors_never_become_empty_success_or_leak_keys(monkeypatch, text, status):
    monkeypatch.setattr(firms.requests, 'get', lambda *a, **k: response(text, status))
    with pytest.raises(firms.FIRMSError) as caught:
        firms.fetch_hotspots('private-test-value')
    assert 'private-test-value' not in str(caught.value)


def test_request_exception_does_not_expose_credential_url(monkeypatch):
    def broken(*args, **kwargs):
        raise requests.ConnectionError('https://host/area/private-test-value/VIIRS')
    monkeypatch.setattr(firms.requests, 'get', broken)
    with pytest.raises(firms.FIRMSError) as caught:
        firms.fetch_hotspots('private-test-value')
    assert 'private-test-value' not in str(caught.value)


def test_header_only_csv_is_valid_empty_observation_result(monkeypatch):
    monkeypatch.setattr(firms.requests, 'get', lambda *a, **k: response(HEADER))
    result = firms.fetch_hotspots('test')
    assert result['raw'].empty and result['observations'].empty
    assert 'observed_at_utc' in result['observations']
    assert firms.hotspot_figures(result['observations'], result['query']['source']) == {}
    assert firms.hotspot_excel(result).startswith(b'PK')


def test_response_size_limit_rejects_data_instead_of_truncating(monkeypatch):
    monkeypatch.setattr(firms, 'MAX_RESPONSE_BYTES', 25)
    monkeypatch.setattr(firms.requests, 'get', lambda *a, **k: response())
    with pytest.raises(firms.FIRMSError, match='too large'):
        firms.fetch_hotspots('test')


def test_invalid_coordinates_and_times_remain_visible_for_review(monkeypatch):
    csv = VIIRS_CSV.replace('23.5,58.4', '123,58.4').replace('0004', '2460')
    monkeypatch.setattr(firms.requests, 'get', lambda *a, **k: response(csv))
    result = firms.fetch_hotspots('test')
    assert not result['observations'].loc[0, 'coordinate_valid']
    assert pd.isna(result['observations'].loc[0, 'observed_at_utc'])
    assert result['raw'].loc[0, 'acq_time'] == '2460'
    assert len(result['observations']) == 2


def test_modis_confidence_is_not_converted_to_viirs_categories(monkeypatch):
    csv = VIIRS_CSV.replace(',n,2.0NRT', ',75,6.1NRT').replace(',h,2.0NRT', ',99,6.1NRT')
    monkeypatch.setattr(firms.requests, 'get', lambda *a, **k: response(csv))
    result = firms.fetch_hotspots('test', source='MODIS_NRT')
    assert list(result['observations']['confidence']) == ['75', '99']
    assert result['observations']['confidence_meaning'].str.contains('percent').all()


def test_availability_requires_the_documented_schema(monkeypatch):
    csv = 'data_id,min_date,max_date\nVIIRS_NOAA20_NRT,2026-08-01,2026-11-01\n'
    monkeypatch.setattr(firms.requests, 'get', lambda *a, **k: response(csv))
    frame = firms.data_availability('test')
    assert frame.loc[0, 'max_date'] == '2026-11-01'


def test_figures_count_detection_records_and_excel_retains_source(snapshot):
    figures = firms.hotspot_figures(snapshot['observations'], snapshot['query']['source'])
    assert sum(figures['Detections by date'].data[0].y) == 2
    assert len(figures['Hotspot coordinates'].data) == 2
    workbook = firms.hotspot_excel(snapshot)
    with zipfile.ZipFile(BytesIO(workbook)) as archive:
        names = archive.read('xl/workbook.xml').decode()
        assert all(name in names for name in ['Thermal detections', 'Original NASA fields',
                                              'Provenance and units'])
        text = archive.read('xl/sharedStrings.xml').decode()
        assert 'private-test-value' not in text
        assert '[MAP_KEY]' in text
        assert 'megawatts' in text


def _panel():
    from src.fire_hotspots import render_fire_hotspots
    render_fire_hotspots()


def test_panel_success_empty_and_error_clear_previous_results(monkeypatch, snapshot):
    from streamlit.testing.v1 import AppTest
    from src import fire_hotspots
    monkeypatch.setattr(fire_hotspots, '_configured_key', lambda: 'test')
    calls = []

    def fetch(*args, **kwargs):
        calls.append(1)
        if len(calls) == 1:
            return snapshot
        if len(calls) == 2:
            return {**snapshot, 'raw': snapshot['raw'].iloc[:0],
                    'observations': snapshot['observations'].iloc[:0]}
        raise firms.FIRMSError('NASA FIRMS transaction limit reached.')
    monkeypatch.setattr(fire_hotspots, 'fetch_hotspots', fetch)
    app = AppTest.from_function(_panel, default_timeout=20).run()
    next(b for b in app.button if b.label == 'Fetch NASA fire hotspots').click().run()
    assert not app.exception
    assert len(app.dataframe) == 1
    assert len(app.get('plotly_chart')) == 1
    assert len(app.get('download_button')) == 3
    next(b for b in app.button if b.label == 'Fetch NASA fire hotspots').click().run()
    assert not app.exception
    assert not app.dataframe
    assert any('no satellite detections' in item.value for item in app.info)
    next(b for b in app.button if b.label == 'Fetch NASA fire hotspots').click().run()
    assert not app.exception
    assert not app.dataframe
    assert not app.get('download_button')
    assert any('transaction limit' in item.value for item in app.error)


def test_full_app_with_firms_unconfigured(monkeypatch):
    from streamlit.testing.v1 import AppTest
    from src import air_quality, exports, fire_hotspots
    monkeypatch.setattr(air_quality, '_configured_key', lambda: '')
    monkeypatch.setattr(fire_hotspots, '_configured_key', lambda: '')
    monkeypatch.setattr(exports, 'figure_png', lambda *a, **k: b'png-test')
    app = AppTest.from_file(Path(__file__).resolve().parents[1] / 'app.py', default_timeout=45).run()
    assert not app.exception
    assert any('To enable NASA FIRMS' in item.value for item in app.info)
