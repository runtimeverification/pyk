from typing import Final

from ..kast.inner import KInner, KSort, KToken, bottom_up
from ..utils import enquote_str

BYTES: Final = KSort('Bytes')


def bytesToken(s: str) -> KToken:  # noqa: N802
    return KToken(f'b"{s}"', BYTES)


def enquote_bytes(kast: KInner) -> KInner:
    def _enquote_bytes(_kast: KInner) -> KInner:
        if type(_kast) is KToken and _kast.sort == BYTES:
            assert len(_kast.token) >= 3
            assert _kast.token[0:2] == 'b"'
            assert _kast.token[-1] == '"'
            new_token = enquote_str(_kast.token[2:-1])
            return bytesToken(new_token)
        return _kast

    return bottom_up(_enquote_bytes, kast)
