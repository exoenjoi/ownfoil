"""Find the content missing from the library and grab it through Prowlarr.

Prowlarr hands the release to its own download client, so nothing here writes to
qBittorrent: it is only read to report progress.
"""
import logging
import re
import unicodedata

import downloads_store as store
import prowlarr
import qbittorrent
import titles as titles_lib
from titledb import store as titledb_store
from constants import APP_TYPE_BASE, APP_TYPE_DLC, APP_TYPE_UPD
from db import Apps, Titles, get_app_by_id_and_version

logger = logging.getLogger('main')

SWITCH_EXTS = ('nsz', 'nsp', 'xcz', 'xci')


def is_app_owned(app_id, app_version):
    """True if the library holds this exact app version. Lived in db.py until the 2.4.0
    sync; this is its only caller, so it stays out of a file upstream owns."""
    app = get_app_by_id_and_version(app_id, app_version)
    return app.owned if app else False


def _norm(value):
    return re.sub(r'[^a-z0-9]', '', (value or '').lower())


# Release names are not prose and \b is the wrong tool on them: '_' is a word character,
# so \b never falls inside The_Legend_of_Zelda_v1.9.0_NSW-SUXXORS. These two say what is
# actually meant — a token edge is anything that is not a letter or a digit.
TOKEN_START = r'(?<![a-z0-9])'
TOKEN_END = r'(?![a-z0-9])'


def _ext_of(release_title):
    # "SuperXCI" / "SuperNSP" is scene naming for a merged dump (base + updates + DLCs).
    # It is still an XCI, still an NSP, so the prefix is spelled out here rather than
    # left to a boundary that does not exist between "Super" and "XCI".
    match = re.search(rf'{TOKEN_START}(?:super)?(nsp|nsz|xci|xcz){TOKEN_END}',
                      (release_title or '').lower())
    return match.group(1) if match else None


def _has_token(release_title, number):
    """True if the number appears as a standalone token, optionally prefixed by v."""
    return re.search(rf'{TOKEN_START}v?0*{number}{TOKEN_END}',
                     (release_title or '').lower()) is not None


# ---------------------------------------------------------------- ranking (pure)

