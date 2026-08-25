"""Self-checks for the organizer file placement, run with: python app/test_organizer.py"""
import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import library
from library import link_organized_file, same_file


class FakeFile:
    """Enough of a Files row for the hardlink path: it never reaches the database,
    because publish_as is the only writer and update_file_name is stubbed below."""
    def __init__(self, filepath, extension='nsp'):
        self.id = 1
        self.filepath = filepath
        self.filename = os.path.basename(filepath)
        self.extension = extension


def published_names():
    """Capture what publish_as would write to Files.filename."""
    written = []
    library.update_file_name = lambda file_id, filename: written.append(filename)
    return written


def make_source(tmp, name='ugly.name.nsp'):
    src = os.path.join(tmp, 'source', name)
    os.makedirs(os.path.dirname(src), exist_ok=True)
    with open(src, 'wb') as f:
        f.write(b'nsp')
    return src


def test_hardlink_is_created_and_source_is_untouched():
    with tempfile.TemporaryDirectory() as tmp:
        written = published_names()
        src = make_source(tmp)
        file_obj = FakeFile(src)
        dest = os.path.join(tmp, 'organized', 'Game Name', 'Game Name [0100][v0].nsp')

        assert link_organized_file(file_obj, dest)
        assert os.path.exists(src), 'the source file must never be moved'
        assert same_file(src, dest)
        assert os.stat(src).st_nlink == 2
        # The database keeps pointing at the source; only the published name changes
        assert file_obj.filepath == src
        assert written == ['Game Name [0100][v0].nsp']


def test_hardlink_is_idempotent():
    # The organizer runs again on every scan: linking twice must not create a second link
    with tempfile.TemporaryDirectory() as tmp:
        published_names()
        src = make_source(tmp)
        dest = os.path.join(tmp, 'organized', 'Game Name [0100][v0].nsp')

        for _ in range(3):
            assert link_organized_file(FakeFile(src), dest)
        assert os.stat(src).st_nlink == 2
        assert os.listdir(os.path.dirname(dest)) == [os.path.basename(dest)]


def test_a_different_file_at_the_same_name_gets_a_suffix():
    with tempfile.TemporaryDirectory() as tmp:
        written = published_names()
        first = make_source(tmp, 'first.nsp')
        second = make_source(tmp, 'second.nsp')
        dest = os.path.join(tmp, 'organized', 'Game Name [0100][v0].nsp')

        assert link_organized_file(FakeFile(first), dest)
        assert link_organized_file(FakeFile(second), dest)
        # The second file is published under a (N) name, not linked over the first
        assert written[-1] == 'Game Name [0100][v0](2).nsp'
        assert same_file(second, os.path.join(os.path.dirname(dest), written[-1]))
        assert os.stat(first).st_nlink == 2


def test_link_to_a_missing_source_fails_without_raising():
    with tempfile.TemporaryDirectory() as tmp:
        published_names()
        missing = FakeFile(os.path.join(tmp, 'nope.nsp'))
        assert not link_organized_file(missing, os.path.join(tmp, 'out.nsp'))


def test_same_file_on_missing_paths():
    with tempfile.TemporaryDirectory() as tmp:
        assert not same_file(os.path.join(tmp, 'a'), os.path.join(tmp, 'b'))


def test_organize_file_without_a_destination_moves_instead_of_linking():
    # Guard the branch itself: no destination must stay on upstream's move path
    with tempfile.TemporaryDirectory() as tmp:
        published_names()
        src = make_source(tmp)
        file_obj = FakeFile(src)
        file_obj.library_id = 1
        moved = []
        library.organized_relpath = lambda *a: os.path.join('Game', 'Game [0100][v0].nsp')
        library.get_library_path = lambda library_id: tmp
        library.add_ignored_event = lambda *a: None
        library.update_file_path = lambda *a: moved.append(a)

        assert library.organize_file(file_obj, tmp, {'templates': {}}) is True
        dest = os.path.join(tmp, 'Game', 'Game [0100][v0].nsp')
        assert os.path.exists(dest), 'the file should have been moved into place'
        assert not os.path.exists(src), 'a move must not leave the source behind'
        assert os.stat(dest).st_nlink == 1, 'the move path must not hardlink'
        assert moved, 'the move path must update the file path in the database'


if __name__ == '__main__':
    for name, fn in sorted(globals().items()):
        if name.startswith('test_'):
            fn()
            print(f'ok  {name}')
    print('all organizer checks passed')
