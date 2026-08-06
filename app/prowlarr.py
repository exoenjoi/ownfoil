"""Prowlarr client: search indexers and hand a release to Prowlarr's own download client."""
import logging
import requests

logger = logging.getLogger('main')

REQUEST_TIMEOUT = 30


def normalize_url(url):
    url = (url or '').strip().rstrip('/')
    if url and not url.startswith(('http://', 'https://')):
        url = 'http://' + url
    return url


def _request(method, settings, path, **kwargs):
    url = normalize_url(settings.get('url'))
    api_key = settings.get('api_key')
    if not url or not api_key:
        raise ValueError('Prowlarr URL and API key are required.')
    return requests.request(
        method, f'{url}/api/v1/{path}',
        headers={'X-Api-Key': api_key},
        timeout=REQUEST_TIMEOUT,
        **kwargs
    )


def test_connection(settings):
    try:
        r = _request('GET', settings, 'system/status')
        if r.status_code == 401:
            return False, 'Invalid Prowlarr API key.'
        r.raise_for_status()
        version = (r.json() or {}).get('version', '')
        return True, f'Connected to Prowlarr {version}.'.strip()
    except ValueError as e:
        return False, str(e)
    except requests.exceptions.ConnectionError:
        return False, f"Could not reach Prowlarr at {normalize_url(settings.get('url'))}."
    except Exception as e:
        return False, f'Prowlarr error: {e}'


def _release(item):
    """Normalize a Prowlarr ReleaseResource into the fields we care about."""
    seeders = int(item.get('seeders') or 0)
    return {
        'guid': item.get('guid') or '',
        'indexer_id': item.get('indexerId'),
        'indexer': item.get('indexer') or '',
        'title': item.get('title') or '',
        'size': int(item.get('size') or 0),
        'seeders': seeders,
        'leechers': int(item.get('leechers') or 0),
        'info_hash': (item.get('infoHash') or '').lower(),
        'protocol': item.get('protocol') or '',
        'publish_date': item.get('publishDate') or '',
    }


def search(settings, query, categories=None, limit=100):
    """Search all configured indexers. Returns a list of normalized releases."""
    if not query:
        return []
    params = [('query', query), ('type', 'search'), ('limit', limit)]
    # Prowlarr expects the parameter repeated, not a comma separated list
    params += [('categories', c) for c in (categories or [])]
    try:
        r = _request('GET', settings, 'search', params=params)
        r.raise_for_status()
        results = r.json() or []
    except Exception as e:
        logger.warning(f'Prowlarr search failed for "{query}": {e}')
        return []
    return [_release(item) for item in results if item.get('guid')]


def grab(settings, release):
    """Ask Prowlarr to send a release to its own download client."""
    if not release.get('guid') or not release.get('indexer_id'):
        return False, 'Release is missing its guid or indexer.'
    try:
        r = _request('POST', settings, 'search',
                     json={'guid': release['guid'], 'indexerId': release['indexer_id']})
        r.raise_for_status()
        return True, None
    except requests.exceptions.HTTPError as e:
        # Prowlarr answers 400 with a readable message when no download client is configured
        detail = ''
        try:
            detail = r.text[:200]
        except Exception:
            pass
        return False, f'Prowlarr refused the grab: {e} {detail}'.strip()
    except Exception as e:
        return False, f'Prowlarr error: {e}'
