"""Keyword interest and a direct handoff to source based claim discovery."""
from datetime import date, datetime, timedelta, timezone
from hashlib import sha256

import pandas as pd
import streamlit as st

from src.claim_navigation import start_claim_search
from src.data_connectors import google_trends_rss, parse_trends_csv
from src.trends_search import REGIONS, chart_values, keyword_claim_query, prepare_keyword_search


def render_google_trends():
    st.subheader('Google Trends keyword interest')
    st.caption('Use keyword interest to study attention. Find claims searches news and research for source statements. These are separate types of evidence.')
    keyword_tab, current_tab = st.tabs(['Keyword search and CSV results', 'Current trending topics'])
    with keyword_tab:
        today = datetime.now(timezone.utc).date()
        with st.form('trends_keyword_form'):
            keywords = st.text_area('Google Trends keywords, one per line',
                value=st.session_state.get('last_claim_search_keywords', 'heat stress'), height=100,
                help='This prototype compares up to five terms. Arabic and English terms are accepted.')
            region = st.selectbox('Google Trends country or region', list(REGIONS))
            a, b = st.columns(2)
            start = a.date_input('Keyword interest start date', value=today-timedelta(days=365),
                                 min_value=date(2004, 1, 1), max_value=today)
            end = b.date_input('Keyword interest end date', value=today,
                               min_value=date(2004, 1, 1), max_value=today)
            prepare = st.form_submit_button('Prepare Google Trends keyword search')
        if prepare:
            st.session_state.pop('trends_keyword_search', None)
            try:
                st.session_state['trends_keyword_search'] = prepare_keyword_search(keywords, region, start, end)
            except ValueError as exc:
                st.error(str(exc))
        search = st.session_state.get('trends_keyword_search')
        if search is not None:
            st.write('Keywords: '+', '.join(search['terms']))
            st.caption(f"Region: {search['region']} | Period: {search['start_date']} to {search['end_date']}")
            st.link_button('Open keyword interest in Google Trends', search['url'])
            st.info('The button opens the official Google Trends website. Export its Interest over time chart as CSV, then upload it below to view and download the results inside this app. Keyword data have not been fetched automatically.')
            if st.button('Find news claims using the first keyword'):
                try:
                    start_claim_search(keyword_claim_query(search))
                except ValueError as exc:
                    st.error(str(exc))
        st.caption('Direct keyword API access requires admission to Google’s alpha program. The app currently uses official search links and CSV imports. Availability and low search volume can limit results.')
        st.markdown('[Google instructions for exporting a Trends chart](https://support.google.com/trends/answer/4365538?hl=en)')
        uploaded = st.file_uploader('Upload keyword Interest over time CSV from Google Trends', type=['csv'], key='google_trends_csv')
        if uploaded is not None:
            try:
                frame = parse_trends_csv(uploaded)
                st.session_state['keyword_interest_import'] = {'frame': frame, 'filename': uploaded.name,
                    'sha256': sha256(uploaded.getvalue()).hexdigest(),
                    'imported_at_utc': datetime.now(timezone.utc).isoformat()}
            except (ValueError, UnicodeError, pd.errors.ParserError) as exc:
                st.session_state.pop('keyword_interest_import', None)
                st.error(f'Unable to read this Google Trends export: {exc}')
        imported = st.session_state.get('keyword_interest_import')
        if imported is not None:
            frame = imported['frame']
            st.write('Imported keyword interest data')
            st.caption(f"File: {imported['filename']} | Imported UTC: {imported['imported_at_utc']}")
            st.dataframe(frame, hide_index=True, use_container_width=True)
            try:
                chart, suppressed = chart_values(frame)
                st.line_chart(chart)
                if suppressed:
                    st.caption(f'{suppressed} values reported as <1 are shown as chart gaps. The original markers remain in the table and download.')
            except ValueError as exc:
                st.info(str(exc))
            st.download_button('Download imported keyword interest CSV', frame.to_csv(index=False).encode('utf-8-sig'),
                               'google_trends_keyword_interest.csv', 'text/csv')
            st.caption('The CSV retains its own keyword and region column labels. A prepared search link does not establish the origin or settings of an uploaded file. Imports remain available in this session when moving between pages.')
    with current_tab:
        st.caption('This feed contains currently trending topics for a country. It does not search your chosen keyword.')
        country = st.selectbox('Country for trending searches RSS', ['US','OM','RU','GB','IN','FR','DE','AU','CA','BR'], index=1)
        if st.button('Fetch Google trending searches'):
            st.session_state.pop('trending_rss', None)
            try:
                st.session_state['trending_rss'] = google_trends_rss(country)
            except Exception as exc:
                st.error(f'Google Trends RSS unavailable or unsupported for this country: {exc}')
        if 'trending_rss' in st.session_state:
            rss = st.session_state['trending_rss']
            st.dataframe(rss, use_container_width=True)
            st.download_button('Download trending searches CSV', rss.to_csv(index=False).encode('utf-8-sig'),
                               'google_trending_searches.csv', 'text/csv')
    st.caption('Data source: Google Trends. Website interest values from 0 to 100 are relative to the selected terms, region and period. They are not absolute search counts, claim reach, misinformation prevalence or public trust. Short time windows may use the browser’s local time zone; check the exported resolution before aligning dates.')
