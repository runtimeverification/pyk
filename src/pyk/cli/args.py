from __future__ import annotations

import json
import sys
from abc import abstractmethod
from argparse import ArgumentParser, FileType
from enum import Enum
from pathlib import Path
from typing import IO, TYPE_CHECKING, Any

from graphviz import Digraph

from pyk.coverage import get_rule_by_id, strip_coverage_logger
from pyk.cterm import CTerm
from pyk.kast.inner import KInner
from pyk.kast.manip import (
    flatten_label,
    minimize_rule,
    minimize_term,
    propagate_up_constraints,
    remove_source_map,
    split_config_and_constraints,
)
from pyk.kast.outer import read_kast_definition
from pyk.kast.pretty import PrettyPrinter
from pyk.kore.parser import KoreParser
from pyk.kore.rpc import ExecuteResult, StopReason
from pyk.kore.syntax import Pattern, kore_term
from pyk.ktool.kprint import KPrint
from pyk.ktool.kprove import KProve
from pyk.prelude.k import GENERATED_TOP_CELL
from pyk.prelude.ml import is_top, mlAnd, mlOr
from pyk.utils import _LOGGER, ensure_dir_path

from .utils import bug_report_arg, dir_path, file_path

if TYPE_CHECKING:
    from argparse import _SubParsersAction
    from collections.abc import Iterable
    from typing import TypeVar

    from ..utils import BugReport

    T = TypeVar('T')


class PrintInput(Enum):
    KORE_JSON = 'kore-json'
    KAST_JSON = 'kast-json'


class CLI:
    commands: list[type[Command]]

    # Input a list of all Command types to be used
    def __init__(self, commands: Iterable[type[Command]]):
        self.commands = list(commands)

    # Return an instance of the correct Options subclass by matching its name with the requested command
    def generate_command(self, args: dict[str, Any]) -> Command:
        command = args['command'].lower()
        for cmd_type in self.commands:
            if cmd_type.name() == command:
                return cmd_type(args)
        raise ValueError(f'Unrecognized command: {command}')

    # Generate the parsers for all commands
    def add_parsers(self, base: _SubParsersAction) -> _SubParsersAction:
        for cmd_type in self.commands:
            base = cmd_type.parser(base)
        return base

    def create_argument_parser(self) -> ArgumentParser:
        pyk_args = ArgumentParser()
        pyk_args_command = pyk_args.add_subparsers(dest='command', required=True)

        pyk_args_command = self.add_parsers(pyk_args_command)

        return pyk_args


class Options:
    def __init__(self, args: dict[str, Any]) -> None:
        # Get defaults from this and all superclasses that define them, preferring the most specific class
        defaults: dict[str, Any] = {}
        for cl in reversed(type(self).mro()):
            if hasattr(cl, 'default'):
                defaults = defaults | cl.default()

        # Overwrite defaults with args from command line
        _args = defaults | args

        for attr, val in _args.items():
            self.__setattr__(attr, val)

    @classmethod
    def all_args(cls: type[Options]) -> ArgumentParser:
        # Collect args from this and all superclasses
        parser = ArgumentParser(add_help=False)
        mro = cls.mro()
        mro.reverse()
        for cl in mro:
            if hasattr(cl, 'update_args') and 'update_args' in cl.__dict__:
                cl.update_args(parser)
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
    def update_args(parser: ArgumentParser) -> None:
        parser.add_argument('--verbose', '-v', action='store_true', help='Verbose output.')
        parser.add_argument('--debug', action='store_true', help='Debug output.')


class Command(LoggingOptions):
    @staticmethod
    @abstractmethod
    def name() -> str:
        ...

    @staticmethod
    @abstractmethod
    def help_str() -> str:
        ...

    @abstractmethod
    def exec(self) -> None:
        ...

    @classmethod
    def parser(cls, base: _SubParsersAction) -> _SubParsersAction:
        base.add_parser(
            name=cls.name(),
            help=cls.help_str(),
            parents=[cls.all_args()],
        )
        return base


class JsonToKoreOptions(Command):
    @staticmethod
    def name() -> str:
        return 'json-to-kore'

    @staticmethod
    def help_str() -> str:
        return 'Convert JSON to textual KORE'

    def exec(self) -> None:
        text = sys.stdin.read()
        kore = Pattern.from_json(text)
        kore.write(sys.stdout)
        sys.stdout.write('\n')


class KoreToJsonOptions(Command):
    @staticmethod
    def name() -> str:
        return 'kore-to-json'

    @staticmethod
    def help_str() -> str:
        return 'Convert textual KORE to JSON'

    def exec(self) -> None:
        text = sys.stdin.read()
        kore = KoreParser(text).pattern()
        print(kore.json)


