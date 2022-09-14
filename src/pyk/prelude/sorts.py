from typing import Final

from ..kast import BOOL as KAST_BOOL
from ..kast import KSort

BOOL: Final = KAST_BOOL
INT: Final = KSort('Int')
STRING: Final = KSort('String')
K: Final = KSort('K')
GENERATED_TOP_CELL: Final = KSort('GeneratedTopCell')
