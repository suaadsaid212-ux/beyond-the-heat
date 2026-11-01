"""Optional NASA FIRMS observations in the Streamlit dashboard."""
from datetime import datetime, timedelta, timezone
import os

import pandas as pd
import streamlit as st

from src.exports import figure_png
from src.firms import (
    AREA_DOCS, ATTRIBUTION, FAQ, SOURCES, FIRMSError,
    data_availability, fetch_hotspots, hotspot_excel, hotspot_figures,
)


def _configured_key():
    try:
        value = st.secrets.get('FIRMS_MAP_KEY', '')
    except (FileNotFoundError, KeyError):
        value = ''
    return str(value or os.environ.get('FIRMS_MAP_KEY', '')).strip()


def render_fire_hotspots():
    with st.expander('🔥 Fire hotspots: NASA FIRMS', expanded=False):
        st.caption('Satellite observations of active fire and thermal anomalies. Points are detected pixels, not confirmed wildfire incidents. Industrial heat sources can also appear.')
        map_key = _configured_key()
        if not map_key:
            st.info('To enable NASA FIRMS, add FIRMS_MAP_KEY in Streamlit app settings under Secrets, then restart the app.')
            st.code('FIRMS_MAP_KEY = "paste your NASA MAP key here"', language='toml')
            st.link_button('NASA FIRMS API information', AREA_DOCS)
            return
        source = st.selectbox('FIRMS satellite product', list(SOURCES),
                              format_func=lambda value: SOURCES[value], key='firms_source')
        if st.button('Check FIRMS product date availability', key='firms_check_availability'):
            st.session_state.pop('firms_availability', None)
            try:
                availability = data_availability(map_key, source)
                st.session_state['firms_availability'] = {'source': source, 'data': availability}
            except (FIRMSError, ValueError) as exc:
                st.error(str(exc))
        availability = st.session_state.get('firms_availability')
        if availability is not None and availability['source'] == source:
            st.dataframe(availability['data'], use_container_width=True, hide_index=True)
        mode = st.radio('FIRMS observation period', ['Latest days', 'Choose start date'],
                        key='firms_date_mode', horizontal=True)
        with st.form('firms_area_form'):
            st.caption('Bounding rectangle in degrees. The default covers the Oman region and may include neighbouring territory; it is not a national boundary filter.')
            a, b, c, d = st.columns(4)
            west = a.number_input('West longitude', -180., 180., 52., 0.1, key='firms_west')
            south = b.number_input('South latitude', -90., 90., 16., 0.1, key='firms_south')
            east = c.number_input('East longitude', -180., 180., 60.1, 0.1, key='firms_east')
            north = d.number_input('North latitude', -90., 90., 26.5, 0.1, key='firms_north')
            days = st.slider('FIRMS days per query', 1, 5, 1, key='firms_days')
            start = None
            if mode == 'Choose start date':
                today = datetime.now(timezone.utc).date()
                start = st.date_input('FIRMS start date (UTC)', value=today-timedelta(days=1),
                                      max_value=today, key='firms_start_date')
                st.caption('The requested period starts on this date and includes the following days. Check product availability first for historical research.')
            else:
                st.caption('Latest days includes today in UTC and the preceding selected days. The latest calendar day can still be incomplete.')
            fetch = st.form_submit_button('Fetch NASA fire hotspots')
        if fetch:
            st.session_state.pop('firms_snapshot', None)
            st.session_state.pop('firms_png', None)
            try:
                with st.spinner('Retrieving NASA satellite observations...'):
                    st.session_state['firms_snapshot'] = fetch_hotspots(
                        map_key, source=source, bbox=(west, south, east, north),
                        days=days, start_date=start)
            except (FIRMSError, ValueError) as exc:
                st.error(str(exc))
        st.caption('Requests run when you press a button. NASA applies transaction quotas; wider areas and longer periods may use more transactions.')
        snapshot = st.session_state.get('firms_snapshot')
        if snapshot is None:
            return
        data, query = snapshot['observations'], snapshot['query']
        st.caption(f"Displayed result: {query['source']} | Area: {query['bbox_west_south_east_north']} | Days: {query['days']} | Date mode: {query['date_mode']} | Start: {query['start_date_utc']} | Retrieved UTC: {query['retrieved_at_utc']}")
        st.download_button('Download FIRMS observations CSV', data.to_csv(index=False).encode('utf-8-sig'),
                           'nasa_firms_observations.csv', 'text/csv')
        st.download_button('Download original NASA fields CSV', snapshot['raw'].to_csv(index=False).encode('utf-8-sig'),
                           'nasa_firms_original_fields.csv', 'text/csv')
        st.download_button('Download FIRMS Excel workbook', hotspot_excel(snapshot),
                           'nasa_firms_observations.xlsx',
                           'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
        if data.empty:
            st.info('NASA returned no satellite detections for this query. This does not establish that the area was free of fires or that every location was observed.')
            st.caption(ATTRIBUTION)
            return
        a, b = st.columns(2)
        a.metric('Satellite detection records', len(data))
        dates = pd.to_datetime(data['observed_at_utc'], errors='coerce', utc=True)
        latest = dates.max()
        b.metric('Latest observation (UTC)', latest.strftime('%Y-%m-%d %H:%M') if pd.notna(latest) else 'Unavailable')
        if not data['coordinate_valid'].all() or not data['within_query_bbox'].all():
            st.warning('Some returned coordinates are invalid or outside the requested rectangle. All rows remain in downloads, while these points are omitted from the map and coordinate figure.')
        if dates.isna().any():
            st.warning('Some observation dates or times could not be read. Original values remain in the downloads.')
        map_data = data[data['coordinate_valid'] & data['within_query_bbox']]
        if not map_data.empty:
            # Render only public coordinates in the browser. Provider URLs remain on the server.
            plotted = map_data.head(5000)
            st.map(plotted[['latitude_numeric', 'longitude_numeric']].rename(
                columns={'latitude_numeric': 'latitude', 'longitude_numeric': 'longitude'}),
                use_container_width=True)
            if len(map_data) > len(plotted):
                st.caption('The interactive map displays the first 5,000 points. All records are retained in the tables, exports and coordinate figure.')
        st.dataframe(data, use_container_width=True, hide_index=True)
        if query['source'].startswith('MODIS'):
            st.caption('MODIS confidence is reported as a percentage. Brightness is in kelvins, and fire radiative power (FRP) is in megawatts.')
        else:
            st.caption('VIIRS confidence uses l (low), n (nominal) and h (high). Brightness is in kelvins, and fire radiative power (FRP) is in megawatts.')
        figures = hotspot_figures(data, query['source'])
        if figures:
            chart_name = st.selectbox('FIRMS figure', list(figures), key='firms_figure')
            st.plotly_chart(figures[chart_name], use_container_width=True)
            if st.button('Prepare FIRMS figure PNG', key='firms_prepare_png'):
                st.session_state.pop('firms_png', None)
                try:
                    st.session_state['firms_png'] = {
                        'retrieved_at': query['retrieved_at_utc'], 'chart': chart_name,
                        'bytes': figure_png(figures[chart_name]),
                    }
                except Exception:
                    st.info('Use the chart toolbar camera button if server PNG rendering is unavailable.')
            png = st.session_state.get('firms_png')
            if png and png['retrieved_at'] == query['retrieved_at_utc'] and png['chart'] == chart_name:
                st.download_button('Download FIRMS figure PNG', png['bytes'], 'nasa_firms_figure.png', 'image/png')
        st.caption('Repeated observations can describe the same fire or other heat source. Detection counts are not unique fire counts or burned area. Cloud, smoke and satellite sampling can hide fires.')
        st.caption('NRT data are provisional. Use appropriate standard processing data and independent verification for research. These observations do not automatically change EMNRI scores.')
        st.caption(ATTRIBUTION)
        st.link_button('NASA FIRMS interpretation and limitations', FAQ)
