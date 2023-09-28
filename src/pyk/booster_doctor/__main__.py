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
from ..kast.outer import KAtt, KFlatModule
from ..kcfg.kcfg import build_claim
from ..kore.rpc import LogFallback
from ..ktool.kprint import KPrint

if TYPE_CHECKING:
    from argparse import Namespace
    from typing import Final, Iterable

    from ..kast.outer import KClaim, KDefinition

_LOGGER: Final = logging.getLogger(__name__)
_LOG_FORMAT: Final = '%(levelname)s %(name)s - %(message)s'


def describe_session(args: Namespace) -> None:
    """Give a human-readable explanation of runtime parameters"""
    session_info = []
    if args.definition_dir:
        session_info.append(f'I will use the kompiled definition from {args.definition_dir}')
    if args.input_file:
        session_info.append(f'I will look for RPC execute responses in {args.input_file}')
    if args.build_claims:
        session_info.append('I will build K claims from found RPC execute responses')
        if args.output_dir:
            session_info.append(f'I will store K claims in {args.output_dir}')
    else:
        session_info.append('I will not build any K claims (give --build-claims option to do so)')

    for s in session_info:
        _LOGGER.info(s)


def configure_logging(args: Namespace) -> None:
    level = logging.INFO if args.verbose else logging.WARNING
    pyk_kast_logger = logging.getLogger('pyk.kast')
    pyk_kprint_logger = logging.getLogger('pyk.ktool.kprint')
    if args.verbose > 1:
        pyk_kast_logger.level = logging.INFO
        pyk_kast_logger.level = logging.INFO
        pyk_kprint_logger.level = logging.INFO
    else:
        pyk_kast_logger.level = logging.WARNING
        pyk_kast_logger.level = logging.WARNING
        pyk_kprint_logger.level = logging.WARNING

    logging.basicConfig(level=level, format=_LOG_FORMAT)


def main() -> None:
    sys.setrecursionlimit(10**7)

    args = _argument_parser().parse_args()

    configure_logging(args)
    describe_session(args)

    kprint = KPrint(args.definition_dir)

    if args.input_file.suffix in ['.tar', '.gz']:
        process_bug_report(
            kprint=kprint,
            bug_report=args.input_file,
            build_claims=args.build_claims,
            output_dir=args.output_dir,
        )
    else:
        assert args.input_file.suffix == '.json'
        process_single_response(kprint=kprint, response_file=args.input_file)


@final
@dataclass(frozen=True)
class KClaimWithComment:
    claim: KClaim | None
    comment: Iterable[str]


def process_single_response(
    kprint: KPrint, response_file: Path, build_claims: bool = False
) -> Optional[dict[str, KClaimWithComment]]:
    """
    Process a single JSON response of the `kore-rpc-booster`'s exectute endpoint.
    Generate 'KClaim's and human-readable description of `kore-rpc-booster`'s abort and recovery.
    """
    _LOGGER.info(f'Processing {response_file}')
    response_dict = json.loads(response_file.read_text())
    if not ('result' in response_dict and 'logs' in response_dict['result']):
        _LOGGER.warning(f'{response_file.name} does not contain logs, skipping')
        return None
    fallback_logs_in_reponse = list(parse_fallback_logs_from_response(response_dict))
    _LOGGER.info(f'Found {len(fallback_logs_in_reponse)} fallback logs')

    fallback_claims = {}
    claim_counter = 1  # TODO: better use Depth, need to add it to RPC response
    for fallback_log in fallback_logs_in_reponse:
        fallback_info = extract_basic_fallback_info(kprint.definition, fallback_log)
        claim_id = f'{response_file.stem}-{claim_counter}'
        if build_claims:
            claim = build_fallback_claim(kprint, fallback_log, claim_id)
            if claim is not None:
                _LOGGER.info(f'Generated claim {claim_id}')
            fallback_claims[f'{claim_id}'] = KClaimWithComment(claim=claim, comment=fallback_info)
        else:
            fallback_claims[f'{claim_id}'] = KClaimWithComment(claim=None, comment=fallback_info)
        claim_counter += 1
    return fallback_claims


