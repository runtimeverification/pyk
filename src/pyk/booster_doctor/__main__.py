from __future__ import annotations

import logging
from argparse import ArgumentParser
from typing import TYPE_CHECKING
import tarfile
import json

from ..cli.utils import dir_path, file_path
from ..ktool.kprint import KPrint
from ..kcfg.kcfg import build_claim
from ..cterm import CTerm
from ..kast.outer import read_kast_definition, KDefinition, KClaim, KAtt
from ..kore.rpc import LogEntry, LogFallback
from ..coverage import get_rule_by_id

if TYPE_CHECKING:
    from pathlib import Path
    from typing import Iterable, Final

_LOGGER: Final = logging.getLogger(__name__)
_LOG_FORMAT: Final = '%(levelname)s %(name)s - %(message)s'


def main() -> None:
    args = _argument_parser().parse_args()

    level = logging.INFO if args.verbose else logging.WARNING
    pyk_kast_logger = logging.getLogger('pyk.kast')
    pyk_kprint_logger = logging.getLogger('pyk.ktool.kprint')
    if args.pyk_verbose:
        pyk_kast_logger.level = logging.INFO
        pyk_kast_logger.level = logging.INFO
        pyk_kprint_logger.level = logging.INFO
    else:
        pyk_kast_logger.level = logging.WARNING
        pyk_kast_logger.level = logging.WARNING
        pyk_kprint_logger.level = logging.WARNING

    logging.basicConfig(level=level, format=_LOG_FORMAT)

    if args.input_file.suffix == '.tar':
        process_bug_report()
    else:
        assert args.input_file.suffix == '.json'
        try:
            assert args.definition_dir
        except AssertionError:
            _LOGGER.error('Please provide path to kompiled definition with --definition-dir')
            exit(1)
        process_single_response(definition_dir=args.definition_dir, response_file=args.input_file, build_claims=False)


def process_single_response(definition_dir: Path, response_file: Path, build_claims: bool) -> None:
    kprint = KPrint(definition_dir)

    _LOGGER.info(f'Processing {response_file}')
    fallback_logs_in_reponse = parse_fallback_logs_from_response(json.loads(response_file.read_text()))

    for fallback_log in fallback_logs_in_reponse:
        fallback_info = extract_basic_fallback_info(kprint.definition, fallback_log)
        for info_str in fallback_info:
            print(info_str)
        if build_claims:
            fallback_claim = build_fallback_claim(kprint, fallback_log)
            print(kprint.pretty_print(fallback_claim))


def process_bug_report() -> None:
    pass


def parse_fallback_logs_from_response(response_dict) -> Iterable[LogFallback]:
    '''Filter all "fallback" log entries and parse them into LogFallback objects'''
    for log_entry_dict in response_dict['result']['logs']:
        if log_entry_dict['tag'] == 'fallback':
            yield LogFallback.from_dict(log_entry_dict)


def extract_basic_fallback_info(kdef: KDefinition, fallback_log_entry: LogFallback) -> Iterable[str]:
    fallback_rule_msg = 'Booster Abort'
    if fallback_log_entry.fallback_rule_id:
        fallback_rule = get_rule_by_id(kdef, fallback_log_entry.fallback_rule_id)
        fallback_rule_source = fallback_rule.att.atts[KAtt.SOURCE]
        fallback_rule_location = fallback_rule.att.atts[KAtt.LOCATION]
        fallback_rule_label = fallback_rule.att.atts['label']
        fallback_rule_msg = f'Booster Abort due to rule {fallback_rule_label} at {fallback_rule_source}:{_location_tuple_to_str(fallback_rule_location)}'
    yield fallback_rule_msg

    if fallback_log_entry.recovery_rule_ids:
        pass


def build_fallback_claim(kprint: KPrint, fallback_log_entry: LogFallback) -> KClaim:
    claim_id = 'booster-fallback'
    assert fallback_log_entry.original_term
    lhs = CTerm.from_kast(kprint.kore_to_kast(fallback_log_entry.original_term))
    assert fallback_log_entry.rewritten_term
    rhs = CTerm.from_kast(kprint.kore_to_kast(fallback_log_entry.rewritten_term))
    claim, _ = build_claim(claim_id=claim_id, init_cterm=lhs, final_cterm=rhs)
    return claim


def _location_tuple_to_str(location: tuple[int, int, int, int]) -> str:
    start_line, start_col, end_line, end_col = location
    return f'{start_line}:{start_col}-{end_line}:{end_col}'


def _argument_parser() -> ArgumentParser:
    parser = ArgumentParser(description='Symbolic execution logs analysis tool')
    parser.add_argument(
        '--definition-dir',
        type=dir_path,
        help='Path to Haskell-kompiled definition to use.',
    )
    parser.add_argument('--verbose', action='store_true')
    parser.add_argument('--pyk-verbose', action='store_true')
    parser.add_argument('--build-claims', action='store_true', help='build claims from fallback logs')
    parser.add_argument('--no-build-claims', action='store_false', help='do not build claims from fallback logs')
    # parser.add_argument('input_file', type=file_path, help='path to bug_report.tar to analyze')
    parser.add_argument('input_file', type=file_path, help='path to bug_report.tar or response.json to analyze')

    return parser


if __name__ == '__main__':
    main()
