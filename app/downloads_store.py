"""Grab history, kept in a JSON file next to the settings.

Deliberately not a database table: a schema change would add an Alembic revision that
conflicts with upstream's own migrations every time the fork is synced, for what is a
single-writer list of a few hundred entries.
"""
import datetime
import json
import os
import threading

from constants import CONFIG_DIR
from utils import safe_write_json

DOWNLOADS_FILE = os.path.join(CONFIG_DIR, 'downloads.json')

# The scheduler job and the HTTP requests both write, a lock guards the read-modify-write
_lock = threading.Lock()

STATUS_GRABBED = 'grabbed'
STATUS_DOWNLOADING = 'downloading'
STATUS_COMPLETED = 'completed'
STATUS_FAILED = 'failed'
# A target in one of those states must not be grabbed again by the job
ACTIVE_STATUSES = (STATUS_GRABBED, STATUS_DOWNLOADING, STATUS_COMPLETED)


def _read():
    try:
        with open(DOWNLOADS_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return []


def _write(downloads):
    os.makedirs(os.path.dirname(DOWNLOADS_FILE), exist_ok=True)
    safe_write_json(DOWNLOADS_FILE, downloads)


def all():
    with _lock:
        return _read()


def get(app_id, app_version):
    """Latest entry for an app, the one that reflects its current state."""
    return next((d for d in reversed(all())
                 if d['app_id'] == app_id and str(d['app_version']) == str(app_version)), None)


def add(**fields):
    with _lock:
        downloads = _read()
        entry = dict(fields)
        entry['id'] = max((d['id'] for d in downloads), default=0) + 1
        entry['grabbed_at'] = datetime.datetime.now().isoformat(timespec='seconds')
        entry['app_version'] = str(entry.get('app_version', ''))
        downloads.append(entry)
        _write(downloads)
        return entry


def update(download_id, **fields):
    with _lock:
        downloads = _read()
        entry = next((d for d in downloads if d['id'] == download_id), None)
        if entry is None:
            return None
        entry.update(fields)
        _write(downloads)
        return entry


def delete(download_id):
    with _lock:
        downloads = _read()
        remaining = [d for d in downloads if d['id'] != download_id]
        if len(remaining) == len(downloads):
            return False
        _write(remaining)
        return True