def rank_releases(releases, target, filters):
    """Annotate every release with a score and a rejection reason, best first.

    Returning the rejected ones too is what lets the UI show the whole list with the
    reason, so a human can override a rejection the automatic job would never take.
    """
    preferred = [e.lower() for e in (filters.get('preferred_ext') or SWITCH_EXTS)]
    pref_rank = {ext: len(preferred) - i for i, ext in enumerate(preferred)}
    min_seeders = int(filters.get('min_seeders') or 0)
    try:
        max_size_gb = float(filters.get('max_size_gb') or 0)
    except (TypeError, ValueError):
        max_size_gb = 0

    name_norm = _norm(target.get('name'))
    app_id_norm = _norm(target.get('app_id'))
    title_id_norm = _norm(target.get('title_id'))
    version = str(target.get('app_version') or '')
    patch_level = target.get('patch_level')

    ranked = []
    dead = 0
    for release in releases:
        release = dict(release)
        title = release.get('title') or ''
        title_norm = _norm(title)
        seeders = int(release.get('seeders') or 0)

        # A release nobody seeds cannot be downloaded at all, so it is not an override
        # the user might want — it is noise. Dropped whatever min_seeders is set to.
        if seeders == 0:
            dead += 1
            continue
        size = int(release.get('size') or 0)
        ext = _ext_of(title)

        has_version = bool(version) and _has_token(title, version)
        has_patch_level = patch_level is not None and _has_token(title, patch_level)
        has_app_id = bool(app_id_norm) and app_id_norm in title_norm
        has_title_id = bool(title_id_norm) and title_id_norm in title_norm

        # No extension token is only damning when nothing else proves the release is a
        # Switch dump. An app id, a title id or the NSW scene tag prove it — a soundtrack
        # or a WiiU rip carries none of them.
        if ext is None and not (has_app_id or has_title_id
                                or re.search(rf'{TOKEN_START}nsw{TOKEN_END}', title.lower())):
            reason = 'No Switch file extension in the release name.'
        elif ext is not None and ext not in pref_rank:
            reason = f'Extension {ext} is not in the preferred list.'
        elif not (name_norm and name_norm in title_norm) and not has_app_id:
            reason = 'Release name matches neither the game name nor its app id.'
        elif seeders < min_seeders:
            reason = f'Only {seeders} seeder(s), minimum is {min_seeders}.'
        elif max_size_gb and size > max_size_gb * 1024 ** 3:
            reason = f'Bigger than the {max_size_gb} GB limit.'
        elif size and size < 1024 * 1024:
            reason = 'Suspiciously small (under 1 MB).'
        elif target.get('app_type') == APP_TYPE_UPD and not (has_version or has_patch_level or has_app_id):
            # Without a version marker an "update" release is most likely the base game
            reason = 'No version marker in the release name, cannot tell which update it is.'
        else:
            reason = None

        # Only how well the release identifies the content scores. Seeders are a
        # tiebreaker below: a popular release of the wrong version is still the wrong one.
        score = 0
        if has_version:
            score += 100
        elif has_patch_level:
            score += 50
        if has_app_id:
            score += 30
        if has_title_id:
            score += 20
        score += pref_rank.get(ext, 0)

        release['score'] = score
        release['rejected'] = reason
        ranked.append(release)

    ranked.sort(key=lambda r: (r['rejected'] is not None, -r['score'], -int(r.get('seeders') or 0)))
    if dead:
        logger.info(f'[downloader] Ignored {dead} release(s) with no seeder.')
    return ranked


def best_release(ranked):
    """Pick the best release the automatic job is allowed to grab."""
    for release in ranked:
        if not release['rejected']:
            return release, None
    if not ranked:
        return None, 'No results from Prowlarr.'
    return None, ranked[0]['rejected']


# ---------------------------------------------------------------- targets (DB + titledb)

def _target(app, title_id, name):
    version = str(app.app_version)
    return {
        'title_id': title_id,
        'app_id': app.app_id,
        'app_version': version,
        'app_type': app.app_type,
        'name': name,
        'patch_level': titles_lib.get_update_number(version) if version.isdigit() else None,
    }


def _game_name(title_id):
    info = titles_lib.get_game_info(title_id) or {}
    name = info.get('name')
    return None if name in (None, 'Unrecognized') else name


def catalog_target(title_id):
    """Target for a base game that is not in the library at all.

    No Apps row exists for it, so everything comes from titledb. A base game's app
    id is its title id.
    """
    name = _game_name(title_id)
    if not name:
        return None
    return {
        'title_id': title_id,
        'app_id': title_id,
        'app_version': '0',
        'app_type': APP_TYPE_BASE,
        'name': name,
        'patch_level': 0,
    }


def _fold(text):
    """Lowercase and strip accents, so 'pokemon' matches 'Pokémon'."""
    decomposed = unicodedata.normalize('NFKD', text or '')
    return ''.join(c for c in decomposed if not unicodedata.combining(c)).lower()


# The whole catalogue used to be loaded into memory to be scanned. Since 2.4.0 titledb is
# SQLite, so this reads two dozen bytes per base game instead and matches in Python -
# SQL's LIKE cannot fold accents or anchor at word starts without a UDF, and the fold
# would defeat the index anyway.
_CATALOG_SQL = """
    SELECT id, name, icon_url, banner_url, publisher, release_date
    FROM titles
    WHERE id LIKE '%000' AND name IS NOT NULL
"""


