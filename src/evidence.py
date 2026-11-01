"""Source linked claim capture and explicit researcher coding."""
from datetime import datetime, timezone
from hashlib import sha256
from io import BytesIO
import math
import re

import pandas as pd

from src.scoring import FIELDS
from src.source_search import public_link

CORPUS_FIELDS = [
    'claim_id', 'claim', 'source', 'source_url', 'source_title', 'source_passage',
    'passage_kind', 'source_text_sha256', 'published_at', 'date', 'retrieved_at',
    'country', 'language', 'topic', 'search_query', 'search_provider',
    'review_status', 'coding_protocol', 'coding_rationale', 'coded_at', *FIELDS,
]


def compact(text):
    return re.sub(r'\s+', ' ', str(text or '')).strip()


def document_from_result(result):
    text = result.get('excerpt') or result['title']
    return {**result, 'text': text, 'text_kind': result['excerpt_kind'],
            'partial': True, 'text_sha256': sha256(text.encode()).hexdigest()}


def candidate_passages(text, query='', limit=8):
    """Return source substrings; rank by word overlap without generating claims."""
    chunks = re.split(r'(?<=[.!?؟。])\s+|\n\s*\n', str(text or ''))
    tokens = set(re.findall(r'[^\W_]{3,}', query.lower(), re.UNICODE))
    found = []
    for index, chunk in enumerate(chunks):
        chunk = chunk.strip()
        if len(chunk) < 25:
            continue
        # A long source paragraph is an excerpt, not a reconstructed sentence.
        if len(chunk) > 1000:
            chunk = chunk[:1000].rsplit(' ', 1)[0]
        overlap = sum(token in chunk.lower() for token in tokens)
        if chunk not in [row[2] for row in found]:
            found.append((-overlap, index, chunk))
    if not found and compact(text):
        return [str(text).strip()[:1000]]
    return [row[2] for row in sorted(found)[:limit]]


def capture_claim(document, claim, passage, *, country='', language='', topic=''):
    claim, passage = compact(claim), compact(passage)
    if not claim or len(claim) > 1500 or not passage or len(passage) > 1500:
        raise ValueError('Enter a claim and a short source passage of up to 1500 characters each.')
    if passage not in compact(document.get('text')):
        raise ValueError('The source passage must be copied from the displayed source text. Put your interpretation in the claim field.')
    url = public_link(document.get('url'))
    if not url:
        raise ValueError('A valid source link is required.')
    published = str(document.get('published_at') or '')
    return {
        'claim_id': sha256((url+'\0'+claim+'\0'+passage).encode()).hexdigest()[:20],
        'claim': claim, 'source': document.get('publisher') or url,
        'source_url': url, 'source_title': document.get('title') or url,
        'source_passage': passage, 'passage_kind': document.get('text_kind', 'Source passage'),
        'source_text_sha256': document.get('text_sha256', ''),
        'published_at': published, 'date': published[:10] if re.match(r'^\d{4}-\d{2}-\d{2}', published) else '',
        'retrieved_at': document.get('retrieved_at') or datetime.now(timezone.utc).isoformat(),
        'country': country.strip(), 'language': language.strip(), 'topic': topic.strip(),
        'search_query': document.get('query', ''), 'search_provider': document.get('provider', 'Direct public URL'),
        'review_status': 'Unreviewed', 'coding_protocol': '', 'coding_rationale': '', 'coded_at': '',
        **{field: None for field in FIELDS},
    }


def add_claim(corpus, record):
    if any(row['claim_id'] == record['claim_id'] for row in corpus):
        return False
    if len(corpus) >= 500:
        raise ValueError('This session already holds 500 claims. Download the corpus before collecting a new batch.')
    corpus.append(record)
    return True


def apply_coding(record, indicators, protocol, rationale, status):
    if status not in ('Unreviewed', 'In review', 'Reviewed'):
        raise ValueError('Choose a review status.')
    checked = {}
    for field in FIELDS:
        value = indicators.get(field)
        if value is None or value == '':
            checked[field] = None
        else:
            try:
                numeric = float(value)
            except (ValueError, TypeError):
                raise ValueError('Indicator values must be between 0 and 1.') from None
            if not math.isfinite(numeric) or not 0 <= numeric <= 1:
                raise ValueError('Indicator values must be between 0 and 1.')
            checked[field] = numeric
    return {**record, **checked, 'coding_protocol': compact(protocol),
            'coding_rationale': compact(rationale), 'review_status': status,
            'coded_at': datetime.now(timezone.utc).isoformat()}


