from typing import Final, Union, final

from ..kast import KLabel, KToken
from .kbool import boolToken
from .kint import intToken
from .sorts import STRING, K

DOTS: Final = KToken('...', K)


@final
class Labels:
    K_CELLS: Final = KLabel('#KCells')
    EMPTY_K: Final = KLabel('#EmptyK')

    def __init__(self):
        raise ValueError('Class Labels should not be instantiated')


def token(x: Union[bool, int, str]) -> KToken:
    if type(x) is bool:
        return boolToken(x)
    if type(x) is int:
        return intToken(x)
    if type(x) is str:
        return stringToken(x)
    raise AssertionError()


def stringToken(s: str) -> KToken:  # noqa: N802
    return KToken(f'"{s}"', STRING)
