import os
import sys
import re
import json
import unicodedata

import titledb
from constants import *
from utils import *
from settings import *
from pathlib import Path
from binascii import hexlify as hx, unhexlify as uhx
import logging

from nsz.Fs import Pfs0, Xci, Nsp, Nca, Type, factory
from nsz.nut import Keys

# Retrieve main logger
logger = logging.getLogger('main')

Pfs0.Print.silent = True

app_id_regex = r"\[([0-9A-Fa-f]{16})\]"
version_regex = r"\[v(\d+)\]"

# Global variables for TitleDB data
identification_in_progress_count = 0
_titles_db_loaded = False
_cnmts_db = None
_titles_db = None
_versions_db = None
_versions_txt_db = None

def getDirsAndFiles(path):
    entries = os.listdir(path)
    allFiles = []
    allDirs = []

    for entry in entries:
        fullPath = os.path.join(path, entry)
        if os.path.isdir(fullPath):
            allDirs.append(fullPath)
            dirs, files = getDirsAndFiles(fullPath)
            allDirs += dirs
            allFiles += files
        elif fullPath.split('.')[-1] in ALLOWED_EXTENSIONS:
            allFiles.append(fullPath)
    return allDirs, allFiles

def get_app_id_from_filename(filename):
    app_id_match = re.search(app_id_regex, filename)
    return app_id_match[1] if app_id_match is not None else None

def get_version_from_filename(filename):
    version_match = re.search(version_regex, filename)
    return version_match[1] if version_match is not None else None

def get_title_id_from_app_id(app_id, app_type):
    base_id = app_id[:-3]
    if app_type == APP_TYPE_UPD:
        title_id = base_id + '000'
    elif app_type == APP_TYPE_DLC:
        title_id = hex(int(base_id, base=16) - 1)[2:].rjust(len(base_id), '0') + '000'
    return title_id.upper()

def get_file_size(filepath):
    return os.path.getsize(filepath)

def get_file_info(filepath):
    filedir, filename = os.path.split(filepath)
    extension = filename.split('.')[-1]
    
    compressed = False
    if extension in ['nsz', 'xcz']:
        compressed = True

    return {
        'filepath': filepath,
        'filedir': filedir,
        'filename': filename,
        'extension': extension,
        'compressed': compressed,
        'size': get_file_size(filepath),
    }

def identify_appId(app_id):
    app_id = app_id.lower()
    
    global _cnmts_db
    if _cnmts_db is None:
        logger.error("cnmts_db is not loaded. Call load_titledb first.")
        return None, None

    if app_id in _cnmts_db:
        app_id_keys = list(_cnmts_db[app_id].keys())
        if len(app_id_keys):
            app = _cnmts_db[app_id][app_id_keys[-1]]
            
            if app['titleType'] == 128:
                app_type = APP_TYPE_BASE
                title_id = app_id.upper()
            elif app['titleType'] == 129:
                app_type = APP_TYPE_UPD
                if 'otherApplicationId' in app:
                    title_id = app['otherApplicationId'].upper()
                else:
                    title_id = get_title_id_from_app_id(app_id, app_type)
            elif app['titleType'] == 130:
                app_type = APP_TYPE_DLC
                if 'otherApplicationId' in app:
                    title_id = app['otherApplicationId'].upper()
                else:
                    title_id = get_title_id_from_app_id(app_id, app_type)
        else:
            logger.warning(f'{app_id} has no keys in cnmts_db, fallback to default identification.')
            if app_id.endswith('000'):
                app_type = APP_TYPE_BASE
                title_id = app_id
            elif app_id.endswith('800'):
                app_type = APP_TYPE_UPD
                title_id = get_title_id_from_app_id(app_id, app_type)
            else:
                app_type = APP_TYPE_DLC
                title_id = get_title_id_from_app_id(app_id, app_type)
    else:
        logger.warning(f'{app_id} not in cnmts_db, fallback to default identification.')
        if app_id.endswith('000'):
            app_type = APP_TYPE_BASE
            title_id = app_id
        elif app_id.endswith('800'):
            app_type = APP_TYPE_UPD
            title_id = get_title_id_from_app_id(app_id, app_type)
        else:
            app_type = APP_TYPE_DLC
            title_id = get_title_id_from_app_id(app_id, app_type)
    
    return title_id.upper(), app_type

