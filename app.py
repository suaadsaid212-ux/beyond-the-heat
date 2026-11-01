import io
from pathlib import Path
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st
from src.scoring import Weights, score_records, bootstrap_mean_ci
from src.localization import LANGUAGES, translate
from src.exports import excel_bytes, figure_png
from src.theme import apply_theme, hero
from src.research import weight_sensitivity, narrative_shift, annotation_agreement
from datetime import datetime, timezone

st.set_page_config(page_title='Beyond the Heat', page_icon='🌡️', layout='wide')
interface = st.sidebar.selectbox('Interface language / لغة الواجهة / Язык интерфейса',list(LANGUAGES))
lang = LANGUAGES[interface]
t = lambda key: translate(lang,key)
apply_theme()
hero(t('title'),t('subtitle')+' | Research prototype v0.5')
st.warning(t('warning'))

with st.sidebar:
    st.header(t('data'))
    uploaded = st.file_uploader(t('upload'), type=['csv'])
    st.caption('Required numeric columns: claim_reliability, amplification, health_risk, communication_credibility, political_framing (all 0 to 1). Optional: date, topic, source, claim, event, event_date, source_type.')
    st.header(t('weights'))
    a = st.slider(t('amplification'),0.,1.,0.33,0.01)
    h = st.slider(t('health'),0.,1.,0.33,0.01)
    c = st.slider(t('credibility'),0.,1.,0.34,0.01)
    total=a+h+c
    st.caption(f'Weights normalized to sum to 1 (raw sum {total:.2f})')
    if total == 0:
        st.error('At least one weight must be positive')
        st.stop()
    weights=Weights(a/total,h/total,c/total)

try:
    df=pd.read_csv(uploaded, encoding='utf-8-sig') if uploaded is not None else pd.read_csv(Path(__file__).parent/'data'/'demo_synthetic.csv')
    scored=score_records(df, weights)
except Exception as e:
    st.error(f'Unable to load or score dataset: {e}')
    st.stop()

if uploaded is None:
    st.info(t('demo'))

# Country and content-language filters are metadata, never inferred from language or identity.
for column, label in [('country',t('country')),('language',t('language'))]:
    if column in scored.columns:
        choices=sorted(scored[column].dropna().astype(str).unique())
        selected_values=st.multiselect(label,choices,default=choices)
        scored=scored[scored[column].astype(str).isin(selected_values)]
if 'topic' in scored.columns:
    selected=st.multiselect(t('topics'), sorted(scored['topic'].dropna().unique()), default=sorted(scored['topic'].dropna().unique()))
    scored=scored[scored['topic'].isin(selected)]
if scored.empty:
    st.warning(t('missing'))
    st.stop()

m1,m2,m3,m4=st.columns(4)
m1.metric(t('records'),len(scored))
m2.metric(t('risk'),f"{scored['emnri'].mean():.1f} / 100")
m3.metric(t('politics'),f"{scored['political_framing'].mean()*100:.1f} / 100")
lo,hi=bootstrap_mean_ci(scored['emnri'])
m4.metric(t('interval'),f'{lo:.1f} to {hi:.1f}')
st.caption('Bootstrap interval describes sampling variation in this dataset only. It does not establish construct validity or account for annotation error.')

chart_registry = {}
radar,scatter=st.columns(2)
with radar:
    st.subheader(t('radar'))
    options={f"{i}: {str(row.get('claim','Record'))[:65]}":i for i,row in scored.iterrows()}
    key=st.selectbox(t('choose'),list(options))
    record=scored.loc[options[key]]
    names=['Claim unreliability','Amplification','Health risk','Credibility gap','Political framing']
    values=[1-record['claim_reliability'],record['amplification'],record['health_risk'],1-record['communication_credibility'],record['political_framing']]
    fig=go.Figure(go.Scatterpolar(r=values+[values[0]],theta=names+[names[0]],fill='toself',name='Indicators'))
    fig.update_layout(polar=dict(radialaxis=dict(visible=True,range=[0,1])),showlegend=False,margin=dict(t=25,b=20))
    st.plotly_chart(fig,use_container_width=True)
    chart_registry['Indicator radar'] = fig
    st.caption('Political framing is displayed independently and is excluded from EMNRI.')
