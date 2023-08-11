from __future__ import annotations

from typing import TYPE_CHECKING

import pyk.kllvm.load  # noqa: F401
from pyk.kllvm.parser import parse_definition, parse_definition_file, parse_pattern, parse_pattern_file

if TYPE_CHECKING:
    from pathlib import Path


def test_parse_pattern_file(tmp_path: Path) -> None:
    # Given
    kore_text = 'A{}(B{}(),C{}())'
    kore_file = tmp_path / 'test.kore'
    kore_file.write_text(kore_text)

    # When
    actual = parse_pattern_file(kore_file)

    # Then
    assert str(actual) == kore_text


def test_parse_pattern() -> None:
    # Given
    kore_text = 'A{}(X : S,Y : Z,Int{}())'

    # When
    actual = parse_pattern(kore_text)

    # Then
    assert str(actual) == kore_text


def test_parse_definition_file(tmp_path: Path) -> None:
    # Given
    kore_text = """[]

module FOO
  axiom {S}A{}(B{}(),C{}()) [group{}("foo")]
endmodule
[concrete{}()]
"""
    kore_file = tmp_path / 'test.kore'
    kore_file.write_text(kore_text)

    # When
    actual = parse_definition_file(kore_file)

    # Then
    assert str(actual) == kore_text


def test_parse_definition() -> None:
    # Given
    kore_text = (
        '[]\n'
        '\n'
        'module FOO\n'
        '  axiom {S}A{}(X : S,Y : Z,Int{}()) [group{}("foo")]\n'
        'endmodule\n'
        '[concrete{}()]\n'
    )

    # When
    actual = parse_definition(kore_text)

    # Then
    assert str(actual) == kore_text
