"""One entry point for keyword searches from any application page."""
import streamlit as st


def start_claim_search(query, page='views/source_search.py'):
    query = str(query or '').strip()
    if not 2 <= len(query) <= 250:
        raise ValueError('Enter 2 to 250 characters of keywords for finding claims.')
    st.session_state['claim_search_request'] = {'query': query}
    st.switch_page(page)


def render_claim_search_bar():
    with st.form('global_claim_search', border=False):
        a, b = st.columns([5, 1], vertical_alignment='bottom')
        query = a.text_input('Find claims by keyword',
                             value=st.session_state.get('last_claim_search_keywords', ''),
                             placeholder='For example: heat stress Oman or الإجهاد الحراري عُمان')
        submit = b.form_submit_button('Find claims', use_container_width=True)
    if submit:
        try:
            start_claim_search(query)
        except ValueError as exc:
            st.error(str(exc))
