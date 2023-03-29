from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

from _kllvm.parser import Parser  # type: ignore

from ..cli_utils import check_file_path

if TYPE_CHECKING:
    pass

    from .ast import Pattern


def read_pattern(path: str | Path) -> Pattern:
    path = Path(path)
    check_file_path(path)
    parser = Parser(str(path))
    return parser.pattern()
