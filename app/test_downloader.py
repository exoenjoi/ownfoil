"""Self-checks for the downloader ranking and the grab history.

No network, no database: only the pure ranking logic and the JSON store.
Run with: python app/test_downloader.py
"""
import os
import shutil
import sqlite3
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import downloader
import downloads_store as store
import prowlarr
from titledb import store as titledb_store
from downloader import best_release, rank_releases

FILTERS = {'min_seeders': 3, 'preferred_ext': ['nsz', 'nsp', 'xcz', 'xci'],
           'max_size_gb': 0}

# Mario Kart 8 Deluxe, update 3 (3 * 65536 = 196608)
UPDATE_TARGET = {
    'title_id': '0100152000022000',
    'app_id': '0100152000022800',
    'app_version': '196608',
    'app_type': 'UPDATE',
    'name': 'Mario Kart 8 Deluxe',
    'patch_level': 3,
}


def release(title, seeders=50, size=1024 ** 3, guid=None):
    return {'guid': guid or title, 'indexer_id': 1, 'indexer': 'test', 'title': title,
            'size': size, 'seeders': seeders, 'leechers': 1, 'info_hash': ''}


def best(titles_or_releases, target=UPDATE_TARGET, filters=None):
    releases = [r if isinstance(r, dict) else release(r) for r in titles_or_releases]
    return best_release(rank_releases(releases, target, filters or FILTERS))


def test_the_matching_update_is_picked():
    chosen, reason = best([
        'Some Other Game [v196608].nsp',
        'Mario Kart 8 Deluxe [0100152000022800][v196608].nsp',
    ])
    assert chosen is not None, reason
    assert chosen['title'] == 'Mario Kart 8 Deluxe [0100152000022800][v196608].nsp'


def test_base_game_is_never_taken_for_an_update():
    # The dangerous case: right game, right extension, but no version marker at all
    chosen, reason = best(['Mario Kart 8 Deluxe NSW-VENOM.nsp'])
    assert chosen is None
    assert 'version marker' in reason


def test_a_catalog_date_is_readable_or_absent():
    # titledb writes a release date as the integer 20170303.
    assert downloader._catalog_date(20170303) == '2017-03-03'
    assert downloader._catalog_date('20170303') == '2017-03-03'
    # Not every entry has one, and a malformed one is worse than none on a card.
    assert downloader._catalog_date(None) == ''
    assert downloader._catalog_date(2017) == ''
    assert downloader._catalog_date('march 2017') == ''


def test_a_release_carries_a_link_to_its_tracker_page():
    # Prowlarr fills infoUrl; when it does not, the guid is often the page URL itself.
    assert prowlarr._release({'infoUrl': 'https://tracker/1'})['info_url'] == 'https://tracker/1'
    assert prowlarr._release({'guid': 'https://tracker/2'})['info_url'] == 'https://tracker/2'
    # A guid that is not a URL is not a link, it is an indexer's internal id.
    assert prowlarr._release({'guid': 'abcd-1234'})['info_url'] == ''
    # The link goes into an href, and an indexer is not a party we trust with a scheme.
    assert prowlarr._release({'infoUrl': 'javascript:alert(1)'})['info_url'] == ''


def test_a_super_dump_keeps_its_extension():
    # "SuperXCI" / "SuperNSP" is scene naming for a merged dump — base, updates and DLCs
    # in one file. It is still an XCI, still an NSP, and was being refused for having
    # "no Switch file extension" because the word boundary fell before "Super".
    assert downloader._ext_of('Zelda V1.6.0 Incl. All Dlcs SuperXCi PROPER - CLC') == 'xci'
    assert downloader._ext_of('Zelda V1.6.0 Incl. All Dlcs SuperNSP PROPER - CLC') == 'nsp'
    chosen, reason = best(['Mario Kart 8 Deluxe [v196608] Incl. All Dlcs SuperXCi - CLC'])
    assert chosen is not None, reason


def test_a_release_naming_the_app_id_needs_no_extension():
    # No extension token in the name, but it carries the app id: nothing but a Switch
    # dump does that, so refusing it for "no Switch file extension" was wrong.
    chosen, reason = best(['Mario Kart 8 Deluxe [0100152000022800] [v196608] 1G+1U+2D'])
    assert chosen is not None, reason


def test_a_scene_release_tagged_nsw_needs_no_extension():
    # NSW is the scene tag for a Switch dump; those releases never spell the extension out.
    chosen, reason = best(['Mario_Kart_8_Deluxe_Update_v196608_PROPER_NSW-SUXXORS'])
    assert chosen is not None, reason


def test_a_soundtrack_is_still_refused():
    # The extension check earns its keep here: same game name, no dump in sight.
    chosen, reason = best(['Mario Kart 8 Deluxe v196608 Original Soundtrack [FLAC]'])
    assert chosen is None
    assert 'No Switch file extension' in reason