class OutputFileOptions(Options):
    output_file: IO[Any]

    @staticmethod
    def default() -> dict[str, Any]:
        return {
            'output_file': sys.stdout,
        }

    @staticmethod
    def update_args(parser: ArgumentParser) -> None:
        parser.add_argument('--output-file', type=FileType('w'))


class DefinitionOptions(LoggingOptions):
    definition_dir: Path

    @staticmethod
    def update_args(parser: ArgumentParser) -> None:
        parser.add_argument('definition_dir', type=dir_path, help='Path to definition directory.')


class CoverageOptions(Command, DefinitionOptions, OutputFileOptions):
    coverage_file: IO[Any]

    @staticmethod
    def name() -> str:
        return 'coverage'

    @staticmethod
    def help_str() -> str:
        return 'Convert coverage file to human readable log.'

    @staticmethod
    def update_args(parser: ArgumentParser) -> None:
        parser.add_argument('coverage_file', type=FileType('r'), help='Coverage file to build log for.')

    def exec(self) -> None:
        kompiled_dir: Path = self.definition_dir
        definition = remove_source_map(read_kast_definition(kompiled_dir / 'compiled.json'))
        pretty_printer = PrettyPrinter(definition)
        for rid in self.coverage_file:
            rule = minimize_rule(strip_coverage_logger(get_rule_by_id(definition, rid.strip())))
            self.output_file.write('\n\n')
            self.output_file.write('Rule: ' + rid.strip())
            self.output_file.write('\nUnparsed:\n')
            self.output_file.write(pretty_printer.print(rule))
        _LOGGER.info(f'Wrote file: {self.output_file.name}')


class GraphImportsOptions(Command, DefinitionOptions):
    @staticmethod
    def name() -> str:
        return 'graph-imports'

    @staticmethod
    def help_str() -> str:
        return 'Graph the imports of a given definition.'

    def exec(self) -> None:
        kompiled_dir: Path = self.definition_dir
        kprinter = KPrint(kompiled_dir)
        definition = kprinter.definition
        import_graph = Digraph()
        graph_file = kompiled_dir / 'import-graph'
        for module in definition.modules:
            module_name = module.name
            import_graph.node(module_name)
            for module_import in module.imports:
                import_graph.edge(module_name, module_import.name)
        import_graph.render(graph_file)
        _LOGGER.info(f'Wrote file: {graph_file}')


class RPCKastOptions(Command, OutputFileOptions):
    reference_request_file: IO[Any]
    response_file: IO[Any]

    @staticmethod
    def name() -> str:
        return 'rpc-kast'

    @staticmethod
    def help_str() -> str:
        return 'Convert an "execute" JSON RPC response to a new "execute" or "simplify" request, copying parameters from a reference request.'

    @staticmethod
    def update_args(parser: ArgumentParser) -> None:
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

    def exec(self) -> None:
        """
        Convert an 'execute' JSON RPC response to a new 'execute' or 'simplify' request,
        copying parameters from a reference request.
        """
        reference_request = json.loads(self.reference_request_file.read())
        input_dict = json.loads(self.response_file.read())
        execute_result = ExecuteResult.from_dict(input_dict['result'])
        non_state_keys = set(reference_request['params'].keys()).difference(['state'])
        request_params = {}
        for key in non_state_keys:
            request_params[key] = reference_request['params'][key]
        request_params['state'] = {'format': 'KORE', 'version': 1, 'term': execute_result.state.kore.dict}
        request = {
            'jsonrpc': reference_request['jsonrpc'],
            'id': reference_request['id'],
            'method': reference_request['method'],
            'params': request_params,
        }
        self.output_file.write(json.dumps(request))


