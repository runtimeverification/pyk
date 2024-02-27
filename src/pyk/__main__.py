from __future__ import annotations

import json
import logging
import sys
from argparse import ArgumentParser
from pathlib import Path
from typing import TYPE_CHECKING

from graphviz import Digraph

from pyk.kast.inner import KInner
from pyk.kore.rpc import ExecuteResult

from .cli.args import (
    CoverageOptions,
    GraphImportsOptions,
    JsonToKoreOptions,
    KoreToJsonOptions,
    PrintInput,
    PrintOptions,
    ProveOptions,
    RPCKastOptions,
    RPCPrintOptions,
    generate_command_options,
)
from .cli.utils import LOG_FORMAT, dir_path, loglevel
from .coverage import get_rule_by_id, strip_coverage_logger
from .cterm import CTerm
from .kast.manip import (
    flatten_label,
    minimize_rule,
    minimize_term,
    propagate_up_constraints,
    remove_source_map,
    split_config_and_constraints,
)
from .kast.outer import read_kast_definition
from .kast.pretty import PrettyPrinter
from .kore.parser import KoreParser
from .kore.rpc import StopReason
from .kore.syntax import Pattern, kore_term
from .ktool.kprint import KPrint
from .ktool.kprove import KProve
from .prelude.k import GENERATED_TOP_CELL
from .prelude.ml import is_top, mlAnd, mlOr

if TYPE_CHECKING:
    from typing import Any, Final


_LOGGER: Final = logging.getLogger(__name__)


def main() -> None:
    # KAST terms can end up nested quite deeply, because of the various assoc operators (eg. _Map_, _Set_, ...).
    # Most pyk operations are defined recursively, meaning you get a callstack the same depth as the term.
    # This change makes it so that in most cases, by default, pyk doesn't run out of stack space.
    sys.setrecursionlimit(10**7)

    cli_parser = create_argument_parser()
    args = cli_parser.parse_args()

    options = generate_command_options({key: val for (key, val) in vars(args).items() if val is not None})

    logging.basicConfig(level=loglevel(options), format=LOG_FORMAT)

    executor_name = 'exec_' + args.command.lower().replace('-', '_')
    if executor_name not in globals():
        raise AssertionError(f'Unimplemented command: {args.command}')

    execute = globals()[executor_name]
    execute(options)


def exec_print(options: PrintOptions) -> None:
    kompiled_dir: Path = options.definition_dir
    printer = KPrint(kompiled_dir)
    if options.input == PrintInput.KORE_JSON:
        _LOGGER.info(f'Reading Kore JSON from file: {options.term.name}')
        kore = Pattern.from_json(options.term.read())
        term = printer.kore_to_kast(kore)
    else:
        _LOGGER.info(f'Reading Kast JSON from file: {options.term.name}')
        term = KInner.from_json(options.term.read())
    if is_top(term):
        options.output_file.write(printer.pretty_print(term))
        _LOGGER.info(f'Wrote file: {options.output_file.name}')
    else:
        if options.minimize:
            if options.omit_labels != None and options.keep_cells != None:
                raise ValueError('You cannot use both --omit-labels and --keep-cells.')

            abstract_labels = options.omit_labels.split(',') if options.omit_labels is not None else []
            keep_cells = options.keep_cells.split(',') if options.keep_cells is not None else []
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

        options.output_file.write(printer.pretty_print(term))
        _LOGGER.info(f'Wrote file: {options.output_file.name}')


def exec_rpc_print(options: RPCPrintOptions) -> None:
    kompiled_dir: Path = options.definition_dir
    printer = KPrint(kompiled_dir)
    input_dict = json.loads(options.input_file.read())
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
        if options.output_file is not None:
            options.output_file.write('\n'.join(output_buffer))
        else:
            print('\n'.join(output_buffer))
    except ValueError as e:
        # shorten and print the error message in case kore_to_kast throws ValueError
        _LOGGER.critical(str(e)[:200])
        exit(1)


def exec_rpc_kast(options: RPCKastOptions) -> None:
    """
    Convert an 'execute' JSON RPC response to a new 'execute' or 'simplify' request,
    copying parameters from a reference request.
    """
    reference_request = json.loads(options.reference_request_file.read())
    input_dict = json.loads(options.response_file.read())
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
    options.output_file.write(json.dumps(request))


def exec_prove(options: ProveOptions) -> None:
    kompiled_dir: Path = options.definition_dir
    kprover = KProve(kompiled_dir, options.main_file)
    final_state = kprover.prove(Path(options.spec_file), spec_module_name=options.spec_module, args=options.k_args)
    options.output_file.write(json.dumps(mlOr([state.kast for state in final_state]).to_dict()))
    _LOGGER.info(f'Wrote file: {options.output_file.name}')


def exec_graph_imports(options: GraphImportsOptions) -> None:
    kompiled_dir: Path = options.definition_dir
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


def exec_coverage(options: CoverageOptions) -> None:
    kompiled_dir: Path = options.definition_dir
    definition = remove_source_map(read_kast_definition(kompiled_dir / 'compiled.json'))
    pretty_printer = PrettyPrinter(definition)
    for rid in options.coverage_file:
        rule = minimize_rule(strip_coverage_logger(get_rule_by_id(definition, rid.strip())))
        options.output_file.write('\n\n')
        options.output_file.write('Rule: ' + rid.strip())
        options.output_file.write('\nUnparsed:\n')
        options.output_file.write(pretty_printer.print(rule))
    _LOGGER.info(f'Wrote file: {options.output_file.name}')


def exec_kore_to_json(options: KoreToJsonOptions) -> None:
    text = sys.stdin.read()
    kore = KoreParser(text).pattern()
    print(kore.json)


def exec_json_to_kore(options: JsonToKoreOptions) -> None:
    text = sys.stdin.read()
    kore = Pattern.from_json(text)
    kore.write(sys.stdout)
    sys.stdout.write('\n')


def create_argument_parser() -> ArgumentParser:
    definition_args = ArgumentParser(add_help=False)
    definition_args.add_argument('definition_dir', type=dir_path, help='Path to definition directory.')

    pyk_args = ArgumentParser()
    pyk_args_command = pyk_args.add_subparsers(dest='command', required=True)

    pyk_args_command = PrintOptions.parser(pyk_args_command)
    pyk_args_command = RPCPrintOptions.parser(pyk_args_command)
    pyk_args_command = RPCKastOptions.parser(pyk_args_command)
    pyk_args_command = ProveOptions.parser(pyk_args_command)
    pyk_args_command = GraphImportsOptions.parser(pyk_args_command)
    pyk_args_command = CoverageOptions.parser(pyk_args_command)
    pyk_args_command = KoreToJsonOptions.parser(pyk_args_command)
    pyk_args_command = JsonToKoreOptions.parser(pyk_args_command)

    return pyk_args


if __name__ == '__main__':
    main()
