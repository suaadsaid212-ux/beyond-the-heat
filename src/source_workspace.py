"""Search, read, capture and review public sources inside the prototype."""
from hashlib import sha256
from datetime import date, datetime, timedelta, timezone
import pandas as pd
import streamlit as st

from src.evidence import (
    CORPUS_FIELDS, add_claim, analysis_claims, apply_coding, candidate_passages,
    capture_claim, document_from_result, evidence_excel, ready_for_analysis, restore_corpus,
)
from src.scoring import FIELDS
from src.source_reader import SourceReadError, read_source
from src.source_search import EDITIONS, OFFICIAL_SOURCES, PROVIDERS, SourceSearchError, search_sources
from src.time_periods import publication_span
from src.definitions import explain

TOPICS = ['Extreme heat', 'Air quality', 'Water security', 'Food and climate', 'Other environmental issue']
LANGUAGES = {'Unknown / to review': '', 'English': 'en', 'العربية': 'ar',
             'Русский': 'ru', 'Español': 'es', 'Français': 'fr'}


@st.cache_data(ttl=900, max_entries=64, show_spinner=False)
def _search(query, provider, country, language, scope, days, limit, start=None, end=None):
    return search_sources(query, provider=provider, country=country, language=language,
                          scope=scope, days=days, limit=limit, start_date=start, end_date=end)


def _activate_result(result):
    st.session_state['evidence_active'] = document_from_result(result)


def _load_public_url(url, metadata=None):
    document = read_source(url)
    st.session_state['evidence_active'] = {
        **(metadata or {}), **document,
        'title': (metadata or {}).get('title') or document['url'],
        'provider': (metadata or {}).get('provider') or 'Direct public URL',
    }


