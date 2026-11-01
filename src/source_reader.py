"""Read bounded public HTTPS documents without contacting private network targets."""
from datetime import datetime, timezone
from hashlib import sha256
import http.client
import ipaddress
import json
import os
import socket
import ssl
import subprocess
import sys
from urllib.parse import parse_qsl, urljoin, urlsplit

MAX_BYTES = 8 * 1024 * 1024


class SourceReadError(RuntimeError):
    pass


def _destination(url):
    try:
        p = urlsplit(url)
        if (p.scheme != 'https' or not p.hostname or p.username is not None
                or p.password is not None or p.port not in (None, 443)):
            raise ValueError()
        host = p.hostname.rstrip('.').encode('idna').decode('ascii')
        if host == 'localhost' or host.endswith(('.localhost', '.local', '.internal')):
            raise ValueError()
        if any(key.lower() in {'token', 'api_key', 'apikey', 'access_token', 'signature', 'password', 'key'}
               for key, value in parse_qsl(p.query)):
            raise SourceReadError('Use a public source URL without access tokens or credentials.')
        try:
            ipaddress.ip_address(host)
        except ValueError:
            pass
        else:
            raise ValueError()
    except (ValueError, UnicodeError):
        raise SourceReadError('Enter an HTTPS URL on a public website domain.') from None
    try:
        addresses = list(dict.fromkeys(row[4][0] for row in socket.getaddrinfo(host, 443, type=socket.SOCK_STREAM)))
    except OSError:
        raise SourceReadError('The source website could not be resolved. Open the original link or try another source.') from None
    if not addresses or any(not ipaddress.ip_address(address).is_global for address in addresses):
        raise SourceReadError('This URL does not resolve exclusively to public internet addresses.')
    addresses.sort(key=lambda address: ipaddress.ip_address(address).version)
    return p, host, addresses


def _public_document(url):
    current = url
    for attempt in range(4):
        parts, host, addresses = _destination(current)
        if host == 'news.google.com':
            raise SourceReadError('Open the news link, then paste the publisher article URL in Read a URL. The headline can already be saved as an unreviewed candidate.')
        connection = None
        try:
            # Pin the already validated address; preserve the original TLS hostname.
            connection = http.client.HTTPSConnection(host, timeout=18, context=ssl.create_default_context())
            raw_socket = socket.create_connection((addresses[0], 443), timeout=10)
            try:
                connection.sock = ssl.create_default_context().wrap_socket(raw_socket, server_hostname=host)
            except Exception:
                raw_socket.close()
                raise
            path = (parts.path or '/') + ('?'+parts.query if parts.query else '')
            connection.request('GET', path, headers={'Host': host, 'User-Agent': 'BeyondTheHeatResearch/0.6',
                                                     'Accept-Encoding': 'identity', 'Accept': 'text/html,application/pdf,text/plain'})
            response = connection.getresponse()
            if response.status in (301, 302, 303, 307, 308):
                location = response.getheader('Location')
                if not location:
                    raise SourceReadError('The source returned an incomplete redirect.')
                current = urljoin(current, location)
                continue
            if response.status != 200:
                raise SourceReadError(f'The source returned HTTP {response.status}. Open the original source; its text is not available in this reader.')
            declared = response.getheader('Content-Length')
            if declared and declared.isdigit() and int(declared) > MAX_BYTES:
                raise SourceReadError('The source is larger than this reader supports. Use a smaller document or a specific article page.')
            body = response.read(MAX_BYTES+1)
            if len(body) > MAX_BYTES:
                raise SourceReadError('The source is larger than this reader supports.')
            return body, response.getheader('Content-Type', ''), current
        except SourceReadError:
            raise
        except (OSError, ssl.SSLError, http.client.HTTPException):
            raise SourceReadError('This website could not be read here. Open its source link or try another public article.') from None
        finally:
            if connection is not None:
                connection.close()
    raise SourceReadError('The source redirected too many times.')


_PDF_WORKER = '''
import io,json,sys
try:
    import resource
    resource.setrlimit(resource.RLIMIT_AS,(512*1024*1024,512*1024*1024))
    resource.setrlimit(resource.RLIMIT_CPU,(10,10))
except ImportError:
    pass
from pypdf import PdfReader
reader=PdfReader(io.BytesIO(sys.stdin.buffer.read()),strict=False)
if reader.is_encrypted:
    raise ValueError('Encrypted PDF')
pages=[]
remaining=60000
for index,page in enumerate(reader.pages[:25]):
    contents=page.get_contents()
    if contents is not None and len(contents.get_data())>4*1024*1024:
        raise ValueError('Page too complex')
    text=(page.extract_text() or '')[:remaining]
    pages.append({'page':index+1,'text':text})
    remaining-=len(text)
    if remaining<=0:break
print(json.dumps({'pages':pages,'partial':len(reader.pages)>len(pages) or remaining<=0}))
'''


def extract_document(body, content_type, url):
    if body.startswith(b'%PDF-') or 'application/pdf' in content_type:
        try:
            result = subprocess.run([sys.executable, '-c', _PDF_WORKER], input=body,
                                    stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=15,
                                    env={'PATH': os.environ.get('PATH', ''), 'LANG': 'C.UTF-8'})
            if result.returncode != 0:
                raise ValueError()
            parsed = json.loads(result.stdout)
            pages = parsed['pages']
        except (ValueError, KeyError, subprocess.TimeoutExpired):
            raise SourceReadError('This PDF could not be extracted within the reader limits. Open the original PDF.') from None
        text = '\n\n'.join(f"[Page {page['page']}]\n{page['text']}" for page in pages)
        if sum(len(page['text'].strip()) for page in pages) < 80:
            raise SourceReadError('This PDF has too little selectable text. It may be scanned; use the original document for review.')
        return text, 'PDF source text', bool(parsed.get('partial'))
    if not any(kind in content_type for kind in ('text/html', 'text/plain', 'application/xhtml+xml')):
        raise SourceReadError('This reader supports public HTML pages, text and PDFs. Open other data formats at the original source.')
    if 'text/plain' in content_type:
        text = body.decode('utf-8', errors='replace')
    else:
        import trafilatura
        text = trafilatura.extract(body, url=url, include_comments=False,
                                   include_tables=False, favor_precision=True) or ''
    if len(text.strip()) < 80 or any(marker in text[:1500].lower() for marker in
                                   ('verify you are human', 'checking your browser', 'enable javascript and cookies to continue')):
        raise SourceReadError('This page has no readable public article text. Open the source link for its full context.')
    return text[:60000], 'Original source text', len(text) > 60000


def read_source(url):
    if not isinstance(url, str) or len(url) > 2000:
        raise SourceReadError('Enter a public source URL of up to 2000 characters.')
    body, content_type, final_url = _public_document(url.strip())
    text, kind, partial = extract_document(body, content_type, final_url)
    return {'requested_url': url.strip(), 'url': final_url, 'text': text,
            'text_kind': kind, 'partial': partial, 'retrieved_at': datetime.now(timezone.utc).isoformat(),
            'text_sha256': sha256(text.encode()).hexdigest()}
