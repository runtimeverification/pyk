from typing import Final

from ..kast import KLabel, KSort, KToken

K: Final = KSort('K')
GENERATED_TOP_CELL: Final = KSort('GeneratedTopCell')

DOTS: Final = KToken('...', K)

# Shouldn't these be KApply instead?
K_CELLS: Final = KLabel('#KCells')
EMPTY_K: Final = KLabel('#EmptyK')