class RPCPrintOptions(Command, DefinitionOptions, OutputFileOptions):
    input_file: IO[Any]

    @staticmethod
    def name() -> str:
        return 'rpc-print'

    @staticmethod
    def help_str() -> str:
        return 'Pretty-print an RPC request/response'

    @staticmethod
    def update_args(parser: ArgumentParser) -> None:
        parser.add_argument(
            'input_file',
            type=FileType('r'),
            help='An input file containing the JSON RPC request or response with KoreJSON payload.',
        )

    def exec(self) -> None:
        kompiled_dir: Path = self.definition_dir
        printer = KPrint(kompiled_dir)
        input_dict = json.loads(self.input_file.read())
        output_buffer = []

        def pretty_print_request(request_params: dict[str, Any]) -> list[str]:
            output_buffer = []
            non_state_keys = set(request_params.keys()).difference(['state'])
            for key in non_state_keys:
                output_buffer.append(f'{key}: {request_params[key]}')
            state = CTerm.from_kast(printer.kore_to_kast(kore_term(request_params['state'])))
            output_buffer.append('State:')
            output_buffer.append(printer.pretty_print(state.kast, sort_collections=True))
            return output_buffer

        def pretty_print_execute_response(execute_result: ExecuteResult) -> list[str]:
            output_buffer = []
            output_buffer.append(f'Depth: {execute_result.depth}')
            output_buffer.append(f'Stop reason: {execute_result.reason.value}')
            if execute_result.reason == StopReason.TERMINAL_RULE or execute_result.reason == StopReason.CUT_POINT_RULE:
                output_buffer.append(f'Stop rule: {execute_result.rule}')
            output_buffer.append(
                f'Number of next states: {len(execute_result.next_states) if execute_result.next_states is not None else 0}'
            )
            state = CTerm.from_kast(printer.kore_to_kast(execute_result.state.kore))
            output_buffer.append('State:')
            output_buffer.append(printer.pretty_print(state.kast, sort_collections=True))
            if execute_result.next_states is not None:
                next_states = [CTerm.from_kast(printer.kore_to_kast(s.kore)) for s in execute_result.next_states]
                for i, s in enumerate(next_states):
                    output_buffer.append(f'Next state #{i}:')
                    output_buffer.append(printer.pretty_print(s.kast, sort_collections=True))
            return output_buffer

        try:
            if 'method' in input_dict:
                output_buffer.append('JSON RPC request')
                output_buffer.append(f'id: {input_dict["id"]}')
                output_buffer.append(f'Method: {input_dict["method"]}')
                try:
                    if 'state' in input_dict['params']:
                        output_buffer += pretty_print_request(input_dict['params'])
                    else:  # this is an "add-module" request, skip trying to print state
                        for key in input_dict['params'].keys():
                            output_buffer.append(f'{key}: {input_dict["params"][key]}')
                except KeyError as e:
                    _LOGGER.critical(f'Could not find key {str(e)} in input JSON file')
                    exit(1)
            else:
                if not 'result' in input_dict:
                    _LOGGER.critical('The input is neither a request not a resonse')
                    exit(1)
                output_buffer.append('JSON RPC Response')
                output_buffer.append(f'id: {input_dict["id"]}')
                if list(input_dict['result'].keys()) == ['state']:  # this is a "simplify" response
                    output_buffer.append('Method: simplify')
                    state = CTerm.from_kast(printer.kore_to_kast(kore_term(input_dict['result']['state'])))
                    output_buffer.append('State:')
                    output_buffer.append(printer.pretty_print(state.kast, sort_collections=True))
                elif list(input_dict['result'].keys()) == ['module']:  # this is an "add-module" response
                    output_buffer.append('Method: add-module')
                    output_buffer.append('Module:')
                    output_buffer.append(input_dict['result']['module'])
                else:
                    try:  # assume it is an "execute" response
                        output_buffer.append('Method: execute')
                        execute_result = ExecuteResult.from_dict(input_dict['result'])
                        output_buffer += pretty_print_execute_response(execute_result)
                    except KeyError as e:
                        _LOGGER.critical(f'Could not find key {str(e)} in input JSON file')
                        exit(1)
            if self.output_file is not None:
                self.output_file.write('\n'.join(output_buffer))
            else:
                print('\n'.join(output_buffer))
        except ValueError as e:
            # shorten and print the error message in case kore_to_kast throws ValueError
            _LOGGER.critical(str(e)[:200])
            exit(1)


class DisplayOptions(Options):
    minimize: bool

    @staticmethod
    def default() -> dict[str, Any]:
        return {
            'minimize': True,
        }

    @staticmethod
    def update_args(parser: ArgumentParser) -> None:
        parser.add_argument('--minimize', dest='minimize', action='store_true', help='Minimize output.')
        parser.add_argument('--no-minimize', dest='minimize', action='store_false', help='Do not minimize output.')


