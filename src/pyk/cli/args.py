from __future__ import annotations

import sys
from argparse import ArgumentParser, FileType
from enum import Enum
from functools import cached_property
from typing import IO, TYPE_CHECKING, Any, Iterable, Type

from ..utils import ensure_dir_path
from .utils import bug_report_arg, dir_path, file_path

if TYPE_CHECKING:
    from argparse import _SubParsersAction
    from pathlib import Path
    from typing import TypeVar

    T = TypeVar('T')


class PrintInput(Enum):
    KORE_JSON = 'kore-json'
    KAST_JSON = 'kast-json'


def generate_command_options(args: dict[str, Any]) -> LoggingOptions:
    command = args['command'].lower()
    match command:
        case 'print':
            return PrintOptions(args)
        case 'rpc-print':
            return RPCPrintOptions(args)
        case 'rpc-kast':
            return RPCKastOptions(args)
        case 'prove':
            return ProveOptions(args)
        case 'graph-imports':
            return GraphImportsOptions(args)
        case 'coverage':
            return CoverageOptions(args)
        case 'kore-to-json':
            return KoreToJsonOptions(args)
        case 'json-to-kore':
            return JsonToKoreOptions(args)
        case _:
            raise ValueError('Unrecognized command.')


class Options(object):
    def __init__(self, args: dict[str, Any]) -> None:
        # Get defaults from this and all superclasses that define them, preferring the most specific class
        defaults: dict[str, Any] = {}
        mro = type(self).mro()
        mro.reverse()
        for cl in mro:
            if hasattr(cl, 'default'):
                defaults = defaults | cl.default()

        # Overwrite defaults with args from command line
        _args = defaults | args

        for attr, val in _args.items():
            self.__setattr__(attr, val)

    @classmethod
    def all_args(cls: Type[Options]) -> ArgumentParser:
        # Collect args from this and all superclasses
        parser = ArgumentParser(add_help=False)
        mro = set(cls.mro())
        for cl in mro:
            if hasattr(cl, 'args') and 'args' in cl.__dict__:
                parser = cl.args(parser)
        return parser


class LoggingOptions(Options):
    debug: bool
    verbose: bool

    @staticmethod
    def default() -> dict[str, Any]:
        return {
            'verbose': False,
            'debug': False,
        }

    @staticmethod
    def args(parser: ArgumentParser) -> ArgumentParser:
        parser.add_argument('--verbose', '-v', default=None, action='store_true', help='Verbose output.')
        parser.add_argument('--debug', default=None, action='store_true', help='Debug output.')
        return parser


class JsonToKoreOptions(LoggingOptions):
    @staticmethod
    def parser(base: _SubParsersAction) -> _SubParsersAction:
        base.add_parser(
            'json-to-kore',
            help='Convert JSON to textual KORE',
            parents=[JsonToKoreOptions.all_args()],
        )
        return base


class KoreToJsonOptions(LoggingOptions):
    @staticmethod
    def parser(base: _SubParsersAction) -> _SubParsersAction:
        base.add_parser(
            'kore-to-json',
            help='Convert textual KORE to JSON',
            parents=[KoreToJsonOptions.all_args()],
        )
        return base


class OutputFileOptions(Options):
    output_file: IO[Any]

    @staticmethod
    def default() -> dict[str, Any]:
        return {
            'output_file': sys.stdout,
        }

    @staticmethod
    def args(parser: ArgumentParser) -> ArgumentParser:
        parser.add_argument('--output-file', type=FileType('w'), default=None)
        return parser


class DefinitionOptions(LoggingOptions):
    definition_dir: Path

    @staticmethod
    def args(parser: ArgumentParser) -> ArgumentParser:
        parser.add_argument('definition_dir', type=dir_path, help='Path to definition directory.')
        return parser


class CoverageOptions(DefinitionOptions, OutputFileOptions):
    coverage_file: IO[Any]

    @staticmethod
    def parser(base: _SubParsersAction) -> _SubParsersAction:
        base.add_parser(
            'coverage',
            help='Convert coverage file to human readable log.',
            parents=[CoverageOptions.all_args()],
        )
        return base

    @staticmethod
    def args(parser: ArgumentParser) -> ArgumentParser:
        parser.add_argument('coverage_file', type=FileType('r'), help='Coverage file to build log for.')
        return parser


