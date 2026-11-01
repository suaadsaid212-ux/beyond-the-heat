"""Streamlit panel for optional, independently sourced air quality observations."""
import os
import pandas as pd
import plotly.express as px
import streamlit as st

from src.exports import figure_png
from src.openaq import (
    OpenAQError, fetch_latest, locations_frame, search_locations, snapshot_excel,
)


def _configured_key():
    try:
        configured = st.secrets.get('OPENAQ_API_KEY', '')
    except (FileNotFoundError, KeyError):
        configured = ''
    return str(configured or os.environ.get('OPENAQ_API_KEY', '')).strip()


def render_air_quality():
    with st.expander('🌬️ Air quality: OpenAQ', expanded=False):
        st.caption('Latest available observations from participating stations. Coverage and reporting frequency vary. These readings are context only and do not change EMNRI scores.')
        api_key = _configured_key()
        if not api_key:
            st.info('To enable OpenAQ, add your key in Streamlit app settings under Secrets, then restart the app.')
            st.code('OPENAQ_API_KEY = "paste your key here"', language='toml')
            st.link_button('OpenAQ account settings', 'https://explore.openaq.org/account')
            return
        st.success('OpenAQ key configured. Search for a station to check coverage.')
        mode = st.radio('Search area', ['Nearby coordinates', 'Country code'], horizontal=True,
                        key='openaq_mode')
        with st.form('openaq_search_form'):
            coordinates, country, radius = None, None, 25000
            if mode == 'Nearby coordinates':
                a, b, c = st.columns(3)
                latitude = a.number_input('Air quality latitude', -90., 90., 23.59, 0.01)
                longitude = b.number_input('Air quality longitude', -180., 180., 58.41, 0.01)
                radius = c.slider('Search radius (km)', 1, 25, 25) * 1000
                coordinates = (latitude, longitude)
            else:
                country = st.text_input('Two letter country code', value='OM', max_chars=2)
                st.caption('Examples: OM for Oman, GB for the United Kingdom, US for the United States. Country labels are reported by the provider; check coordinates and locality.')
            a, b = st.columns(2)
            limit = a.selectbox('Stations per page', [10, 25, 50, 100], index=2)
            page = b.number_input('Results page', min_value=1, max_value=10000, value=1, step=1)
            search = st.form_submit_button('Find air quality stations')
        if search:
            # Remove the previous search on both empty responses and errors.
            st.session_state.pop('openaq_search_result', None)
            st.session_state.pop('openaq_snapshot', None)
            try:
                with st.spinner('Finding stations in OpenAQ...'):
                    st.session_state['openaq_search_result'] = search_locations(
                        api_key, iso=country, coordinates=coordinates,
                        radius_m=radius, page=int(page), limit=limit)
            except (OpenAQError, ValueError) as exc:
                st.error(str(exc))
        result = st.session_state.get('openaq_search_result')
        if result is None:
            return
        stations = result['results']
        query = result['query']
        st.caption(f"Search: {query} | Retrieved UTC: {result['retrieved_at_utc']}")
        if not stations:
            st.info('No stations were returned for this query and page. Try page 1, another area or a country search. No readings are estimated to fill a gap in coverage.')
            return
        st.caption(f"Showing {len(stations)} station records on page {query['page']}. This is one results page, not a complete inventory.")
        station_table = locations_frame(stations)
        st.dataframe(station_table, use_container_width=True, hide_index=True)
        st.download_button('Download station list CSV', station_table.to_csv(index=False).encode('utf-8-sig'),
                           'openaq_stations.csv', 'text/csv')
        st.caption('For mobile stations, the listed coordinates are the first recorded point. The observation table uses the coordinates of each reading.')
        by_id = {station['id']: station for station in stations}
        station_id = st.selectbox('Station for latest observations', list(by_id),
            format_func=lambda key: f"{by_id[key].get('name', 'Unnamed')} | ID {key}",
            key='openaq_station')
        station = by_id[station_id]
        if st.button('Fetch latest air quality readings', key='openaq_fetch_latest'):
            st.session_state.pop('openaq_snapshot', None)
            try:
                with st.spinner('Fetching latest available station observations...'):
                    readings = fetch_latest(api_key, station)
                    st.session_state['openaq_snapshot'] = {
                        'station_id': station_id, 'readings': readings, 'station': station,
                        'query': dict(query),
                    }
            except (OpenAQError, ValueError) as exc:
                st.error(str(exc))
        snapshot = st.session_state.get('openaq_snapshot')
        if snapshot is None or snapshot['station_id'] != station_id:
            return
        readings = snapshot['readings']
        if readings.empty:
            st.info('OpenAQ has no latest readings for this station.')
            return
        st.caption('These are the latest records available to OpenAQ. They may have different observation times and are not a synchronised sample.')
        if readings['age_hours_at_retrieval'].gt(24).any():
            st.warning('Some observations were already more than 24 hours old when retrieved. Check the timestamp before describing present conditions.')
        if readings['age_hours_at_retrieval'].isna().any():
            st.warning('Some observations have no usable observation timestamp.')
        if readings['age_hours_at_retrieval'].lt(0).any():
            st.warning('Some observation timestamps are later than the retrieval time. Verify the source timing.')
        if readings['value'].lt(0).any():
            st.warning('Some reported values are negative. They are preserved for review rather than converted to zero.')
        if readings['parameter'].isna().any() or readings['units'].isna().any():
            st.warning('Some sensors have missing parameter or unit metadata. These rows are retained in downloads but omitted from the chart.')
        st.dataframe(readings, use_container_width=True, hide_index=True)
        st.download_button('Download air quality CSV', readings.to_csv(index=False).encode('utf-8-sig'),
                           'openaq_latest_observations.csv', 'text/csv')
        st.download_button('Download air quality Excel workbook',
                           snapshot_excel(readings, snapshot['station'], snapshot['query']),
                           'openaq_air_quality.xlsx',
                           'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
        plottable = readings.dropna(subset=['parameter', 'units', 'value']).copy()
        if not plottable.empty:
            labels = plottable[['parameter', 'units']].drop_duplicates()
            choices = list(labels.itertuples(index=False, name=None))
            selected = st.selectbox('Parameter and original unit for chart', choices,
                                    format_func=lambda value: f'{value[0]} ({value[1]})')
            chart_data = plottable[(plottable['parameter'] == selected[0]) &
                                   (plottable['units'] == selected[1])].copy()
            chart_data['sensor'] = chart_data['sensor_id'].astype(str)
            figure = px.bar(chart_data, x='sensor', y='value',
                            hover_data=['station', 'observed_at_utc', 'provider'],
                            labels={'sensor': 'Sensor ID', 'value': f'{selected[0]} ({selected[1]})'},
                            title=f"{station.get('name')} | Latest {selected[0]} observations")
            st.plotly_chart(figure, use_container_width=True)
            if st.button('Prepare air quality PNG', key='openaq_prepare_png'):
                try:
                    png = figure_png(figure)
                    st.download_button('Download air quality figure PNG', png,
                                       'openaq_latest_observations.png', 'image/png')
                except Exception:
                    st.info('Use the chart toolbar camera button to save this chart if server PNG rendering is unavailable.')
        st.write('Data attribution: OpenAQ and the original station provider shown above.')
        licenses = snapshot['station'].get('licenses') or []
        if licenses:
            st.dataframe(pd.json_normalize(licenses), use_container_width=True, hide_index=True)
        else:
            st.info('No licence metadata was supplied for this station. Check the original provider terms before reusing its data.')
        st.caption('Values retain original units. No AQI, health category, misinformation label or replacement estimate is calculated.')
