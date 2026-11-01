"""Free source discovery. Search results are evidence candidates, not truth labels."""
from datetime import date, datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from hashlib import sha256
from html import unescape
from html.parser import HTMLParser
import re
from urllib.parse import urlsplit, urlunsplit
import xml.etree.ElementTree as ET

import requests
from src.time_periods import date_bounds, publication_in_period

PROVIDERS = ['News: Google News RSS', 'Research papers: Crossref']
EDITIONS = {
    'English': ('en-US', 'US', 'US:en'), 'العربية': ('ar', 'SA', 'SA:ar'),
    'Русский': ('ru', 'RU', 'RU:ru'), 'Español': ('es', 'ES', 'ES:es'),
    'Français': ('fr', 'FR', 'FR:fr'),
}
OFFICIAL_SOURCES = {
    'All indexed sources': (), 'WHO': ('who.int',), 'WMO': ('wmo.int',),
    'NASA': ('nasa.gov',), 'Copernicus': ('copernicus.eu',),
    'NOAA': ('noaa.gov',), 'US EPA': ('epa.gov',),
    'European Environment Agency': ('eea.europa.eu',),
    'Oman NCSI': ('ncsi.gov.om',), 'Roshydromet': ('meteorf.gov.ru',),
}
SEARCH_FIELDS = ['result_id', 'title', 'url', 'publisher', 'published_at',
                 'excerpt', 'excerpt_kind', 'provider', 'query', 'country_focus',
                 'edition_language', 'edition_country', 'retrieved_at']


class SourceSearchError(RuntimeError):
    pass


class _PlainText(HTMLParser):
    def __init__(self):
        super().__init__()
        self.parts = []

    def handle_data(self, data):
        self.parts.append(data)


def plain_text(value):
    parser = _PlainText()
    parser.feed(str(value or ''))
    return re.sub(r'\s+', ' ', unescape(' '.join(parser.parts))).strip()


def public_link(url):
    """Validate display links; outbound retrieval applies stricter IP validation."""
    try:
        parts = urlsplit(str(url or '').strip())
        if (parts.scheme not in ('https', 'http') or not parts.hostname
                or parts.username is not None or parts.password is not None):
            return ''
        if parts.port not in (None, 80, 443):
            return ''
        return urlunsplit((parts.scheme, parts.netloc, parts.path, parts.query, ''))
    except ValueError:
        return ''


def _response(url, params):
    try:
        response = requests.get(url, params=params, headers={
            'User-Agent': 'BeyondTheHeatResearch/0.6', 'Accept': 'application/json, application/rss+xml, text/xml'},
            timeout=(8, 22), stream=True)
        try:
            if response.status_code == 429:
                raise SourceSearchError('The source index is busy or rate limited. Please try again later.')
            if response.status_code != 200:
                raise SourceSearchError(f'The source index returned HTTP {response.status_code}. Try the other search provider or read a public URL.')
            chunks, size = [], 0
            for chunk in response.iter_content(65536):
                size += len(chunk)
                if size > 4 * 1024 * 1024:
                    raise SourceSearchError('The source index returned too much data. Use fewer results.')
                chunks.append(chunk)
            return b''.join(chunks)
        finally:
            response.close()
    except requests.RequestException:
        raise SourceSearchError('The source index could not be reached. Try again later or read a public URL.') from None


def _record(title, url, publisher, published, excerpt, kind, provider, query, country, language='', edition=''):
    title, url = plain_text(title), public_link(url)
    if not title or not url:
        return None
    return dict(zip(SEARCH_FIELDS, [
        sha256((provider+'\0'+url+'\0'+title).encode()).hexdigest()[:20],
        title, url, plain_text(publisher), published or '', plain_text(excerpt),
        kind, provider, query, country, language, edition,
        datetime.now(timezone.utc).isoformat(),
    ]))


def _news(query, country, language, scope, days, limit, start=None, end=None, custom=False):
    hl, gl, ceid = EDITIONS[language]
    terms = ' '.join(part for part in [query.strip(), country.strip()] if part)
    domains = OFFICIAL_SOURCES[scope]
    if domains:
        terms += ' ' + ' OR '.join('site:'+domain for domain in domains)
    if custom:
        terms += f' after:{(start-timedelta(days=1)).isoformat()} before:{(end+timedelta(days=1)).isoformat()}'
    elif days is not None:
        terms += f' when:{days}d'
    data = _response('https://news.google.com/rss/search',
                     {'q': terms, 'hl': hl, 'gl': gl, 'ceid': ceid})
    try:
        root = ET.fromstring(data)
    except ET.ParseError:
        raise SourceSearchError('The news feed did not return readable RSS. Try again later.') from None
    if root.tag != 'rss' or root.find('channel') is None:
        raise SourceSearchError('The news provider returned an unexpected response.')
    rows = []
    for item in root.findall('./channel/item'):
        publisher_node = item.find('source')
        publisher = publisher_node.text if publisher_node is not None else ''
        if domains:
            source_host = urlsplit(publisher_node.get('url', '') if publisher_node is not None else '').hostname or ''
            if not any(source_host == d or source_host.endswith('.'+d) for d in domains):
                continue
        published = item.findtext('pubDate') or ''
        try:
            stamp = parsedate_to_datetime(published)
            stamp = stamp.replace(tzinfo=timezone.utc) if stamp.tzinfo is None else stamp
            published = stamp.isoformat()
        except (TypeError, ValueError, OverflowError):
            pass
        if start is not None and not publication_in_period(published, start, end):
            continue
        title = item.findtext('title') or ''
        row = _record(title, item.findtext('link'), publisher, published, title,
                      'News headline', PROVIDERS[0], terms, country, hl, gl)
        if row:
            rows.append(row)
        if len(rows) >= limit:
            break
    return rows, terms


