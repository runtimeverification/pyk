import json
import logging
from enum import Enum
from pathlib import Path
from subprocess import CalledProcessError, CompletedProcess
from tempfile import NamedTemporaryFile
from typing import Final, Iterable, List, Mapping, Optional

from ..cli_utils import check_dir_path, check_file_path, run_process
from ..cterm import CTerm
from ..kast import KAst, KInner, KSort
from ..kore.parser import KoreParser
from .kprint import KPrint

_LOGGER: Final = logging.getLogger(__name__)


def _krun(
    definition_dir: Path,
    input_file: Path,
    check: bool = True,
    profile: bool = True,
    output: str = 'json',
    expand_macros: bool = False,
    depth: Optional[int] = None,
    args: Iterable[str] = (),
) -> CompletedProcess:
    check_file_path(input_file)

    krun_command = ['krun', '--definition', str(definition_dir), str(input_file), '--output', output]
    args = list(args)

    if depth and depth >= 0:
        args += ['--depth', str(depth)]

    if profile:
        args += ['--profile']

    if not expand_macros:
        args += ['--no-expand-macros']

    try:
        return run_process(krun_command + args, logger=_LOGGER, check=check, profile=profile)
    except CalledProcessError as err:
        raise RuntimeError(
            f'Command krun exited with code {err.returncode} for: {input_file}', err.stdout, err.stderr
        ) from err


class KRun(KPrint):

    backend: str
    main_module: str

    def __init__(self, definition_dir: Path, use_directory: Optional[Path] = None, profile: bool = False) -> None:
        super(KRun, self).__init__(definition_dir, use_directory=use_directory, profile=profile)
        with open(self.definition_dir / 'backend.txt', 'r') as ba:
            self.backend = ba.read()
        with open(self.definition_dir / 'mainModule.txt', 'r') as mm:
            self.main_module = mm.read()

    def run(
        self, pgm: KInner, depth: Optional[int] = None, expand_macros: bool = False, args: Iterable[str] = ()
    ) -> CTerm:
        with NamedTemporaryFile('w', dir=self.use_directory, delete=False) as ntf:
            ntf.write(self.pretty_print(pgm))
            ntf.flush()
            result = _krun(
                self.definition_dir,
                Path(ntf.name),
                depth=depth,
                expand_macros=expand_macros,
                args=(list(args) + ['--output', 'json']),
                profile=self._profile,
            )
            if result.returncode != 0:
                raise RuntimeError('Non-zero exit-code from krun.')
            result_kast = KAst.from_dict(json.loads(result.stdout)['term'])
            assert isinstance(result_kast, KInner)
            return CTerm(result_kast)

    def run_kore(
        self,
        pgm: KInner,
        depth: Optional[int] = None,
        sort: Optional[KSort] = None,
        expand_macros: bool = False,
        args: Iterable[str] = (),
    ) -> CTerm:
        kore_pgm = self.kast_to_kore(pgm, sort=sort)
        with NamedTemporaryFile('w', dir=self.use_directory, delete=True) as ntf:
            ntf.write(kore_pgm.text)
            ntf.flush()
            result = _krun(
                self.definition_dir,
                Path(ntf.name),
                depth=depth,
                expand_macros=expand_macros,
                args=(list(args) + ['--output', 'kore', '--parser', 'cat']),
                profile=self._profile,
            )
            if result.returncode != 0:
                raise RuntimeError('Non-zero exit-code from krun.')
            result_kore = KoreParser(result.stdout).pattern()
            result_kast = self.kore_to_kast(result_kore)
            assert isinstance(result_kast, KInner)
            return CTerm(result_kast)


class KRunOutput(Enum):
    PRETTY = 'pretty'
    PROGRAM = 'program'
    KAST = 'kast'
    BINARY = 'binary'
    JSON = 'json'
    LATEX = 'latex'
    KORE = 'kore'
    NONE = 'none'


def _krunx(
    command: str = 'krun',
    *,
    input_file: Optional[Path] = None,
    definition_dir: Optional[Path] = None,
    output: Optional[KRunOutput] = None,
    parser: Optional[str] = None,
    depth: Optional[int] = None,
    pmap: Optional[Mapping[str, str]] = None,
    cmap: Optional[Mapping[str, str]] = None,
    term: bool = False,
    no_expand_macros: bool = False,
    # ---
    check: bool = True,
    profile: bool = True,
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
        no_expand_macros=no_expand_macros,
    )

    try:
        return run_process(args, logger=_LOGGER, check=check, profile=profile)
    except CalledProcessError as err:
        raise RuntimeError(
            f'Command krun exited with code {err.returncode} for: {input_file}', err.stdout, err.stderr
        ) from err


def _build_arg_list(
    *,
    command: str,
    input_file: Optional[Path],
    definition_dir: Optional[Path],
    output: Optional[KRunOutput],
    parser: Optional[str],
    depth: Optional[int],
    pmap: Optional[Mapping[str, str]],
    cmap: Optional[Mapping[str, str]],
    term: bool,
    no_expand_macros: bool,
) -> List[str]:
    args = [command]
    if input_file:
        args += [str(input_file)]
    if definition_dir:
        args += ['--definition', str(definition_dir)]
    if output:
        args += ['--output', output.value]
    if parser:
        args += ['--parser', parser]
    if depth:
        args += ['--depth', str(depth)]
    for name, value in (pmap or {}).items():
        args += [f'--p{name}={value}']
    for name, value in (cmap or {}).items():
        args += [f'--c{name}={value}']
    if term:
        args += ['--term']
    if no_expand_macros:
        args += ['--no-expand-macros']
    return args
