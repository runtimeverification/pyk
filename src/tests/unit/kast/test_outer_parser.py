from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from pyk.kast.outer_parser import OuterParser
from pyk.kast.outer_syntax import Alias, Att, Claim, Config, Context, Import, Rule

if TYPE_CHECKING:
    from typing import Final

    from pyk.kast.outer_syntax import AST


SENTENCE_TEST_DATA: Final = (
    ('rule x', Rule('x')),
    ('rule [label]: x', Rule('x', label='label')),
    ('rule x [key1, key2(value)]', Rule('x', att=Att((('key1', ''), ('key2', 'value'))))),
    (
        'rule [label]: x [key1, key2(value)]',
        Rule('x', label='label', att=Att((('key1', ''), ('key2', 'value')))),
    ),
    (
        'rule [label]: X => Y [key1, key2(value)]',
        Rule('X => Y', label='label', att=Att((('key1', ''), ('key2', 'value')))),
    ),
    ('claim x', Claim('x')),
    ('configuration x', Config('x')),
    ('context x', Context('x')),
    ('context alias x', Alias('x')),
)


@pytest.mark.parametrize('k_text,expected', SENTENCE_TEST_DATA, ids=[k_text for k_text, _ in SENTENCE_TEST_DATA])
def test_sentence(k_text: str, expected: AST) -> None:
    # Given
    parser = OuterParser(k_text)

    # When
    actual = parser.sentence()

    # Then
    assert actual == expected


IMPORT_TEST_DATA: Final = (
    ('import TEST', Import('TEST', public=True)),
    ('import public TEST', Import('TEST', public=True)),
    ('import private TEST', Import('TEST', public=False)),
    ('imports TEST', Import('TEST', public=True)),
    ('imports public TEST', Import('TEST', public=True)),
    ('imports private TEST', Import('TEST', public=False)),
)


@pytest.mark.parametrize('k_text,expected', IMPORT_TEST_DATA, ids=[k_text for k_text, _ in IMPORT_TEST_DATA])
def test_import(k_text: str, expected: AST) -> None:
    # Given
    parser = OuterParser(k_text)

    # When
    actual = parser.importt()

    # Then
    assert actual == expected