def _saved_claims(analysis_page=None):
    corpus = st.session_state['claim_corpus']
    st.caption('Claims are kept in this browser session. Download the corpus before closing it; restore the CSV here to continue later.')
    restore = st.file_uploader('Restore a saved claim corpus CSV', type=['csv'], key='restore_claim_corpus')
    if restore is not None and st.button('Restore claims from CSV'):
        try:
            count = restore_corpus(restore, corpus)
            st.success(f'Restored {count} new claims.')
        except (ValueError, pd.errors.ParserError) as exc:
            st.error(str(exc))
    if not corpus:
        st.info('Search for a source or read a public URL, then save a claim passage to start your corpus.')
        return
    ready = analysis_claims(corpus)
    st.write(f'{len(corpus)} saved claims. {len(ready)} fully coded and ready for analysis.')
    st.dataframe(pd.DataFrame(corpus, columns=CORPUS_FIELDS), use_container_width=True, hide_index=True,
                 column_config={'source_url': st.column_config.LinkColumn('Source link')})
    st.download_button('Download collected claims CSV',
                       pd.DataFrame(corpus, columns=CORPUS_FIELDS).to_csv(index=False).encode('utf-8-sig'),
                       'beyond_the_heat_claim_corpus.csv', 'text/csv')
    st.download_button('Download evidence workbook', evidence_excel(corpus, st.session_state['source_search_log']),
                       'beyond_the_heat_source_evidence.xlsx',
                       'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
    chosen = st.selectbox('Claim to review', list(range(len(corpus))),
                          format_func=lambda index: corpus[index]['claim'][:150], key='claim_review_selection')
    record = corpus[chosen]
    st.link_button('Open the saved source', record['source_url'])
    st.write(record['source_passage'])
    with st.form('review_claim_'+record['claim_id']):
        status = st.selectbox('Review status', ['Unreviewed', 'In review', 'Reviewed'],
                              index=['Unreviewed', 'In review', 'Reviewed'].index(record['review_status']))
        st.caption('Supply documented measurements or researcher coding on a 0 to 1 scale. Search rank, publisher identity and environmental observations do not supply these scores automatically.')
        labels = {
            'claim_reliability': 'Claim reliability (ECR)', 'amplification': 'Measured amplification (A)',
            'health_risk': 'Defined environmental health risk (H)',
            'communication_credibility': 'Communication credibility (ICC)',
            'political_framing': 'Political framing, recorded separately',
        }
        terms = dict(zip(FIELDS, ['ECR', 'A', 'H', 'ICC', 'Political framing']))
        columns = st.columns(2)
        values = {}
        for index, field in enumerate(FIELDS):
            value = record.get(field)
            values[field] = columns[index % 2].number_input(labels[field], min_value=0., max_value=1.,
                value=float(value) if value is not None and value != '' else None, step=0.01,
                key=record['claim_id']+'_'+field, placeholder='Not coded', help=explain(terms[field]))
        protocol = st.text_input('Coding protocol or measurement definition', value=record.get('coding_protocol', ''))
        rationale = st.text_area('Evidence and rationale for the coding', value=record.get('coding_rationale', ''))
        save = st.form_submit_button('Save claim review')
    if save:
        try:
            corpus[chosen] = apply_coding(record, values, protocol, rationale, status)
            st.success('Claim review saved.')
            st.rerun()
        except ValueError as exc:
            st.error(str(exc))
    if ready_for_analysis(corpus[chosen]):
        st.success('This claim is ready for exploratory analysis.')
    else:
        st.info('For analysis, complete all five indicators, provide the protocol and rationale, and mark the record Reviewed.')
    if not ready.empty:
        st.download_button('Download analysis ready claims CSV', ready.to_csv(index=False).encode('utf-8-sig'),
                           'beyond_the_heat_reviewed_claims.csv', 'text/csv')
        if st.button('Analyse my reviewed claims', key='analyse_reviewed_claims'):
            st.session_state['use_collected_claims'] = True
            if analysis_page:
                st.switch_page(analysis_page)
            st.rerun()


def _capture_active():
    document = st.session_state.get('evidence_active')
    if document is None:
        return
    st.subheader('Capture a source linked claim')
    st.write(document.get('title') or document['url'])
    st.link_button('Open original source', document['url'])
    st.caption(f"Text available: {document['text_kind']} | Retrieved UTC: {document.get('retrieved_at', '')}")
    if document.get('partial'):
        st.caption('This is an excerpt or a limited preview. Open the original source for complete context.')
    st.text_area('Source text preview', document['text'][:20000], height=180, disabled=True,
                  key='source_preview_'+document['text_sha256'][:12])
    passages = candidate_passages(document['text'], document.get('query', ''))
    stamp = sha256((document['url']+document['text_sha256']).encode()).hexdigest()[:12]
    selected = st.selectbox('Suggested passage to inspect', passages,
                           format_func=lambda text: text[:170], key='source_passage_choice_'+stamp)
    form_stamp = stamp + sha256(selected.encode()).hexdigest()[:8]
    with st.form('capture_claim_form_'+form_stamp):
        passage = st.text_area('Source passage to retain', selected, height=100,
                               help='Keep the words copied from the source. Use the claim field for your interpretation.')
        claim = st.text_area('Claim candidate for review', selected, height=100)
        span = publication_span(document.get('published_at'))
        known_date = span[0] if span and span[0] == span[1] else None
        publication_date = st.date_input('Source publication date, if known', value=known_date,
                                         min_value=date(1900, 1, 1), max_value=date(2100, 12, 31))
        date_evidence = st.text_input('Publication date evidence, if entered or corrected',
                                      placeholder='For example: date printed below the source headline')
        st.caption('Keep unknown dates empty. Use the publication date printed in the source, not the day you retrieved it. Partial year or month dates are retained as supplied and do not become invented daily observations.')
        a, b, c = st.columns(3)
        country = a.text_input('Country discussed, confirm manually', value='')
        language_name = b.selectbox('Content language, confirm manually', list(LANGUAGES))
        topic = c.selectbox('Environmental topic', TOPICS)
        save = st.form_submit_button('Save claim and source link')
    if save:
        try:
            record = capture_claim(document, claim, passage, country=country,
                                   language=LANGUAGES[language_name], topic=topic,
                                   publication_date=publication_date, date_evidence=date_evidence)
            added = add_claim(st.session_state['claim_corpus'], record)
            if added:
                st.session_state['claim_capture_notice'] = 'Claim saved. Open Saved claims to review, code or download it.'
                st.rerun()
            st.info('This claim and passage are already saved.')
        except ValueError as exc:
            st.error(str(exc))


def render_source_workspace(analysis_page=None):
    st.session_state.setdefault('claim_corpus', [])
    st.session_state.setdefault('source_search_log', [])
    st.header('🔎 Search sources and collect claims')
    st.caption('Find real news and research, open source links, and retain passages for review. Search results and suggested passages are unreviewed candidates.')
    if 'claim_capture_notice' in st.session_state:
        st.success(st.session_state.pop('claim_capture_notice'))
    search_tab, read_tab, saved_tab = st.tabs(['Search sources', 'Read a URL', 'Saved claims'])
    with search_tab:
        provider = st.selectbox('Search provider', PROVIDERS, key='source_search_provider', help=explain('RSS'))
        choices = ['Last 7 days', 'Last 30 days', 'Last 90 days', 'Custom dates']
        if provider == PROVIDERS[1]:
            choices = ['Any publication date', *choices]
        period = st.selectbox('Publication period', choices, index=1 if provider == PROVIDERS[0] else 0,
                              key='source_publication_period_'+str(PROVIDERS.index(provider)))
        today = datetime.now(timezone.utc).date()
        with st.form('source_search_form'):
            query = st.text_input('Search topic, claim or organisation', placeholder='For example: extreme heat Oman, air pollution, climate misinformation')
            country = st.text_input('Country or region focus (optional)', placeholder='For example: Oman')
            start, end = None, None
            days = {'Last 7 days': 7, 'Last 30 days': 30, 'Last 90 days': 90}.get(period)
            if period == 'Custom dates':
                a, b = st.columns(2)
                start = a.date_input('Source publication start date', value=today-timedelta(days=90),
                                     min_value=date(1900, 1, 1), max_value=today)
                end = b.date_input('Source publication end date', value=today,
                                   min_value=date(1900, 1, 1), max_value=today)
            st.caption('Both selected dates are included. Publication dates are separate from retrieval time. Timed records use UTC. Bounded searches omit unknown dates or partial dates that cross the boundary; index coverage is incomplete.')
            if provider == PROVIDERS[0]:
                a, b = st.columns(2)
                language = a.selectbox('News edition language', list(EDITIONS))
                scope = b.selectbox('Source scope', list(OFFICIAL_SOURCES))
                limit = st.selectbox('Maximum results', [10, 20, 30], index=1)
                st.caption('Official website filters apply to coverage available in the news index. A news edition is not proof of the article language or the country discussed.')
            else:
                language, scope = 'English', 'All indexed sources'
                limit = st.selectbox('Maximum results', [10, 20, 30], index=1)
                st.caption('Crossref searches scholarly metadata. Displayed records must contain the supplied keywords and country words in their title or available abstract. Use a few focused keywords; this is not a complete literature search. Abstracts, publication types and full text availability vary.')
            submit = st.form_submit_button('Search sources now')
        if submit:
            st.session_state.pop('source_search_results', None)
            try:
                with st.spinner('Searching public sources...'):
                    result = _search(query, provider, country, language, scope, days, limit, start, end)
                st.session_state['source_search_results'] = result
                st.session_state['source_search_log'].append({key: value for key, value in result.items() if key != 'results'} |
                                                            {'returned_records': len(result['results'])})
                st.session_state['source_search_log'] = st.session_state['source_search_log'][-100:]
            except (SourceSearchError, ValueError) as exc:
                st.error(str(exc))
        result = st.session_state.get('source_search_results')
        if result is not None:
            rows = result['results']
            st.caption(f"Displayed search: {result['provider']} | {result['query']} | Retrieved UTC: {result['retrieved_at']}")
            if result.get('start_date'):
                st.caption(f"Publication period: {result['start_date']} to {result['end_date']}, inclusive. Missing or boundary ambiguous publication dates are excluded.")
            if not rows:
                st.info('No indexed results were returned. Broaden the words or source scope, try the other provider, or use Read a URL for a specific public report.')
            else:
                st.dataframe(pd.DataFrame(rows)[['title', 'publisher', 'published_at', 'excerpt_kind', 'url']],
                             use_container_width=True, hide_index=True,
                             column_config={'url': st.column_config.LinkColumn('Source link')})
                st.download_button('Download source search CSV', pd.DataFrame(rows).to_csv(index=False).encode('utf-8-sig'),
                                   'beyond_the_heat_source_search.csv', 'text/csv')
                chosen = st.selectbox('Source to inspect', list(range(len(rows))),
                                      format_func=lambda index: rows[index]['title'][:180], key='source_search_selection')
                record = rows[chosen]
                st.write(record['title'])
                st.caption(f"{record['publisher']} | Published: {record['published_at'] or 'not supplied'} | {record['excerpt_kind']}")
                st.write(record['excerpt'][:2000])
                st.link_button('Open source article or paper', record['url'])
                a, b = st.columns(2)
                if a.button('Capture a claim from this result', key='use_search_result'):
                    _activate_result(record)
                if b.button('Read original source text', key='read_search_result'):
                    try:
                        with st.spinner('Reading the public source...'):
                            _load_public_url(record['url'], record)
                    except SourceReadError as exc:
                        _activate_result(record)
                        st.info(str(exc))
    with read_tab:
        st.caption('Paste a public HTTPS article, agency report or PDF URL, including sources outside the search indexes.')
        with st.form('read_public_source_form'):
            url = st.text_input('Public source URL', placeholder='https://www.who.int/...')
            read = st.form_submit_button('Read this public source')
        if read:
            st.session_state.pop('evidence_active', None)
            try:
                with st.spinner('Reading the public source...'):
                    _load_public_url(url)
            except SourceReadError as exc:
                st.error(str(exc))
        st.caption('Some websites require sign in, use scripts, or restrict extraction. Source links remain available for inspection at the publisher.')
    with saved_tab:
        _saved_claims(analysis_page)
    _capture_active()
    st.divider()
    return analysis_claims(st.session_state['claim_corpus'])
