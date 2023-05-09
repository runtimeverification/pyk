from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

if TYPE_CHECKING:
    from typing import Final

from pyk.dequote import dequote_string, enquote_string

TEST_DATA: Final = (
    # enquoted, dequoted
    ('', ''),
    (' ', ' '),
    ('1', '1'),
    ('012', '012'),
    ('a', 'a'),
    ('abc', 'abc'),
    ("'", "'"),
    (r'\\ ', r'\ '),
    (r'\\1', r'\1'),
    (r'\\a', r'\a'),
    ('\\\\', '\\'),
    (r'\"', '"'),
    (r'\t', '\t'),
    (r'\n', '\n'),
    (r'\r', '\r'),
    (r'\f', '\f'),
    (r'Hello World!\n', 'Hello World!\n'),
    (r'\r\n', '\r\n'),
    ('$', '$'),
    (r'\u03b1', 'α'),
    (r'\u4e80', '亀'),
    (r'\U0001f642', '🙂'),
    (r'\u6b66\u5929\u8001\u5e2b', '武天老師'),
    (r'a\n\u03b1\n', 'a\nα\n'),
)

DEQUOTE_TEST_DATA: Final = TEST_DATA + (
    (r'\x0c', '\f'),
    (r'\x24', '$'),
    (r'\u0024', '$'),
    (r'\U00000024', '$'),
    (r'\x4e80', 'N80'),
)


@pytest.mark.parametrize(
    'enquoted,expected',
    DEQUOTE_TEST_DATA,
    ids=[enquoted for enquoted, *_ in DEQUOTE_TEST_DATA],
)
def test_dequote_string(enquoted: str, expected: str) -> None:
    # When
    actual = dequote_string(enquoted)

    # Then
    assert actual == expected


@pytest.mark.parametrize('expected,dequoted', TEST_DATA, ids=[expected for expected, *_ in TEST_DATA])
def test_enquote_string(expected: str, dequoted: str) -> None:
    # When
    actual = enquote_string(dequoted)

    # Then
    assert actual == expected