def search_base_games(query, limit=60):
    """Base games from titledb whose name matches the query.

    Returns None when titledb has not been built yet, so the caller can tell that apart
    from an empty result. Returns up to limit + 1 records for the same reason: exactly
    limit would be indistinguishable from a capped list. Names starting with the query
    come first - searching 'zelda' should not bury the Zelda games.
    """
    needle = _fold(query).strip()
    if not needle:
        return []
    words = needle.split()

    conn = titledb_store._connect_ro()
    if conn is None:
        logger.error('titledb has not been built yet.')
        return None
    try:
        rows = conn.execute(_CATALOG_SQL).fetchall()
    finally:
        conn.close()

    matches = []
    for row in rows:
        folded = _fold(row['name'])
        # Whole query first, then every typed word at the start of a word: 'zelda breath
        # of the wild' has to find 'The Legend of Zelda: Breath of the Wild'. Word starts
        # only, or a stray letter would match half the catalog.
        if needle in folded or all(re.search(rf'\b{re.escape(word)}', folded) for word in words):
            matches.append((not folded.startswith(needle), folded, row))

    matches.sort(key=lambda match: match[:2])
    return [match[2] for match in matches[:limit + 1]]


def _latest(apps):
    return max(apps, key=lambda a: int(a.app_version or 0)) if apps else None


def resolve_target(app_id=None, app_version=None, title_id=None, catalog=False):
    """Target of a manual search from the UI.

    Accepts an exact app, an app id whose latest missing version is picked, or a title id
    whose latest missing update is picked. Resolving here rather than in the browser keeps
    the app id arithmetic (base id -> update id) in one place.

    catalog=True means the title comes from the Discover page and has no Apps row: the
    flag is explicit so the library's own search keeps its behaviour untouched.
    """
    if catalog:
        return catalog_target(title_id) if title_id else None
    if app_id and app_version:
        app = Apps.query.filter_by(app_id=app_id, app_version=str(app_version)).first()
    elif app_id:
        app = _latest(Apps.query.filter_by(app_id=app_id, owned=False).all())
    elif title_id:
        app = _latest(Apps.query.join(Titles)
                      .filter(Titles.title_id == title_id, Apps.owned.is_(False),
                              Apps.app_type == APP_TYPE_UPD).all())
    else:
        return None
    if app is None:
        return None

    resolved_title_id = app.title.title_id
    # A DLC carries its own name, an update is named after its base game
    name = (_game_name(app.app_id) if app.app_type == APP_TYPE_DLC else None) \
        or _game_name(resolved_title_id)
    if not name:
        return None
    return _target(app, resolved_title_id, name)


def _catalog_date(value):
    """titledb writes a release date as the integer 20170303. Anything else is dropped."""
    text = str(value or '')
    return f'{text[:4]}-{text[4:6]}-{text[6:8]}' if len(text) == 8 and text.isdigit() else ''


def search_catalog(query, limit=60):
    """Base games matching the query, flagged with whether the library owns them."""
    records = search_base_games(query, limit)
    if records is None:
        return None

    truncated = len(records) > limit
    records = records[:limit]
    title_ids = [record['id'] for record in records]
    owned = set()
    if title_ids:
        owned = {app.app_id for app in Apps.query.filter(
            Apps.app_id.in_(title_ids), Apps.owned.is_(True)).all()}

    return {
        'results': [{
            'title_id': record['id'],
            'name': record['name'],
            'iconUrl': record['icon_url'],
            'bannerUrl': record['banner_url'],
            'owned': record['id'] in owned,
            # Enough to tell two games with the same name apart, no extra lookup: these
            # fields are already on the record the scan just walked.
            'release_date': _catalog_date(record['release_date']),
            'publisher': record['publisher'] or '',
        } for record in records],
        'truncated': truncated,
    }


# ---------------------------------------------------------------- search & grab

