"""Self-checks for the downloader ranking and the grab history.

No network, no database: only the pure ranking logic and the JSON store.
Run with: python app/test_downloader.py
"""
import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import downloader
import downloads_store as store
from downloader import best_release, rank_releases

FILTERS = {'min_seeders': 3, 'preferred_ext': ['nsz', 'nsp', 'xcz', 'xci'],
           'max_size_gb': 0, 'max_per_run': 10}

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


if __name__ == '__main__':
    for name, test in sorted(globals().items()):
        if name.startswith('test_'):
            test()
            print(f'ok {name}')
