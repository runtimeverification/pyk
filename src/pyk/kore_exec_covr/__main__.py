import logging
import re
from argparse import ArgumentParser
from enum import Enum
from pathlib import Path
from typing import Any, Dict, Final, Tuple

import coloredlogs  # type: ignore

from pyk.kast.kast import KAtt
from pyk.kast.outer import KDefinition, KRule, read_kast_definition
from pyk.ktool.kprint import build_symbol_table, pretty_print_kast

from ..cli_utils import dir_path, file_path

_LOG_FORMAT: Final = '%(levelname)s %(name)s - %(message)s'
_LOGGER: Final = logging.getLogger(__name__)

haskell_log_entry_regexp = r'kore-exec: \[\d*\] Debug \(([a-zA-Z]*)\): (.*)'


class HaskellLogEntry(Enum):
    DebugApplyEquation = 'DebugApplyEquation'
    DebugAppliedRewriteRules = 'DebugAppliedRewriteRules'


def do_analyze(definition_dir: Path, input_file: Path, **kwargs: Any) -> None:
    """
    Inputs:
       * definition compiled with "kompile --backend haskell --emit-json"
       * Log file produced with "KORE_EXEC_OPTS='--log-format oneline --log-entries DebugAppliedRewriteRules,DebugApplyEquation'"

    Outputs:
       * human-readable report of applied rewrite and simplification rules,
         with labels (if declared) and locations
    """
    definition = read_kast_definition(definition_dir / 'compiled.json')

    _LOGGER.info(f'Discovering rewrite and simplification rules in {definition_dir}')
    rule_dict = build_rule_dict(definition)

    rewrites: Dict[str, int] = {key: 0 for key, rule in rule_dict.items() if not 'simplification' in rule.att.atts}
    simplifications: Dict[str, int] = {key: 0 for key, rule in rule_dict.items() if 'simplification' in rule.att.atts}
    _LOGGER.info(f'    Found {len(rewrites)} rewrite rules')
    _LOGGER.info(f'    Found {len(simplifications)} simplification rules')

    log_entries = input_file.read_text().splitlines()
    for log_entry in log_entries:
        entry_type, location_str = parse_haskell_one_line_log(log_entry)
        # TODO: the haskell backend log files often contain items with no location. it is not clear to me what happens.
        if location_str:
            try:
                if entry_type == HaskellLogEntry.DebugAppliedRewriteRules:
                    rewrites[location_str] += 1
                elif entry_type == HaskellLogEntry.DebugApplyEquation:
                    simplifications[location_str] += 1
            except KeyError:
                _LOGGER.warning(f'unknown rule location: {location_str}')

    print('=================================')
    print('=== REWRITES ====================')
    print('=================================')
    for location_str, hits in rewrites.items():
        rule_label_str = ''
        if 'label' in rule_dict[location_str].att.atts:
            rule_label_str = f'[{rule_dict[location_str].att.atts["label"]}]'
        if hits > 0:
            print(f'    {hits} applications of rule {rule_label_str} defined at {location_str}')
    total_rewrites = sum([v for v in rewrites.values() if v > 0])
    print(f'Total rewrites: {total_rewrites}')

    print('=================================')
    print('=== SIMPLIFICATIONS =============')
    print('=================================')
    for location_str, hits in simplifications.items():
        rule_label_str = ''
        if 'label' in rule_dict[location_str].att.atts:
            rule_label_str = f'[{rule_dict[location_str].att.atts["label"]}]'
        if hits > 0:
            print(f'    {hits} applications of rule {rule_label_str} defined at {location_str}')
    total_simplifications = sum([v for v in simplifications.values() if v > 0])
    print(f'Total simplifications: {total_simplifications}')


def location_tuple_to_str(location: Tuple[int, int, int, int]) -> str:
    start_line, start_col, end_line, end_col = location
    return f'{start_line}:{start_col}-{end_line}:{end_col}'


def parse_haskell_one_line_log(log_entry: str) -> Tuple[HaskellLogEntry, str]:
    """Attempt to parse a one-line log string emmitted by K's Haskell backend"""
    matches = re.match(haskell_log_entry_regexp, log_entry)
    try:
        assert matches
        entry = matches.groups()[0]
        location_str = matches.groups()[1].strip()
        return HaskellLogEntry(entry), location_str
    except (AssertionError, KeyError, ValueError) as err:
        _LOGGER.error(f'failed to parse log entry: {log_entry}')
        raise err


def build_rule_dict(
    definition: KDefinition, skip_projections: bool = True, skip_initializers: bool = True
) -> Dict[str, KRule]:
    """
    Traverse the kompiled definition and build a dictionary mapping str(file:location) to KRule
    """
    symbol_table = build_symbol_table(definition)

    rule_dict: Dict[str, KRule] = {}

    for rule in definition.rules:
        if skip_projections and 'projection' in rule.att.atts:
            continue
        if skip_initializers and 'initializer' in rule.att.atts:
            continue
        try:
            rule_source = rule.att.atts[KAtt.SOURCE]
            rule_location = rule.att.atts[KAtt.LOCATION]
        except KeyError:
            _LOGGER.warning(
                'Skipping rule with no location information {msg:.50}...<truncated>'.format(
                    msg=str(pretty_print_kast(rule.body, symbol_table))
                )
            )
            rule_source = None
            rule_location = None
            continue
        if rule_source and rule_location:
            rule_dict[f'{rule_source}:{location_tuple_to_str(rule_location)}'] = rule
        else:
            raise ValueError(pretty_print_kast(rule.body, symbol_table))

    return rule_dict


def main() -> None:
    coloredlogs.install(fmt=_LOG_FORMAT)
    args = vars(_argument_parser().parse_args())

    if args['quiet']:
        logging.basicConfig(level=logging.ERROR, format=_LOG_FORMAT)
    else:
        logging.basicConfig(level=logging.INFO, format=_LOG_FORMAT)

    return do_analyze(**args)


def _argument_parser() -> ArgumentParser:
    parser = ArgumentParser(description='Symbolic execution logs analysis tool')
    parser.add_argument(
        '--definition-dir',
        dest='definition_dir',
        type=dir_path,
        help='Path to Haskell-kompiled definition to use.',
    )
    parser.add_argument('--quiet', action='store_true', help='Be quiet and do not output warnings')
    parser.add_argument('input_file', type=file_path, help='path to kore-exec log file to analyze')

    return parser


if __name__ == '__main__':
    main()
