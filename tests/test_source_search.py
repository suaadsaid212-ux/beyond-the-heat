from datetime import datetime, timedelta, timezone
from email.utils import format_datetime
from io import BytesIO
import json
import socket
import zipfile

import pandas as pd
import pytest
import requests

from src import evidence, source_reader, source_search
from src.exports import excel_bytes
from src.scoring import FIELDS, Weights, score_records


def reply(data, status=200):
    class Response:
        status_code = status
        closed = False

        def iter_content(self, size):
            yield data

        def close(self):
            self.closed = True
    return Response()


def news_item(title, url='https://news.google.com/articles/example', domain='https://www.who.int', age=1):
    stamp = format_datetime(datetime.now(timezone.utc)-timedelta(days=age))
    return f'<item><title>{title}</title><link>{url}</link><pubDate>{stamp}</pubDate><source url="{domain}">World Health Organization</source></item>'


def rss(*items):
    return ('<rss><channel>'+''.join(items)+'</channel></rss>').encode()


def result_record():
    return {'title': 'Heat exposure has increased in this region.',
            'excerpt': 'Heat exposure has increased in this region.',
            'excerpt_kind': 'News headline', 'url': 'https://example.org/article',
            'publisher': 'Example source', 'published_at': '2026-10-30T12:00:00+00:00',
            'retrieved_at': '2026-11-01T00:00:00+00:00', 'provider': 'Test index',
            'query': 'heat', 'country_focus': 'Oman'}


def captured():
    document = evidence.document_from_result(result_record())
    return evidence.capture_claim(document, 'Heat exposure has increased.', document['text'],
                                  country='Oman', language='en', topic='Extreme heat')


def test_news_scope_dates_duplicates_and_query_provenance(monkeypatch):
    calls = []
    response = reply(rss(news_item('Heat and health'), news_item('Heat and health'),
                         news_item('Wrong domain', domain='https://who.int.example.org'),
                         news_item('Old story', age=50)))

    def get(url, **kwargs):
        calls.append((url, kwargs))
        return response
    monkeypatch.setattr(source_search.requests, 'get', get)
    found = source_search.search_sources('heat', country='Oman', scope='WHO', language='العربية')
    assert response.closed
    assert len(found['results']) == 1
    row = found['results'][0]
    assert row['excerpt_kind'] == 'News headline'
    assert row['excerpt'] == row['title']
    assert row['edition_language'] == 'ar'
    assert 'heat Oman site:who.int when:30d' == found['query']
    assert calls[0][1]['params']['ceid'] == 'SA:ar'
    assert row['retrieved_at'] and row['published_at']
    assert all(field not in row for field in FIELDS)


def test_crossref_title_abstract_date_precision_and_type(monkeypatch):
    requests_seen = []
    payload = {'message': {'items': [
        {'title': ['Heat research'], 'URL': 'https://doi.org/10.test/one', 'publisher': 'Publisher',
         'published': {'date-parts': [[2024]]}, 'type': 'posted-content',
         'abstract': '<jats:p>Evidence &amp; uncertainty are discussed.</jats:p>',
         'DOI': '10.test/one', 'license': [{'URL': 'https://example.org/license'}]},
        {'title': ['Heat paper without abstract'], 'URL': 'https://doi.org/10.test/two',
         'published': {'date-parts': [[2025, 7]]}},
        {'title': ['Unrelated research'], 'URL': 'https://doi.org/10.test/unrelated'},
        None, {'title': [], 'URL': 'javascript:alert(1)'},
    ]}}
    def get(*args, **kwargs):
        requests_seen.append(kwargs['params'])
        return reply(json.dumps(payload).encode())
    monkeypatch.setattr(source_search.requests, 'get', get)
    found = source_search.search_sources('heat', provider=source_search.PROVIDERS[1])['results']
    assert len(found) == 2
    assert found[0]['published_at'] == '2024'
    assert found[1]['published_at'] == '2025-07'
    assert found[0]['excerpt'] == 'Evidence & uncertainty are discussed.'
    assert found[0]['publication_type'] == 'posted-content'
    assert found[1]['excerpt_kind'] == 'Research title only'
    assert requests_seen[0] == {'query.bibliographic': 'heat', 'rows': 60}
    document = evidence.document_from_result(found[0])
    assert evidence.capture_claim(document, document['text'], document['text'])['date'] == ''


