import streamlit as st
from src.localization import LANGUAGES, translate
from src.theme import apply_theme, hero

st.set_page_config(page_title='Beyond the Heat', page_icon='🌡️', layout='wide')
interface = st.sidebar.selectbox('Interface language / لغة الواجهة / Язык интерфейса', list(LANGUAGES))
lang = LANGUAGES[interface]
st.session_state['interface_lang'] = lang
apply_theme()
hero(translate(lang, 'title'), translate(lang, 'subtitle')+' | Research prototype v0.7')
st.warning(translate(lang, 'warning'))

page = st.navigation([
    st.Page('views/source_search.py', title='Source search', icon='🔎', default=True, url_path='sources'),
    st.Page('views/analysis.py', title='Claim analysis', icon='📊', url_path='analysis'),
    st.Page('views/environment.py', title='Environmental data', icon='🌍', url_path='environment'),
    st.Page('views/methodology.py', title='Methodology and definitions', icon='📖', url_path='methodology'),
])
page.run()
