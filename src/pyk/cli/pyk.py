from __future__ import annotations

import logging
from argparse import ArgumentParser, FileType
from enum import Enum
from typing import IO, TYPE_CHECKING, Any

import tomli

from pyk.ktool.kompile import KompileBackend

from ..ktool import TypeInferenceMode
from .args import (
    ConfigArgs,
    DefinitionOptions,
    DisplayOptions,
    KCLIArgs,
    KDefinitionOptions,
    KompileOptions,
    LoggingOptions,
    OutputFileOptions,
)
from .utils import dir_path, file_path

if TYPE_CHECKING:
    from argparse import Namespace
    from collections.abc import Iterable
    from pathlib import Path
    from typing import Final


_LOGGER: Final = logging.getLogger(__name__)


def generate_options(args: dict[str, Any]) -> LoggingOptions:
    command = args['command']
    match command:
        case 'json-to-kore':
            return JsonToKoreOptions(args)
        case 'kore-to-json':
            return KoreToJsonOptions(args)
        case 'coverage':
            return CoverageOptions(args)
        case 'graph-imports':
            return GraphImportsOptions(args)
        case 'rpc-kast':
            return RPCKastOptions(args)
        case 'rpc-print':
            return RPCPrintOptions(args)
        case 'print':
            return PrintOptions(args)
        case 'prove-legacy':
            return ProveLegacyOptions(args)
        case 'prove':
            return ProveOptions(args)
        case 'kompile':
            return KompileCommandOptions(args)
        case 'run':
            return RunOptions(args)
        case _:
            raise ValueError(f'Unrecognized command: {command}')


def get_option_string_destination(command: str, option_string: str) -> str:
    option_string_destinations = {}
    match command:
        case 'json-to-kore':
            option_string_destinations = JsonToKoreOptions.from_option_string()
        case 'kore-to-json':
            option_string_destinations = KoreToJsonOptions.from_option_string()
        case 'coverage':
            option_string_destinations = CoverageOptions.from_option_string()
        case 'graph-imports':
            option_string_destinations = GraphImportsOptions.from_option_string()
        case 'rpc-kast':
            option_string_destinations = RPCKastOptions.from_option_string()
        case 'rpc-print':
            option_string_destinations = RPCPrintOptions.from_option_string()
        case 'print':
            option_string_destinations = PrintOptions.from_option_string()
        case 'prove-legacy':
            option_string_destinations = ProveLegacyOptions.from_option_string()
        case 'prove':
            option_string_destinations = ProveOptions.from_option_string()
        case 'kompile':
            option_string_destinations = KompileCommandOptions.from_option_string()
        case 'run':
            option_string_destinations = RunOptions.from_option_string()

    if option_string in option_string_destinations:
        return option_string_destinations[option_string]
    else:
        return option_string.replace('-', '_')


class PrintInput(Enum):
    KORE_JSON = 'kore-json'
    KAST_JSON = 'kast-json'


class JsonToKoreOptions(LoggingOptions):
    ...


class KoreToJsonOptions(LoggingOptions):
    ...


class CoverageOptions(DefinitionOptions, OutputFileOptions, LoggingOptions):
    coverage_file: IO[Any]

    @staticmethod
    def from_option_string() -> dict[str, str]:
        return (
            DefinitionOptions.from_option_string()
            | OutputFileOptions.from_option_string()
            | LoggingOptions.from_option_string()
        )


class GraphImportsOptions(DefinitionOptions, LoggingOptions):
    @staticmethod
    def from_option_string() -> dict[str, str]:
        return DefinitionOptions.from_option_string() | LoggingOptions.from_option_string()


class RPCKastOptions(OutputFileOptions, LoggingOptions):
    reference_request_file: IO[Any]
    response_file: IO[Any]

    @staticmethod
    def from_option_string() -> dict[str, str]:
        return OutputFileOptions.from_option_string() | LoggingOptions.from_option_string()


class RPCPrintOptions(DefinitionOptions, OutputFileOptions, LoggingOptions):
    input_file: IO[Any]

    @staticmethod
    def from_option_string() -> dict[str, str]:
        return (
            DefinitionOptions.from_option_string()
            | OutputFileOptions.from_option_string()
            | LoggingOptions.from_option_string()
        )


class PrintOptions(DefinitionOptions, OutputFileOptions, DisplayOptions, LoggingOptions):
    term: IO[Any]
    input: PrintInput
    minimize: bool
    omit_labels: str | None
    keep_cells: str | None

    @staticmethod
    def default() -> dict[str, Any]:
        return {
            'input': PrintInput.KAST_JSON,
            'omit_labels': None,
            'keep_cells': None,
        }

    @staticmethod
    def from_option_string() -> dict[str, str]:
        return (
            DefinitionOptions.from_option_string()
            | OutputFileOptions.from_option_string()
            | DisplayOptions.from_option_string()
            | LoggingOptions.from_option_string()
        )


