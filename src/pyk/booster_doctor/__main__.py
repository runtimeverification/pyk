from __future__ import annotations

import json
import logging
import re
import sys
import tarfile
import tempfile
from argparse import ArgumentParser
from dataclasses import dataclass
from pathlib import Path, PurePath
from typing import TYPE_CHECKING, Optional, final

from ..cli.utils import dir_path, file_path
from ..coverage import get_rule_by_id
from ..cterm import CTerm
from ..kast.outer import KAtt
from ..kcfg.kcfg import build_claim
from ..kore.rpc import LogFallback
from ..ktool.kprint import KPrint

if TYPE_CHECKING:
    from typing import Final, Iterable

    from ..kast.outer import KClaim, KDefinition

_LOGGER: Final = logging.getLogger(__name__)
_LOG_FORMAT: Final = '%(levelname)s %(name)s - %(message)s'


def main() -> None:
    sys.setrecursionlimit(10**7)

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

    if args.input_file.suffix in ['.tar', '.gz']:
        process_bug_report(args.input_file, args.definition_dir)
    else:
        assert args.input_file.suffix == '.json'
        try:
            assert args.definition_dir
        except AssertionError:
            _LOGGER.error('Please provide path to kompiled definition with --definition-dir')
            exit(1)
        process_single_response(definition_dir=args.definition_dir, response_file=args.input_file)


@final
@dataclass(frozen=True)
class KCalimWithComment:
    claim: KClaim
    comment: Iterable[str]


def process_single_response(definition_dir: Path, response_file: Path) -> Optional[dict[str, KCalimWithComment]]:
    """
    Process a single JSON response of the `kore-rpc-booster`'s exectute endpoint.
    Generate 'KClaim's and human-readable description of `kore-rpc-booster`'s abort and recovery.
    """
    kprint = KPrint(definition_dir)

    _LOGGER.info(f'Processing {response_file}')
    response_dict = json.loads(response_file.read_text())
    if not ('result' in response_dict and 'logs' in response_dict['result']):
        _LOGGER.warning(f'{response_file.name} does not contain logs, skipping')
        return None
    fallback_logs_in_reponse = parse_fallback_logs_from_response(response_dict)

    fallback_claims = {}
    claim_counter = 1  # better use Depth, need to add it to response
    for fallback_log in fallback_logs_in_reponse:
        fallback_info = extract_basic_fallback_info(kprint.definition, fallback_log)
        claim_id = f'{response_file.stem}-{claim_counter}'
        fallback_claims[f'{claim_id}'] = KCalimWithComment(
            claim=build_fallback_claim(kprint, fallback_log, claim_id), comment=fallback_info
        )
        claim_counter += 1
        _LOGGER.info(f'Generated claim {claim_id}')

    return None