def test_another_game_is_rejected():
    chosen, reason = best(['Super Mario Odyssey [v196608].nsp'])
    assert chosen is None
    assert 'neither the game name nor its app id' in reason


def test_seeders_and_size_limits():
    chosen, reason = best([release('Mario Kart 8 Deluxe [v196608].nsp', seeders=1)])
    assert chosen is None and 'seeder' in reason

    big = release('Mario Kart 8 Deluxe [v196608].nsp', size=20 * 1024 ** 3)
    chosen, reason = best([big], filters={**FILTERS, 'max_size_gb': 10})
    assert chosen is None and 'limit' in reason

    chosen, reason = best([release('Mario Kart 8 Deluxe [v196608].nsp', size=1024)])
    assert chosen is None and 'small' in reason


def test_extension_preference_breaks_a_tie():
    chosen, _ = best([
        'Mario Kart 8 Deluxe [v196608].xci',
        'Mario Kart 8 Deluxe [v196608].nsz',
    ])
    assert chosen['title'].endswith('.nsz')

    # An extension outside the preferred list is refused, not just ranked last
    chosen, reason = best(['Mario Kart 8 Deluxe [v196608].xci'],
                          filters={**FILTERS, 'preferred_ext': ['nsz']})
    assert chosen is None and 'not in the preferred list' in reason


def test_exact_version_beats_patch_level():
    chosen, _ = best([
        release('Mario Kart 8 Deluxe Update v3.nsp', seeders=200),
        release('Mario Kart 8 Deluxe [v196608].nsp', seeders=5),
    ])
    assert '196608' in chosen['title'], 'the exact version must win over more seeders'


def test_patch_level_is_matched_as_a_whole_token():
    # v30 must not satisfy a search for patch level 3
    chosen, reason = best(['Mario Kart 8 Deluxe Update v30.nsp'])
    assert chosen is None, chosen


def test_a_dlc_needs_no_version_marker():
    dlc_target = {**UPDATE_TARGET, 'app_type': 'DLC', 'app_id': '0100152000022001',
                  'app_version': '0', 'name': 'Mario Kart 8 Deluxe Booster Course'}
    chosen, reason = best(['Mario Kart 8 Deluxe Booster Course Pass.nsp'], target=dlc_target)
    assert chosen is not None, reason


def test_rejected_releases_are_still_returned_for_the_ui():
    ranked = rank_releases([release('Totally Unrelated Game.nsp')], UPDATE_TARGET, FILTERS)
    assert len(ranked) == 1
    assert ranked[0]['rejected']


def test_store_round_trip():
    with tempfile.TemporaryDirectory() as tmp:
        store.DOWNLOADS_FILE = os.path.join(tmp, 'downloads.json')
        assert store.all() == []

        first = store.add(app_id='0100152000022800', app_version=196608, app_type='UPDATE',
                          name='Mario Kart 8 Deluxe', status=store.STATUS_GRABBED)
        second = store.add(app_id='0100152000022800', app_version=196608, app_type='UPDATE',
                           name='Mario Kart 8 Deluxe', status=store.STATUS_FAILED)
        assert first['id'] != second['id']
        assert first['app_version'] == '196608', 'the version must be stored as a string'

        # get() must return the latest entry, the one reflecting the current state
        assert store.get('0100152000022800', '196608')['id'] == second['id']
        assert store.get('0100152000022800', 196608)['status'] == store.STATUS_FAILED

        store.update(second['id'], status=store.STATUS_COMPLETED)
        assert store.get('0100152000022800', '196608')['status'] == store.STATUS_COMPLETED

        assert store.delete(second['id'])
        assert not store.delete(second['id'])
        assert len(store.all()) == 1


# ------------------------------------------------------------- dead releases

def dead_and_alive():
    """One unusable release, one merely below the seeder threshold."""
    return [
        release('Mario Kart 8 Deluxe [v196608].nsp', seeders=0, guid='dead'),
        release('Mario Kart 8 Deluxe [v196608].nsp', seeders=1, guid='thin'),
    ]


def test_a_dead_torrent_is_dropped_not_greyed():
    # 0 seeders is not an override opportunity, it is undownloadable.
    ranked = rank_releases(dead_and_alive(), UPDATE_TARGET, FILTERS)
    assert [r['guid'] for r in ranked] == ['thin']


def test_a_release_below_the_threshold_is_kept_and_greyed():
    # 1 seeder with a minimum of 3 is a rejection the user may still want to override.
    ranked = rank_releases(dead_and_alive(), UPDATE_TARGET, FILTERS)
    assert ranked[0]['rejected'] and 'seeder' in ranked[0]['rejected']


def test_a_dead_torrent_is_dropped_even_with_no_minimum():
    # min_seeders=0 makes nothing "rejected" for seeders, but dead is still dead.
    ranked = rank_releases(dead_and_alive(), UPDATE_TARGET, dict(FILTERS, min_seeders=0))
    assert [r['guid'] for r in ranked] == ['thin']