@pytest.mark.parametrize('data,status', [(b'<html>blocked</html>', 200), (b'', 429), (b'', 503)])
def test_search_error_is_not_empty_success(monkeypatch, data, status):
    response = reply(data, status)
    monkeypatch.setattr(source_search.requests, 'get', lambda *a, **k: response)
    with pytest.raises(source_search.SourceSearchError):
        source_search.search_sources('heat')
    assert response.closed


def test_search_network_errors_are_sanitised(monkeypatch):
    def unavailable(*args, **kwargs):
        raise requests.ConnectionError('private connection detail')
    monkeypatch.setattr(source_search.requests, 'get', unavailable)
    with pytest.raises(source_search.SourceSearchError, match='could not be reached') as error:
        source_search.search_sources('heat')
    assert 'private connection' not in str(error.value)


@pytest.mark.parametrize('kwargs', [{'query': ''}, {'query': 'x'}, {'limit': True},
    {'limit': 31}, {'days': 91}, {'provider': 'other'}, {'country': None},
    {'provider': source_search.PROVIDERS[1], 'scope': 'WHO'}])
def test_invalid_search_never_calls_network(monkeypatch, kwargs):
    def unexpected(*a, **k):
        pytest.fail('Invalid queries must not contact a provider')
    monkeypatch.setattr(source_search.requests, 'get', unexpected)
    with pytest.raises(ValueError):
        source_search.search_sources(**{'query': 'heat', **kwargs})


def test_capture_preserves_passage_and_leaves_indicators_missing():
    record = captured()
    assert record['source_passage'] == result_record()['excerpt']
    assert record['date'] == '2026-10-30'
    assert record['source_text_sha256']
    assert record['review_status'] == 'Unreviewed'
    assert all(record[field] is None for field in FIELDS)
    assert not evidence.ready_for_analysis(record)
    assert evidence.analysis_claims([record]).empty
    with pytest.raises(ValueError, match='copied'):
        evidence.capture_claim(evidence.document_from_result(result_record()), 'Invented claim', 'Invented quotation')


def test_candidates_are_verbatim_and_claim_deduplication():
    text = 'This sentence describes unrelated soil research. Heat exposure increased during the summer months.\n\nAnother long paragraph describes rain.'
    passages = evidence.candidate_passages(text, 'heat exposure')
    assert passages[0] == 'Heat exposure increased during the summer months.'
    assert all(passage in text for passage in passages)
    corpus = []
    assert evidence.add_claim(corpus, captured())
    assert not evidence.add_claim(corpus, captured())
    assert len(corpus) == 1


def test_review_gate_and_original_formula():
    record = captured()
    scores = dict(zip(FIELDS, [0.2, 0.6, 0.8, 0.3, 0.9]))
    reviewed = evidence.apply_coding(record, scores, 'Protocol v1', 'Independent evidence assessment', 'Reviewed')
    assert evidence.ready_for_analysis(reviewed)
    assert not evidence.ready_for_analysis({**reviewed, 'coding_protocol': ''})
    assert not evidence.ready_for_analysis({**reviewed, 'political_framing': None})
    assert not evidence.ready_for_analysis({**reviewed, 'review_status': 'In review'})
    frame = evidence.analysis_claims([record, reviewed])
    assert len(frame) == 1
    score = score_records(frame, Weights(.33, .33, .34)).iloc[0]['emnri']
    assert score == pytest.approx(100*.8*(.33*.6+.33*.8+.34*.7))
    assert record['claim_reliability'] is None


@pytest.mark.parametrize('value', [-1, 1.1, 'unknown', float('nan'), float('inf')])
def test_invalid_coding_is_rejected(value):
    with pytest.raises(ValueError):
        evidence.apply_coding(captured(), {FIELDS[0]: value}, '', '', 'Reviewed')


def test_restore_round_trip_retains_missing_values_and_validates_entire_batch():
    record = captured()
    corpus = []
    data = pd.DataFrame([record, record]).to_csv(index=False).encode('utf-8-sig')
    assert evidence.restore_corpus(BytesIO(data), corpus) == 1
    assert all(corpus[0][field] is None for field in FIELDS)
    assert corpus[0]['coded_at'] == ''
    assert evidence.restore_corpus(BytesIO(data), corpus) == 0
    invalid = pd.DataFrame([record, {**record, 'source_url': 'javascript:alert(1)'}]).to_csv(index=False).encode()
    empty = []
    with pytest.raises(ValueError):
        evidence.restore_corpus(BytesIO(invalid), empty)
    assert empty == []


