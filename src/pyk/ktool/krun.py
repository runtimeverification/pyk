from __future__ import annotations

import json
import logging
import sys
from enum import Enum
from pathlib import Path
from subprocess import CalledProcessError
from typing import TYPE_CHECKING

from ..cli.utils import check_dir_path, check_file_path
from ..cterm import CTerm
from ..kast import kast_term
from ..kast.inner import KInner
from ..kore.parser import KoreParser
from ..utils import run_process
from .kprint import KPrint

if TYPE_CHECKING:
    from collections.abc import Callable, Iterable, Mapping
    from logging import Logger
    from subprocess import CompletedProcess
    from typing import Final

    from ..kast.outer import KFlatModule
    from ..kast.pretty import SymbolTable
    from ..kore.syntax import Pattern
    from ..utils import BugReport

_LOGGER: Final = logging.getLogger(__name__)


class KRunOutput(Enum):
    PRETTY = 'pretty'
    PROGRAM = 'program'
    KAST = 'kast'
    BINARY = 'binary'
    JSON = 'json'
    LATEX = 'latex'
    KORE = 'kore'
    NONE = 'none'


class KRun(KPrint):
    command: str

    def __init__(
        self,
        definition_dir: Path,
        use_directory: Path | None = None,
        command: str = 'krun',
        bug_report: BugReport | None = None,
        extra_unparsing_modules: Iterable[KFlatModule] = (),
        patch_symbol_table: Callable[[SymbolTable], None] | None = None,
    ) -> None:
        super().__init__(
            definition_dir,
            use_directory=use_directory,
            bug_report=bug_report,
            extra_unparsing_modules=extra_unparsing_modules,
            patch_symbol_table=patch_symbol_table,
        )
        self.command = command

    def run_pgm_config(
        self,
        pgm: KInner,
        *,
        config: Mapping[str, KInner] | None = None,
        depth: int | None = None,
        expand_macros: bool = False,
        search_final: bool = False,
        no_pattern: bool = False,
        expect_rc: int | Iterable[int] = 0,
    ) -> CTerm:
        if config is not None and 'PGM' in config:
            raise ValueError('Cannot supply both pgm and config with PGM variable.')
        pmap = {k: 'cat' for k in config} if config is not None else None
        cmap = {k: self.kast_to_kore(v).text for k, v in config.items()} if config is not None else None
        with self._temp_file() as ntf:
            kore_pgm = self.kast_to_kore(pgm)
            ntf.write(kore_pgm.text)
            ntf.flush()

            result = _krun(
                command=self.command,
                input_file=Path(ntf.name),
                definition_dir=self.definition_dir,
                output=KRunOutput.JSON,
                depth=depth,
                parser='cat',
                cmap=cmap,
                pmap=pmap,
                temp_dir=self.use_directory,
                no_expand_macros=not expand_macros,
                search_final=search_final,
                no_pattern=no_pattern,
                bug_report=self._bug_report,
                check=(expect_rc == 0),
            )

        self._check_return_code(result.returncode, expect_rc)

        result_kast = kast_term(json.loads(result.stdout), KInner)  # type: ignore # https://github.com/python/mypy/issues/4717
        return CTerm.from_kast(result_kast)

    def run_kore(
        self,
        pgm: Pattern,
        *,
        cmap: Mapping[str, str] | None = None,
        pmap: Mapping[str, str] | None = None,
        depth: int | None = None,
        expand_macros: bool = True,
        search_final: bool = False,
        no_pattern: bool = False,
        output: KRunOutput | None = KRunOutput.PRETTY,
        check: bool = False,
        bug_report: BugReport | None = None,
    ) -> CompletedProcess:
        with self._temp_file() as ntf:
            ntf.write(pgm.text)
            ntf.flush()

            result = _krun(
                command=self.command,
                input_file=Path(ntf.name),
                definition_dir=self.definition_dir,
                output=KRunOutput.KORE,
                depth=depth,
                parser='cat',
                cmap=cmap,
                pmap=pmap,
                temp_dir=self.use_directory,
                no_expand_macros=not expand_macros,
                search_final=search_final,
                no_pattern=no_pattern,
                bug_report=self._bug_report,
                check=False,
            )

        if output != KRunOutput.NONE:
            output_kore = KoreParser(result.stdout).pattern()
            match output:
                case KRunOutput.PRETTY:
                    print(self.kore_to_pretty(output_kore) + '\n')
                case KRunOutput.JSON:
                    print(self.kore_to_kast(output_kore).to_json() + '\n')
                case KRunOutput.KORE:
                    print(output_kore.text + '\n')
                case KRunOutput.PROGRAM | KRunOutput.KAST | KRunOutput.BINARY | KRunOutput.LATEX:
                    raise NotImplementedError(f'Option --output {output} unsupported!')
                case KRunOutput.NONE:
                    pass

        sys.stderr.write(result.stderr + '\n')
        sys.stderr.flush()

        if check and result.returncode != 0:
            sys.exit(result.returncode)

        return result

    def run_kore_term(
        self,
        pattern: Pattern,
        *,
        depth: int | None = None,
        expand_macros: bool = False,
        search_final: bool = False,
        no_pattern: bool = False,
        bug_report: BugReport | None = None,
        expect_rc: int | Iterable[int] = 0,
    ) -> Pattern:
        with self._temp_file() as ntf:
            pattern.write(ntf)
            ntf.write('\n')
            ntf.flush()

            proc_res = _krun(
                command=self.command,
                input_file=Path(ntf.name),
                definition_dir=self.definition_dir,
                output=KRunOutput.KORE,
                parser='cat',
                term=True,
                depth=depth,
                temp_dir=self.use_directory,
                no_expand_macros=not expand_macros,
                search_final=search_final,
                no_pattern=no_pattern,
                bug_report=self._bug_report,
                check=(expect_rc == 0),
            )

        self._check_return_code(proc_res.returncode, expect_rc)

        parser = KoreParser(proc_res.stdout)
        res = parser.pattern()
        assert parser.eof
        return res

    @staticmethod
    def _check_return_code(actual: int, expected: int | Iterable[int]) -> None:
        if isinstance(expected, int):
            expected = [expected]

        if actual not in expected:
            raise RuntimeError(f'Expected {expected} as exit code from krun, but got {actual}')


