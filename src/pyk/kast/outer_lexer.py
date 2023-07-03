from __future__ import annotations

from enum import Enum, auto
from typing import TYPE_CHECKING, NamedTuple

if TYPE_CHECKING:
    from collections.abc import Iterable, Iterator
    from typing import Final


class TokenType(Enum):
    EOF = 0
    COMMA = auto()
    LPAREN = auto()
    RPAREN = auto()
    LBRACE = auto()
    RBRACE = auto()
    LBRACK = auto()
    RBRACK = auto()
    VBAR = auto()
    EQ = auto()
    GT = auto()
    PLUS = auto()
    TIMES = auto()
    QUESTION = auto()
    TILDE = auto()
    COLON = auto()
    DCOLONEQ = auto()
    KW_ALIAS = auto()
    KW_CLAIM = auto()
    KW_CONFIG = auto()
    KW_CONTEXT = auto()
    KW_ENDMODULE = auto()
    KW_IMPORT = auto()
    KW_IMPORTS = auto()
    KW_LEFT = auto()
    KW_LEXICAL = auto()
    KW_LIST = auto()
    KW_MODULE = auto()
    KW_NELIST = auto()
    KW_NONASSOC = auto()
    KW_PRIORITIES = auto()
    KW_PRIORITY = auto()
    KW_PRIVATE = auto()
    KW_PUBLIC = auto()
    KW_REQUIRE = auto()
    KW_REQUIRES = auto()
    KW_RIGHT = auto()
    KW_RULE = auto()
    KW_SYNTAX = auto()
    NAT = auto()
    STRING = auto()
    REGEX = auto()
    ID_LOWER = auto()
    ID_UPPER = auto()
    MODNAME = auto()
    KLABEL = auto()
    KEY = auto()
    TAG = auto()
    BUBBLE = auto()


class Token(NamedTuple):
    text: str
    type: TokenType


_EOF_TOKEN: Final = Token('', TokenType.EOF)
_COLON_TOKEN: Final = Token(':', TokenType.COLON)
_DCOLONEQ_TOKEN: Final = Token('::=', TokenType.DCOLONEQ)

_SIMPLE_CHARS: Final = {
    ',': Token(',', TokenType.COMMA),
    '(': Token('(', TokenType.LPAREN),
    ')': Token(')', TokenType.RPAREN),
    '{': Token('{', TokenType.LBRACE),
    '}': Token('}', TokenType.RBRACE),
    '[': Token('[', TokenType.LBRACK),
    ']': Token(']', TokenType.RBRACK),
    '|': Token('|', TokenType.VBAR),
    '=': Token('=', TokenType.EQ),
    '>': Token('>', TokenType.GT),
    '+': Token('+', TokenType.PLUS),
    '*': Token('*', TokenType.TIMES),
    '?': Token('?', TokenType.QUESTION),
    '~': Token('~', TokenType.TILDE),
}

_KEYWORDS: Final = {
    'alias': Token('alias', TokenType.KW_ALIAS),
    'claim': Token('claim', TokenType.KW_CLAIM),
    'configuration': Token('configuration', TokenType.KW_CONFIG),
    'context': Token('context', TokenType.KW_CONTEXT),
    'endmodule': Token('endmodule', TokenType.KW_ENDMODULE),
    'import': Token('import', TokenType.KW_IMPORT),
    'imports': Token('imports', TokenType.KW_IMPORTS),
    'left': Token('left', TokenType.KW_LEFT),
    'lexical': Token('lexical', TokenType.KW_LEXICAL),
    'List': Token('List', TokenType.KW_LIST),
    'module': Token('module', TokenType.KW_MODULE),
    'NeList': Token('NeList', TokenType.KW_NELIST),
    'non-assoc': Token('non-assoc', TokenType.KW_NONASSOC),
    'priorities': Token('priorities', TokenType.KW_PRIORITIES),
    'priority': Token('priority', TokenType.KW_PRIORITY),
    'private': Token('private', TokenType.KW_PRIVATE),
    'public': Token('public', TokenType.KW_PUBLIC),
    'require': Token('require', TokenType.KW_REQUIRE),
    'requires': Token('requires', TokenType.KW_REQUIRES),
    'right': Token('right', TokenType.KW_RIGHT),
    'rule': Token('rule', TokenType.KW_RULE),
    'syntax': Token('sytnax', TokenType.KW_SYNTAX),
}

