# Beyond the Heat

**Environmental Misinformation Intelligence Platform**

An open, exploratory Streamlit research prototype for analyzing environmental claims, media framing, narrative amplification, and environmental health communication risk.

## Research status

**Version 0.6: prototype only.** Search real news and scholarly metadata, read public source pages, and build a corpus of claims with source passages and links. The EMNRI composite score is a proposed construct, not a validated scientific or public health measure. Bundled scoring data are synthetic. Optional environmental observations are retrieved separately and are not automatically included in the score. Political framing is not equivalent to misinformation, and the platform does not identify political ideology or prove causality.

## Search sources and collect claims

1. In **Search sources**, enter a topic, claim or organisation and an optional country focus. Choose Google News RSS for news or Crossref for research metadata. No additional API key is required.
2. Select a result and open its source link. **Capture a claim from this result** retains the headline or available abstract as an unreviewed candidate. The text type is labelled; a title is never presented as the full article.
3. To inspect a public article or agency report, use **Read a URL** with its HTTPS publisher URL. The reader supports HTML, plain text and selectable text PDFs. Google News redirect links must first be opened to obtain the publisher URL. Restricted, scanned or inaccessible sources may need manual reading at the original link.
4. Inspect a suggested passage or retain another passage copied from the source text. Enter the claim for review, confirm the country and language, choose a topic, then save. Suggested passages are selected by word overlap and source order; they are not generated fact checks.
5. In **Saved claims**, record all five indicators using your documented protocol, add the evidence and rationale, and mark the claim **Reviewed**. **Analyse my reviewed claims** sends only complete reviewed records to the dashboard. Uncoded values stay missing and cannot enter the score. The EMNRI formula is unchanged.

Search results include a title, publisher, source URL, publication date when supplied, retrieval time, provider and search query. Saved claims retain the passage type and a hash of the available source text. Publication dates keep the provider's precision. A year only date does not become an invented daily observation. Country focus and news editions are search settings, not verified content geography or detected language. Confirm those separately when capturing a claim.

Google News is a changing news index. Its 7, 30 and 90 day windows and official website filters do not provide a complete agency archive or database search. Crossref returns publisher deposited metadata across publication types; abstracts and linked full text vary. The app examines up to three times the requested number of Crossref results, at most 90, and displays only records containing the supplied keywords and country words in the title or available abstract, ignoring common English connecting words. Use a few focused keywords. This literal filter can miss relevant work and is not a systematic literature search. Neither provider establishes claim reliability, scientific consensus or peer review status. Source text can be incomplete and may have reuse restrictions; read and attribute the original source. Provider availability and terms can change.

The reader accepts public HTTPS domains without URL credentials or access tokens, validates every redirect, rejects private network destinations and limits documents to 8 MiB. It retains up to 60,000 text characters; PDFs are limited to 25 pages with extraction time and memory limits. A limited preview is labelled. The reader does not sign in, run website scripts or perform OCR.

Claims and searches remain in the current Streamlit session. Download the claim corpus CSV or evidence workbook before closing the session. Restore the corpus CSV in **Saved claims** to continue later. The session holds up to 500 claims and the last 100 searches. Search responses are cached for 15 minutes; the original retrieval timestamp remains visible. No automatic crawling or background polling runs. The evidence workbook contains claims, search provenance and collection notes. A separate CSV contains only analysis ready claims.

## Run locally

```bash
pip install -r requirements.txt
streamlit run app.py
```

## Deploy to Streamlit Community Cloud

1. Create a GitHub repository and upload the contents of this folder, including `app.py`, `src/`, `data/`, and `requirements.txt`.
2. Open https://share.streamlit.io and sign in with GitHub.
3. Select the repository, branch `main`, and entrypoint `app.py`.
4. Deploy. The demonstration, weather and Google Trends panels do not need an OpenAQ key. To enable air quality, add `OPENAQ_API_KEY` in Streamlit app settings under Secrets and restart the app. See the OpenAQ setup below.

## Input data

Upload a CSV with required columns:

| Column | Meaning | Range |
|---|---|---|
| `claim_reliability` | Independently assessed evidence support | 0 to 1 |
| `amplification` | Normalized observed narrative amplification | 0 to 1 |
| `health_risk` | Validated or clearly defined environmental health risk measure | 0 to 1 |
| `communication_credibility` | Source communication credibility | 0 to 1 |
| `political_framing` | Political framing intensity, separate from misinformation | 0 to 1 |

Optional columns: `date`, `topic`, `source`, `claim`. Each row represents one observation. Values must be scored using a documented protocol before uploading. The app does not compute these five indicators from raw text or live sensor data.

## Proposed score

`EMNRI = 100 × (1 - ECR) × (wA × A + wH × H + wC × (1 - ICC))`

All indicators are in [0, 1]. Weights are nonnegative and sum to one. Political framing is excluded from EMNRI and shown separately. Weights are exploratory and require empirical validation. Do not interpret score thresholds as established categories.

## Next scientific development

