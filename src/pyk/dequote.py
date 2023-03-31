from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from typing import Final, Iterable, Iterator


NORMAL = 1
ESCAPE = 2
CPOINT = 3

ESCAPE_TABLE: Final = {
    '"': '"',
    '\\': '\\',
    'n': '\n',
    't': '\t',
    'r': '\r',
    'f': '\f',
}

CPOINT_TABLE: Final = {
    'x': 2,
    'u': 4,
    'U': 8,
}


def dequoted(it: Iterable[str]) -> Iterator[str]:
    acc = 0
    cnt = 0
    state = NORMAL
    for c in it:
        if state == CPOINT:
            acc *= 16
            acc += int(c, 16)
            cnt -= 1
            if cnt == 0:
                yield chr(acc)
                acc = 0
                state = NORMAL
        elif state == ESCAPE:
            if c in CPOINT_TABLE:
                cnt = CPOINT_TABLE[c]
                state = CPOINT
            elif c in ESCAPE_TABLE:
                yield ESCAPE_TABLE[c]
                state = NORMAL
            else:
                raise ValueError(fr'Unexpected escape sequence: \{c}')
        elif c == '\\':
            state = ESCAPE
        else:
            yield c

    if state != NORMAL:
        assert state == CPOINT
        raise ValueError('Invalid Unicode code point')


ENQUOTE_TABLE: Final = {
    ord('\t'): r'\t',  # 9
    ord('\n'): r'\n',  # 10
    ord('\f'): r'\f',  # 12
    ord('\r'): r'\r',  # 13
    ord('"'): r'\"',  # 34
    ord('\\'): r'\\',  # 92
}


def enquoted(it: Iterable[str]) -> Iterator[str]:
    for c in it:
        code = ord(c)
        if code in ENQUOTE_TABLE:
            yield ENQUOTE_TABLE[code]
        elif 32 <= code < 127:
            yield c
        elif code <= 0xFF:
            yield fr'\x{code:02x}'
        elif code <= 0xFFFF:
            yield fr'\u{code:04x}'
        elif code <= 0xFFFFFFFF:
            yield fr'\U{code:08x}'
        else:
            raise ValueError(f"Unsupported character: '{c}' ({code})")
