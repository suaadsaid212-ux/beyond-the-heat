import streamlit as st
from src.localization import translate
from src.definitions import render_definitions


def render_methodology(lang='en'):
    t = lambda key: translate(lang, key)
    render_definitions()
    st.header(t('method'))
    st.latex(r'EMNRI_i=100(1-ECR_i)[w_A A_i+w_H H_i+w_C(1-ICC_i)]')
    st.write('ECR is claim reliability; A is amplification; H is environmental health risk; ICC is communication credibility. Each indicator must be independently operationalized and validated. Political framing is kept separate.')
    st.write('The application does not independently fact-check text or infer political ideology. External weather and air quality observations provide optional context and do not automatically change the score. Uploaded scores must come from a documented coding or measurement process. Missing data are rejected rather than silently imputed.')
    st.write('Version 0.8 organises the prototype into Find claims, Claim analysis, Environmental data, and Methodology and definitions pages. Keyword claim searches can be started from every page. Find claims retrieves news and scholarly source material; Google Trends keyword controls prepare official website links and accept exported CSV results. Trends interest does not identify claims or supply an amplification score. The app also includes publication period searches, public source reading, dated claim collection and descriptive period comparisons. Headlines, abstracts and extracted passages are candidate evidence. Source links, passage types and retrieval dates are retained. The researcher must independently code all five indicators, record a protocol and rationale, and mark a collected claim Reviewed before it enters analysis. Country and content language are researcher supplied metadata. A search country focus or news edition does not establish either.')
    st.write('Source publication dates and retrieval times are separate. Selected period endpoints are inclusive and timed records use UTC. Unknown dates are not replaced with retrieval dates. Year or month precision is preserved. Such records enter a bounded source search only if their entire publication span fits inside it; a documented complete date is required for daily, weekly and monthly claim analysis. Period counts and averages describe the selected corpus and can change with collection coverage, source composition and coding. They do not establish misinformation prevalence or causal effects.')
    st.write('Descriptive political event shifts, weight sensitivity, optional annotation agreement and provenance metadata are not substitutes for external validation. Future research: annotated claim datasets, inter-rater reliability, supervised classifiers, event study methods, uncertainty propagation, temporal leakage checks, cross-region validation and public trust surveys.')

    st.subheader(t('sources'))
    st.markdown('''**Global:** [WHO](https://www.who.int/data), [WMO](https://wmo.int/), [NASA Earthdata](https://www.earthdata.nasa.gov/), [Copernicus](https://climate.copernicus.eu/).  
    **United States:** [NOAA](https://www.noaa.gov/), [EPA AirData](https://www.epa.gov/outdoor-air-quality-data).  
    **Europe:** [European Environment Agency](https://www.eea.europa.eu/).  
    **Oman:** [National Centre for Statistics and Information](https://www.ncsi.gov.om/).  
    **Russia:** [Roshydromet](https://www.meteorf.gov.ru/).  
    Open the Find claims page for indexed news or scholarly metadata, or use its Read a URL tab for a specific public report. Official website filters depend on news index coverage and do not search every agency dataset. The Environmental data page provides its own integrations. Verify licensing, coverage and country-specific access before use.''')
