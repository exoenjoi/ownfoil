"""Self-checks for the organizer file placement, run with: python app/test_organizer.py"""
import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from library import place_file, same_file


def test_hardlink_is_created():
    with tempfile.TemporaryDirectory() as tmp:
        src = os.path.join(tmp, 'source', 'ugly.name.nsp')
        dest = os.path.join(tmp, 'library', 'Game Name', 'Game Name [0100][v0].nsp')
        os.makedirs(os.path.dirname(src))
        with open(src, 'wb') as f:
            f.write(b'nsp')

        assert place_file(src, dest, hardlink=True)
        assert os.path.exists(src), 'the source file must never be moved'
        assert same_file(src, dest)
        assert os.stat(src).st_nlink == 2


def test_hardlink_is_idempotent():
    # The organizer runs again on every scan: linking twice must not create a second link
    with tempfile.TemporaryDirectory() as tmp:
        src = os.path.join(tmp, 'ugly.name.nsp')
        dest = os.path.join(tmp, 'library', 'Game Name [0100][v0].nsp')
        with open(src, 'wb') as f:
            f.write(b'nsp')

        for _ in range(3):
            assert place_file(src, dest, hardlink=True)
        assert os.stat(src).st_nlink == 2
        assert os.listdir(os.path.dirname(dest)) == [os.path.basename(dest)]


def test_link_to_a_missing_source_fails_without_raising():
    with tempfile.TemporaryDirectory() as tmp:
        assert not place_file(os.path.join(tmp, 'nope.nsp'), os.path.join(tmp, 'out.nsp'), hardlink=True)


def test_move_still_moves():
    with tempfile.TemporaryDirectory() as tmp:
        src = os.path.join(tmp, 'ugly.name.nsp')
        dest = os.path.join(tmp, 'library', 'Game Name [0100][v0].nsp')
        with open(src, 'wb') as f:
            f.write(b'nsp')

        assert place_file(src, dest, hardlink=False)
        assert not os.path.exists(src)
        assert os.path.exists(dest)


def test_same_file_on_missing_paths():
    with tempfile.TemporaryDirectory() as tmp:
        assert not same_file(os.path.join(tmp, 'a'), os.path.join(tmp, 'b'))


if __name__ == '__main__':
    for name, test in sorted(globals().items()):
        if name.startswith('test_'):
            test()
            print(f'ok {name}')
