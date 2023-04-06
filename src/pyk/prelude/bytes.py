from typing import Final

from ..kast.inner import KSort, KToken
from ..utils import dequote_str, enquote_str

BYTES: Final = KSort('Bytes')


def bytesToken(pretty: str) -> KToken:  # noqa: N802
    return KToken(f'b"{enquote_str(pretty)}"', BYTES)


def pretty_bytes(token: KToken) -> str:
    if token.sort != BYTES:
        raise ValueError(f'Expected Bytes token, got: {token}')
    assert token.token[0:2] == 'b"'
    assert token.token[-1] == '"'
    return dequote_str(token.token[2:-1])
