import streamlit as st
from src.analysis_view import render_claim_analysis

render_claim_analysis(st.session_state.get('interface_lang', 'en'))
