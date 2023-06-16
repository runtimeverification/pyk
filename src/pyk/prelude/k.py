from __future__ import annotations

from typing import Final

from ..kast.inner import EMPTY_K_LABEL, KApply, KSort, KToken

K: Final = KSort('K')
GENERATED_TOP_CELL: Final = KSort('GeneratedTopCell')

DOTS: Final = KToken('...', K)

EMPTY_K: Final = KApply(EMPTY_K_LABEL)