with scatter:
    st.subheader(t('scatter'))
    fig=px.scatter(scored,x='political_framing',y='claim_reliability',color='topic' if 'topic' in scored else None,
                   hover_data=[x for x in ['claim','source'] if x in scored],size='amplification',
                   labels={'political_framing':'Political framing intensity','claim_reliability':'Claim reliability'})
    fig.update_xaxes(range=[0,1]);fig.update_yaxes(range=[0,1]);st.plotly_chart(fig,use_container_width=True)
    chart_registry['Political framing scatter'] = fig

st.subheader(t('trend'))
if 'date' in scored:
    tmp=scored.copy();tmp['date']=pd.to_datetime(tmp['date'],errors='coerce');tmp=tmp.dropna(subset=['date'])
    if not tmp.empty:
        trend=tmp.groupby(['date','topic'] if 'topic' in tmp else ['date'],as_index=False).agg(emnri=('emnri','mean'),political_framing=('political_framing','mean'))
        fig=px.line(trend,x='date',y='emnri',color='topic' if 'topic' in trend else None,markers=True)
        st.plotly_chart(fig,use_container_width=True)
        chart_registry['Narrative trend'] = fig
        st.caption('Descriptive trends only. Coincidence with a policy event is not proof of causation.')
    else:st.info('No valid dates supplied')
else:st.info('Add a date column to display a trend.')

st.subheader(t('network'))
if {'claim','source'}.issubset(scored.columns):
    import networkx as nx
    graph=nx.Graph()
    for _,r in scored.head(60).iterrows():
        source='Source: '+str(r['source']);claim='Claim: '+str(r['claim'])[:45]
        graph.add_node(source,kind='source');graph.add_node(claim,kind='claim');graph.add_edge(source,claim)
    pos=nx.spring_layout(graph,seed=42)
    edge_x=[];edge_y=[]
    for u,v in graph.edges():
        edge_x += [pos[u][0],pos[v][0],None];edge_y += [pos[u][1],pos[v][1],None]
    fig=go.Figure()
    fig.add_trace(go.Scatter(x=edge_x,y=edge_y,mode='lines',line=dict(width=1,color='lightgray'),hoverinfo='skip'))
    for kind,color in [('source','#4472c4'),('claim','#e29a49')]:
        nodes=[n for n,d in graph.nodes(data=True) if d['kind']==kind]
        fig.add_trace(go.Scatter(x=[pos[n][0] for n in nodes],y=[pos[n][1] for n in nodes],mode='markers',name=kind,
                                 marker=dict(size=10,color=color),text=nodes,hovertemplate='%{text}<extra></extra>'))
    fig.update_layout(xaxis=dict(visible=False),yaxis=dict(visible=False),height=430,margin=dict(t=10,b=10))
    st.plotly_chart(fig,use_container_width=True)
    chart_registry['Claim source network'] = fig
    st.caption('Edges show only source to claim relationships present in the uploaded data. They do not establish reposting, influence or causation.')
else:st.info('Add claim and source columns to build a network.')

st.subheader('🔬 Research validation and sensitivity')
st.caption('Exploratory diagnostics only. These do not establish predictive validity or causation.')
sensitivity = weight_sensitivity(scored)
base_mean = float(scored['emnri'].mean())
s1,s2,s3=st.columns(3)
s1.metric('Lowest mean across tested weights',f"{sensitivity.mean_emnri.min():.1f}")
s2.metric('Highest mean across tested weights',f"{sensitivity.mean_emnri.max():.1f}")
s3.metric('Current mean',f"{base_mean:.1f}")
st.caption('Sensitivity uses all nonnegative weight combinations on a 0.1 grid. This is not a confidence interval.')
fig_sens=px.scatter(sensitivity,x='weight_amplification',y='mean_emnri',color='weight_health',
                    labels={'weight_amplification':'Amplification weight','mean_emnri':'Mean risk index','weight_health':'Health risk weight'})
st.plotly_chart(fig_sens,use_container_width=True)
chart_registry['Weight sensitivity']=fig_sens
agreement=annotation_agreement(scored)
if agreement is not None:
    st.metric('Two annotator Cohen kappa',f'{agreement:.3f}')
    st.caption('Kappa describes categorical agreement; it is not classifier accuracy.')
else:
    st.info('For annotation agreement, upload annotator_1 and annotator_2 columns with independent categorical judgments.')