def _krun(
    command: str = 'krun',
    *,
    input_file: Path | None = None,
    definition_dir: Path | None = None,
    output: KRunOutput | None = None,
    parser: str | None = None,
    depth: int | None = None,
    cmap: Mapping[str, str] | None = None,
    pmap: Mapping[str, str] | None = None,
    term: bool = False,
    temp_dir: Path | None = None,
    no_expand_macros: bool = False,
    search_final: bool = False,
    no_pattern: bool = False,
    # ---
    check: bool = True,
    pipe_stderr: bool = False,
    logger: Logger | None = None,
    bug_report: BugReport | None = None,
) -> CompletedProcess:
    if input_file:
        check_file_path(input_file)

    if definition_dir:
        check_dir_path(definition_dir)

    if depth and depth < 0:
        raise ValueError(f'Expected non-negative depth, got: {depth}')

    args = _build_arg_list(
        command=command,
        input_file=input_file,
        definition_dir=definition_dir,
        output=output,
        parser=parser,
        depth=depth,
        pmap=pmap,
        cmap=cmap,
        term=term,
        temp_dir=temp_dir,
        no_expand_macros=no_expand_macros,
        search_final=search_final,
        no_pattern=no_pattern,
    )

    if bug_report is not None:
        if input_file is not None:
            new_input_file = Path(f'krun_inputs/{input_file}')
            bug_report.add_file(input_file, new_input_file)
            bug_report.add_command([a if a != str(input_file) else str(new_input_file) for a in args])
        else:
            bug_report.add_command(args)

    try:
        return run_process(args, check=check, pipe_stderr=pipe_stderr, logger=logger or _LOGGER)
    except CalledProcessError as err:
        raise RuntimeError(
            f'Command krun exited with code {err.returncode} for: {input_file}', err.stdout, err.stderr
        ) from err


def _build_arg_list(
    *,
    command: str,
    input_file: Path | None,
    definition_dir: Path | None,
    output: KRunOutput | None,
    parser: str | None,
    depth: int | None,
    pmap: Mapping[str, str] | None,
    cmap: Mapping[str, str] | None,
    term: bool,
    temp_dir: Path | None,
    no_expand_macros: bool,
    search_final: bool,
    no_pattern: bool,
) -> list[str]:
    args = [command]
    if input_file:
        args += [str(input_file)]
    if definition_dir:
        args += ['--definition', str(definition_dir)]
    if output:
        args += ['--output', output.value]
    if parser:
        args += ['--parser', parser]
    if depth is not None:
        args += ['--depth', str(depth)]
    for name, value in (pmap or {}).items():
        args += [f'-p{name}={value}']
    for name, value in (cmap or {}).items():
        args += [f'-c{name}={value}']
    if term:
        args += ['--term']
    if temp_dir:
        args += ['--temp-dir', str(temp_dir)]
    if no_expand_macros:
        args += ['--no-expand-macros']
    if search_final:
        args += ['--search-final']
    if no_pattern:
        args += ['--no-pattern']
    return args
