from itertools import count
from pathlib import Path
from typing import Final, Iterator, Tuple

import pytest
from pytest import TempPathFactory

from pyk.kast.inner import KInner, KLabel, KVariable
from pyk.kompile import KompiledDefn, munge, unmunge
from pyk.kore.parser import KoreParser
from pyk.kore.syntax import SortApp


def munge_test_data_reader() -> Iterator[Tuple[str, str]]:
    test_data_file = Path(__file__).parent / 'test-data/munge-tests'
    with open(test_data_file, 'r') as f:
        while True:
            try:
                label = next(f)
                symbol = next(f)
            except StopIteration:
                raise AssertionError('Malformed test data') from None

            yield label.rstrip('\n'), symbol.rstrip('\n')

            try:
                next(f)
            except StopIteration:
                return


MUNGE_TEST_DATA: Final = tuple(munge_test_data_reader())


@pytest.mark.parametrize('label,expected', MUNGE_TEST_DATA, ids=[label for label, _ in MUNGE_TEST_DATA])
def test_munge(label: str, expected: str) -> None:
    # When
    actual = munge(label)

    # Then
    assert actual == expected


@pytest.mark.parametrize('expected,symbol', MUNGE_TEST_DATA, ids=[symbol for _, symbol in MUNGE_TEST_DATA])
def test_unmunge(symbol: str, expected: str) -> None:
    # When
    actual = unmunge(symbol)

    # Then
    assert actual == expected


class DefnFactory:
    _tmp_path_factory: TempPathFactory

    def __init__(self, tmp_path_factory: TempPathFactory):
        self._tmp_path_factory = tmp_path_factory

    def __call__(self, definition_text: str) -> KompiledDefn:
        path = self._tmp_path_factory.mktemp('kompiled-defn')
        (path / 'definition.kore').write_text(definition_text)
        (path / 'timestamp').touch()
        return KompiledDefn(path)


@pytest.fixture(scope='session')
def defn_factory(tmp_path_factory: TempPathFactory) -> DefnFactory:
    return DefnFactory(tmp_path_factory)


def test_subsort_table(defn_factory: DefnFactory) -> None:
    # When
    definition_text = r"""
        []
        module MODULE-1
            axiom{R} \top{R}() [subsort{A{}, D{}}()]
            axiom{R} \top{R}() [subsort{B{}, D{}}()]
        endmodule []
        module MODULE-2
            axiom{R} \top{R}() [subsort{B{}, C{}}()]
        endmodule []
    """
    defn = defn_factory(definition_text)

    a, b, c, d = (SortApp(name) for name in ['A', 'B', 'C', 'D'])
    expected = {
        c: {b},
        d: {a, b},
    }

    # When
    actual = defn._subsort_table

    # Then
    assert actual == expected


X, Y, Z = (KVariable(name) for name in ('X', 'Y', 'Z'))
KAST_TO_KORE_TEST_DATA: Final = (
    (
        KLabel('foo', 'Int', 'String')(X, Y, Z),
        'Lblfoo{SortInt{}, SortString{}} (VarX: SortInt{}, VarY: SortInt{}, VarZ: SortBool{})',
    ),
    (
        KLabel('#And', 'Int')(X, Y),
        r'\and{SortInt{}} (VarX: SortInt{}, VarY: SortInt{})',
    ),
    (
        KLabel('#Exists', 'Int')(X, Y),
        r'\exists{SortInt{}} (VarX: SortKItem{}, VarY: SortInt{})',
    ),
)


@pytest.mark.parametrize('kast,expected_text', KAST_TO_KORE_TEST_DATA, ids=count())
def test_kast_to_kore(defn_factory: DefnFactory, kast: KInner, expected_text: str) -> None:
    # When
    definition_text = r"""
        []
        module MODULE
            symbol Lblfoo{S, T} (S, S, SortBool{}) : T []
        endmodule []
    """
    defn = defn_factory(definition_text)
    expected = KoreParser(expected_text).pattern()

    # When
    actual = defn.kast_to_kore(kast)

    # Then
    assert actual == expected