def load_titledb():
    global _cnmts_db
    global _titles_db
    global _versions_db
    global _versions_txt_db
    global identification_in_progress_count
    global _titles_db_loaded

    identification_in_progress_count += 1
    if not _titles_db_loaded:
        logger.info("Loading TitleDBs into memory...")
        app_settings = load_settings()
        with open(os.path.join(TITLEDB_DIR, 'cnmts.json'), "r", encoding="utf-8") as f:
            _cnmts_db = json.load(f)

        with open(os.path.join(TITLEDB_DIR, titledb.get_region_titles_file(app_settings)), "r", encoding="utf-8") as f:
            _titles_db = json.load(f)

        with open(os.path.join(TITLEDB_DIR, 'versions.json'), "r", encoding="utf-8") as f:
            _versions_db = json.load(f)

        _versions_txt_db = {}
        with open(os.path.join(TITLEDB_DIR, 'versions.txt'), "r", encoding="utf-8") as f:
            for line in f:
                line_strip = line.rstrip("\n")
                app_id, rightsId, version = line_strip.split('|')
                if not version:
                    version = "0"
                _versions_txt_db[app_id] = version
        _titles_db_loaded = True
        logger.info("TitleDBs loaded.")

@debounce(30)
def unload_titledb():
    global _cnmts_db
    global _titles_db
    global _versions_db
    global _versions_txt_db
    global identification_in_progress_count
    global _titles_db_loaded

    if identification_in_progress_count:
        logger.debug('Identification still in progress, not unloading TitleDB.')
        return

    logger.info("Unloading TitleDBs from memory...")
    _cnmts_db = None
    _titles_db = None
    _versions_db = None
    _versions_txt_db = None
    _titles_db_loaded = False
    logger.info("TitleDBs unloaded.")

def identify_file_from_filename(filename):
    title_id = None
    app_id = None
    app_type = None
    version = None
    errors = []

    app_id = get_app_id_from_filename(filename)
    if app_id is None:
        errors.append('Could not determine App ID from filename, pattern [APPID] not found. Title ID and Type cannot be derived.')
    else:
        title_id, app_type = identify_appId(app_id)

    version = get_version_from_filename(filename)
    if version is None:
        errors.append('Could not determine version from filename, pattern [vVERSION] not found.')
    
    error = ' '.join(errors)
    return app_id, title_id, app_type, version, error

def get_cnmts(container):
    cnmts = []
    if isinstance(container, Nsp.Nsp):
        # One CNMT per content, so a merged base+update NSP holds several. Nsp.cnmt()
        # returns the first one and stops, which left the other contents unowned in the
        # library. Walk the whole container, like the Xci branch below already does.
        cnmts = [f for f in container if f._path.endswith('.cnmt.nca')]
        if not cnmts:
            logger.warning('CNMT section not found in Nsp.')

    elif isinstance(container, Xci.Xci):
        container = container.hfs0['secure']
        for nspf in container:
            if isinstance(nspf, Nca.Nca) and nspf.header.contentType == Type.Content.META:
                cnmts.append(nspf)

    return cnmts

def extract_meta_from_cnmt(cnmt_sections):
    contents = []
    for section in cnmt_sections:
        if isinstance(section, Pfs0.Pfs0):
            Cnmt = section.getCnmt()
            titleType = APP_TYPE_MAP[Cnmt.titleType]
            titleId = Cnmt.titleId.upper()
            version = Cnmt.version
            contents.append((titleType, titleId, version))
    return contents

def identify_file_from_cnmt(filepath):
    contents = []
    container = factory(Path(filepath).resolve())
    try:
        container.open(filepath, 'rb', meta_only=True)
        for cnmt_sections in get_cnmts(container):
            contents += extract_meta_from_cnmt(cnmt_sections)
    except OSError as e:
        # Check if the error is due to a missing master_key
        match = re.search(r"master_key_([0-9a-fA-F]{2}) missing from", str(e))
        if match:
            key_index = match.group(1)
            raise ValueError(f"Missing valid master_key_{key_index} from keys file.") from e
        else:
            raise # Re-raise other OSErrors
    finally:
        container.close()

    return contents

def identify_file(filepath):
    filename = os.path.split(filepath)[-1]
    contents = []
    success = True
    error = ''
    if Keys.keys_loaded:
        identification = 'cnmt'
        try:
            cnmt_contents = identify_file_from_cnmt(filepath)
            if not cnmt_contents:
                error = 'No content found in NCA containers.'
                success = False
            else:
                for content in cnmt_contents:
                    app_type, app_id, version = content
                    if app_type != APP_TYPE_BASE:
                        # need to get the title ID from cnmts
                        title_id, app_type = identify_appId(app_id)
                    else:
                        title_id = app_id
                    contents.append((title_id, app_type, app_id, version))
        except Exception as e:
            logger.error(f'Could not identify file {filepath} from metadata: {e}')
            error = str(e)
            success = False

    else:
        identification = 'filename'
        app_id, title_id, app_type, version, error = identify_file_from_filename(filename)
        if not error:
            contents.append((title_id, app_type, app_id, version))
        else:
            success = False

    if contents:
        contents = [{
            'title_id': c[0],
            'app_id': c[2],
            'type': c[1],
            'version': c[3],
            } for c in contents]
    return identification, success, contents, error


