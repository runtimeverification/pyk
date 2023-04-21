from __future__ import annotations

import json
from typing import TYPE_CHECKING

import pytest

from pyk.kast import KInner, kast_term
from pyk.konvert import _kast_to_kore, _kore_to_kast
from pyk.kore.parser import KoreParser
from pyk.kore.prelude import STRING, int_dv, string_dv
from pyk.kore.rpc import KoreClient, KoreServer, StuckResult
from pyk.kore.syntax import App, SortApp
from pyk.ktool.kprint import _kast, pretty_print_kast
from pyk.prelude.string import stringToken

if TYPE_CHECKING:
    from pathlib import Path
    from typing import Final

    from pytest import FixtureRequest

    from pyk.kore.syntax import Pattern

    from .utils import Kompiler

TEST_DATA: Final = (
    'hello',
    '\n',
    '武天老師',
    '🙂',
)

KOMPILE_MAIN_FILE = 'k-files/string-rewrite.k'
KOMPILE_MAIN_MODULE = 'STRING-REWRITE'


@pytest.fixture(scope='module')
def llvm_dir(kompile: Kompiler) -> Path:
    return kompile(
        KOMPILE_MAIN_FILE,
        main_module=KOMPILE_MAIN_MODULE,
        backend='llvm',
    )


@pytest.fixture(scope='module')
def haskell_dir(kompile: Kompiler) -> Path:
    return kompile(
        KOMPILE_MAIN_FILE,
        main_module=KOMPILE_MAIN_MODULE,
        backend='haskell',
    )


@pytest.fixture(scope='module', params=['llvm', 'haskell'])
def definition_dir(request: FixtureRequest) -> Path:
    return request.getfixturevalue(f'{request.param}_dir')


@pytest.mark.parametrize('text', TEST_DATA, ids=TEST_DATA)
def test_kast_to_kore(text: str) -> None:  # TODO turn into unit test
    # Given
    kast = stringToken(text)

    # When
    kore = _kast_to_kore(kast)

    # Then
    assert kore == string_dv(text)


@pytest.mark.parametrize('text', TEST_DATA, ids=TEST_DATA)
def test_kore_to_kast(text: str) -> None:  # TODO turn into unit test
    # Given
    kore = string_dv(text)

    # When
    kast = _kore_to_kast(kore)

    # Then
    assert kast == stringToken(text)


@pytest.mark.parametrize('text', TEST_DATA, ids=TEST_DATA)
def test_cli_kast_to_kore(llvm_dir: Path, text: str) -> None:
    # Given
    kast = stringToken(text)
    kast_dict = {'format': 'KAST', 'version': 2, 'term': kast.to_dict()}  # TODO extract function
    kast_json = json.dumps(kast_dict)

    # When
    proc_res = _kast(
        definition_dir=llvm_dir,
        expression=kast_json,
        input='json',
        output='kore',
    )
    kore_text = proc_res.stdout
    kore = KoreParser(kore_text).dv()

    # Then
    assert kore == string_dv(text)


@pytest.mark.parametrize('text', TEST_DATA, ids=TEST_DATA)
def test_cli_kore_to_kast(llvm_dir: Path, text: str) -> None:
    # Given
    kore = string_dv(text)
    kore_text = kore.text

    # When
    proc_res = _kast(
        definition_dir=llvm_dir,
        expression=kore_text,
        input='kore',
        output='json',
    )
    kast_json = proc_res.stdout
    kast = kast_term(json.loads(kast_json), KInner)  # type: ignore

    # Then
    assert kast == stringToken(text)


# @pytest.mark.parametrize('definition_dir', ['haskell', 'llvm'], indirect=True)
@pytest.mark.parametrize('text', TEST_DATA, ids=TEST_DATA)
def test_cli_rule_to_kast(llvm_dir: Path, text: str) -> None:
    # Given
    input_kast = stringToken(text)
    rule_text = pretty_print_kast(input_kast, {})

    # When
    proc_res = _kast(
        definition_dir=llvm_dir,
        expression=rule_text,
        input='rule',
        output='json',
    )
    kast_json = proc_res.stdout
    output_kast = kast_term(json.loads(kast_json), KInner)  # type: ignore

    # Then
    assert input_kast == output_kast


@pytest.mark.parametrize('text', TEST_DATA, ids=TEST_DATA)
def test_kore_rpc(haskell_dir: Path, text: str) -> None:
    def config(k: Pattern | None, s: Pattern) -> Pattern:
        dotk = App('dotk', (), ())
        kseq = App('kseq', (), (App('inj', (STRING, SortApp('SortKItem')), (k,)), dotk)) if k else dotk
        return App(
            "Lbl'-LT-'generatedTop'-GT-'",
            (),
            (
                App("Lbl'-LT-'k'-GT-'", (), (kseq,)),
                App("Lbl'-LT-'generatedCounter'-GT-'", (), (int_dv(0),)),
                App("Lbl'-LT-'s'-GT-'", (), (s,)),
            ),
        )

    try:
        text.encode('latin-1')
    except ValueError:
        # https://github.com/runtimeverification/pyk/issues/348
        pytest.skip()

    # Given
    init = config(string_dv(text), string_dv(''))

    # When
    with KoreServer(haskell_dir, KOMPILE_MAIN_MODULE) as server:
        with KoreClient('localhost', server.port) as client:
            result = client.execute(init)

    assert isinstance(result, StuckResult)
    assert result.state.term == config(None, string_dv(text))
