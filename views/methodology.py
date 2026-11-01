import streamlit as st
from src.methodology_view import render_methodology

render_methodology(st.session_state.get('interface_lang', 'en'))