def get_game_info(title_id):
    global _titles_db
    if _titles_db is None:
        logger.error("titles_db is not loaded. Call load_titledb first.")
        return None

    try:
        title_info = [_titles_db[t] for t in list(_titles_db.keys()) if _titles_db[t]['id'] == title_id][0]
        return {
            'name': title_info['name'],
            'bannerUrl': title_info['bannerUrl'],
            'iconUrl': title_info['iconUrl'],
            'id': title_info['id'],
            'category': title_info['category'],
        }
    except Exception:
        logger.error(f"Title ID not found in titledb: {title_id}")
        return {
            'name': 'Unrecognized',
            'bannerUrl': '//placehold.it/400x200',
            'iconUrl': '',
            'id': title_id + ' not found in titledb',
            'category': '',
        }


def _fold(text):
    """Lowercase and strip accents, so 'pokemon' matches 'Pokémon'."""
    decomposed = unicodedata.normalize('NFKD', text or '')
    return ''.join(c for c in decomposed if not unicodedata.combining(c)).lower()


# ponytail: linear scan of the whole titledb per search. The load it needs is already
# paid by every manual downloader search, so this costs nothing extra today. If it ever
# drags, build a slim (id, name, iconUrl) index when titledb is downloaded — or wait for
# upstream 2.4.0, which puts titledb in SQL and makes this a LIKE query.
def search_base_games(query, limit=60):
    """Base games from titledb whose name contains the query.

    Returns None when titledb is not loaded, so the caller can tell that apart from
    an empty result. Returns up to limit + 1 records for the same reason: exactly
    limit would be indistinguishable from a capped list. Names starting with the
    query come first — searching 'zelda' should not bury the Zelda games.
    """
    global _titles_db
    if _titles_db is None:
        logger.error("titles_db is not loaded. Call load_titledb first.")
        return None

    needle = _fold(query).strip()
    if not needle:
        return []
    words = needle.split()

    matches = []
    for record in _titles_db.values():
        app_id, name = record.get('id'), record.get('name')
        # An update id ends in 800 and a DLC id in something else; only a base game
        # can be grabbed on its own.
        if not app_id or not name or not app_id.endswith('000'):
            continue
        folded = _fold(name)
        # Whole query first, then every typed word at the start of a word: 'zelda breath
        # of the wild' has to find 'The Legend of Zelda: Breath of the Wild'. Word starts
        # only, or a stray letter would match half the catalog.
        if needle in folded or all(re.search(rf'\b{re.escape(word)}', folded) for word in words):
            matches.append((not folded.startswith(needle), folded, record))

    matches.sort(key=lambda match: match[:2])
    return [match[2] for match in matches[:limit + 1]]

def get_update_number(version):
    return int(version)//65536

def get_game_latest_version(all_existing_versions):
    return max(v['version'] for v in all_existing_versions)

def get_all_existing_versions(titleid):
    global _versions_db
    if _versions_db is None:
        logger.error("versions_db is not loaded. Call load_titledb first.")
        return []

    titleid = titleid.lower()
    if titleid not in _versions_db:
        # print(f'Title ID not in versions.json: {titleid.upper()}')
        return []

    versions_from_db = _versions_db[titleid].keys()
    return [
        {
            'version': int(version_from_db),
            'update_number': get_update_number(version_from_db),
            'release_date': _versions_db[titleid][str(version_from_db)],
        }
        for version_from_db in versions_from_db
    ]

def get_all_app_existing_versions(app_id):
    global _cnmts_db
    if _cnmts_db is None:
        logger.error("cnmts_db is not loaded. Call load_titledb first.")
        return None

    app_id = app_id.lower()
    if app_id in _cnmts_db:
        versions_from_cnmts_db = _cnmts_db[app_id].keys()
        if len(versions_from_cnmts_db):
            return sorted(versions_from_cnmts_db)
        else:
            logger.warning(f'No keys in cnmts.json for app ID: {app_id.upper()}')
            return None
    else:
        # print(f'DLC app ID not in cnmts.json: {app_id.upper()}')
        return None
    
def get_app_id_version_from_versions_txt(app_id):
    global _versions_txt_db
    if _versions_txt_db is None:
        logger.error("versions_txt_db is not loaded. Call load_titledb first.")
        return None
    return _versions_txt_db.get(app_id, None)
    
def get_all_existing_dlc(title_id):
    global _cnmts_db
    if _cnmts_db is None:
        logger.error("cnmts_db is not loaded. Call load_titledb first.")
        return []

    title_id = title_id.lower()
    dlcs = []
    for app_id in _cnmts_db.keys():
        for version, version_description in _cnmts_db[app_id].items():
            if version_description.get('titleType') == 130 and version_description.get('otherApplicationId') == title_id:
                if app_id.upper() not in dlcs:
                    dlcs.append(app_id.upper())
    return dlcs