def process_bug_report(
    bug_report: Path,
    kprint: KPrint,
    build_claims: bool = False,
    output_dir: Optional[Path] = None,
    keep_going: bool = True,
) -> None:
    """
    Process a 'bug_report.tar'.

    For every execute endpoin response, generate 'KClaim's and human-readable description of `kore-rpc-booster`'s abort and recovery.

    Use definition.kore suppleid with the bug_report.tar, unless an explicit override definition_dir is provided.
    """

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

    execute_responses: dict[str, dict[str, KClaimWithComment]] = {}

    with tarfile.open(bug_report, 'r') as bug_report_archive, tempfile.TemporaryDirectory() as tmpdirname:
        rpc_requests = [member for member in bug_report_archive.getmembers() if match_rpc_request_filename(member.name)]

        execute_request_ids = set()
        for request_tarinfo in rpc_requests:
            try:
                bug_report_archive.extract(member=request_tarinfo, path=tmpdirname)
                json_str = (tmpdirname / Path(request_tarinfo.name)).read_text()
                if match_rpc_request_method_execute(json_str):
                    _LOGGER.info(f'Found execute request {request_tarinfo.name}')
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
            fallback_claims = process_single_response(
                kprint=kprint, response_file=response_file, build_claims=build_claims
            )
            if fallback_claims is not None:
                fallback_claim_module_name = f'{bug_report.name}-{response_tarinfo.name}'
                if output_dir is None:
                    _LOGGER.warning(f'No --output-dir given, writing claims to {tmpdirname}')
                    fallback_claim_module_path = tmpdirname / Path(f'{fallback_claim_module_name}.k')
                else:
                    fallback_claim_module_path = output_dir / Path(f'{fallback_claim_module_name}.k')
                execute_responses[response_tarinfo.name] = fallback_claims
                fallback_claim_module_sentenses = []
                fallback_claim_module_toplevel_description = []
                for claim_id, claim_with_comment in fallback_claims.items():
                    fallback_reason = ' '.join(claim_with_comment.comment)
                    if claim_with_comment.claim is not None:
                        fallback_claim_module_sentenses.append(claim_with_comment.claim)
                        fallback_claim_module_toplevel_description.append(
                            f'// Claim {claim_id} describes: {fallback_reason}'
                        )
                fallback_claim_module_name = str(fallback_claim_module_path).replace('/', '_').replace('.', '_').upper()
                fallback_claims_module = KFlatModule(
                    name=fallback_claim_module_name, sentences=tuple(fallback_claim_module_sentenses)
                )
                if build_claims:
                    _LOGGER.info(f'Writing claims to file {str(fallback_claim_module_path)}')
                    fallback_claim_module_path.parent.mkdir(exist_ok=True, parents=True)
                    fallback_claim_module_path.write_text(
                        '\n'.join(
                            [
                                *fallback_claim_module_toplevel_description,
                                kprint.pretty_print(fallback_claims_module),
                            ]
                        )
                    )


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
        fallback_rule_label = fallback_rule.att.atts['label'] if 'label' in fallback_rule.att.atts else 'NOLABEL'
        fallback_rule_msg = f'Booster Abort due to rule {fallback_rule_label} at {fallback_rule_source}:{_location_tuple_to_str(fallback_rule_location)} with reason: {fallback_log_entry.reason}'
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


def build_fallback_claim(kprint: KPrint, fallback_log_entry: LogFallback, claim_id: str | None = None) -> KClaim | None:
    """
    Given a LogFallback RPC log entry, build the K Claim that reproduces it
    """
    if claim_id is None:
        claim_id = 'booster-fallback'
    if fallback_log_entry.original_term is None:
        _LOGGER.error(f'Cannot build K Claim {claim_id} Fallback entry does not the contain "origianl-term" field')
        return None
    if fallback_log_entry.rewritten_term is None:
        _LOGGER.error(f'Cannot build K Claim {claim_id} Fallback entry does not the contain "rewritten-term" field')
        return None
    lhs = CTerm.from_kast(kprint.kore_to_kast(fallback_log_entry.original_term))
    if fallback_log_entry.rewritten_term is None:
        _LOGGER.error(f'Cannot build K Claim {claim_id} Fallback entry does not the contain "rewritten-term" field')
        return None
    rhs = CTerm.from_kast(kprint.kore_to_kast(fallback_log_entry.rewritten_term))
    claim, _ = build_claim(claim_id=claim_id, init_cterm=lhs, final_cterm=rhs)
    return claim


def _location_tuple_to_str(location: tuple[int, int, int, int]) -> str:
    start_line, start_col, end_line, end_col = location
    return f'{start_line}:{start_col}-{end_line}:{end_col}'


def _argument_parser() -> ArgumentParser:
    parser = ArgumentParser(description='Analyze kore-rpc-booster fallback logs and convert them to K claims.')
    parser.add_argument(
        '--definition-dir',
        type=dir_path,
        required=True,
        help='path to kompiled definition to use',
    )
    parser.add_argument('--verbose', '-v', action='count', default=0)
    parser.add_argument('--build-claims', action='store_true', help='build claims from fallback logs')
    parser.add_argument('--output-dir', type=dir_path, help='path to output directory')
    parser.add_argument(
        'input_file', type=file_path, help='path to a bug report archive or a single response JSON file to analyze'
    )

    return parser


if __name__ == '__main__':
    main()
