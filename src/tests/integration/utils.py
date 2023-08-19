from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from typing import Final


K_FILES: Final = (Path(__file__).parent / 'k-files').resolve(strict=True)
TEST_DATA: Final = (Path(__file__).parent / 'kcfg/test-data').resolve(strict=True)
JSON_DATA: Final = TEST_DATA / 'json'