# ------------------------------------------------------------- catalog target

def with_fake_game_info(name):
    """Swap the titledb lookup downloader uses, returning a restore callable."""
    previous = downloader.titles_lib.get_game_info
    downloader.titles_lib.get_game_info = lambda title_id: {'name': name} if name else None

    def restore():
        downloader.titles_lib.get_game_info = previous
    return restore


def test_catalog_target_describes_a_base_game():
    # A game absent from the library has no Apps row, so the target is built from
    # titledb alone. For a base game the app id is the title id.
    restore = with_fake_game_info("Yoshi's Crafted World")
    try:
        target = downloader.catalog_target('01006000040C2000')
    finally:
        restore()
    assert target == {
        'title_id': '01006000040C2000',
        'app_id': '01006000040C2000',
        'app_version': '0',
        'app_type': 'BASE',
        'name': "Yoshi's Crafted World",
        'patch_level': 0,
    }


def test_catalog_target_without_a_known_name_is_none():
    restore = with_fake_game_info(None)
    try:
        assert downloader.catalog_target('01006000040C2000') is None
    finally:
        restore()


# ------------------------------------------------------------- catalog search

# (id, name, publisher, release_date). Update ids end in 800, DLC ids in something else.
FAKE_TITLES = [
    ('01006000040C2000', "Yoshi's Crafted World", 'Nintendo', 20190329),
    ('0100000000010000', 'Super Mario Odyssey', 'Nintendo', 20171027),
    ('010003F003A34800', 'Pokemon Update', 'Nintendo', None),
    ('01009BF0072D5001', 'Captain Toad DLC', 'Nintendo', None),
    ('0100ABCDEF012000', 'Pok\u00e9mon \u00c9carlate', 'Nintendo', 20221118),
    ('0100111111112000', None, 'Nintendo', None),
    (None, 'No id at all', 'Nintendo', None),
    ('0100222222222000', 'A Game About Pokemon', 'Indie', None),
]


def fake_titledb(rows=FAKE_TITLES):
    """Build a throwaway titles.db and point the store at it. Returns a restore callable."""
    tmpdir = tempfile.mkdtemp()
    path = os.path.join(tmpdir, 'titles.db')
    conn = sqlite3.connect(path)
    conn.execute('CREATE TABLE titles (id TEXT, name TEXT, icon_url TEXT, '
                 'banner_url TEXT, publisher TEXT, release_date INTEGER)')
    conn.executemany('INSERT INTO titles VALUES (?, ?, ?, ?, ?, ?)',
                     [(i, n, 'icon', 'banner', pub, date) for i, n, pub, date in rows])
    conn.commit()
    conn.close()

    previous = titledb_store.TITLES_DB_FILE
    titledb_store.TITLES_DB_FILE = path

    def restore():
        titledb_store.TITLES_DB_FILE = previous
        shutil.rmtree(tmpdir)
    return restore


def search(query, limit=60):
    restore = fake_titledb()
    try:
        return downloader.search_base_games(query, limit)
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
    assert [r['id'] for r in search('POK\u00c9MON \u00c9')] == ['0100ABCDEF012000']


def test_the_typed_words_may_be_scattered_through_the_name():
    # "zelda breath of the wild" must find "The Legend of Zelda: Breath of the Wild",
    # where the typed words are there but not side by side.
    assert [r['id'] for r in search('super odyssey')] == ['0100000000010000']


def test_a_typed_word_matches_only_at_the_start_of_a_word():
    # Otherwise a stray letter matches half the catalog: 'e' is not a word of this name.
    assert [r['id'] for r in search('pokemon e')] == ['0100ABCDEF012000']


def test_prefix_matches_come_first():
    names = [r['name'] for r in search('pokemon')]
    assert names == ['Pok\u00e9mon \u00c9carlate', 'A Game About Pokemon']


def test_the_limit_leaves_room_to_detect_truncation():
    # limit + 1 records come back so the caller can tell "capped" from "exactly that many".
    assert len(search('pokemon', limit=1)) == 2


def test_records_missing_a_name_or_an_id_are_skipped():
    assert search('no id at all') == []
    assert all(r['name'] for r in search('o'))


def test_a_blank_query_matches_nothing():
    assert search('   ') == []


def test_a_titledb_that_was_never_built_returns_none():
    # None, not [], so the UI can say "scan the library first" instead of "no results".
    previous = titledb_store.TITLES_DB_FILE
    titledb_store.TITLES_DB_FILE = os.path.join(tempfile.gettempdir(), 'no-such-titles.db')
    try:
        assert downloader.search_base_games('zelda') is None
    finally:
        titledb_store.TITLES_DB_FILE = previous


if __name__ == '__main__':
    for name, test in sorted(globals().items()):
        if name.startswith('test_'):
            test()
            print(f'ok {name}')
