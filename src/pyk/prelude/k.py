from typing import Final

from ..kast import KLabel, KToken
from .sorts import K

DOTS: Final = KToken('...', K)
# Shouldn't these be KApply instead?
K_CELLS: Final = KLabel('#KCells')
EMPTY_K: Final = KLabel('#EmptyK')
