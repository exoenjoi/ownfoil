import os

APP_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(APP_DIR, 'data')
CONFIG_DIR = os.path.join(APP_DIR, 'config')
DB_FILE = os.path.join(CONFIG_DIR, 'ownfoil.db')
CONFIG_FILE = os.path.join(CONFIG_DIR, 'settings.yaml')
KEYS_FILE = os.path.join(CONFIG_DIR, 'keys.txt')
CACHE_DIR = os.path.join(DATA_DIR, 'cache')
LIBRARY_CACHE_FILE = os.path.join(CACHE_DIR, 'library.json')
ALEMBIC_DIR = os.path.join(APP_DIR, 'migrations')
ALEMBIC_CONF = os.path.join(ALEMBIC_DIR, 'alembic.ini')
TITLEDB_DIR = os.path.join(DATA_DIR, 'titledb')
TITLEDB_URL = 'https://github.com/blawar/titledb.git'
TITLEDB_ARTEFACTS_URL = 'https://nightly.link/a1ex4/ownfoil/workflows/region_titles/master/titledb.zip'
TITLEDB_DEFAULT_FILES = [
    'cnmts.json',
    'versions.json',
    'versions.txt',
    'languages.json',
]

OWNFOIL_DB = 'sqlite:///' + DB_FILE

DEFAULT_SETTINGS = {
    "library": {
        "paths": ["/games"],
        "management": {
            "compress_files": False,
            "delete_older_updates": False,
            "organizer": {
                "enabled": False,
                "destination": "",
                "remove_empty_folders": False,
                "windows_compatible": False,
                "templates": {
                    "base": "{titleName}/{titleName} [{appId}][v{appVersion}]",
                    # [UPD] because otherwise an update is named exactly like its base game,
                    # and only one hex digit of the app id (…2000 vs …2800) tells them apart.
                    "update": "{titleName}/{titleName} [UPD][{appId}][v{appVersion}]",
                    "dlc": "{titleName}/{appName} [{appId}][v{appVersion}]",
                    "multi": "{titleName}/{titleName} [{titleId}]"
                }
            }
        }
    },
    "titles": {
        "language": "en",
        "region": "US",
    },
    "shop": {
        "host": "",
        "public": False,
        "motd": "Welcome to your own shop!",
        "clients": {
            "cyberfoil": {
                "enabled": True,
                "hauth": {},
            },
            "tinfoil": {
                "enabled": True,
                "encrypt": True,
                "clientCertPub": "-----BEGIN PUBLIC KEY-----",
                "clientCertKey": "-----BEGIN PRIVATE KEY-----",
                "hauth": {},
            },
            "sphaira": {"enabled": True,}
        }
    },
    "scheduler": {
        "scan_interval": "12h",
        "download_interval": "6h",
    },
    "downloader": {
        "enabled": False,
        "prowlarr": {
            "url": "",
            "api_key": "",
            # No standard Newznab category exists for the Switch, so no filter by default:
            # filtering would silently return nothing on most indexers
            "categories": [],
        },
        "qbittorrent": {
            # Optional, read only: Prowlarr adds the torrents, this is just for progress
            "url": "",
            "username": "",
            "password": "",
        },
        "filters": {
            "min_seeders": 3,
            "preferred_ext": ["nsz", "nsp", "xcz", "xci"],
            "max_size_gb": 0,
            "max_per_run": 10,
        },
    }
}


ALLOWED_EXTENSIONS = [
    'nsp',
    'nsz',
    'xci',
    'xcz',
]

APP_TYPE_BASE = 'BASE'
APP_TYPE_UPD = 'UPDATE'
APP_TYPE_DLC = 'DLC'
APP_TYPE_MAP = {
    128: APP_TYPE_BASE,
    129: APP_TYPE_UPD,
    130: APP_TYPE_DLC
}

APP_TYPE_FILTERS = {
    'base': APP_TYPE_BASE,
    'update': APP_TYPE_UPD,
    'dlc': APP_TYPE_DLC,
    'multi': 'MULTI'
}

# Define OS-specific forbidden characters for Organizer
FORBIDDEN_CHARS_WINDOWS = set('<>:"/\\|?*')
FORBIDDEN_CHARS_UNIX = set('/') # Only / is truly forbidden on Unix-like systems

# Reserved names on Windows
RESERVED_NAMES_WINDOWS = {
    'con', 'prn', 'aux', 'nul', 'com1', 'com2', 'com3', 'com4', 'com5', 'com6', 'com7', 'com8', 'com9',
    'lpt1', 'lpt2', 'lpt3', 'lpt4', 'lpt5', 'lpt6', 'lpt7', 'lpt8', 'lpt9'
}