class PrintOptions(Command, DefinitionOptions, OutputFileOptions, DisplayOptions):
    term: IO[Any]
    input: PrintInput
    minimize: bool
    omit_labels: str | None
    keep_cells: str | None

    @staticmethod
    def name() -> str:
        return 'print'

    @staticmethod
    def help_str() -> str:
        return 'Pretty print a term.'

    @staticmethod
    def default() -> dict[str, Any]:
        return {
            'input': PrintInput.KAST_JSON,
            'omit_labels': None,
            'keep_cells': None,
        }

    @staticmethod
    def update_args(parser: ArgumentParser) -> None:
        parser.add_argument(
            'term', type=FileType('r'), help='File containing input term (in format specified with --input).'
        )
        parser.add_argument('--input', type=PrintInput, choices=list(PrintInput))
        parser.add_argument('--omit-labels', nargs='?', help='List of labels to omit from output.')
        parser.add_argument('--keep-cells', nargs='?', help='List of cells with primitive values to keep in output.')

    def exec(self) -> None:
        kompiled_dir: Path = self.definition_dir
        printer = KPrint(kompiled_dir)
        if self.input == PrintInput.KORE_JSON:
            _LOGGER.info(f'Reading Kore JSON from file: {self.term.name}')
            kore = Pattern.from_json(self.term.read())
            term = printer.kore_to_kast(kore)
        else:
            _LOGGER.info(f'Reading Kast JSON from file: {self.term.name}')
            term = KInner.from_json(self.term.read())
        if is_top(term):
            self.output_file.write(printer.pretty_print(term))
            _LOGGER.info(f'Wrote file: {self.output_file.name}')
        else:
            if self.minimize:
                if self.omit_labels != None and self.keep_cells != None:
                    raise ValueError('You cannot use both --omit-labels and --keep-cells.')

                abstract_labels = self.omit_labels.split(',') if self.omit_labels is not None else []
                keep_cells = self.keep_cells.split(',') if self.keep_cells is not None else []
                minimized_disjuncts = []

                for disjunct in flatten_label('#Or', term):
                    try:
                        minimized = minimize_term(disjunct, abstract_labels=abstract_labels, keep_cells=keep_cells)
                        config, constraint = split_config_and_constraints(minimized)
                    except ValueError as err:
                        raise ValueError('The minimized term does not contain a config cell.') from err

                    if not is_top(constraint):
                        minimized_disjuncts.append(mlAnd([config, constraint], sort=GENERATED_TOP_CELL))
                    else:
                        minimized_disjuncts.append(config)
                term = propagate_up_constraints(mlOr(minimized_disjuncts, sort=GENERATED_TOP_CELL))

            self.output_file.write(printer.pretty_print(term))
            _LOGGER.info(f'Wrote file: {self.output_file.name}')


class ProveOptions(Command, DefinitionOptions, OutputFileOptions):
    main_file: Path
    spec_file: Path
    spec_module: str
    k_args: Iterable[str]

    @staticmethod
    def name() -> str:
        return 'prove'

    @staticmethod
    def help_str() -> str:
        return 'Prove an input specification (using kprovex).'

    @staticmethod
    def update_args(parser: ArgumentParser) -> None:
        parser.add_argument('main_file', type=str, help='Main file used for kompilation.')
        parser.add_argument('spec_file', type=str, help='File with the specification module.')
        parser.add_argument('spec_module', type=str, help='Module with claims to be proven.')
        parser.add_argument('k_args', nargs='*', help='Arguments to pass through to K invocation.')

    def exec(self) -> None:
        kompiled_dir: Path = self.definition_dir
        kprover = KProve(kompiled_dir, self.main_file)
        final_state = kprover.prove(Path(self.spec_file), spec_module_name=self.spec_module, args=self.k_args)
        self.output_file.write(json.dumps(mlOr([state.kast for state in final_state]).to_dict()))
        _LOGGER.info(f'Wrote file: {self.output_file.name}')


class KDefinitionOptions(Options):
    includes: list[str]
    main_module: str | None
    syntax_module: str | None
    spec_module: str | None
    definition_dir: Path | None
    md_selector: str

    @staticmethod
    def default() -> dict[str, Any]:
        return {
            'spec_module': None,
            'main_module': None,
            'syntax_module': None,
            'definition_dir': None,
            'md_selector': 'k',
            'includes': [],
        }

    @staticmethod
    def update_args(parser: ArgumentParser) -> None:
        parser.add_argument(
            '-I', type=str, dest='includes', action='append', help='Directories to lookup K definitions in.'
        )
        parser.add_argument('--main-module', type=str, help='Name of the main module.')
        parser.add_argument('--syntax-module', type=str, help='Name of the syntax module.')
        parser.add_argument('--spec-module', type=str, help='Name of the spec module.')
        parser.add_argument('--definition', type=dir_path, dest='definition_dir', help='Path to definition to use.')
        parser.add_argument(
            '--md-selector',
            type=str,
            help='Code selector expression to use when reading markdown.',
        )


class SaveDirOptions(Options):
    save_directory: Path | None

    @staticmethod
    def default() -> dict[str, Any]:
        return {
            'save_directory': None,
        }

    @staticmethod
    def update_args(parser: ArgumentParser) -> None:
        parser.add_argument('--save-directory', type=ensure_dir_path, help='Path to where CFGs are stored.')