class GraphImportsOptions(DefinitionOptions):
    @staticmethod
    def parser(base: _SubParsersAction) -> _SubParsersAction:
        base.add_parser(
            'graph-imports',
            help='Graph the imports of a given definition.',
            parents=[GraphImportsOptions.all_args()],
        )
        return base


class RPCKastOptions(DefinitionOptions, OutputFileOptions):
    reference_request_file: IO[Any]
    response_file: IO[Any]

    @staticmethod
    def parser(base: _SubParsersAction) -> _SubParsersAction:
        base.add_parser(
            'rpc-kast',
            help='Convert an "execute" JSON RPC response to a new "execute" or "simplify" request, copying parameters from a reference request.',
            parents=[RPCKastOptions.all_args()],
        )
        return base

    @staticmethod
    def args(parser: ArgumentParser) -> ArgumentParser:
        parser.add_argument(
            'reference_request_file',
            type=FileType('r'),
            help='An input file containing a JSON RPC request to server as a reference for the new request.',
        )
        parser.add_argument(
            'response_file',
            type=FileType('r'),
            help='An input file containing a JSON RPC response with KoreJSON payload.',
        )
        return parser


class RPCPrintOptions(DefinitionOptions, OutputFileOptions):
    input_file: IO[Any]

    @staticmethod
    def parser(base: _SubParsersAction) -> _SubParsersAction:
        base.add_parser(
            'rpc-print',
            help='Pretty-print an RPC request/response',
            parents=[RPCPrintOptions.all_args()],
        )
        return base

    @staticmethod
    def args(parser: ArgumentParser) -> ArgumentParser:
        parser.add_argument(
            'input_file',
            type=FileType('r'),
            help='An input file containing the JSON RPC request or response with KoreJSON payload.',
        )
        return parser


class DisplayOptions(Options):
    @staticmethod
    def args(parser: ArgumentParser) -> ArgumentParser:
        parser.add_argument('--minimize', dest='minimize', default=None, action='store_true', help='Minimize output.')
        parser.add_argument('--no-minimize', dest='minimize', action='store_false', help='Do not minimize output.')
        return parser


class PrintOptions(DefinitionOptions, OutputFileOptions, DisplayOptions):
    term: IO[Any]
    input: PrintInput
    minimize: bool
    omit_labels: str | None
    keep_cells: str | None

    @staticmethod
    def default() -> dict[str, Any]:
        return {
            'input': PrintInput.KAST_JSON,
            'minimize': True,
            'omit_labels': None,
            'keep_cells': None,
        }

    @staticmethod
    def args(parser: ArgumentParser) -> ArgumentParser:
        parser.add_argument(
            'term', type=FileType('r'), help='File containing input term (in format specified with --input).'
        )
        parser.add_argument('--input', default=None, type=PrintInput, choices=list(PrintInput))
        parser.add_argument('--omit-labels', default=None, nargs='?', help='List of labels to omit from output.')
        parser.add_argument(
            '--keep-cells', default=None, nargs='?', help='List of cells with primitive values to keep in output.'
        )
        return parser

    @staticmethod
    def parser(base: _SubParsersAction) -> _SubParsersAction:
        base.add_parser(
            'print',
            help='Pretty print a term.',
            parents=[PrintOptions.all_args()],
        )
        return base


class ProveOptions(DefinitionOptions, OutputFileOptions):
    main_file: Path
    spec_file: Path
    spec_module: str
    k_args: Iterable[str]

    @staticmethod
    def args(parser: ArgumentParser) -> ArgumentParser:
        parser.add_argument('main_file', type=str, help='Main file used for kompilation.')
        parser.add_argument('spec_file', type=str, help='File with the specification module.')
        parser.add_argument('spec_module', type=str, help='Module with claims to be proven.')
        parser.add_argument('k_args', nargs='*', help='Arguments to pass through to K invocation.')
        return parser

    @staticmethod
    def parser(base: _SubParsersAction) -> _SubParsersAction:
        base.add_parser(
            'prove',
            help='Prove an input specification (using kprovex).',
            parents=[ProveOptions.all_args()],
        )
        return base


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
