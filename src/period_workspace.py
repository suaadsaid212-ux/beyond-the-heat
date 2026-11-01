"""Date selection and descriptive comparisons for the active claim dataset."""
from datetime import timedelta
from hashlib import sha256

import plotly.express as px
import streamlit as st

from src.time_periods import compare_periods, filter_period, period_summary, record_dates


def select_analysis_period(frame):
    dates = record_dates(frame)
    known = dates.dropna()
    missing = int(dates.isna().sum())
    st.subheader('Time period for claim analysis')
    st.caption('Uses the claim dataset date column. For collected claims this is the source publication date, or a researcher documented publication date. Retrieval time is kept separately. Timestamps are interpreted in UTC.')
    settings = {'analysis_period_start': '', 'analysis_period_end': '',
                'undated_records_before_date_filter': missing, 'date_field': 'date', 'time_zone': 'UTC',
                'time_aggregation': 'Monthly', 'period_endpoints': 'inclusive'}
    if known.empty:
        st.info(f'{len(frame)} records have no complete valid date. Date filters and temporal comparisons require a documented date; retrieval dates are not substituted.')
        return frame, settings, 'Monthly'
    first, last = known.min().date(), known.max().date()
    st.caption(f'Available dated records: {len(known)}. Undated or incomplete dates: {missing}. Observed dates: {first.isoformat()} to {last.isoformat()}.')
    stamp = sha256((str(first)+str(last)).encode()).hexdigest()[:10]
    enabled = st.checkbox('Filter claim analysis by date', value=False)
    if enabled:
        a, b = st.columns(2)
        start = a.date_input('Analysis start date', value=first, key='analysis_start_'+stamp)
        end = b.date_input('Analysis end date', value=last, key='analysis_end_'+stamp)
        try:
            frame = filter_period(frame, start, end)
            settings.update(analysis_period_start=start.isoformat(), analysis_period_end=end.isoformat())
            st.caption(f'Inclusive period: {start.isoformat()} to {end.isoformat()}. {len(frame)} records selected; {missing} records without a complete date excluded.')
        except ValueError as exc:
            st.error(str(exc))
            return frame.iloc[:0], settings, 'Monthly'
    frequency = st.selectbox('Group dated claims by', ['Daily', 'Weekly', 'Monthly'], index=2)
    settings['time_aggregation'] = frequency
    return frame, settings, frequency


def render_time_analysis(frame, frequency, chart_registry):
    summary = period_summary(frame, frequency)
    comparison = None
    if summary.empty:
        st.info('Add complete source publication dates to display period trends.')
        return summary, comparison
    detail = period_summary(frame, frequency, by_topic=True)
    fig = px.line(detail, x='period_start', y='mean_emnri', color='topic' if 'topic' in detail else None,
                  markers=True, hover_data=['period_end', 'records'],
                  labels={'period_start': 'Calendar period start', 'mean_emnri': 'Mean EMNRI'})
    st.plotly_chart(fig, use_container_width=True)
    chart_registry['Narrative trend'] = fig
    counts = px.bar(summary, x='period_start', y='records', hover_data=['period_end'],
                    labels={'period_start': 'Calendar period start', 'records': 'Selected claim records'})
    st.plotly_chart(counts, use_container_width=True)
    chart_registry['Claims per period'] = counts
    st.caption('Weekly bins start on Monday; monthly bins start on the first day. Edge bins may cover only part of a period after filtering. Only periods with dated records are shown. Counts describe this selected corpus, not all news or misinformation prevalence. Differences can reflect collection coverage, source mix or coding, and do not establish causality.')
    st.dataframe(summary, hide_index=True, use_container_width=True)
    st.download_button('Download period summary CSV', summary.to_csv(index=False).encode('utf-8-sig'),
                       'beyond_the_heat_period_summary.csv', 'text/csv')
    dates = record_dates(frame).dropna()
    first, last = dates.min().date(), dates.max().date()
    if first == last:
        st.info('At least two distinct dated days are needed to compare separate periods.')
        return summary, comparison
    middle = first + timedelta(days=(last-first).days//2)
    # Store the chosen comparison bounds, and recompute on every rerun so changes
    # in weights or dataset filters cannot leave a stale numerical comparison.
    stamp = sha256((str(first)+str(last)).encode()).hexdigest()[:10]
    with st.expander('Compare two periods'):
        st.caption('Uses the currently selected country, language, topic and analysis date filters. Choose two disjoint periods in chronological order. End dates are included.')
        with st.form('compare_periods_'+stamp):
            a, b = st.columns(2)
            start_a = a.date_input('First period start', value=first)
            end_a = b.date_input('First period end', value=middle)
            a, b = st.columns(2)
            start_b = a.date_input('Second period start', value=middle+timedelta(days=1))
            end_b = b.date_input('Second period end', value=last)
            compare = st.form_submit_button('Compare selected periods')
        if compare:
            st.session_state['comparison_bounds_'+stamp] = (start_a, end_a, start_b, end_b)
        bounds = st.session_state.get('comparison_bounds_'+stamp)
        if bounds:
            try:
                comparison = compare_periods(frame, *bounds)
                st.dataframe(comparison, hide_index=True, use_container_width=True)
                if comparison['records'].eq(0).any():
                    st.info('One or both periods contain no selected dated records. Their averages and the change are unavailable.')
                else:
                    change = comparison.iloc[1]['mean_emnri']-comparison.iloc[0]['mean_emnri']
                    st.metric('Second period minus first period, EMNRI points', f'{change:+.2f}')
                st.download_button('Download period comparison CSV', comparison.to_csv(index=False).encode('utf-8-sig'),
                                   'beyond_the_heat_period_comparison.csv', 'text/csv')
                st.caption('These are descriptive means for the collected records. Unequal durations and sample composition affect interpretation. No effect estimate, significance test or causal attribution is implied.')
            except ValueError as exc:
                st.error(str(exc))
    return summary, comparison