1. Define a claim-level annotation manual with uncertainty and insufficient-evidence labels.
2. Connect environmental datasets and verified fact-check sources with documented provenance.
3. Estimate construct validity, inter-rater agreement, predictive performance and calibration.
4. Test robustness across extreme heat, water, air quality and food security.
5. Integrate policy event timelines using documented sources and careful temporal methods.
6. Add trust surveys or experiments before making claims about changes in public trust.

## License

No license is assigned yet. Choose one before publishing if you want others to reuse the code.


## Multilingual and multi-country support (v0.2)
Choose English, Arabic, Russian, Spanish or French in the sidebar. Upload UTF-8 CSV files with optional `country` and `language` columns (BCP-47 language codes such as `ar`, `ru`, `en`). Filter by country, language and topic. Export preserves non-Latin scripts in UTF-8 with BOM for spreadsheet compatibility. See `data/multilingual_upload_template.csv`.

**Important:** interface translation is not claim translation, language detection or fact checking. The source search and collection controls currently use English labels; news editions support the five listed languages. Scores must be obtained through documented language appropriate annotation and verification; do not compare scores across countries until measurement equivalence is tested. Suggested agency links can be opened in the URL reader where public text is available, with index and extraction coverage limitations as described above.

## Version 0.3: export and climate visuals

* Export the filtered, scored dataset as CSV or a formatted Excel workbook (`.xlsx`) with summary, model weights, and methodology sheets.
* Export each Plotly radar, scatter, trend, or network chart as a high-resolution PNG image. The figure selector only lists charts present for the selected dataset.
* Animated climate-inspired gradient background and sun-like orb, responsive for mobile screens. Reduced-motion accessibility settings disable animations.
* Styling is CSS only, so no external climate images or image licensing are required. The interface uses Google Fonts when available and system sans-serif otherwise.
* PNG generation uses Kaleido. If a Streamlit deployment lacks the compatible rendering environment, use the chart toolbar camera button or configure the runtime accordingly.
* The visuals are illustrative, and the model remains an unvalidated research prototype.

## Version 0.4 research upgrades

* Fixed Excel export parameter mismatch (`credibility_gap`).
* Added a weight sensitivity grid over all 66 possible nonnegative weight triplets in increments of 0.1, downloadable as an Excel sheet.
* Added descriptive Political Narrative Shift Indicator (PNSI) with event date and time window. The output is not causal evidence.
* Added optional Cohen's kappa for two independently supplied categorical annotations (`annotator_1`, `annotator_2`).
* Added export provenance with model status, weight configuration, record count, timestamp and data origin.
* Flagged missing source provenance (`source_url`, `retrieved_at`) in uploaded data.

**Research limitations:** The five input indicators must be independently measured and validated. The demo dataset is synthetic. The existing bootstrap interval covers resampling variation only, not measurement or weight uncertainty. Scores with missing indicators are rejected. No political ideology is inferred. Real multilingual model evaluation, missingness strategies, calibration, and external validity studies are future work.

## External data connectors (v0.5)

The dashboard includes four optional data panels:

* Open-Meteo historical weather API, with coordinates and historical date filters. No key required for eligible noncommercial use. Data can be downloaded as CSV. Cite Open-Meteo and comply with its terms.
* Google Trends current trending searches RSS (country availability varies), plus an importer for Google Trends Interest over time CSV exported from https://trends.google.com/trends/. Official Google Trends API access is restricted and not bundled. Trending searches are not the same as a topic-specific time series.
* OpenAQ air quality observations with station search and CSV, Excel and chart exports. A free API key is required; see the setup below.
* NASA FIRMS satellite fire and thermal anomaly detections with a map, original data, observation dates and downloadable figures. A free MAP key is required; see the setup below.

Connectors show an error message if an external service is unavailable. They do not inject search interest, weather or air quality variables into misinformation scoring: such an inference requires a documented research design and validation. Configure provider keys through Streamlit Cloud Secrets.

Further optional sources: GDELT for international news, Google Trends API alpha (approval), Google Trends BigQuery public trending datasets (Google Cloud project). Check licensing and quotas before integrating.

## OpenAQ air quality setup

The air quality panel uses OpenAQ API v3. It supports searching by coordinates within a radius of up to 25 km or by a two letter country code, selecting a station, and retrieving its latest available observations. Requests run only when a search or fetch button is pressed. Results remain in the current Streamlit session during unrelated widget changes. There is no background polling.

1. Register at https://explore.openaq.org/register and obtain your key at https://explore.openaq.org/account.
2. In Streamlit Community Cloud, open your app settings and select Secrets.
3. Enter the following configuration with your own key and restart the app:

```toml
OPENAQ_API_KEY = "paste your key here"
```

For local use, you can configure the same environment variable or create `.streamlit/secrets.toml` using the included `.streamlit/secrets.toml.example`. The real secrets file is ignored by Git. The download contains a placeholder only.

