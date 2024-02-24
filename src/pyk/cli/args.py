from __future__ import annotations

import sys
from argparse import ArgumentParser
from enum import Enum
from functools import cached_property
from typing import IO, TYPE_CHECKING, Any, Iterable

from ..utils import ensure_dir_path
from .utils import bug_report_arg, dir_path, file_path

if TYPE_CHECKING:
    from pathlib import Path
    from typing import TypeVar

    T = TypeVar('T')


class PrintInput(Enum):
    KORE_JSON = 'kore-json'
    KAST_JSON = 'kast-json'


def generate_command_options(args: dict[str, Any]) -> Options:
    command = args['command'].lower()
    match command:
        case 'print':
            return PrintOptions(args)
        case 'rpc-print':
            raise ValueError('Not implemented.')
        case 'rpc-kast':
            raise ValueError('Not implemented.')
        case 'prove':
            return ProveOptions(args)
        case 'graph-imports':
            raise ValueError('Not implemented.')
        case 'coverage':
            raise ValueError('Not implemented.')
        case 'kore-to-json':
            raise ValueError('Not implemented.')
        case 'json-to-kore':
            raise ValueError('Not implemented.')
        case _:
            raise ValueError('Unrecognized command.')


class Options:
    ...


class PrintOptions(Options):
    def __init__(self, args: dict[str, Any]) -> None:
        self.definition_dir = args['definition_dir']
        self.term = args['term']

        self.input = PrintInput.KAST_JSON if args['input'] is None else args['input']
        self.output_file = sys.stdout if args['output_file'] is None else args['output_file']
        self.minimize = True if args['minimize'] is None else args['minimize']
        self.omit_labels = args['omit_labels']
        self.keep_cells = args['keep_cells']

    definition_dir: Path
    term: IO[Any]

    input: PrintInput
    output_file: IO[Any]
    minimize: bool
    omit_labels: str | None
    keep_cells: str | None


class ProveOptions(Options):
    def __init__(self, args: dict[str, Any]) -> None:
        self.definition_dir = args['definition_dir']
        self.main_file = args['main_file']
        self.spec_file = args['spec_file']
        self.spec_module = args['spec_module']

        self.k_args = args['k_args']

        self.output_file = sys.stdout if args['output_file'] is None else args['output_file']

    definition_dir: Path
    main_file: Path
    spec_file: Path
    spec_module: str
    k_args: Iterable[str]
    output_file: IO[Any]


class KCLIArgs:
    @cached_property
    def logging_args(self) -> ArgumentParser:
        args = ArgumentParser(add_help=False)
        args.add_argument('--verbose', '-v', default=False, action='store_true', help='Verbose output.')
        args.add_argument('--debug', default=False, action='store_true', help='Debug output.')
        return args

    @cached_property
    def parallel_args(self) -> ArgumentParser:
        args = ArgumentParser(add_help=False)
        args.add_argument('--workers', '-j', default=1, type=int, help='Number of processes to run in parallel.')
        return args

    @cached_property
    def bug_report_args(self) -> ArgumentParser:
        args = ArgumentParser(add_help=False)
        args.add_argument(
            '--bug-report',
            type=bug_report_arg,
            help='Generate bug report with given name',
        )
        return args

    @cached_property
    def kompile_args(self) -> ArgumentParser:
        args = ArgumentParser(add_help=False)
        args.add_argument(
            '--emit-json',
            dest='emit_json',
            default=True,
            action='store_true',
            help='Emit JSON definition after compilation.',
        )
        args.add_argument(
            '--no-emit-json', dest='emit_json', action='store_false', help='Do not JSON definition after compilation.'
        )
        args.add_argument(
            '-ccopt',
            dest='ccopts',
            default=[],
            action='append',
            help='Additional arguments to pass to llvm-kompile.',
        )
        args.add_argument(
            '--no-llvm-kompile',
            dest='llvm_kompile',
            default=True,
            action='store_false',
            help='Do not run llvm-kompile process.',
        )
        args.add_argument(
            '--with-llvm-library',
            dest='llvm_library',
            default=False,
            action='store_true',
            help='Make kompile generate a dynamic llvm library.',
        )
        args.add_argument(
            '--enable-llvm-debug',
            dest='enable_llvm_debug',
            default=False,
            action='store_true',
            help='Make kompile generate debug symbols for llvm.',
        )
        args.add_argument(
            '--read-only-kompiled-directory',
            dest='read_only',
            default=False,
            action='store_true',
            help='Generated a kompiled directory that K will not attempt to write to afterwards.',
        )
        args.add_argument('-O0', dest='o0', default=False, action='store_true', help='Optimization level 0.')
        args.add_argument('-O1', dest='o1', default=False, action='store_true', help='Optimization level 1.')
        args.add_argument('-O2', dest='o2', default=False, action='store_true', help='Optimization level 2.')
        args.add_argument('-O3', dest='o3', default=False, action='store_true', help='Optimization level 3.')
        return args

    @cached_property
    def smt_args(self) -> ArgumentParser:
        args = ArgumentParser(add_help=False)
        args.add_argument('--smt-timeout', dest='smt_timeout', type=int, help='Timeout in ms to use for SMT queries.')
        args.add_argument(
            '--smt-retry-limit',
            dest='smt_retry_limit',
            type=int,
            help='Number of times to retry SMT queries with scaling timeouts.',
        )
        args.add_argument(
            '--smt-tactic',
            dest='smt_tactic',
            type=str,
            help='Z3 tactic to use when checking satisfiability. Example: (check-sat-using smt)',
        )
        return args

    @cached_property
    def display_args(self) -> ArgumentParser:
        args = ArgumentParser(add_help=False)
        args.add_argument('--minimize', dest='minimize', default=None, action='store_true', help='Minimize output.')
        args.add_argument('--no-minimize', dest='minimize', action='store_false', help='Do not minimize output.')
        return args

    @cached_property
    def definition_args(self) -> ArgumentParser:
        args = ArgumentParser(add_help=False)
        args.add_argument(
            '-I', type=str, dest='includes', default=[], action='append', help='Directories to lookup K definitions in.'
        )
        args.add_argument('--main-module', default=None, type=str, help='Name of the main module.')
        args.add_argument('--syntax-module', default=None, type=str, help='Name of the syntax module.')
        args.add_argument('--spec-module', default=None, type=str, help='Name of the spec module.')
        args.add_argument('--definition', type=dir_path, dest='definition_dir', help='Path to definition to use.')
        args.add_argument(
            '--md-selector',
            type=str,
            help='Code selector expression to use when reading markdown.',
        )
        return args

    @cached_property
    def spec_args(self) -> ArgumentParser:
        args = ArgumentParser(add_help=False)
        args.add_argument('spec_file', type=file_path, help='Path to spec file.')
        args.add_argument('--save-directory', type=ensure_dir_path, help='Path to where CFGs are stored.')
        args.add_argument(
            '--claim',
            type=str,
            dest='claim_labels',
            action='append',
            help='Only prove listed claims, MODULE_NAME.claim-id',
        )
        args.add_argument(
            '--exclude-claim',
            type=str,
            dest='exclude_claim_labels',
            action='append',
            help='Skip listed claims, MODULE_NAME.claim-id',
        )
        return args