def search_releases(target, settings):
    """Search Prowlarr for a target, by game name then by app id, ranked."""
    downloader_settings = settings.get('downloader', {})
    prowlarr_settings = downloader_settings.get('prowlarr', {}) or {}
    filters = downloader_settings.get('filters', {}) or {}
    categories = prowlarr_settings.get('categories') or []

    # Search by name: an app id almost never appears in a release name
    results = prowlarr.search(prowlarr_settings, target.get('name'), categories)
    ranked = rank_releases(results, target, filters)
    if any(not r['rejected'] for r in ranked):
        return ranked

    # Nothing usable, retry with the app id for scene releases named with it
    by_id = prowlarr.search(prowlarr_settings, target.get('app_id'), categories)
    seen = {r['guid'] for r in results}
    extra = [r for r in by_id if r['guid'] not in seen]
    return rank_releases(results + extra, target, filters) if extra else ranked


def grab_release(target, release, settings):
    """Send a release to Prowlarr and record it in the history."""
    prowlarr_settings = settings.get('downloader', {}).get('prowlarr', {}) or {}
    common = {
        'title_id': target.get('title_id'),
        'app_id': target.get('app_id'),
        'app_version': target.get('app_version'),
        'app_type': target.get('app_type'),
        'name': target.get('name'),
        'release_title': release.get('title'),
        'indexer': release.get('indexer'),
        'size': release.get('size'),
        'seeders': release.get('seeders'),
        'torrent_hash': release.get('info_hash') or '',
    }
    ok, error = prowlarr.grab(prowlarr_settings, release)
    if not ok:
        store.add(status=store.STATUS_FAILED, error=error, **common)
        logger.error(f"[downloader] Grab failed for {target.get('name')}: {error}")
        return False, error
    store.add(status=store.STATUS_GRABBED, error=None, **common)
    logger.info(f"[downloader] Grabbed {release.get('title')} for {target.get('name')}")
    return True, None


# ---------------------------------------------------------------- status

def sync_status(settings):
    """Refresh pending entries and return the whole history with live progress."""
    downloads = store.all()
    pending = [d for d in downloads
               if d.get('status') in (store.STATUS_GRABBED, store.STATUS_DOWNLOADING)]

    torrents = {}
    qbt_settings = settings.get('downloader', {}).get('qbittorrent', {}) or {}
    if pending and (qbt_settings.get('url') or '').strip():
        client = qbittorrent.QbtClient(qbt_settings)
        ok, error = client.login()
        if ok:
            torrents = client.torrents()
        else:
            logger.warning(f'[downloader] qBittorrent unavailable: {error}')

    by_name = {(t.get('name') or '').strip().lower(): t for t in torrents.values()}

    for download in pending:
        # The library is the source of truth: the file arrived and was identified
        if is_app_owned(download['app_id'], download['app_version']):
            store.update(download['id'], status=store.STATUS_COMPLETED, error=None)
            continue
        torrent = torrents.get((download.get('torrent_hash') or '').lower())
        if torrent is None:
            torrent = by_name.get((download.get('release_title') or '').strip().lower())
            if torrent and torrent.get('hash'):
                store.update(download['id'], torrent_hash=torrent['hash'].lower())
        if torrent is None:
            continue
        state = torrent.get('state') or ''
        if state in qbittorrent.ERROR_STATES:
            store.update(download['id'], status=store.STATUS_FAILED,
                         error=f'qBittorrent state: {state}')
        elif download['status'] != store.STATUS_DOWNLOADING:
            store.update(download['id'], status=store.STATUS_DOWNLOADING, error=None)

    # Re-read to pick up the updates, then attach the live progress
    result = []
    for download in store.all():
        torrent = torrents.get((download.get('torrent_hash') or '').lower())
        result.append({
            **download,
            'progress': round((torrent.get('progress') or 0) * 100, 1) if torrent else None,
            'dlspeed': torrent.get('dlspeed') if torrent else None,
            'eta': torrent.get('eta') if torrent else None,
            'state': torrent.get('state') if torrent else None,
        })
    return result
