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