def ready_for_analysis(record):
    if record.get('review_status') != 'Reviewed' or not compact(record.get('coding_protocol')) or not compact(record.get('coding_rationale')):
        return False
    for field in FIELDS:
        try:
            value = float(record.get(field))
            if not math.isfinite(value) or not 0 <= value <= 1:
                return False
        except (TypeError, ValueError):
            return False
    return True


def analysis_claims(corpus):
    return pd.DataFrame([row for row in corpus if ready_for_analysis(row)], columns=CORPUS_FIELDS)


def restore_corpus(uploaded, corpus):
    if len(uploaded.getvalue()) > 2 * 1024 * 1024:
        raise ValueError('The saved corpus must be smaller than 2 MiB.')
    try:
        frame = pd.read_csv(BytesIO(uploaded.getvalue()), encoding='utf-8-sig', keep_default_na=False, dtype=str)
    except (UnicodeError, pd.errors.ParserError, pd.errors.EmptyDataError):
        raise ValueError('The saved corpus must be a readable UTF-8 CSV.') from None
    required = {'claim', 'source_url', 'source_passage'}
    if not required.issubset(frame.columns) or len(frame) > 500:
        raise ValueError('Use a saved claim corpus CSV containing claim, source_url and source_passage, with at most 500 records.')
    prepared = []
    for item in frame.to_dict('records'):
        if not public_link(item['source_url']) or not compact(item['claim']) or not compact(item['source_passage']):
            raise ValueError('Every restored claim needs a valid source link, claim and source passage.')
        record = {field: item.get(field, None if field in FIELDS else '') for field in CORPUS_FIELDS}
        record['source_url'] = public_link(record['source_url'])
        record['claim_id'] = sha256((record['source_url']+'\0'+compact(record['claim'])+'\0'+compact(record['source_passage'])).encode()).hexdigest()[:20]
        record = apply_coding(record, item, record['coding_protocol'], record['coding_rationale'],
                              record['review_status'] or 'Unreviewed')
        # Restoring a CSV is not a new assessment; preserve the original coding timestamp.
        record['coded_at'] = item.get('coded_at', '')
        prepared.append(record)
    existing = {row['claim_id'] for row in corpus}
    new = [row for row in prepared if row['claim_id'] not in existing]
    unique_new = {row['claim_id']: row for row in new}
    if len(corpus) + len(unique_new) > 500:
        raise ValueError('The combined corpus would exceed 500 records.')
    corpus.extend(unique_new.values())
    return len(unique_new)


def evidence_excel(corpus, searches):
    output = BytesIO()
    notes = pd.DataFrame({'Collection and coding notes': [
        'Retrieved headlines, abstracts and source passages are candidate evidence, not fact checks.',
        'A source link, retrieval time, source passage and text kind are retained for each claim.',
        'Publication dates retain the precision returned by the provider.',
        'Claim indicators remain missing until independently coded by the researcher.',
        'Only reviewed records with all five indicators, a protocol and a rationale enter analysis.',
        'Political framing is recorded separately and does not enter EMNRI.',
        'Source text and abstracts may have reuse restrictions; consult the original source.',
    ]})
    with pd.ExcelWriter(output, engine='xlsxwriter', engine_kwargs={
            'options': {'strings_to_formulas': False, 'strings_to_urls': False}}) as writer:
        pd.DataFrame(corpus, columns=CORPUS_FIELDS).to_excel(writer, sheet_name='Collected claims', index=False)
        pd.DataFrame(searches).to_excel(writer, sheet_name='Search log', index=False)
        notes.to_excel(writer, sheet_name='Collection notes', index=False)
        for sheet in writer.sheets.values():
            sheet.freeze_panes(1, 0)
            sheet.set_column(0, 30, 24)
    return output.getvalue()