Open the **Air quality: OpenAQ** panel and search for stations, then select one and fetch its latest readings. The default coordinates are near Muscat. An empty response is displayed as missing coverage, never as a zero pollution reading. Search results are paginated and are not presented as a complete country inventory.

CSV and Excel exports retain sensor IDs, original units, observation times, retrieval times, coordinates, source URLs, providers and licence metadata. The Excel workbook also includes the station metadata and the search query. Charts compare sensors for one parameter and unit at a time. A PNG can be prepared on demand; the Plotly camera button is available if the host does not support server image rendering.

Some stations no longer report, so the latest available observation may be old. Observations already older than 24 hours at retrieval are flagged. This is a freshness notice, not a health threshold. Reported country labels and localities are preserved without geographic correction. Check these against the station coordinates before comparing countries. During the setup check on 1 November 2026, the `iso=OM` query included records labelled Oman with an Abu Dhabi provider and Al Ain locality, with some last updates in May 2024. This source metadata issue should not be interpreted as confirmed current Oman coverage.

Raw concentrations are not AQI values, misinformation judgments or validated health risk scores. Missing units are not guessed and values are not converted. OpenAQ observations do not alter EMNRI weights or inputs. Attribute data to OpenAQ and the original provider, and check each station's licence and its validity period. Missing licence metadata is disclosed, not replaced with an assumed open licence.

General API use is free within the published limits of 60 requests per minute and 2,000 per hour. Authentication, quota and connectivity errors are shown without raw request headers. Details: https://docs.openaq.org/using-the-api/rate-limits, https://docs.openaq.org/resources/locations and https://docs.openaq.org/resources/latest.

This update also fixes duplicate score columns when the dashboard recomputes sensitivity from already scored data, and includes the previously missing annotation agreement dependency. The EMNRI formula and weights are unchanged.

To run the validation suite locally, install `pytest` and run `python -m pytest -q` from this folder. The tests cover scoring, source search parsing and errors, bounded public document reading, claim capture and coding, exports and Streamlit workflows without making external API calls.

## NASA FIRMS fire hotspot setup

In Streamlit app settings under Secrets, add the following alongside your existing OpenAQ setting, then restart the app:

```toml
FIRMS_MAP_KEY = "paste your NASA MAP key here"
```

The included secrets example has placeholders for both providers. Neither credential is included in this download. For local use, the same setting can be supplied in your private `.streamlit/secrets.toml` or as an environment variable.

Open **Fire hotspots: NASA FIRMS**. Choose VIIRS NOAA 20, VIIRS NOAA 21 or MODIS and either recent observations or standard processing. The default is VIIRS NOAA 20. Check product date availability with the supplied button before requesting a historical period.

Enter a bounding rectangle as west, south, east and north coordinates. The default rectangle covers the Oman region and can include neighbouring territory. This is a geographic rectangle, not an Oman administrative boundary filter. NASA currently marks the country query API as unavailable, so this connector uses the documented Area API. Split a rectangle crossing the date line into separate queries.

Each query covers one product and 1 to 5 days, matching the current Area API documentation. With no start date, NASA returns the latest selected days including today in UTC. With a start date, the query covers that date through start plus days minus one. Availability and completeness depend on the product, satellite overpasses and processing. NASA applies transaction quotas; your key confirmation states 5,000 transactions per 10 minutes, and a request may consume multiple transactions. The app fetches only on button clicks and retains the last result during unrelated widget changes.

The panel provides an interactive point map, a coordinate plot, daily detection counts and CSV, Excel and PNG downloads. Original NASA CSV columns are retained in their own export and Excel sheet. Normalised observations add parsed UTC times, numeric coordinates, FRP in megawatts, product, retrieval time and a public documentation URL. Credential bearing API URLs are never included in the downloads. The reproducible request template uses `[MAP_KEY]` in place of the credential. A response exceeding 20 MiB is rejected with a request to narrow the area, rather than truncated. The interactive map displays up to 5,000 points with an explicit notice; tables, figures and exports retain all records.

FIRMS detections mark satellite pixels containing active fire or other thermal anomalies, including possible industrial sources. They do not establish confirmed wildfire events, exact ignition locations, unique fire counts, burned area, local air temperature or misinformation. Empty results do not prove an absence of fire. Clouds, smoke, overpass timing and outages affect detection. The existing EMNRI formula is unchanged and FIRMS observations do not automatically enter that score.

VIIRS confidence uses low, nominal and high categories (l, n and h). MODIS confidence is reported as a percentage. These measures are not interchangeable. Brightness temperatures are in kelvins. FRP is fire radiative power in megawatts, not energy or burned area. NRT products are provisional; use appropriate standard processing products for scientific analysis. Cite NASA FIRMS and retain the specific source product, version and retrieval date supplied by the data.

References: https://firms.modaps.eosdis.nasa.gov/api/, https://firms.modaps.eosdis.nasa.gov/api/area/, https://firms.modaps.eosdis.nasa.gov/api/data_availability/ and https://www.earthdata.nasa.gov/data/tools/firms/faq.
