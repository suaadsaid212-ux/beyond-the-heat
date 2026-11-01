import streamlit as st
import pandas as pd


def render_environment_data():
    st.header('🌍 Live environmental and search interest data')
    st.caption('Research data connectors. These sources are not automatically included in EMNRI scores. Compare aligned time periods before statistical analysis.')
    from src.data_connectors import open_meteo_history, google_trends_rss, parse_trends_csv
    from datetime import date, timedelta
    with st.expander('🌡️ Historical weather: Open-Meteo', expanded=False):
        oc1, oc2, oc3, oc4 = st.columns(4)
        lat = oc1.number_input('Latitude', min_value=-90., max_value=90., value=23.59, step=0.01)
        lon = oc2.number_input('Longitude', min_value=-180., max_value=180., value=58.41, step=0.01)
        start = oc3.date_input('Start date', value=date.today()-timedelta(days=90), key='weather_start')
        end = oc4.date_input('End date', value=date.today()-timedelta(days=7), key='weather_end')
        if st.button('Fetch historical weather'):
            if start > end or end >= date.today():
                st.error('Choose a valid historical date range ending before today.')
            else:
                try:
                    weather = open_meteo_history(lat, lon, str(start), str(end))
                    st.session_state['weather_data'] = weather
                except Exception as exc:
                    st.error(f'Weather data unavailable: {exc}')
        if 'weather_data' in st.session_state:
            weather = st.session_state['weather_data']
            st.line_chart(weather.set_index('date')[['temperature_2m_max','temperature_2m_mean']])
            st.dataframe(weather, use_container_width=True)
            st.download_button('Download weather CSV', weather.to_csv(index=False).encode('utf-8-sig'), 'open_meteo_weather.csv','text/csv')
        st.caption('Source: Open-Meteo historical weather (ERA5). Temperature is modelled/reanalysis data, not direct local station observations. Attribution: Open-Meteo.com, CC BY 4.0.')

    with st.expander('🔎 Google Trends: country trends and CSV import', expanded=False):
        st.caption('The official Google Trends API is restricted access. Current trending searches RSS and manually exported Interest over time CSV are separate sources.')
        country = st.selectbox('Country for trending searches RSS', ['US','OM','RU','GB','IN','FR','DE','AU','CA','BR'], index=1)
        if st.button('Fetch Google trending searches'):
            try:
                st.session_state['trending_rss'] = google_trends_rss(country)
            except Exception as exc:
                st.error(f'Google Trends RSS unavailable or unsupported for this country: {exc}')
        if 'trending_rss' in st.session_state:
            rss = st.session_state['trending_rss']
            st.dataframe(rss, use_container_width=True)
            st.download_button('Download trending searches CSV', rss.to_csv(index=False).encode('utf-8-sig'), 'google_trending_searches.csv', 'text/csv')
        trends_file = st.file_uploader('Upload Interest over time CSV exported from Google Trends', type=['csv'], key='google_trends_csv')
        if trends_file is not None:
            try:
                trends_df = parse_trends_csv(trends_file)
                st.dataframe(trends_df, use_container_width=True)
                st.line_chart(trends_df.set_index('date'))
                st.download_button('Download parsed Google Trends CSV', trends_df.to_csv(index=False).encode('utf-8-sig'), 'google_trends_parsed.csv', 'text/csv')
            except Exception as exc:
                st.error(f'Unable to read this Google Trends export: {exc}')
        st.caption('Google Trends scores are relative search interest (0 to 100), not search counts, misinformation prevalence or public trust. Attribute exported data to Google Trends.')

    from src.air_quality import render_air_quality
    render_air_quality()

    from src.fire_hotspots import render_fire_hotspots
    render_fire_hotspots()