class SpecOptions(SaveDirOptions):
    spec_file: Path
    claim_labels: list[str] | None
    exclude_claim_labels: list[str]

    @staticmethod
    def default() -> dict[str, Any]:
        return {
            'claim_labels': None,
            'exclude_claim_labels': [],
        }

    @staticmethod
    def update_args(parser: ArgumentParser) -> None:
        parser.add_argument('spec_file', type=file_path, help='Path to spec file.')
        parser.add_argument(
            '--claim',
            type=str,
            dest='claim_labels',
            action='append',
            help='Only prove listed claims, MODULE_NAME.claim-id',
        )
        parser.add_argument(
            '--exclude-claim',
            type=str,
            dest='exclude_claim_labels',
            action='append',
            help='Skip listed claims, MODULE_NAME.claim-id',
        )


class KompileOptions(Options):
    emit_json: bool
    ccopts: list[str]
    llvm_kompile: bool
    llvm_library: bool
    enable_llvm_debug: bool
    read_only: bool
    o0: bool
    o1: bool
    o2: bool
    o3: bool

    @staticmethod
    def default() -> dict[str, Any]:
        return {
            'emit_json': True,
            'llvm_kompile': False,
            'llvm_library': False,
            'enable_llvm_debug': False,
            'read_only': False,
            'o0': False,
            'o1': False,
            'o2': False,
            'o3': False,
            'ccopt': [],
        }

    @staticmethod
    def update_args(parser: ArgumentParser) -> None:
        parser.add_argument(
            '--emit-json',
            dest='emit_json',
            action='store_true',
            help='Emit JSON definition after compilation.',
        )
        parser.add_argument(
            '--no-emit-json', dest='emit_json', action='store_false', help='Do not JSON definition after compilation.'
        )
        parser.add_argument(
            '-ccopt',
            dest='ccopts',
            action='append',
            help='Additional arguments to pass to llvm-kompile.',
        )
        parser.add_argument(
            '--no-llvm-kompile',
            dest='llvm_kompile',
            action='store_false',
            help='Do not run llvm-kompile process.',
        )
        parser.add_argument(
            '--with-llvm-library',
            dest='llvm_library',
            action='store_true',
            help='Make kompile generate a dynamic llvm library.',
        )
        parser.add_argument(
            '--enable-llvm-debug',
            dest='enable_llvm_debug',
            action='store_true',
            help='Make kompile generate debug symbols for llvm.',
        )
        parser.add_argument(
            '--read-only-kompiled-directory',
            dest='read_only',
            action='store_true',
            help='Generated a kompiled directory that K will not attempt to write to afterwards.',
        )
        parser.add_argument('-O0', dest='o0', action='store_true', help='Optimization level 0.')
        parser.add_argument('-O1', dest='o1', action='store_true', help='Optimization level 1.')
        parser.add_argument('-O2', dest='o2', action='store_true', help='Optimization level 2.')
        parser.add_argument('-O3', dest='o3', action='store_true', help='Optimization level 3.')


class ParallelOptions(Options):
    workers: int

    @staticmethod
    def default() -> dict[str, Any]:
        return {
            'workers': 1,
        }

    @staticmethod
    def update_args(parser: ArgumentParser) -> None:
        parser.add_argument('--workers', '-j', type=int, help='Number of processes to run in parallel.')


class BugReportOptions(Options):
    bug_report: BugReport | None

    @staticmethod
    def default() -> dict[str, Any]:
        return {'bug_report': None}

    @staticmethod
    def update_args(parser: ArgumentParser) -> None:
        parser.add_argument(
            '--bug-report',
            type=bug_report_arg,
            help='Generate bug report with given name',
        )


class SMTOptions(Options):
    smt_timeout: int
    smt_retry_limit: int
    smt_tactic: str | None

    @staticmethod
    def default() -> dict[str, Any]:
        return {
            'smt_timeout': 300,
            'smt_retry_limit': 10,
            'smt_tactic': None,
        }

    @staticmethod
    def update_args(parser: ArgumentParser) -> None:
        parser.add_argument('--smt-timeout', dest='smt_timeout', type=int, help='Timeout in ms to use for SMT queries.')
        parser.add_argument(
            '--smt-retry-limit',
            dest='smt_retry_limit',
            type=int,
            help='Number of times to retry SMT queries with scaling timeouts.',
        )
        parser.add_argument(
            '--smt-tactic',
            dest='smt_tactic',
            type=str,
            help='Z3 tactic to use when checking satisfiability. Example: (check-sat-using smt)',
        )