def test_workbook_retains_unicode_and_never_executes_source_text():
    record = {**captured(), 'claim': '=HYPERLINK("https://example.org", "claim")',
              'source_passage': 'الحرارة والبيئة'}
    reviewed = evidence.apply_coding(record, dict.fromkeys(FIELDS, .5), 'Protocol', 'Evidence', 'Reviewed')
    for workbook in [evidence.evidence_excel([record], [{'query': 'heat Oman'}]),
                     excel_bytes(score_records(pd.DataFrame([reviewed])), Weights())]:
        with zipfile.ZipFile(BytesIO(workbook)) as archive:
            sheets = ''.join(archive.read(name).decode() for name in archive.namelist() if name.startswith('xl/worksheets/') and name.endswith('.xml'))
            assert '<f>' not in sheets
            assert 'الحرارة والبيئة' in archive.read('xl/sharedStrings.xml').decode()


@pytest.mark.parametrize('url', ['http://example.org', 'https://localhost/a',
    'https://127.0.0.1/', 'https://169.254.169.254/', 'https://internal.local/',
    'https://user:password@example.org/', 'https://example.org:8443/',
    'https://example.org/?api_key=secret', 'file:///etc/passwd'])
def test_reader_rejects_unsafe_destination_before_dns(monkeypatch, url):
    def unexpected(*a, **k):
        pytest.fail('Unsafe URLs must not resolve or connect')
    monkeypatch.setattr(source_reader.socket, 'getaddrinfo', unexpected)
    with pytest.raises(source_reader.SourceReadError):
        source_reader._destination(url)


def test_reader_rejects_mixed_public_private_dns(monkeypatch):
    monkeypatch.setattr(source_reader.socket, 'getaddrinfo', lambda *a, **k: [
        (socket.AF_INET, socket.SOCK_STREAM, 6, '', ('8.8.8.8', 443)),
        (socket.AF_INET, socket.SOCK_STREAM, 6, '', ('10.0.0.1', 443))])
    with pytest.raises(source_reader.SourceReadError, match='public internet'):
        source_reader._destination('https://example.org/')


def test_redirect_is_validated_and_public_connection_is_pinned(monkeypatch):
    from urllib.parse import urlsplit
    destinations, connections = [], []

    def destination(url):
        destinations.append(url)
        if urlsplit(url).hostname == 'internal.local':
            raise source_reader.SourceReadError('Private redirect blocked')
        return urlsplit(url), 'example.org', ['8.8.8.8']

    class Connection:
        def __init__(self, host, **kwargs):
            self.sock = None

        def request(self, *args, **kwargs):
            connections.append((args, kwargs))

        def getresponse(self):
            class Redirect:
                status = 302

                def getheader(self, key, default=None):
                    return 'https://internal.local/secrets' if key == 'Location' else default
            return Redirect()

        def close(self):
            pass

    class Context:
        def wrap_socket(self, raw, server_hostname):
            assert raw == ('8.8.8.8', 443)
            assert server_hostname == 'example.org'
            return raw

    monkeypatch.setattr(source_reader, '_destination', destination)
    monkeypatch.setattr(source_reader.http.client, 'HTTPSConnection', Connection)
    monkeypatch.setattr(source_reader.socket, 'create_connection', lambda address, **kwargs: address)
    monkeypatch.setattr(source_reader.ssl, 'create_default_context', Context)
    with pytest.raises(source_reader.SourceReadError, match='Private redirect'):
        source_reader._public_document('https://example.org/article')
    assert destinations == ['https://example.org/article', 'https://internal.local/secrets']
    assert len(connections) == 1
    assert connections[0][1]['headers']['Host'] == 'example.org'


def test_reader_html_and_provenance(monkeypatch):
    paragraph = 'Heat exposure can vary with location, timing and environmental conditions. Inspect the original evidence before interpreting this passage. '
    body = ('<html><body><article><h1>Heat study</h1><p>'+paragraph*4+'</p></article></body></html>').encode()
    monkeypatch.setattr(source_reader, '_public_document', lambda url: (body, 'text/html', 'https://example.org/final'))
    document = source_reader.read_source('https://example.org/start')
    assert paragraph.strip() in document['text']
    assert document['url'] == 'https://example.org/final'
    assert document['requested_url'] == 'https://example.org/start'
    assert document['text_sha256'] and document['retrieved_at']
    assert '<article>' not in document['text']


