from __future__ import annotations

from enum import Enum
from pathlib import Path
from tempfile import NamedTemporaryFile

from ..cli.utils import check_dir_path, check_file_path
from ..utils import run_process
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


def kore_print(
    pattern: str | Pattern,
    *,
    definition_dir: str | Path | None = None,
    output_file: str | Path | None = None,
    output: str | PrintOutput | None = None,
    color: bool | None = None,
) -> str:
    if output is PrintOutput.KORE and isinstance(pattern, str):
        return pattern

    with NamedTemporaryFile(mode='w') as f:
        if isinstance(pattern, Pattern):
            pattern.write(f)
            f.write('\n')
        elif isinstance(pattern, str):
            f.write(pattern)
        else:
            raise TypeError(f'Unexpected type, expected [str | Pattern], got: {type(pattern)}')
        f.flush()

        return _kore_print(f.name, definition_dir=definition_dir, output_file=output_file, output=output, color=color)


def _kore_print(
    input_file: str | Path,
    *,
    definition_dir: str | Path | None = None,
    output_file: str | Path | None = None,
    output: str | PrintOutput | None = None,
    color: bool | None = None,
) -> str:
    args = ['kore-print']

    input_file = Path(input_file)
    check_file_path(input_file)
    args += [str(input_file)]

    if definition_dir is not None:
        definition_dir = Path(definition_dir)
        check_dir_path(definition_dir)
        args += ['--definition', str(definition_dir)]

    if output_file is not None:
        output_file = Path(output_file)
        check_file_path(output_file)
        args += ['--output_file', str(output_file)]

    if output is not None:
        output = PrintOutput(output)
        args += ['--output', output.value]

    if color is not None:
        args += ['--color', 'on' if color else 'off']

    run_res = run_process(args)
    return run_res.stdout.strip()
