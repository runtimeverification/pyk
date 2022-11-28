from pathlib import Path

from .utils import KompiledTest, Kompiler


class TestKompile(KompiledTest):
    KOMPILE_MAIN_FILE = 'k-files/imp.k'

    def test1(self, definition_dir: Path) -> None:
        assert definition_dir.is_dir()

    def test2(self, definition_dir: Path) -> None:
        assert definition_dir.is_dir()


def test_kompile(kompile: Kompiler) -> None:
    # When
    definition_dir = kompile(main_file=Path('k-files/imp.k'))

    # Then
    assert definition_dir.is_dir()
