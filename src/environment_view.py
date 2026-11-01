import streamlit as st
import pandas as pd


def render_environment_data():
    st.header('🌍 Live environmental and search interest data')
    st.caption('Research data connectors. These sources are not automatically included in EMNRI scores. Compare aligned time periods before statistical analysis.')
    from src.trends_workspace import render_google_trends
    render_google_trends()
    st.divider()
    from src.data_connectors import open_meteo_history
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

    from src.air_quality import render_air_quality
    render_air_quality()

    from src.fire_hotspots import render_fire_hotspots
    render_fire_hotspots()
