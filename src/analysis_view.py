from pathlib import Path
from io import BytesIO
from datetime import datetime, timezone
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st
from src.scoring import Weights, score_records, bootstrap_mean_ci
from src.localization import translate
from src.exports import excel_bytes, figure_png
from src.research import weight_sensitivity, narrative_shift, annotation_agreement
from src.evidence import analysis_claims
from src.period_workspace import select_analysis_period, render_time_analysis
from src.time_periods import record_dates
from src.definitions import explain


def _remember_uploaded_dataset():
    uploaded = st.session_state.get('analysis_csv_upload')
    st.session_state['analysis_uploaded_bytes'] = uploaded.getvalue() if uploaded is not None else None


def render_claim_analysis(lang='en'):
    t = lambda key: translate(lang, key)
    collected = analysis_claims(st.session_state.get('claim_corpus', []))
    st.session_state.setdefault('use_collected_claims', st.session_state.get('analysis_use_collected', False))
    if collected.empty:
        st.session_state['use_collected_claims'] = False
        st.session_state['analysis_use_collected'] = False
    with st.sidebar:
        st.header(t('data'))
        use_collected = st.checkbox('Analyse my reviewed collected claims',
                                    key='use_collected_claims', disabled=collected.empty)
        st.session_state['analysis_use_collected'] = use_collected
        uploaded = st.file_uploader(t('upload'), type=['csv'], key='analysis_csv_upload',
                                    on_change=_remember_uploaded_dataset)
        uploaded_bytes = st.session_state.get('analysis_uploaded_bytes')
        if uploaded is not None:
            uploaded_bytes = uploaded.getvalue()
        if uploaded is None and uploaded_bytes is not None:
            st.caption('Your uploaded dataset is retained for this session while you move between pages.')
            if st.button('Clear retained uploaded dataset'):
                st.session_state['analysis_uploaded_bytes'] = None
                st.rerun()
        st.caption('Required numeric columns: claim_reliability, amplification, health_risk, communication_credibility, political_framing (all 0 to 1). Optional: date, topic, source, claim, event, event_date, source_type.')
        st.header(t('weights'))
        previous_weights = st.session_state.get('analysis_weights', (.33, .33, .34))
        a = st.slider(t('amplification'),0.,1.,previous_weights[0],0.01, help=explain('A'))
        h = st.slider(t('health'),0.,1.,previous_weights[1],0.01, help=explain('H'))
        c = st.slider(t('credibility'),0.,1.,previous_weights[2],0.01, help=explain('Credibility gap'))
        st.session_state['analysis_weights'] = (a, h, c)
        total=a+h+c
        st.caption(f'Weights normalized to sum to 1 (raw sum {total:.2f})')
        if total == 0:
            st.error('At least one weight must be positive')
            st.stop()
        weights=Weights(a/total,h/total,c/total)

    try:
        if use_collected:
            df = collected.copy()
            data_origin = 'reviewed_collected_claims'
        elif uploaded_bytes is not None:
            df = pd.read_csv(BytesIO(uploaded_bytes), encoding='utf-8-sig')
            data_origin = 'user_uploaded'
        else:
            df = pd.read_csv(Path(__file__).resolve().parents[1]/'data'/'demo_synthetic.csv')
            data_origin = 'synthetic_demonstration'
        scored=score_records(df, weights)
    except Exception as e:
        st.error(f'Unable to load or score dataset: {e}')
        st.stop()

    st.header('Claim analysis')
    if data_origin == 'synthetic_demonstration':
        st.info(t('demo'))
    elif data_origin == 'reviewed_collected_claims':
        st.info(f'Analysing {len(df)} collected claims with researcher supplied coding. Source retrieval does not validate the coding or the proposed score.')

    # Country and content-language filters are metadata, never inferred from language or identity.
    for column, label in [('country',t('country')),('language',t('language'))]:
        if column in scored.columns:
            choices=sorted(scored[column].dropna().astype(str).unique())
            selected_values=st.multiselect(label,choices,default=choices)
            scored=scored[scored[column].astype(str).isin(selected_values)]
    if 'topic' in scored.columns:
        selected=st.multiselect(t('topics'), sorted(scored['topic'].dropna().unique()), default=sorted(scored['topic'].dropna().unique()))
        scored=scored[scored['topic'].isin(selected)]
    scored, time_settings, time_frequency = select_analysis_period(scored)
    if scored.empty:
        st.warning(t('missing'))
        st.stop()

    m1,m2,m3,m4=st.columns(4)
    m1.metric(t('records'),len(scored))
    m2.metric(t('risk'),f"{scored['emnri'].mean():.1f} / 100", help=explain('EMNRI'))
    m3.metric(t('politics'),f"{scored['political_framing'].mean()*100:.1f} / 100", help=explain('Political framing'))
    lo,hi=bootstrap_mean_ci(scored['emnri'])
    m4.metric(t('interval'),f'{lo:.1f} to {hi:.1f}', help=explain('Bootstrap 95% interval'))
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
    time_summary, time_comparison = render_time_analysis(scored, time_frequency, chart_registry)

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
            dates=record_dates(scored).dropna()
            if len(dates):
                chosen=st.date_input('Documented event date',value=dates.median().date())
                days=st.slider('Days before and after',3,60,14)
                result=narrative_shift(scored.loc[record_dates(scored).notna()],chosen,days)
                st.write(pd.DataFrame([result]))
                st.caption('PNSI is the difference in mean political framing after versus before an event. It is descriptive, not evidence that the event caused the change. Provide independent event documentation.')
            else:
                st.info('No valid dates available.')
    provenance={
        'generated_at_utc':datetime.now(timezone.utc).isoformat(),
        'app_version':'0.8',
        'data_origin':data_origin,
        'records_after_filters':len(scored),
        'model_status':'exploratory_unvalidated',
        'weight_amplification':weights.amplification,
        'weight_health_risk':weights.health_risk,
        'weight_credibility_gap':weights.credibility_gap,
        'missing_value_policy':'reject_missing_indicator_values',
        'source_url_field_present':'source_url' in scored.columns,
        'source_retrieval_date_field_present':'retrieved_at' in scored.columns,
        'annotation_protocol_field_present':bool({'annotation_protocol','coding_protocol'} & set(scored.columns)),
        **time_settings,
    }
    if data_origin != 'synthetic_demonstration' and not {'source_url','retrieved_at'}.issubset(scored.columns):
        st.warning('For reproducible research, include source_url and retrieved_at columns. The application does not verify submitted claims.')

    st.subheader(t('export'))
    st.dataframe(scored,use_container_width=True)
    st.download_button(t('download'),scored.to_csv(index=False).encode('utf-8-sig'),file_name='beyond_the_heat_scored.csv',mime='text/csv')
    st.download_button('📊 Download Excel workbook (.xlsx)', data=excel_bytes(scored,weights,sensitivity,provenance,
                       time_summary,time_comparison), file_name='beyond_the_heat_analysis.xlsx', mime='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
    st.markdown('#### 🖼️ Export figures as PNG images')
    st.caption('Choose a chart to export as a high resolution image. Figures reflect the currently selected data and weights.')
    if chart_registry:
        chart_name = st.selectbox('Figure',list(chart_registry),key='figure_export')
        try:
            png = figure_png(chart_registry[chart_name])
            st.download_button('Download selected figure (.png)', data=png, file_name=chart_name.lower().replace(' ','_')+'.png',mime='image/png')
        except Exception as exc:
            st.info('PNG export requires a compatible Kaleido/Chrome installation. If unavailable on this host, use the camera icon in the interactive chart toolbar.')

