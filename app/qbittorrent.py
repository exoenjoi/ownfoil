"""qBittorrent client, read only: Prowlarr adds the torrents, we only report progress."""
import logging
import requests

from prowlarr import normalize_url

logger = logging.getLogger('main')

REQUEST_TIMEOUT = 15

# A torrent in one of those states will never complete on its own
ERROR_STATES = ('error', 'missingFiles', 'unknown')
# 'paused*' was renamed 'stopped*' in qBittorrent 5.x
DONE_STATES = ('uploading', 'stalledUP', 'queuedUP', 'forcedUP', 'checkingUP',
               'pausedUP', 'stoppedUP')


class QbtClient:
    def __init__(self, settings):
        self.url = normalize_url(settings.get('url'))
        self.username = settings.get('username') or ''
        self.password = settings.get('password') or ''
        self.session = requests.Session()
        # Without a matching Referer the WebUI answers 403, this is the classic pitfall
        self.session.headers.update({'Referer': self.url})

    def login(self):
        if not self.url:
            return False, 'qBittorrent URL is required.'
        try:
            r = self.session.post(f'{self.url}/api/v2/auth/login',
                                  data={'username': self.username, 'password': self.password},
                                  timeout=REQUEST_TIMEOUT)
            if r.status_code == 403:
                return False, 'qBittorrent refused the login (banned IP or wrong Referer).'
            r.raise_for_status()
            # An unauthenticated WebUI (auth bypass) answers Ok. without setting a cookie
            if r.text.strip() == 'Fails.':
                return False, 'Invalid qBittorrent username or password.'
            return True, None
        except requests.exceptions.ConnectionError:
            return False, f'Could not reach qBittorrent at {self.url}.'
        except Exception as e:
            return False, f'qBittorrent error: {e}'

    def torrents(self, hashes=None):
        """Return {info_hash: torrent} for the given hashes, or all torrents."""
        params = {}
        if hashes:
            params['hashes'] = '|'.join(hashes)
        try:
            r = self.session.get(f'{self.url}/api/v2/torrents/info',
                                 params=params, timeout=REQUEST_TIMEOUT)
            r.raise_for_status()
            return {(t.get('hash') or '').lower(): t for t in (r.json() or [])}
        except Exception as e:
            logger.warning(f'Could not read qBittorrent torrents: {e}')
            return {}

    def version(self):
        r = self.session.get(f'{self.url}/api/v2/app/version', timeout=REQUEST_TIMEOUT)
        r.raise_for_status()
        return r.text.strip()


def test_connection(settings):
    if not (settings.get('url') or '').strip():
        return True, 'Not configured (optional, only used to show download progress).'
    client = QbtClient(settings)
    ok, error = client.login()
    if not ok:
        return False, error
    try:
        return True, f'Connected to qBittorrent {client.version()}.'
    except Exception as e:
        return False, f'qBittorrent error: {e}'