if 'date' in scored:
    with st.expander('📅 Political Narrative Shift Indicator (PNSI)'):
        dates=pd.to_datetime(scored['date'],errors='coerce',utc=True).dropna()
        if len(dates):
            chosen=st.date_input('Documented event date',value=dates.median().date())
            days=st.slider('Days before and after',3,60,14)
            result=narrative_shift(scored,chosen,days)
            st.write(pd.DataFrame([result]))
            st.caption('PNSI is the difference in mean political framing after versus before an event. It is descriptive, not evidence that the event caused the change. Provide independent event documentation.')
        else:
            st.info('No valid dates available.')
provenance={
    'generated_at_utc':datetime.now(timezone.utc).isoformat(),
    'app_version':'0.5',
    'data_origin':'user_uploaded' if uploaded is not None else 'synthetic_demonstration',
    'records_after_filters':len(scored),
    'model_status':'exploratory_unvalidated',
    'weight_amplification':weights.amplification,
    'weight_health_risk':weights.health_risk,
    'weight_credibility_gap':weights.credibility_gap,
    'missing_value_policy':'reject_missing_indicator_values',
    'source_url_field_present':'source_url' in scored.columns,
    'source_retrieval_date_field_present':'retrieved_at' in scored.columns,
    'annotation_protocol_field_present':'annotation_protocol' in scored.columns,
}
if uploaded is not None and not {'source_url','retrieved_at'}.issubset(scored.columns):
    st.warning('For reproducible research, include source_url and retrieved_at columns. The application does not verify submitted claims.')

st.subheader(t('export'))
st.dataframe(scored,use_container_width=True)
st.download_button(t('download'),scored.to_csv(index=False).encode('utf-8-sig'),file_name='beyond_the_heat_scored.csv',mime='text/csv')
st.download_button('📊 Download Excel workbook (.xlsx)', data=excel_bytes(scored,weights,sensitivity,provenance), file_name='beyond_the_heat_analysis.xlsx', mime='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
st.markdown('#### 🖼️ Export figures as PNG images')
st.caption('Choose a chart to export as a high resolution image. Figures reflect the currently selected data and weights.')
if chart_registry:
    chart_name = st.selectbox('Figure',list(chart_registry),key='figure_export')
    try:
        png = figure_png(chart_registry[chart_name])
        st.download_button('Download selected figure (.png)', data=png, file_name=chart_name.lower().replace(' ','_')+'.png',mime='image/png')
    except Exception as exc:
        st.info('PNG export requires a compatible Kaleido/Chrome installation. If unavailable on this host, use the camera icon in the interactive chart toolbar.')

with st.expander(t('method')):
    st.latex(r'EMNRI_i=100(1-ECR_i)[w_A A_i+w_H H_i+w_C(1-ICC_i)]')
    st.write('ECR is claim reliability; A is amplification; H is environmental health risk; ICC is communication credibility. Each indicator must be independently operationalized and validated. Political framing is kept separate.')
    st.write('The application does not independently fact-check text or infer political ideology. External weather and air quality observations provide optional context and do not automatically change the score. Uploaded scores must come from a documented coding or measurement process. Missing data are rejected rather than silently imputed.')
    st.write('Version 0.4 includes descriptive political event shifts, weight sensitivity, optional annotation agreement and provenance metadata. These are not substitutes for external validation. Future research: annotated claim datasets, inter-rater reliability, supervised classifiers, event study methods, uncertainty propagation, temporal leakage checks, cross-region validation and public trust surveys.')

with st.expander(t('sources')):
    st.markdown('''**Global:** [WHO](https://www.who.int/data), [WMO](https://wmo.int/), [NASA Earthdata](https://www.earthdata.nasa.gov/), [Copernicus](https://climate.copernicus.eu/).  
**United States:** [NOAA](https://www.noaa.gov/), [EPA AirData](https://www.epa.gov/outdoor-air-quality-data).  
**Europe:** [European Environment Agency](https://www.eea.europa.eu/).  
**Oman:** [National Centre for Statistics and Information](https://www.ncsi.gov.om/).  
**Russia:** [Roshydromet](https://www.meteorf.gov.ru/).  
These are research starting points, not live integrations. Verify licensing, coverage and country-specific access before use.''')

# External sources are deliberately independent from the exploratory misinformation score.
# Search interest and environmental measurements are contextual variables, not evidence of falsity.
st.divider()
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
