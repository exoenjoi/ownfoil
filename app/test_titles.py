"""Self-checks for file identification, run with: python app/test_titles.py

No keys, no real containers: only the CNMT collection, with fake entries.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from nsz.Fs import Nsp, Xci

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


if __name__ == '__main__':
    for name, test in sorted(globals().items()):
        if name.startswith('test_'):
            test()
            print(f'ok {name}')