_WHITESPACE: Final = {' ', '\t', '\n', '\r'}
_DIGIT: Final = set('0123456789')
_LOWER: Final = set('abcdefghijklmnopqrstuvwxyz')
_UPPER: Final = set('ABCDEFGHIJKLMNOPQRSTUVWXYZ')
_ALPHA: Final = set().union(_LOWER).union(_UPPER)
_ALNUM: Final = set(_ALPHA).union(_DIGIT)


class State(Enum):
    DEFAULT = auto()
    BUBBLE = auto()
    CONTEXT = auto()
    KLABEL = auto()
    ATTR = auto()
    TAG = auto()
    MODNAME = auto()


def outer_lexer(it: Iterable[str]) -> Iterator[Token]:
    it = iter(it)
    la = next(it, '')
    state = State.DEFAULT

    while True:
        if state is State.DEFAULT:
            token, la = _default(la, it)
            yield token
            if token.type == TokenType.EOF:
                return
            state = _DEFAULT_NEXT_STATE.get(token.type, State.DEFAULT)

        elif state is State.MODNAME:
            token, la = _modname(la, it)
            yield token
            # should not be EOF
            state = _MODNAME_NEXT_STATE.get(token.type, State.MODNAME)

        elif state in {State.BUBBLE, State.CONTEXT}:
            bubble, token, la = _bubble_or_context(la, it, context=state is State.CONTEXT)
            if bubble:
                yield bubble
            yield token
            if token.type == TokenType.EOF:
                return
            next_state = _BUBBLE_NEXT_STATE if state is State.BUBBLE else _CONTEXT_NEXT_STATE
            state = next_state[token.type]

        else:
            raise RuntimeError('TODO')


_DEFAULT_KEYWORDS: Final = {
    'claim',
    'configuration',
    'context',
    'endmodule',
    'import',
    'imports',
    'left',
    'lexical',
    'List',
    'module',
    'NeList',
    'non-assoc',
    'priorities',
    'priority',
    'require',
    'requires',
    'right',
    'rule',
    'syntax',
}
_DEFAULT_NEXT_STATE: Final = {
    TokenType.KW_CLAIM: State.BUBBLE,
    TokenType.KW_CONFIG: State.BUBBLE,
    TokenType.KW_CONTEXT: State.CONTEXT,
    TokenType.KW_IMPORT: State.MODNAME,
    TokenType.KW_IMPORTS: State.MODNAME,
    TokenType.KW_MODULE: State.MODNAME,
    TokenType.KW_PRIORITIES: State.KLABEL,
    TokenType.KW_PRIORITY: State.KLABEL,
    TokenType.KW_RULE: State.BUBBLE,
}


def _default(la: str, it: Iterator[str]) -> tuple[Token, str]:
    la = _skip_ws_and_comments(la, it)

    if not la:
        return _EOF_TOKEN, la

    elif la in _SIMPLE_CHARS:
        return _simple_char(la, it)

    elif la == '"':
        return _string(la, it)

    elif la == 'r':
        return _regex_or_lower_id_or_keyword(la, it)

    elif la in _DIGIT:
        return _nat(la, it)

    elif la in _ALNUM:
        return _id_or_keyword(la, it)

    elif la == '#':
        return _hash_id(la, it)

    elif la == ':':
        return _colon_or_dcoloneq(la, it)

    else:
        raise ValueError(f'Unexpected character: {la}')


def _skip_ws_and_comments(la: str, it: Iterator[str]) -> str:
    while True:
        if la in _WHITESPACE:
            la = next(it, '')
        elif la == '/':
            is_comment, consumed, la = _maybe_comment(la, it)
            if not is_comment:
                raise ValueError(f'Unexpected character sequence: {consumed}')
            la = next(it, '')
        else:
            break
    return la


def _simple_char(la: str, it: Iterator[str]) -> tuple[Token, str]:
    # assert la in _SIMPLE_CHARS

    token = _SIMPLE_CHARS[la]
    la = next(it, '')
    return token, la


def _nat(la: str, it: Iterator[str]) -> tuple[Token, str]:
    # assert la in _DIGIT

    consumed = []
    while la in _DIGIT:
        consumed.append(la)
        la = next(it, '')
    text = ''.join(consumed)
    return Token(text, TokenType.NAT), la


