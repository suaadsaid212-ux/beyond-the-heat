"""Plain language meanings for the prototype's symbols and data terms."""

DEFINITIONS = {
    'EMNRI': ('Environmental Misinformation Narrative Risk Index',
              'The name used in this prototype for the proposed composite communication risk score from 0 to 100. It is exploratory and has not been externally validated.'),
    'ECR': ('Claim reliability',
            'The independently coded reliability input from 0 to 1. Higher values indicate stronger assessed evidence support under the stated protocol. Search results do not supply this value.'),
    'A': ('Amplification',
          'Measured spread or visibility of a claim, normalised to 0 to 1 using a documented measurement rule.'),
    'H': ('Environmental health risk',
          'A defined and independently measured risk input from 0 to 1. Weather or air quality observations do not automatically become this indicator.'),
    'ICC': ('Communication credibility',
            'The communication credibility input used here, independently coded from 0 to 1. The scoring formula uses its complement, 1 minus ICC.'),
    'w_A, w_H, w_C': ('Model weights',
                     'The weights assigned to amplification, health risk and the credibility gap. The application normalises them to sum to 1.'),
    'Credibility gap': ('1 minus communication credibility',
                        'The complement of ICC. A higher gap contributes more to the proposed score, holding the other inputs fixed.'),
    'Political framing': ('Separately coded political framing intensity',
                          'A researcher supplied input from 0 to 1. It is displayed independently and is excluded from EMNRI. Political framing does not establish falsity or ideology.'),
    'PNSI': ('Political Narrative Shift Indicator',
             'The descriptive difference in average political framing after versus before a documented event, within the chosen windows. It is not a causal effect.'),
    'Bootstrap 95% interval': ('Resampling interval for the dataset mean',
                              'An interval obtained by resampling the selected records. It describes sampling variation under that procedure and does not include coding or model uncertainty.'),
    'Weight sensitivity': ('Variation across model weight choices',
                           'How the average proposed score changes when the three nonnegative weights vary on the tested grid.'),
    "Cohen's kappa": ('Agreement between two categorical annotators',
                       'A chance adjusted agreement statistic for two sets of supplied labels. It does not measure factual correctness or classifier accuracy.'),
    'Provenance': ('The recorded origin and processing history',
                   'Source links, publication dates, retrieval times, queries, passage types, coding protocols and other details used to trace a record.'),
    'Claim candidate': ('A statement retained for researcher review',
                        'A headline, abstract passage or other source statement that has not yet been independently assessed. Saving it does not verify it.'),
    'UTC': ('Coordinated Universal Time',
            'The common time standard used for timestamps and dated comparisons here. It can differ from the local date near midnight.'),
    'Publication date': ('When the source was published',
                         'The date supplied by the source index or documented by the researcher. Partial years or months retain their precision.'),
    'Retrieval time': ('When the app obtained the source or data',
                        'A collection timestamp. It does not replace an unknown publication or observation date.'),
    'API': ('Application Programming Interface',
            'A service through which the prototype requests data from a provider.'),
    'RSS': ('Really Simple Syndication',
            'A feed format used to retrieve indexed news or trending search items.'),
    'CSV': ('Comma Separated Values',
            'A plain text table format used for uploads and downloads.'),
    'DOI': ('Digital Object Identifier',
            'A persistent identifier for a registered research or other content item. A DOI alone does not establish peer review or reliability.'),
    'PDF': ('Portable Document Format',
            'A document format. This reader extracts selectable text within its limits and does not perform optical character recognition on scanned pages.'),
    'AQI': ('Air Quality Index',
            'An index derived under a specified air quality methodology. The OpenAQ panel retains original pollutant concentrations and does not calculate AQI.'),
    'PM2.5': ('Fine particulate matter',
              'Airborne particles with diameters generally 2.5 micrometres or smaller. Retain the original concentration unit supplied by the station.'),
    'PM10': ('Particulate matter of 10 micrometres or smaller',
             'A particle size category used in air quality monitoring. It is a pollutant measurement, not an AQI score.'),
    'NO2': ('Nitrogen dioxide', 'An air pollutant. Original units and observation times are retained.'),
    'O3': ('Ozone', 'An air pollutant. Original units and observation times are retained.'),
    'CO': ('Carbon monoxide', 'An air pollutant. Original units and observation times are retained.'),
    'SO2': ('Sulphur dioxide', 'An air pollutant. Original units and observation times are retained.'),
    'FIRMS': ('Fire Information for Resource Management System',
              'NASA service distributing satellite active fire and thermal anomaly observations.'),
    'VIIRS': ('Visible Infrared Imaging Radiometer Suite',
              'A satellite instrument used for active fire and thermal anomaly detection in the supported FIRMS products.'),
    'MODIS': ('Moderate Resolution Imaging Spectroradiometer',
              'A satellite instrument used for active fire and thermal anomaly detection. Its confidence values differ from VIIRS confidence categories.'),
    'NRT': ('Near Real Time',
            'Rapidly processed observations that may be provisional. Check the product documentation and standard processing availability for research use.'),
    'FRP': ('Fire Radiative Power',
            'An estimate of radiant power associated with detected fire pixels, reported in megawatts. It does not measure burned area or unique fire events.'),
    'MW': ('Megawatt', 'A unit of power equal to one million watts, used for FRP.'),
    'K': ('Kelvin', 'The thermodynamic temperature unit used for satellite brightness temperature.'),
    'ERA5': ('ECMWF atmospheric reanalysis, fifth generation',
             'A dataset combining a weather model with observations to estimate past atmospheric conditions. It is not a local station reading.'),
    'WHO': ('World Health Organization', 'A suggested starting point for public health and environmental health data.'),
    'WMO': ('World Meteorological Organization', 'A suggested starting point for weather and climate information.'),
    'NASA': ('National Aeronautics and Space Administration', 'The United States agency providing Earthdata and FIRMS resources.'),
    'NOAA': ('National Oceanic and Atmospheric Administration', 'A United States source of weather, ocean and climate data.'),
    'EPA': ('Environmental Protection Agency', 'The United States agency providing the linked AirData resources.'),
    'EEA': ('European Environment Agency', 'A suggested source of environmental information for Europe.'),
    'NCSI': ('National Centre for Statistics and Information', 'The linked official statistics organisation in Oman.'),
}


def explain(term):
    name, meaning = DEFINITIONS[term]
    return f'{term}: {name}. {meaning}'


def render_definitions():
    import pandas as pd
    import streamlit as st
    st.subheader('Definitions and abbreviations')
    st.caption('Formula symbols use the meanings defined for this prototype. Definitions of an indicator do not establish that its measurement has been validated.')
    query = st.text_input('Find a definition or abbreviation', placeholder='For example: ECR, PNSI, FRP, publication date')
    rows = [{'Term or symbol': term, 'Full name or meaning': name, 'Explanation': meaning}
            for term, (name, meaning) in DEFINITIONS.items()
            if not query or query.casefold() in (term+' '+name+' '+meaning).casefold()]
    if rows:
        st.dataframe(pd.DataFrame(rows), hide_index=True, use_container_width=True)
    else:
        st.info('No matching definition. Try the abbreviation or a word from the term.')
    st.markdown('Data terminology references: [NASA FIRMS](https://www.earthdata.nasa.gov/data/tools/firms/faq), '
                '[AirNow AQI](https://www.airnow.gov/aqi/), '
                '[Copernicus ERA5](https://www.ecmwf.int/en/forecasts/dataset/ecmwf-reanalysis-v5).')
