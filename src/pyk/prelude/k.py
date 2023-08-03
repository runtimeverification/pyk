from typing import Final

from ..kast.inner import KSort, KToken

K: Final = KSort('K')
GENERATED_TOP_CELL: Final[KSort] = KSort('GeneratedTopCell')

DOTS: Final = KToken('...', K)