def _id_or_keyword(la: str, it: Iterator[str]) -> tuple[Token, str]:
    # assert la in _ALPHA

    if la in _LOWER:
        token_type = TokenType.ID_LOWER
    else:
        token_type = TokenType.ID_UPPER

    consumed = []
    while la in _ALNUM:
        consumed.append(la)
        la = next(it, '')
    text = ''.join(consumed)
    if text in _DEFAULT_KEYWORDS:
        return _KEYWORDS[text], la
    return Token(text, token_type), la


def _hash_id(la: str, it: Iterator[str]) -> tuple[Token, str]:
    # assert la == '#'

    consumed = [la]
    la = next(it, '')

    if la in _LOWER:
        token_type = TokenType.ID_LOWER
    elif la in _UPPER:
        token_type = TokenType.ID_UPPER
    else:
        raise ValueError(f'Unexpected character: {la}')  # TODO extract function that handles '' properly

    while la in _ALNUM:
        consumed.append(la)
        la = next(it, '')
    text = ''.join(consumed)
    return Token(text, token_type), la


def _colon_or_dcoloneq(la: str, it: Iterator[str]) -> tuple[Token, str]:
    # assert la == ':'

    la = next(it, '')
    if la != ':':
        return _COLON_TOKEN, la
    la = next(it, '')
    if la != '=':
        raise ValueError(f'Unexpected character: {la}')  # Could return [":", ":"], but that never parses
    la = next(it, '')
    return _DCOLONEQ_TOKEN, la


def _string(la: str, it: Iterator) -> tuple[Token, str]:
    # assert la == '"'
    consumed: list[str] = []
    la = _consume_string(consumed, la, it)
    return Token(''.join(consumed), TokenType.STRING), la


def _regex_or_lower_id_or_keyword(la: str, it: Iterator) -> tuple[Token, str]:
    # assert la == 'r'
    consumed = [la]
    la = next(it, '')

    if la == '"':
        la = _consume_string(consumed, la, it)
        return Token(''.join(consumed), TokenType.REGEX), la

    while la in _ALNUM:
        consumed.append(la)
        la = next(it, '')
    text = ''.join(consumed)
    if text in _DEFAULT_KEYWORDS:
        return _KEYWORDS[text], la
    return Token(text, TokenType.ID_LOWER), la


def _consume_string(consumed: list[str], la: str, it: Iterator[str]) -> str:
    # assert la == '"'
    consumed.append(la)  # ['"']

    la = next(it, '')
    while la not in {'"', '\n', ''}:
        consumed.append(la)  # ['"', ..., X]
        if la == '\\':
            la = next(it, '')
            if not la:
                raise ValueError('Unexpected end of file')
            if la not in {'\\', '"', 'n', 'r', 't'}:
                raise ValueError(f'Unexpected character: {la!r}')
            consumed.append(la)  # ['"', ..., '//', X]
        la = next(it, '')

    if la == '\n':
        raise ValueError(f'Unexpected character: {la!r}')
    if not la:
        raise ValueError('Unexpected end of file')  # TODO extract function

    consumed.append(la)  # ['"', ..., '"']
    la = next(it, '')
    return la


_MODNAME_KEYWORDS: Final = {'private', 'public'}
_MODNAME_CHARS: Final = {'-', '_'}.union(_ALNUM)
_MODNAME_NEXT_STATE: Final = {TokenType.MODNAME: State.DEFAULT}


def _modname(la: str, it: Iterator) -> tuple[Token, str]:
    la = _skip_ws_and_comments(la, it)

    consumed = []

    if la == '#':
        consumed.append(la)
        la = next(it, '')

    if not la:
        raise ValueError('Unexpected end of file')

    allow_dash = False
    while la in _MODNAME_CHARS:
        if la == '-' and not allow_dash:
            raise ValueError(f'Unexpected character: {la}')
        allow_dash = la != '-'
        consumed.append(la)
        la = next(it, '')

    text = ''.join(consumed)
    if text in _MODNAME_KEYWORDS:
        return _KEYWORDS[text], la
    return Token(text, TokenType.MODNAME), la


_BUBBLE_KEYWORDS: Final = {'syntax', 'endmodule', 'rule', 'claim', 'configuration', 'context'}
_CONTEXT_KEYWORDS: Final = {'alias', 'syntax', 'endmodule', 'rule', 'claim', 'configuration', 'context'}

