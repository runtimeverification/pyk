from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from pyk.kast.outer_lexer import (
    Token,
    TokenType,
    _attr,
    _bubble_or_context,
    _default,
    _klabel,
    _maybe_comment,
    _modname,
    outer_lexer,
)

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
    ('X /* Y', 'X /* Y', Token('', TokenType.EOF), ''),
    ('rule', None, Token('rule', TokenType.KW_RULE), ''),
    ('a rule', 'a', Token('rule', TokenType.KW_RULE), ''),
    ('program text // comment\nendmodule', 'program text', Token('endmodule', TokenType.KW_ENDMODULE), ''),
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
    ('alias', 'alias', Token('', TokenType.EOF), ''),
    ('bubble alias', 'bubble alias', Token('', TokenType.EOF), ''),
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
    actual_bubble, actual_terminal, la = _bubble_or_context(la, it)
    actual_remaining = la + ''.join(it)

    # Then
    assert actual_bubble == expected_bubble
    assert actual_terminal == expected_terminal
    assert actual_remaining == expected_remaining


CONTEXT_TEST_DATA: Final = (
    ('alias', None, Token('alias', TokenType.KW_ALIAS), ''),
    ('bubble alias', 'bubble', Token('alias', TokenType.KW_ALIAS), ''),
)