def _crossref_date(item):
    for field in ('published', 'published-online', 'published-print', 'issued'):
        info = item.get(field)
        if not isinstance(info, dict):
            continue
        parts = info.get('date-parts')
        try:
            if not isinstance(parts, list) or not parts or not isinstance(parts[0], list) or not parts[0]:
                continue
            values = [int(value) for value in parts[0][:3]]
            date(*(values + [1] * (3-len(values))))
            # Validate without storing invented month or day values.
            return '-'.join(str(value).zfill(4 if index == 0 else 2) for index, value in enumerate(values))
        except (TypeError, ValueError, OverflowError):
            continue
    return ''


def _papers(query, country, limit, start=None, end=None):
    terms = ' '.join(part for part in [query.strip(), country.strip()] if part)
    # Crossref may return partial matches. Inspect a bounded candidate pool and
    # retain literal keyword matches in the visible title or abstract.
    params = {'query.bibliographic': terms, 'rows': min(90, limit*3)}
    if start is not None:
        params['filter'] = f'from-pub-date:{start.isoformat()},until-pub-date:{end.isoformat()}'
    data = _response('https://api.crossref.org/works', params)
    try:
        import json
        payload = json.loads(data)
        items = payload['message']['items']
        if not isinstance(items, list):
            raise ValueError()
    except (ValueError, KeyError, TypeError):
        raise SourceSearchError('Crossref returned an unexpected metadata response.') from None
    rows = []
    stopwords = {'a', 'an', 'and', 'are', 'as', 'at', 'by', 'for', 'from', 'in', 'is',
                 'of', 'on', 'or', 'the', 'to', 'with'}
    keywords = set(re.findall(r'[^\W_]+', terms.lower(), re.UNICODE))-stopwords
    for item in items:
        if not isinstance(item, dict):
            continue
        titles = item.get('title') or []
        title = titles[0] if isinstance(titles, list) and titles else ''
        abstract = plain_text(item.get('abstract'))
        visible_words = set(re.findall(r'[^\W_]+', (plain_text(title)+' '+abstract).lower(), re.UNICODE))
        if keywords and not keywords.issubset(visible_words):
            continue
        published = _crossref_date(item)
        if start is not None and not publication_in_period(published, start, end):
            continue
        url = item.get('URL') or ''
        row = _record(title, url, item.get('publisher'), published,
                      abstract or title, 'Publisher abstract' if abstract else 'Research title only',
                      PROVIDERS[1], terms, country)
        if row:
            row['doi'] = item.get('DOI', '')
            row['publication_type'] = item.get('type', '')
            licenses = item.get('license') or []
            row['license_urls'] = '; '.join(str(x.get('URL') or '') for x in licenses if isinstance(x, dict))
            rows.append(row)
        if len(rows) >= limit:
            break
    return rows, terms


def search_sources(query, *, provider=PROVIDERS[0], country='', language='English',
                   scope='All indexed sources', days=30, limit=20, start_date=None, end_date=None):
    if not isinstance(query, str) or not 2 <= len(query.strip()) <= 250:
        raise ValueError('Enter a search of 2 to 250 characters.')
    if provider not in PROVIDERS or language not in EDITIONS or scope not in OFFICIAL_SOURCES:
        raise ValueError('Choose one of the available search options.')
    if (type(limit) is not int or not 1 <= limit <= 30
            or (days is not None and (type(days) is not int or not 1 <= days <= 90))):
        raise ValueError('Choose 1 to 30 results and a news window of 1 to 90 days.')
    if not isinstance(country, str) or len(country) > 80:
        raise ValueError('Keep the country or region focus under 80 characters.')
    if provider == PROVIDERS[1] and scope != 'All indexed sources':
        raise ValueError('Official website filters apply to the news index only.')
    custom = start_date is not None or end_date is not None
    if custom:
        start, end = date_bounds(start_date, end_date)
    elif days is not None:
        end = datetime.now(timezone.utc).date()
        start = end-timedelta(days=days-1)
    else:
        start, end = None, None
    rows, terms = (_news(query, country, language, scope, days, limit, start, end, custom)
                   if provider == PROVIDERS[0] else _papers(query, country, limit, start, end))
    unique, seen = [], set()
    for row in rows:
        if row['url'] not in seen:
            row['search_start_date'] = start.isoformat() if start else ''
            row['search_end_date'] = end.isoformat() if end else ''
            unique.append(row)
            seen.add(row['url'])
    return {'results': unique, 'query': terms, 'provider': provider,
            'retrieved_at': datetime.now(timezone.utc).isoformat(),
            'country_focus': country, 'scope': scope, 'news_days': days if not custom and provider == PROVIDERS[0] else None,
            'start_date': start.isoformat() if start else '', 'end_date': end.isoformat() if end else '',
            'date_policy': 'inclusive publication span, UTC for timestamps; missing or boundary ambiguous dates excluded when bounded'}