_BUBBLE_NEXT_STATE: Final = {
    TokenType.KW_SYNTAX: State.DEFAULT,
    TokenType.KW_ENDMODULE: State.DEFAULT,
    TokenType.KW_RULE: State.BUBBLE,
    TokenType.KW_CLAIM: State.BUBBLE,
    TokenType.KW_CONFIG: State.BUBBLE,
    TokenType.KW_CONTEXT: State.CONTEXT,
}
_CONTEXT_NEXT_STATE: Final = {
    TokenType.KW_ALIAS: State.BUBBLE,
    **_BUBBLE_NEXT_STATE,
}


def _bubble_or_context(la: str, it: Iterator, *, context: bool = False) -> tuple[Token | None, Token, str]:
    keywords = _CONTEXT_KEYWORDS if context else _BUBBLE_KEYWORDS

    bubble: list[str] = []  # text that belongs to the bubble
    pending: list[str] = []  # text that belongs to the bubble iff preceded and followed by bubble text

    while True:
        if not la:
            return Token(''.join(bubble), TokenType.BUBBLE) if bubble else None, _EOF_TOKEN, la

        elif la in _WHITESPACE:
            pending.append(la)
            la = next(it, '')
            continue

        elif la == '/':
            is_comment, consumed, la = _maybe_comment(la, it)
            if is_comment:
                pending += consumed
                continue
            else:
                if not la:  # unterminated block comment
                    bubble += pending if bubble else []
                    bubble += consumed
                    return Token(''.join(bubble), TokenType.BUBBLE) if bubble else None, _EOF_TOKEN, la
                else:  # /X
                    bubble += pending if bubble else []
                    bubble += consumed
                    pending = []
                    continue

        else:
            current = [la]  # text that might belong to the bubble or terminate the bubble if keyword
            la = next(it, '')
            while True:
                if not la or la in _WHITESPACE:
                    current_str = ''.join(current)
                    if current_str in keywords:
                        token = _KEYWORDS[current_str]
                        return Token(''.join(bubble), TokenType.BUBBLE) if bubble else None, token, la
                    else:
                        bubble += pending if bubble else []
                        bubble += current
                        pending = []
                        break

                elif la == '/':
                    is_comment, consumed, la = _maybe_comment(la, it)
                    if is_comment:
                        current_str = ''.join(current)
                        if current_str in keywords:
                            token = _KEYWORDS[current_str]
                            return Token(''.join(bubble), TokenType.BUBBLE) if bubble else None, token, la
                        else:
                            bubble += pending if bubble else []
                            bubble += current
                            pending = consumed
                            break
                    else:
                        bubble += pending if bubble else []
                        bubble += current
                        bubble += consumed
                        pending = []
                        break

                else:
                    current.append(la)
                    la = next(it, '')


def _maybe_comment(la: str, it: Iterator[str]) -> tuple[bool, list[str], str]:
    """
    Attempt to consume a line or block comment from the iterator.
    Expects la to be '/'.

    :param la: The current lookahead.
    :param it: The iterator.
    :return: A tuple `(success, consumed, la)` where
      * `success` indicates whether `consumed` is a comment
      * `consumed` is the list of consumed characters
      * `la` is the current lookahead
    """

    assert la == '/'
    consumed = [la]  # ['/']

    la = next(it, '')
    if la == '':
        return False, consumed, la

    elif la == '/':
        consumed.append(la)  # ['/', '/']
        la = next(it, '')
        while la and la != '\n':
            consumed.append(la)  # ['/', '/', ..., X]
            la = next(it, '')
        return True, consumed, la

    elif la == '*':
        consumed.append(la)  # ['/', '*']

        la = next(it, '')
        while True:
            if la == '':
                return False, consumed, la

            elif la == '*':
                consumed.append(la)  # ['/', '*', ..., '*']

                la = next(it, '')
                if la == '':
                    return False, consumed, la
                elif la == '/':
                    consumed.append(la)  # ['/', '*', ..., '*', '/']
                    la = next(it, '')
                    return True, consumed, la
                else:
                    consumed.append(la)  # ['/', '*', ..., '*', X]
                    la = next(it, '')
                    continue

            else:
                consumed.append(la)  # ['/', '*', ..., X]
                la = next(it, '')
                continue

    else:
        consumed.append(la)  # ['/', X]
        la = next(it, '')
        return False, consumed, la