class ProveLegacyOptions(DefinitionOptions, OutputFileOptions, LoggingOptions):
    main_file: Path
    spec_file: Path
    spec_module: str
    k_args: Iterable[str]

    @staticmethod
    def default() -> dict[str, Any]:
        return {
            'k_args': [],
        }

    @staticmethod
    def from_option_string() -> dict[str, str]:
        return (
            DefinitionOptions.from_option_string()
            | OutputFileOptions.from_option_string()
            | LoggingOptions.from_option_string()
            | {'kArgs': 'k_args'}
        )


class KompileCommandOptions(LoggingOptions, KDefinitionOptions, KompileOptions):
    definition_dir: Path | None
    main_file: str
    backend: KompileBackend
    type_inference_mode: TypeInferenceMode | None

    @staticmethod
    def default() -> dict[str, Any]:
        return {
            'definition_dir': None,
            'backend': KompileBackend.LLVM,
            'type_inference_mode': None,
        }

    @staticmethod
    def from_option_string() -> dict[str, str]:
        return (
            KDefinitionOptions.from_option_string()
            | KompileOptions.from_option_string()
            | LoggingOptions.from_option_string()
            | {'definition': 'definition_dir'}
        )


class ProveOptions(LoggingOptions):
    spec_file: Path
    definition_dir: Path | None
    spec_module: str | None
    type_inference_mode: TypeInferenceMode | None
    failure_info: bool

    @staticmethod
    def default() -> dict[str, Any]:
        return {
            'definition_dir': None,
            'spec_module': None,
            'type_inference_mode': None,
            'failure_info': False,
        }

    @staticmethod
    def from_option_string() -> dict[str, str]:
        return (
            KDefinitionOptions.from_option_string()
            | KompileOptions.from_option_string()
            | LoggingOptions.from_option_string()
            | {'definition': 'definition_dir'}
        )


class RunOptions(LoggingOptions):
    pgm_file: str
    definition_dir: Path | None

    @staticmethod
    def default() -> dict[str, Any]:
        return {
            'definition_dir': None,
        }