@pytest.mark.parametrize(
    'text,expected_bubble_text,expected_terminal,expected_remaining',
    CONTEXT_TEST_DATA,
    ids=[text for text, *_ in CONTEXT_TEST_DATA],
)
def test_context(
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
    actual_bubble, actual_terminal, la = _bubble_or_context(la, it, context=True)
    actual_remaining = la + ''.join(it)

    # Then
    assert actual_bubble == expected_bubble
    assert actual_terminal == expected_terminal
    assert actual_remaining == expected_remaining


DEFAULT_TEST_DATA: Final = (
    ('', Token('', TokenType.EOF), ''),
    (' ', Token('', TokenType.EOF), ''),
    ('// comment', Token('', TokenType.EOF), ''),
    ('/* comment */', Token('', TokenType.EOF), ''),
    (' //', Token('', TokenType.EOF), ''),
    ('0', Token('0', TokenType.NAT), ''),
    ('01', Token('01', TokenType.NAT), ''),
    ('012abc', Token('012', TokenType.NAT), 'abc'),
    ('abc012', Token('abc012', TokenType.ID_LOWER), ''),
    ('#abc012', Token('#abc012', TokenType.ID_LOWER), ''),
    ('Abc012', Token('Abc012', TokenType.ID_UPPER), ''),
    ('#Abc012', Token('#Abc012', TokenType.ID_UPPER), ''),
    (':', Token(':', TokenType.COLON), ''),
    ('::=', Token('::=', TokenType.DCOLONEQ), ''),
    ('""', Token('""', TokenType.STRING), ''),
    ('"a"', Token('"a"', TokenType.STRING), ''),
    (r'"\n"', Token(r'"\n"', TokenType.STRING), ''),
    (r'"\""', Token(r'"\""', TokenType.STRING), ''),
    (r'"\\"', Token(r'"\\"', TokenType.STRING), ''),
    ('r', Token('r', TokenType.ID_LOWER), ''),
    ('r1', Token('r1', TokenType.ID_LOWER), ''),
    ('r""', Token('r""', TokenType.REGEX), ''),
    (r'r"\n"', Token(r'r"\n"', TokenType.REGEX), ''),
    (r'r"\""', Token(r'r"\""', TokenType.REGEX), ''),
    (r'r"\\"', Token(r'r"\\"', TokenType.REGEX), ''),
    ('rule', Token('rule', TokenType.KW_RULE), ''),
    ('rule0', Token('rule0', TokenType.ID_LOWER), ''),
    ('rulerule', Token('rulerule', TokenType.ID_LOWER), ''),
)


@pytest.mark.parametrize(
    'text,expected_token,expected_remaining',
    DEFAULT_TEST_DATA,
    ids=[text for text, *_ in DEFAULT_TEST_DATA],
)
def test_default(text: str, expected_token: Token, expected_remaining: str) -> None:
    # Given
    it = iter(text)
    la = next(it, '')

    # When
    actual_token, la = _default(la, it)
    actual_remaining = la + ''.join(it)

    # Then
    assert actual_token == expected_token
    assert actual_remaining == expected_remaining


MODNAME_TEST_DATA: Final = (
    ('private', Token('private', TokenType.KW_PRIVATE), ''),
    ('private MODULE', Token('private', TokenType.KW_PRIVATE), ' MODULE'),
    ('public', Token('public', TokenType.KW_PUBLIC), ''),
    ('module', Token('module', TokenType.MODNAME), ''),
    ('module ', Token('module', TokenType.MODNAME), ' '),
    ('MODULE', Token('MODULE', TokenType.MODNAME), ''),
    ('#module', Token('#module', TokenType.MODNAME), ''),
    ('#module#module', Token('#module', TokenType.MODNAME), '#module'),
    ('mo-du-le', Token('mo-du-le', TokenType.MODNAME), ''),
    ('m0-DU_l3', Token('m0-DU_l3', TokenType.MODNAME), ''),
    ('TEST-MODULE', Token('TEST-MODULE', TokenType.MODNAME), ''),
    ('TEST_MODULE', Token('TEST_MODULE', TokenType.MODNAME), ''),
)


@pytest.mark.parametrize(
    'text,expected_token,expected_remaining',
    MODNAME_TEST_DATA,
    ids=[text for text, *_ in MODNAME_TEST_DATA],
)
def test_modname(text: str, expected_token: Token, expected_remaining: str) -> None:
    # Given
    it = iter(text)
    la = next(it, '')

    # When
    actual_token, la = _modname(la, it)
    actual_remaining = la + ''.join(it)

    # Then
    assert actual_token == expected_token
    assert actual_remaining == expected_remaining


KLABEL_TEST_DATA: Final = (
    ('syntax', Token('syntax', TokenType.KW_SYNTAX), ''),
    ('syntaxx', Token('syntaxx', TokenType.KLABEL), ''),
    ('<foo()>', Token('<foo()>', TokenType.KLABEL), ''),
    ('>', Token('>', TokenType.GT), ''),
    ('> a', Token('>', TokenType.GT), ' a'),
)


@pytest.mark.parametrize(
    'text,expected_token,expected_remaining',
    KLABEL_TEST_DATA,
    ids=[text for text, *_ in KLABEL_TEST_DATA],
)
def test_klabel(text: str, expected_token: Token, expected_remaining: str) -> None:
    # Given
    it = iter(text)
    la = next(it, '')

    # When
    actual_token, la = _klabel(la, it)
    actual_remaining = la + ''.join(it)

    # Then
    assert actual_token == expected_token
    assert actual_remaining == expected_remaining


ATTR_TEST_DATA: Final = (
    ('a]', [Token('a', TokenType.ATTR_KEY), Token(']', TokenType.RBRACK)], ''),
    (' a ] ', [Token('a', TokenType.ATTR_KEY), Token(']', TokenType.RBRACK)], ' '),
    ('a<b>]', [Token('a<b>', TokenType.ATTR_KEY), Token(']', TokenType.RBRACK)], ''),
    ('1a-B<-->]', [Token('1a-B<-->', TokenType.ATTR_KEY), Token(']', TokenType.RBRACK)], ''),
    (
        'a("hello")]',
        [
            Token('a', TokenType.ATTR_KEY),
            Token('(', TokenType.LPAREN),
            Token('"hello"', TokenType.STRING),
            Token(')', TokenType.RPAREN),
            Token(']', TokenType.RBRACK),
        ],
        '',
    ),
    (
        'a( tag content (()) () )]',
        [
            Token('a', TokenType.ATTR_KEY),
            Token('(', TokenType.LPAREN),
            Token(' tag content (()) () ', TokenType.ATTR_CONTENT),
            Token(')', TokenType.RPAREN),
            Token(']', TokenType.RBRACK),
        ],
        '',
    ),
    (
        'a,b,c]',
        [
            Token('a', TokenType.ATTR_KEY),
            Token(',', TokenType.COMMA),
            Token('b', TokenType.ATTR_KEY),
            Token(',', TokenType.COMMA),
            Token('c', TokenType.ATTR_KEY),
            Token(']', TokenType.RBRACK),
        ],
        '',
    ),
    (
        ' /* 1 */ a /* 2 */ , b /* 3 */ ]',
        [
            Token('a', TokenType.ATTR_KEY),
            Token(',', TokenType.COMMA),
            Token('b', TokenType.ATTR_KEY),
            Token(']', TokenType.RBRACK),
        ],
        '',
    ),
    (
        'a<A>("hello"), b(foo(bar(%), baz))]',
        [
            Token('a<A>', TokenType.ATTR_KEY),
            Token('(', TokenType.LPAREN),
            Token('"hello"', TokenType.STRING),
            Token(')', TokenType.RPAREN),
            Token(',', TokenType.COMMA),
            Token('b', TokenType.ATTR_KEY),
            Token('(', TokenType.LPAREN),
            Token('foo(bar(%), baz)', TokenType.ATTR_CONTENT),
            Token(')', TokenType.RPAREN),
            Token(']', TokenType.RBRACK),
        ],
        '',
    ),
)


@pytest.mark.parametrize(
    'text,expected_tokens,expected_remaining',
    ATTR_TEST_DATA,
    ids=[text for text, *_ in ATTR_TEST_DATA],
)
def test_attr(text: str, expected_tokens: list[Token], expected_remaining: str) -> None:
    # Given
    it = iter(text)
    la = next(it, '')

    # When
    actual_tokens, la = _attr(la, it)
    actual_remaining = la + ''.join(it)

    # Then
    assert actual_tokens == expected_tokens
    assert actual_remaining == expected_remaining


LEXER_TEST_DATA: Final = (
    ('', [Token('', TokenType.EOF)]),
    ('1', [Token('1', TokenType.NAT), Token('', TokenType.EOF)]),
    ('1 11', [Token('1', TokenType.NAT), Token('11', TokenType.NAT), Token('', TokenType.EOF)]),
    ('1 /**/ 11', [Token('1', TokenType.NAT), Token('11', TokenType.NAT), Token('', TokenType.EOF)]),
    (
        'rule program text',
        [Token('rule', TokenType.KW_RULE), Token('program text', TokenType.BUBBLE), Token('', TokenType.EOF)],
    ),
    (
        'rule /* */ program /* */ text // ',
        [Token('rule', TokenType.KW_RULE), Token('program /* */ text', TokenType.BUBBLE), Token('', TokenType.EOF)],
    ),
    (
        'rule /* */ program /* */ text /* */ /* */ // ',
        [Token('rule', TokenType.KW_RULE), Token('program /* */ text', TokenType.BUBBLE), Token('', TokenType.EOF)],
    ),
    (
        'module TEST endmodule',
        [
            Token('module', TokenType.KW_MODULE),
            Token('TEST', TokenType.MODNAME),
            Token('endmodule', TokenType.KW_ENDMODULE),
            Token('', TokenType.EOF),
        ],
    ),
    (
        'module TEST rule /* comment */ X => Y /* comment */ endmodule',
        [
            Token('module', TokenType.KW_MODULE),
            Token('TEST', TokenType.MODNAME),
            Token('rule', TokenType.KW_RULE),
            Token('X => Y', TokenType.BUBBLE),
            Token('endmodule', TokenType.KW_ENDMODULE),
            Token('', TokenType.EOF),
        ],
    ),
    (
        'context foo',
        [
            Token('context', TokenType.KW_CONTEXT),
            Token('foo', TokenType.BUBBLE),
            Token('', TokenType.EOF),
        ],
    ),
    (
        'context alias foo',
        [
            Token('context', TokenType.KW_CONTEXT),
            Token('alias', TokenType.KW_ALIAS),
            Token('foo', TokenType.BUBBLE),
            Token('', TokenType.EOF),
        ],
    ),
    (
        'syntax priorities foo bar > baz',
        [
            Token('syntax', TokenType.KW_SYNTAX),
            Token('priorities', TokenType.KW_PRIORITIES),
            Token('foo', TokenType.KLABEL),
            Token('bar', TokenType.KLABEL),
            Token('>', TokenType.GT),
            Token('baz', TokenType.KLABEL),
            Token('', TokenType.EOF),
        ],
    ),
    (
        'syntax Foo ::= "bar" | Baz [group(foo)] syntax',
        [
            Token('syntax', TokenType.KW_SYNTAX),
            Token('Foo', TokenType.ID_UPPER),
            Token('::=', TokenType.DCOLONEQ),
            Token('"bar"', TokenType.STRING),
            Token('|', TokenType.VBAR),
            Token('Baz', TokenType.ID_UPPER),
            Token('[', TokenType.LBRACK),
            Token('group', TokenType.ATTR_KEY),
            Token('(', TokenType.LPAREN),
            Token('foo', TokenType.ATTR_CONTENT),
            Token(')', TokenType.RPAREN),
            Token(']', TokenType.RBRACK),
            Token('syntax', TokenType.KW_SYNTAX),
            Token('', TokenType.EOF),
        ],
    ),
)


@pytest.mark.parametrize(
    'text,expected',
    LEXER_TEST_DATA,
    ids=[text for text, _ in LEXER_TEST_DATA],
)
def test_lexer(text: str, expected: list[Token]) -> None:
    # Given
    it = iter(text)

    # When
    actual = list(outer_lexer(it))
    remaining = ''.join(it)

    # Then
    assert actual == expected
    assert not remaining
