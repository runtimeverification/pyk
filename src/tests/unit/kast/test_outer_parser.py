from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from pyk.kast.outer_parser import OuterParser
from pyk.kast.outer_syntax import Att, Rule

if TYPE_CHECKING:
    from typing import Final

    from pyk.kast.outer_syntax import AST


RULE_TEST_DATA: Final = (
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
)


@pytest.mark.parametrize('k_text,expected', RULE_TEST_DATA, ids=[k_text for k_text, _ in RULE_TEST_DATA])
def test_rule(k_text: str, expected: AST) -> None:
    # Given
    parser = OuterParser(k_text)

    # When
    actual = parser.rule()

    # Then
    assert actual == expected