def create_argument_parser() -> ArgumentParser:
    k_cli_args = KCLIArgs()
    config_args = ConfigArgs()

    pyk_args = ArgumentParser()
    pyk_args_command = pyk_args.add_subparsers(dest='command', required=True)

    print_args = pyk_args_command.add_parser(
        'print',
        help='Pretty print a term.',
        parents=[k_cli_args.logging_args, k_cli_args.display_args, config_args.config_args],
    )
    print_args.add_argument('definition_dir', type=dir_path, help='Path to definition directory.')
    print_args.add_argument('term', type=FileType('r'), help='Input term (in format specified with --input).')
    print_args.add_argument('--input', type=PrintInput, choices=list(PrintInput))
    print_args.add_argument('--omit-labels', nargs='?', help='List of labels to omit from output.')
    print_args.add_argument('--keep-cells', nargs='?', help='List of cells with primitive values to keep in output.')
    print_args.add_argument('--output-file', type=FileType('w'))

    rpc_print_args = pyk_args_command.add_parser(
        'rpc-print',
        help='Pretty-print an RPC request/response',
        parents=[k_cli_args.logging_args, config_args.config_args],
    )
    rpc_print_args.add_argument('definition_dir', type=dir_path, help='Path to definition directory.')
    rpc_print_args.add_argument(
        'input_file',
        type=FileType('r'),
        help='An input file containing the JSON RPC request or response with KoreJSON payload.',
    )
    rpc_print_args.add_argument('--output-file', type=FileType('w'))

    rpc_kast_args = pyk_args_command.add_parser(
        'rpc-kast',
        help='Convert an "execute" JSON RPC response to a new "execute" or "simplify" request, copying parameters from a reference request.',
        parents=[k_cli_args.logging_args, config_args.config_args],
    )
    rpc_kast_args.add_argument(
        'reference_request_file',
        type=FileType('r'),
        help='An input file containing a JSON RPC request to server as a reference for the new request.',
    )
    rpc_kast_args.add_argument(
        'response_file',
        type=FileType('r'),
        help='An input file containing a JSON RPC response with KoreJSON payload.',
    )
    rpc_kast_args.add_argument('--output-file', type=FileType('w'))

    prove_legacy_args = pyk_args_command.add_parser(
        'prove-legacy',
        help='Prove an input specification (using kprovex).',
        parents=[k_cli_args.logging_args, config_args.config_args],
    )
    prove_legacy_args.add_argument('definition_dir', type=dir_path, help='Path to definition directory.')
    prove_legacy_args.add_argument('main_file', type=str, help='Main file used for kompilation.')
    prove_legacy_args.add_argument('spec_file', type=str, help='File with the specification module.')
    prove_legacy_args.add_argument('spec_module', type=str, help='Module with claims to be proven.')
    prove_legacy_args.add_argument('--output-file', type=FileType('w'))
    prove_legacy_args.add_argument('kArgs', nargs='*', help='Arguments to pass through to K invocation.')

    kompile_args = pyk_args_command.add_parser(
        'kompile',
        help='Kompile the K specification.',
        parents=[k_cli_args.logging_args, k_cli_args.definition_args, k_cli_args.kompile_args, config_args.config_args],
    )
    kompile_args.add_argument('main_file', type=str, help='File with the specification module.')

    run_args = pyk_args_command.add_parser(
        'run',
        help='Run a given program using the K definition.',
        parents=[k_cli_args.logging_args, config_args.config_args],
    )
    run_args.add_argument('pgm_file', type=str, help='File program to run in it.')
    run_args.add_argument('--definition', type=dir_path, dest='definition_dir', help='Path to definition to use.')

    prove_args = pyk_args_command.add_parser(
        'prove',
        help='Prove an input specification (using RPC based prover).',
        parents=[k_cli_args.logging_args, config_args.config_args],
    )
    prove_args.add_argument('spec_file', type=file_path, help='File with the specification module.')
    prove_args.add_argument('--definition', type=dir_path, dest='definition_dir', help='Path to definition to use.')
    prove_args.add_argument('--spec-module', dest='spec_module', type=str, help='Module with claims to be proven.')
    prove_args.add_argument(
        '--type-inference-mode', type=TypeInferenceMode, help='Mode for doing K rule type inference in.'
    )
    prove_args.add_argument(
        '--failure-info',
        default=None,
        action='store_true',
        help='Print out more information about proof failures.',
    )

    graph_imports_args = pyk_args_command.add_parser(
        'graph-imports',
        help='Graph the imports of a given definition.',
        parents=[k_cli_args.logging_args, config_args.config_args],
    )
    graph_imports_args.add_argument('definition_dir', type=dir_path, help='Path to definition directory.')

    coverage_args = pyk_args_command.add_parser(
        'coverage',
        help='Convert coverage file to human readable log.',
        parents=[k_cli_args.logging_args, config_args.config_args],
    )
    coverage_args.add_argument('definition_dir', type=dir_path, help='Path to definition directory.')
    coverage_args.add_argument('coverage_file', type=FileType('r'), help='Coverage file to build log for.')
    coverage_args.add_argument('-o', '--output', type=FileType('w'))

    pyk_args_command.add_parser(
        'kore-to-json', help='Convert textual KORE to JSON', parents=[k_cli_args.logging_args, config_args.config_args]
    )

    pyk_args_command.add_parser(
        'json-to-kore', help='Convert JSON to textual KORE', parents=[k_cli_args.logging_args, config_args.config_args]
    )

    return pyk_args


def parse_toml_args(args: Namespace) -> dict[str, Any | Iterable]:
    def get_profile(toml_profile: dict[str, Any], profile_list: list[str]) -> dict[str, Any]:
        if len(profile_list) == 0 or profile_list[0] not in toml_profile:
            return {k: v for k, v in toml_profile.items() if type(v) is not dict}
        elif len(profile_list) == 1:
            return {k: v for k, v in toml_profile[profile_list[0]].items() if type(v) is not dict}
        return get_profile(toml_profile[profile_list[0]], profile_list[1:])

    toml_args = {}
    if args.config_file.is_file():
        with open(args.config_file, 'rb') as config_file:
            try:
                toml_args = tomli.load(config_file)
            except tomli.TOMLDecodeError:
                _LOGGER.error(
                    'Input config file is not in TOML format, ignoring the file and carrying on with the provided command line agruments'
                )

    toml_args = (
        get_profile(toml_args[args.command], args.config_profile.split('.')) if args.command in toml_args else {}
    )
    toml_args = {get_option_string_destination(args.command, k): v for k, v in toml_args.items()}
    for k, v in toml_args.items():
        if k[:3] == 'no-' and (v == 'true' or v == 'false'):
            del toml_args[k]
            toml_args[k[3:]] = 'false' if v == 'true' else 'true'
        if k == 'optimization-level':
            level = toml_args[k] if toml_args[k] >= 0 else 0
            level = level if toml_args[k] <= 3 else 3
            del toml_args[k]
            toml_args['-o' + str(level)] = 'true'

    return toml_args
