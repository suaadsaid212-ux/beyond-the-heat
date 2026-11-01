from pathlib import Path

import pandas as pd

from src.definitions import DEFINITIONS, explain
from src.evidence import apply_coding
from src.scoring import FIELDS

APP = Path(__file__).resolve().parents[1] / 'app.py'


def test_navigation_opens_separate_pages_and_searchable_glossary(monkeypatch):
    from streamlit.testing.v1 import AppTest
    from src import air_quality, exports, fire_hotspots
    monkeypatch.setattr(air_quality, '_configured_key', lambda: '')
    monkeypatch.setattr(fire_hotspots, '_configured_key', lambda: '')
    monkeypatch.setattr(exports, 'figure_png', lambda *a, **k: b'png-test')
    app = AppTest.from_file(APP, default_timeout=45).run()
    assert not app.exception
    assert any('Search sources and collect claims' in item.value for item in app.header)
    assert not app.metric
    app.switch_page('views/methodology.py').run()
    assert not app.exception
    assert any('Scientific methodology' in item.value for item in app.header)
    next(item for item in app.text_input if item.label == 'Find a definition or abbreviation').set_value('FRP').run()
    assert not app.exception
    assert app.dataframe[0].value['Term or symbol'].tolist() == ['FRP', 'MW']
    assert 'Fire Radiative Power' in app.dataframe[0].value['Full name or meaning'].tolist()
    assert any('FRP: Fire Radiative Power' in item.value for item in app.markdown)
    app.switch_page('views/environment.py').run()
    assert not app.exception
    assert any('Live environmental' in item.value for item in app.header)
    assert not any(item.label == 'Search sources now' for item in app.button)
    app.switch_page('views/analysis.py').run()
    assert not app.exception
    assert app.metric[0].value == '80'
    assert not any(item.label == 'Search sources now' for item in app.button)


def test_retained_upload_and_weights_survive_page_navigation(monkeypatch):
    from streamlit.testing.v1 import AppTest
    from src import exports
    monkeypatch.setattr(exports, 'figure_png', lambda *a, **k: b'png-test')
    frame = pd.DataFrame([{**dict.fromkeys(FIELDS, .5), 'date': '2026-01-01'},
                          {**dict.fromkeys(FIELDS, .6), 'date': '2026-01-02'}])
    app = AppTest.from_file(APP, default_timeout=45).run()
    app.session_state['analysis_uploaded_bytes'] = frame.to_csv(index=False).encode()
    app.switch_page('views/analysis.py').run()
    assert not app.exception and app.metric[0].value == '2'
    next(item for item in app.slider if item.label == 'Amplification weight').set_value(.6).run()
    assert app.session_state['analysis_weights'][0] == .6
    app.switch_page('views/methodology.py').run()
    app.switch_page('views/analysis.py').run()
    assert not app.exception and app.metric[0].value == '2'
    assert next(item for item in app.slider if item.label == 'Amplification weight').value == .6


def test_analyse_saved_claims_navigates_and_preserves_selection(monkeypatch):
    from streamlit.testing.v1 import AppTest
    from src import exports
    from test_source_search import captured
    monkeypatch.setattr(exports, 'figure_png', lambda *a, **k: b'png-test')
    reviewed = apply_coding(captured(), dict.fromkeys(FIELDS, .5), 'Protocol', 'Evidence', 'Reviewed')
    app = AppTest.from_file(APP, default_timeout=45)
    app.session_state['claim_corpus'] = [reviewed]
    app.run()
    next(item for item in app.button if item.label == 'Analyse my reviewed claims').click().run()
    assert not app.exception and app.metric[0].value == '1'
    app.switch_page('views/methodology.py').run()
    app.switch_page('views/analysis.py').run()
    assert not app.exception and app.metric[0].value == '1'
    assert next(item for item in app.checkbox if item.label == 'Analyse my reviewed collected claims').value


def test_formula_and_observation_terms_have_distinct_meanings():
    for term in ['EMNRI', 'ECR', 'A', 'H', 'ICC', 'PNSI', 'AQI', 'FIRMS', 'VIIRS', 'MODIS', 'NRT', 'FRP', 'UTC']:
        assert term in DEFINITIONS
        assert len(explain(term)) > 30
    assert 'independently coded' in explain('ECR')
    assert 'excluded from EMNRI' in explain('Political framing')
    assert 'Fire Radiative Power' in explain('FRP')