def test_pdf_selectable_text_and_page_provenance():
    from pypdf import PdfWriter
    from pypdf.generic import DecodedStreamObject, DictionaryObject, NameObject
    writer = PdfWriter()
    page = writer.add_blank_page(width=600, height=800)
    font = DictionaryObject({NameObject('/Type'): NameObject('/Font'),
        NameObject('/Subtype'): NameObject('/Type1'), NameObject('/BaseFont'): NameObject('/Helvetica')})
    page[NameObject('/Resources')] = DictionaryObject({NameObject('/Font'): DictionaryObject({NameObject('/F1'): writer._add_object(font)})})
    stream = DecodedStreamObject()
    sentence = 'Heat exposure research requires careful interpretation of source evidence and measurement limitations.'
    stream.set_data(f'BT /F1 12 Tf 40 700 Td ({sentence}) Tj ET'.encode())
    page[NameObject('/Contents')] = writer._add_object(stream)
    output = BytesIO()
    writer.write(output)
    text, kind, partial = source_reader.extract_document(output.getvalue(), 'application/pdf', 'https://example.org/report.pdf')
    assert sentence in text and '[Page 1]' in text
    assert kind == 'PDF source text' and not partial


@pytest.mark.parametrize('body,kind', [(b'%PDF-invalid', 'application/pdf'),
    (b'{"value":1}', 'application/json'), (b'<html>verify you are human</html>', 'text/html')])
def test_unreadable_documents_do_not_become_claim_text(body, kind):
    with pytest.raises(source_reader.SourceReadError):
        source_reader.extract_document(body, kind, 'https://example.org/')


def _workspace():
    from src.source_workspace import render_source_workspace
    render_source_workspace()


def button(app, label):
    return next(item for item in app.button if item.label == label)


def input_for(app, label):
    return next(item for item in app.text_input if item.label == label)


def test_search_capture_review_workflow_and_error_reset(monkeypatch):
    from streamlit.testing.v1 import AppTest
    from src import source_workspace
    calls = []

    def search(*args):
        calls.append(args)
        if len(calls) > 1:
            raise source_search.SourceSearchError('Search service unavailable')
        return {'results': [result_record()], 'query': 'heat Oman',
                'provider': 'Test index', 'retrieved_at': '2026-11-01T00:00:00+00:00'}
    monkeypatch.setattr(source_workspace, '_search', search)
    app = AppTest.from_function(_workspace, default_timeout=20).run()
    assert not app.exception and not calls
    input_for(app, 'Search topic, claim or organisation').set_value('heat Oman')
    button(app, 'Search sources now').click().run()
    assert not app.exception and len(app.dataframe) == 1
    button(app, 'Capture a claim from this result').click().run()
    assert not app.exception
    button(app, 'Save claim and source link').click().run()
    app.run()
    corpus = app.session_state['claim_corpus']
    assert len(corpus) == 1 and not evidence.ready_for_analysis(corpus[0])
    assert all(item.value is None for item in app.number_input)
    for item in app.number_input:
        item.set_value(.5)
    next(item for item in app.selectbox if item.label == 'Review status').select('Reviewed')
    input_for(app, 'Coding protocol or measurement definition').set_value('Protocol v1')
    next(item for item in app.text_area if item.label == 'Evidence and rationale for the coding').set_value('Independent evidence review')
    button(app, 'Save claim review').click().run()
    assert not app.exception
    assert evidence.ready_for_analysis(app.session_state['claim_corpus'][0])
    assert button(app, 'Analyse my reviewed claims')
    assert len(app.get('download_button')) >= 4
    button(app, 'Search sources now').click().run()
    assert not app.exception
    assert 'source_search_results' not in app.session_state
    assert any('Search service unavailable' in item.value for item in app.error)
    assert len(app.session_state['claim_corpus']) == 1


def test_reviewed_claims_flow_into_dashboard_without_synthetic_data(monkeypatch):
    from pathlib import Path
    from streamlit.testing.v1 import AppTest
    from src import air_quality, exports, fire_hotspots
    monkeypatch.setattr(air_quality, '_configured_key', lambda: '')
    monkeypatch.setattr(fire_hotspots, '_configured_key', lambda: '')
    monkeypatch.setattr(exports, 'figure_png', lambda *args, **kwargs: b'png-test')
    reviewed = evidence.apply_coding(captured(), dict.fromkeys(FIELDS, .5), 'Protocol', 'Evidence', 'Reviewed')
    app = AppTest.from_file(Path(__file__).resolve().parents[1] / 'app.py', default_timeout=45)
    app.session_state['claim_corpus'] = [captured(), reviewed]
    app.session_state['use_collected_claims'] = True
    app.run()
    assert not app.exception
    assert app.metric[0].value == '1'
    assert app.metric[1].value == '25.0 / 100'
    assert any('Analysing 1 collected claims' in item.value for item in app.info)
    assert not any('synthetic demonstration' in item.value.lower() for item in app.info)