def process_bug_report(bug_report: Path, definition_dir: Optional[Path] = None, keep_going: bool = True) -> None:
    """
    Process a 'bug_report.tar'.

    For every exectute endpoin response, generate 'KClaim's and human-readable description of `kore-rpc-booster`'s abort and recovery.

    Use definition.kore suppleid with the bug_report.tar, unless an explicit override definition_dir is provided.
    """
    assert definition_dir, 'Plese supply definiton_dir, as we cannot for now produce it from bug_repor .tar.gz'

    def extract_rpc_id(filename: str) -> str:
        pattern = re.compile(r'(\d*)[\_](?:response|request)\.json')
        return re.findall(pattern, filename)[0]

    def match_rpc_request_method_execute(json_str: str) -> bool:
        pattern = re.compile(r'"method"\s*:\s*"execute"')
        return len(re.findall(pattern, json_str)) == 1

    def match_rpc_request_filename(fname: str) -> bool:
        return PurePath(fname).match('rpc_*/*_request.json')

    def match_rpc_response_filename(fname: str, request_ids: set[str]) -> bool:
        fpath = PurePath(fname)
        return fpath.match('rpc_*/*_response.json') and extract_rpc_id(fpath.name) in request_ids

    execute_responses: dict[str, dict[str, KCalimWithComment]] = {}

    with tarfile.open(bug_report, 'r') as bug_report_archive, tempfile.TemporaryDirectory() as tmpdirname:
        rpc_requests = [member for member in bug_report_archive.getmembers() if match_rpc_request_filename(member.name)]

        execute_request_ids = set()
        for request_tarinfo in rpc_requests:
            try:
                bug_report_archive.extract(member=request_tarinfo, path=tmpdirname)
                json_str = (tmpdirname / Path(request_tarinfo.name)).read_text()
                if match_rpc_request_method_execute(json_str):
                    _LOGGER.info(f'Found execute request {request_tarinfo.name}')
                    print(PurePath(request_tarinfo.name).name)
                    execute_request_ids.add(extract_rpc_id(PurePath(request_tarinfo.name).name))
            except Exception as e:
                _LOGGER.error(f'Error extracting {request_tarinfo.name} from {bug_report.name}, skipping.')
                raise e

        rpc_responses = [
            member
            for member in bug_report_archive.getmembers()
            if match_rpc_response_filename(member.name, execute_request_ids)
        ]
        for response_tarinfo in rpc_responses:
            try:
                bug_report_archive.extract(member=response_tarinfo, path=tmpdirname)
                response_file = tmpdirname / Path(response_tarinfo.name)
            except Exception as e:
                if not keep_going:
                    raise e
                _LOGGER.error(f'Error extracting {response_tarinfo.name} from {bug_report.name}, skipping.')
                continue
            fallback_claims = process_single_response(definition_dir=definition_dir, response_file=response_file)
            if fallback_claims is not None:
                execute_responses[response_tarinfo.name] = fallback_claims


def parse_fallback_logs_from_response(response_dict: dict) -> Iterable[LogFallback]:
    """Filter all "fallback" log entries and parse them into LogFallback objects"""
    for log_entry_dict in response_dict['result']['logs']:
        if log_entry_dict['tag'] == 'fallback':
            yield LogFallback.from_dict(log_entry_dict)


def extract_basic_fallback_info(kdef: KDefinition, fallback_log_entry: LogFallback) -> Iterable[str]:
    fallback_rule_msg = f'Booster Abort due to {fallback_log_entry.fallback_rule_id}'
    try:
        fallback_rule = get_rule_by_id(kdef, fallback_log_entry.fallback_rule_id)
    except ValueError as e:
        _LOGGER.warning(str(e))
        fallback_rule = None
    if fallback_rule is not None:
        fallback_rule = get_rule_by_id(kdef, fallback_log_entry.fallback_rule_id)
        fallback_rule_source = fallback_rule.att.atts[KAtt.SOURCE]
        fallback_rule_location = fallback_rule.att.atts[KAtt.LOCATION]
        fallback_rule_label = fallback_rule.att.atts['label']
        fallback_rule_msg = f'Booster Abort due to rule {fallback_rule_label} at {fallback_rule_source}:{_location_tuple_to_str(fallback_rule_location)}'
    yield fallback_rule_msg

    if fallback_log_entry.recovery_rule_ids:
        recovery_rules_info = []
        for rule_id in fallback_log_entry.recovery_rule_ids:
            recovery_rule = get_rule_by_id(kdef, rule_id)
            recovery_rule_source = recovery_rule.att.atts[KAtt.SOURCE]
            recovery_rule_location = recovery_rule.att.atts[KAtt.LOCATION]
            recovery_rule_label = recovery_rule.att.atts['label']
            recovery_rules_info.append(
                f'{recovery_rule_label} at {recovery_rule_source}:{_location_tuple_to_str(recovery_rule_location)}'
            )
        recovery_rule_msg = f'Recovery in Kore using rules {recovery_rules_info}'
        yield recovery_rule_msg


def build_fallback_claim(kprint: KPrint, fallback_log_entry: LogFallback, claim_id: str | None = None) -> KClaim:
    if claim_id is None:
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
