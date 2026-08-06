"""Self-checks for file identification and the catalog search, run with:
python app/test_titles.py

No keys, no real containers, no titledb on disk: fake entries throughout.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from nsz.Fs import Nsp, Xci

import titles
from constants import DEFAULT_SETTINGS
from titles import get_app_id_from_filename, get_cnmts, get_version_from_filename


class FakeEntry:
    """Stands in for an Nca inside a container: only its path is looked at."""

    def __init__(self, path):
        self._path = path


def nsp_containing(*paths):
    nsp = Nsp.Nsp()
    nsp.files = [FakeEntry(p) for p in paths]
    return nsp


def test_a_single_content_nsp_yields_its_cnmt():
    nsp = nsp_containing('abc.cnmt.nca', 'abc.nca')
    assert [f._path for f in get_cnmts(nsp)] == ['abc.cnmt.nca']


def test_a_merged_nsp_yields_every_cnmt():
    # A base+update NSP has one CNMT per content. Taking only the first one left the
    # other content unowned in the library — that is the "Base missing" bug.
    nsp = nsp_containing('base.cnmt.nca', 'base.nca', 'upd.cnmt.nca', 'upd.nca')
    assert [f._path for f in get_cnmts(nsp)] == ['base.cnmt.nca', 'upd.cnmt.nca']


def test_an_nsp_without_cnmt_yields_nothing():
    assert get_cnmts(nsp_containing('loose.nca')) == []


def test_an_unknown_container_yields_nothing():
    assert get_cnmts(object()) == []


def test_the_update_template_stays_parsable_by_the_filename_fallback():
    # When no keys are loaded, identification falls back to reading the name. The [UPD]
    # marker must not be mistaken for an app id or a version by either regex.
    template = DEFAULT_SETTINGS['library']['management']['organizer']['templates']['update']
    filename = template.format(titleName="Yoshi's Crafted World",
                               appId='01006000040C2800', appVersion='65536').split('/')[-1] + '.nsp'
    assert get_app_id_from_filename(filename) == '01006000040C2800'
    assert get_version_from_filename(filename) == '65536'


# ------------------------------------------------------------- catalog search

FAKE_TITLES = {
    'k1': {'id': '01006000040C2000', 'name': "Yoshi's Crafted World", 'iconUrl': 'i1', 'bannerUrl': 'b1'},
    'k2': {'id': '0100000000010000', 'name': 'Super Mario Odyssey', 'iconUrl': 'i2', 'bannerUrl': 'b2'},
    'k3': {'id': '010003F003A34800', 'name': 'Pokemon Update', 'iconUrl': 'i3', 'bannerUrl': 'b3'},
    'k4': {'id': '01009BF0072D5001', 'name': 'Captain Toad DLC', 'iconUrl': 'i4', 'bannerUrl': 'b4'},
    'k5': {'id': '0100ABCDEF012000', 'name': 'Pokémon Écarlate', 'iconUrl': 'i5', 'bannerUrl': 'b5'},
    'k6': {'id': '0100111111112000', 'name': None, 'iconUrl': 'i6', 'bannerUrl': 'b6'},
    'k7': {'id': None, 'name': 'No id at all', 'iconUrl': 'i7', 'bannerUrl': 'b7'},
    'k8': {'id': '0100222222222000', 'name': 'A Game About Pokemon', 'iconUrl': 'i8', 'bannerUrl': 'b8'},
}


def with_fake_titledb(fake):
    """Swap the module-level titledb, returning a restore callable."""
    previous = titles._titles_db
    titles._titles_db = fake

    def restore():
        titles._titles_db = previous
    return restore


def search(query, limit=60):
    restore = with_fake_titledb(FAKE_TITLES)
    try:
        return titles.search_base_games(query, limit)
    finally:
        restore()


def test_only_base_games_are_returned():
    # Update ids end in 800 and DLC ids in something else; neither is grabbable on its own.
    names = [r['name'] for r in search('o')]
    assert 'Pokemon Update' not in names
    assert 'Captain Toad DLC' not in names


def test_the_match_ignores_case_and_accents():
    # Without folding, a French library is unsearchable from an ASCII keyboard.
    assert [r['id'] for r in search('ecarlate')] == ['0100ABCDEF012000']
    assert [r['id'] for r in search('POKÉMON É')] == ['0100ABCDEF012000']


def test_prefix_matches_come_first():
    names = [r['name'] for r in search('pokemon')]
    assert names == ['Pokémon Écarlate', 'A Game About Pokemon']


def test_the_limit_leaves_room_to_detect_truncation():
    # limit + 1 records come back so the caller can tell "capped" from "exactly that many".
    assert len(search('pokemon', limit=1)) == 2


def test_records_missing_a_name_or_an_id_are_skipped():
    assert search('no id at all') == []
    assert all(r['name'] for r in search('o'))


def test_a_blank_query_matches_nothing():
    assert search('   ') == []


def test_an_unloaded_titledb_returns_none():
    restore = with_fake_titledb(None)
    try:
        assert titles.search_base_games('zelda') is None
    finally:
        restore()


if __name__ == '__main__':
    for name, test in sorted(globals().items()):
        if name.startswith('test_'):
            test()
            print(f'ok {name}')
