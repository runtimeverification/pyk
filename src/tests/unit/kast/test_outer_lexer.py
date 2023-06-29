from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from pyk.kast.outer_lexer import Token, TokenType, _bubble, _maybe_comment

if TYPE_CHECKING:
    from typing import Final


COMMENT_TEST_DATA: Final = (
    ('/', False, '/', ''),
    ('//', True, '//', ''),
    ('///', True, '///', ''),
    ('/*', False, '/*', ''),
    ('/**', False, '/**', ''),
    ('/**/', True, '/**/', ''),
    ('/* comment */', True, '/* comment */', ''),
    ('/**/ //', True, '/**/', ' //'),
    ('// /**/', True, '// /**/', ''),
)


@pytest.mark.parametrize(
    'text,expected_success,expected_consumed_text,expected_remaining',
    COMMENT_TEST_DATA,
    ids=[text for text, *_ in COMMENT_TEST_DATA],
)
def test_maybe_comment(
    text: str,
    expected_success: bool,
    expected_consumed_text: str,
    expected_remaining: str,
) -> None:
    # Given
    it = iter(text)
    la = next(it, '')
    expected_consumed = list(expected_consumed_text)

    # When
    actual_success, actual_consumed, la = _maybe_comment(la, it)
    actual_remaining = la + ''.join(it)

    # Then
    assert actual_success == expected_success
    assert actual_consumed == expected_consumed
    assert actual_remaining == expected_remaining


BUBBLE_TEST_DATA: Final = (
    ('', None, Token('', TokenType.EOF), ''),
    (' ', None, Token('', TokenType.EOF), ''),
    ('/**/', None, Token('', TokenType.EOF), ''),
    ('/**//**//**/', None, Token('', TokenType.EOF), ''),
    ('/**/ /**/ /**/rule', None, Token('rule', TokenType.KW_RULE), ''),
    ('/**/hello/**/rule', 'hello', Token('rule', TokenType.KW_RULE), ''),
    ('/**/hello/**/world/**/rule', 'hello/**/world', Token('rule', TokenType.KW_RULE), ''),
    ('a', 'a', Token('', TokenType.EOF), ''),
    ('abc', 'abc', Token('', TokenType.EOF), ''),
    ('abc //', 'abc', Token('', TokenType.EOF), ''),
    ('abc /* */ //', 'abc', Token('', TokenType.EOF), ''),
    ('rule', None, Token('rule', TokenType.KW_RULE), ''),
    ('a rule', 'a', Token('rule', TokenType.KW_RULE), ''),
    ('Hyrule', 'Hyrule', Token('', TokenType.EOF), ''),
    ('Hy/**/rule', 'Hy', Token('rule', TokenType.KW_RULE), ''),
    ('Hy/* comment */rule', 'Hy', Token('rule', TokenType.KW_RULE), ''),
    ('an other rule', 'an other', Token('rule', TokenType.KW_RULE), ''),
    ('cash rules everything around me', 'cash rules everything around me', Token('', TokenType.EOF), ''),
    ('cash rule/**/s everything around me', 'cash', Token('rule', TokenType.KW_RULE), 's everything around me'),
    (
        '  /* comment */ program /* comment */ text /* comment */ rule ',
        'program /* comment */ text',
        Token('rule', TokenType.KW_RULE),
        ' ',
    ),
    ('rule//comment', None, Token('rule', TokenType.KW_RULE), ''),
    (
        'rule/*comment*/',
        None,
        Token('rule', TokenType.KW_RULE),
        '',
    ),  # the lexer has to consume the comment to check if it is terminated
    (
        'rule/*comment',
        'rule/*comment',
        Token('', TokenType.EOF),
        '',
    ),  # the comment is not terminated, hence it's part of the bubble
)


@pytest.mark.parametrize(
    'text,expected_bubble_text,expected_terminal,expected_remaining',
    BUBBLE_TEST_DATA,
    ids=[text for text, *_ in BUBBLE_TEST_DATA],
)
def test_bubble(
    text: str,
    expected_bubble_text: str | None,
    expected_terminal: Token,
    expected_remaining: str,
) -> None:
    # Given
    it = iter(text)
    la = next(it, '')
    expected_bubble = Token(expected_bubble_text, TokenType.BUBBLE) if expected_bubble_text is not None else None

    # When
    actual_bubble, actual_terminal, la = _bubble(la, it)
    actual_remaining = la + ''.join(it)

    # Then
    assert actual_bubble == expected_bubble
    assert actual_terminal == expected_terminal
    assert actual_remaining == expected_remaining
