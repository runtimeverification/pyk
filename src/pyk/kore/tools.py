from __future__ import annotations

from enum import Enum
from pathlib import Path
from tempfile import NamedTemporaryFile

from ..cli_utils import check_dir_path, run_process
from .syntax import Pattern


class PrintOutput(Enum):
    PRETTY = 'pretty'
    PROGRAM = 'program'
    KAST = 'kast'
    BINARY = 'binary'
    JSON = 'json'
    LATEX = 'latex'
    KORE = 'kore'
    NONE = 'none'


def kore_print(pattern: str | Pattern, definition_dir: str | Path, output: str | PrintOutput) -> str:
    definition_dir = Path(definition_dir)
    check_dir_path(definition_dir)

    output = PrintOutput(output)

    with NamedTemporaryFile(mode='w') as f:
        if type(pattern) is Pattern:
            pattern.write(f)
        elif type(pattern) is str:
            f.write(pattern)
        f.write('\n')
        f.flush()

        run_res = run_process(['kore-print', f.name, '--definition', str(definition_dir), '--output', output.value])

    return run_res.stdout.strip()
