from __future__ import annotations

from typing import TYPE_CHECKING

import pyk.kllvm.load  # noqa: F401
from pyk.kllvm.parser import parse_definition_file, parse_definition_text, parse_pattern_file, parse_pattern_text

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


def test_parse_pattern_text() -> None:
    # Given
    kore_text = 'A{}(X : S,Y : Z,Int{}())'

    # When
    actual = parse_pattern_text(kore_text)

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


def test_parse_definition_text() -> None:
    # Given
    kore_text = """[]

module FOO
  axiom {S}A{}(X : S,Y : Z,Int{}()) [group{}("foo")]
endmodule
[concrete{}()]
"""

    # When
    actual = parse_definition_text(kore_text)

    # Then
    assert str(actual) == kore_text
