import json
import logging
import os
from enum import Enum
from itertools import chain
from pathlib import Path
from subprocess import CalledProcessError, CompletedProcess
from typing import Any, ContextManager, Dict, Final, Iterable, List, Mapping, Optional, Tuple

from ..cli_utils import check_dir_path, check_file_path, gen_file_timestamp, run_process
from ..cterm import CTerm, build_claim
from ..kast.inner import KApply, KInner, KLabel, Subst
from ..kast.manip import extract_subst, flatten_label, free_vars
from ..kast.outer import KClaim, KDefinition, KFlatModule, KImport, KRequire, KRule, KSentence, KVariable
from ..kore.rpc import KoreClient, KoreServer
from ..kore.syntax import Top
from ..prelude.k import GENERATED_TOP_CELL
from ..prelude.ml import is_top, mlAnd, mlBottom, mlEquals, mlTop
from ..utils import unique
from .kprint import KPrint

_LOGGER: Final = logging.getLogger(__name__)


class KProveOutput(Enum):
    PRETTY = 'pretty'
    PROGAM = 'program'
    KAST = 'KAST'
    BINARY = 'binary'
    JSON = 'json'
    LATEX = 'latex'
    KORE = 'kore'
    NONE = 'none'


class KoreExecLogFormat(Enum):
    STANDARD = 'standard'
    ONELINE = 'oneline'


def _kprove(
    spec_file: Path,
    *,
    command: Iterable[str] = ('kprove',),
    kompiled_dir: Optional[Path] = None,
    spec_module_name: Optional[str] = None,
    include_dirs: Iterable[Path] = (),
    emit_json_spec: Optional[Path] = None,
    output: Optional[KProveOutput] = None,
    dry_run: bool = False,
    args: Iterable[str] = (),
    env: Optional[Mapping[str, str]] = None,
    check: bool = True,
    profile: bool = False,
    depth: Optional[int] = None,
) -> CompletedProcess:
    check_file_path(spec_file)

    for include_dir in include_dirs:
        check_dir_path(include_dir)

    if depth is not None and depth < 0:
        raise ValueError(f'Argument "depth" must be non-negative, got: {depth}')

    typed_args = _build_arg_list(
        kompiled_dir=kompiled_dir,
        spec_module_name=spec_module_name,
        include_dirs=include_dirs,
        emit_json_spec=emit_json_spec,
        output=output,
        dry_run=dry_run,
        depth=depth,
    )

    try:
        run_args = tuple(chain(command, [str(spec_file)], typed_args, args))
        return run_process(run_args, logger=_LOGGER, env=env, check=check, profile=profile)
    except CalledProcessError as err:
        raise RuntimeError(
            f'Command kprove exited with code {err.returncode} for: {spec_file}', err.stdout, err.stderr
        ) from err


def _build_arg_list(
    *,
    kompiled_dir: Optional[Path],
    spec_module_name: Optional[str],
    include_dirs: Iterable[Path],
    emit_json_spec: Optional[Path],
    output: Optional[KProveOutput],
    dry_run: bool,
    depth: Optional[int],
) -> List[str]:
    args = []

    if kompiled_dir:
        args += ['--definition', str(kompiled_dir)]

    if spec_module_name:
        args += ['--spec-module', spec_module_name]

    for include_dir in include_dirs:
        args += ['-I', str(include_dir)]

    if emit_json_spec:
        args += ['--emit-json-spec', str(emit_json_spec)]

    if output:
        args += ['--output', output.value]

    if dry_run:
        args.append('--dry-run')

    if depth:
        args += ['--depth', str(depth)]

    return args


class KProve(KPrint, ContextManager['KProve']):
    main_file: Optional[Path]
    prover: List[str]
    prover_args: List[str]
    backend: str
    main_module: str
    port: int
    _kore_rpc: Optional[Tuple[KoreServer, KoreClient]]

    def __init__(
        self,
        definition_dir: Path,
        main_file: Optional[Path] = None,
        use_directory: Optional[Path] = None,
        profile: bool = False,
        command: str = 'kprove',
        port: Optional[int] = None,
    ):
        super(KProve, self).__init__(definition_dir, use_directory=use_directory, profile=profile)
        # TODO: we should not have to supply main_file, it should be read
        # TODO: setting use_directory manually should set temp files to not be deleted and a log message
        self.main_file = main_file
        self.prover = [command]
        self.prover_args = []
        self.port = 3000 if port is None else port
        with open(self.definition_dir / 'backend.txt', 'r') as ba:
            self.backend = ba.read()
        with open(self.definition_dir / 'mainModule.txt', 'r') as mm:
            self.main_module = mm.read()
        self._kore_rpc = None

    def __enter__(self) -> 'KProve':
        return self

    def __exit__(self, *args: Any) -> None:
        self.close()

    def kore_rpc(self) -> Tuple[KoreServer, KoreClient]:
        if not self._kore_rpc:
            _kore_server = KoreServer(self.definition_dir, self.main_module, self.port)
            _kore_client = KoreClient('localhost', self.port)
            self._kore_rpc = (_kore_server, _kore_client)
        return self._kore_rpc

    def close_kore_rpc(self) -> None:
        if self._kore_rpc is not None:
            _kore_server, _kore_client = self._kore_rpc
            _kore_client.close()
            _kore_server.close()
            self._kore_rpc = None

    def set_kore_rpc_port(self, p: int) -> None:
        was_open = self._kore_rpc is not None
        if was_open:
            self.close_kore_rpc()
        self.port = p
        if was_open:
            self.kore_rpc()

    def close(self) -> None:
        self.close_kore_rpc()

    def prove(
        self,
        spec_file: Path,
        spec_module_name: Optional[str] = None,
        args: Iterable[str] = (),
        haskell_args: Iterable[str] = (),
        haskell_log_entries: Iterable[str] = (),
        log_axioms_file: Optional[Path] = None,
        allow_zero_step: bool = False,
        dry_run: bool = False,
        depth: Optional[int] = None,
        haskell_log_format: KoreExecLogFormat = KoreExecLogFormat.ONELINE,
        haskell_log_debug_transition: bool = True,
    ) -> KInner:
        log_file = spec_file.with_suffix('.debug-log') if log_axioms_file is None else log_axioms_file
        if log_file.exists():
            log_file.unlink()
        haskell_log_entries = unique(
            list(haskell_log_entries) + (['DebugTransition'] if haskell_log_debug_transition else [])
        )
        haskell_log_args = [
            '--log',
            str(log_file),
            '--log-format',
            haskell_log_format.value,
            '--log-entries',
            ','.join(haskell_log_entries),
        ]

        kore_exec_opts = ' '.join(list(haskell_args) + haskell_log_args)
        _LOGGER.debug(f'export KORE_EXEC_OPTS="{kore_exec_opts}"')
        env = os.environ.copy()
        env['KORE_EXEC_OPTS'] = kore_exec_opts

        proc_result = _kprove(
            spec_file=spec_file,
            command=self.prover,
            kompiled_dir=self.definition_dir,
            spec_module_name=spec_module_name,
            output=KProveOutput.JSON,
            dry_run=dry_run,
            args=self.prover_args + list(args),
            env=env,
            check=False,
            profile=self._profile,
            depth=depth,
        )

        if proc_result.returncode not in (0, 1):
            raise RuntimeError('kprove failed!')

        if dry_run:
            return mlBottom()

        debug_log = _get_rule_log(log_file)
        final_state = KInner.from_dict(json.loads(proc_result.stdout)['term'])
        if is_top(final_state) and len(debug_log) == 0 and not allow_zero_step:
            raise ValueError(f'Proof took zero steps, likely the LHS is invalid: {spec_file}')
        return final_state

    def prove_claim(
        self,
        claim: KClaim,
        claim_id: str,
        lemmas: Iterable[KRule] = (),
        args: Iterable[str] = (),
        haskell_args: Iterable[str] = (),
        haskell_log_entries: Iterable[str] = (),
        log_axioms_file: Optional[Path] = None,
        allow_zero_step: bool = False,
        dry_run: bool = False,
        depth: Optional[int] = None,
    ) -> KInner:
        claim_path, claim_module_name = self._write_claim_definition(claim, claim_id, lemmas=lemmas)
        return self.prove(
            claim_path,
            spec_module_name=claim_module_name,
            args=args,
            haskell_args=haskell_args,
            haskell_log_entries=haskell_log_entries,
            log_axioms_file=log_axioms_file,
            allow_zero_step=allow_zero_step,
            dry_run=dry_run,
            depth=depth,
        )

    # TODO: This should return the empty disjunction `[]` instead of `#Top`.
    # The prover should never return #Bottom, so we can ignore that case.
    # Once those are taken care of, we can change the return type to a CTerm
    def prove_cterm(
        self,
        claim_id: str,
        init_cterm: CTerm,
        target_cterm: CTerm,
        lemmas: Iterable[KRule] = (),
        args: Iterable[str] = (),
        haskell_args: Iterable[str] = (),
        log_axioms_file: Optional[Path] = None,
        allow_zero_step: bool = False,
        depth: Optional[int] = None,
    ) -> List[KInner]:
        claim, var_map = build_claim(claim_id, init_cterm, target_cterm, keep_vars=free_vars(init_cterm.kast))
        next_state = self.prove_claim(
            claim,
            claim_id,
            lemmas=lemmas,
            args=args,
            haskell_args=haskell_args,
            log_axioms_file=log_axioms_file,
            allow_zero_step=allow_zero_step,
            depth=depth,
        )
        next_states = list(unique(var_map(ns) for ns in flatten_label('#Or', next_state) if not is_top(ns)))
        constraint_subst, _ = extract_subst(init_cterm.kast)
        next_states = [mlAnd([constraint_subst.unapply(ns), constraint_subst.ml_pred]) for ns in next_states]
        return next_states if len(next_states) > 0 else [mlTop()]

    def get_claim_basic_block(
        self,
        claim_id: str,
        claim: KClaim,
        lemmas: Iterable[KRule] = (),
        args: Iterable[str] = (),
        haskell_args: Iterable[str] = (),
        max_depth: int = 1000,
    ) -> Tuple[int, bool, KInner]:
        def _is_fatal_error_log_entry(line: str) -> bool:
            decide_predicate_unknown = line.find('(ErrorDecidePredicateUnknown): ErrorDecidePredicateUnknown') >= 0
            return decide_predicate_unknown

        claim_path, claim_module = self._write_claim_definition(claim, claim_id, lemmas=lemmas)
        log_axioms_file = claim_path.with_suffix('.debug.log')
        next_state = self.prove(
            claim_path,
            spec_module_name=claim_module,
            args=args,
            haskell_args=(['--execute-to-branch'] + list(haskell_args)),
            log_axioms_file=log_axioms_file,
            depth=max_depth,
        )
        if len(flatten_label('#Or', next_state)) != 1:
            raise AssertionError(f'get_basic_block execeted 1 state from Haskell backend, got: {next_state}')
        with open(log_axioms_file) as lf:
            log_file = lf.readlines()
        depth = -1
        branching = False
        could_be_branching = False
        rule_count = 0
        _LOGGER.info(f'log_file: {log_axioms_file}')
        for log_line in log_file:
            if _is_fatal_error_log_entry(log_line):
                depth = rule_count
                _LOGGER.warning(f'Fatal backend error: {log_line}')
            elif log_line.find('InfoUnprovenDepth') >= 0 or log_line.find('InfoProvenDepth') >= 0:
                # example:
                # kore-exec: [12718755] Info (InfoProofDepth): InfoUnprovenDepth : 48
                depth = int(log_line.split(':')[-1].strip())
            elif log_line.find('(DebugTransition): after  apply axioms: ') >= 0:
                rule_count += 1
                # example:
                # kore-exec: [24422822] Debug (DebugTransition): after  apply axioms: /home/dev/src/erc20-verification-pr/.build/usr/lib/ktoken/kevm/lib/kevm/include/kframework/evm.md:1858:10-1859:38
                branching = branching or could_be_branching
                could_be_branching = True
            else:
                could_be_branching = False
        return depth, branching, next_state

    def execute(
        self,
        cterm: CTerm,
        depth: Optional[int] = None,
        cut_point_rules: Optional[Iterable[str]] = None,
        terminal_rules: Optional[Iterable[str]] = None,
        assume_defined: bool = True,
    ) -> Tuple[int, CTerm, List[CTerm]]:
        if assume_defined:
            cterm = cterm.add_constraint(
                KApply(KLabel('#Ceil', [GENERATED_TOP_CELL, GENERATED_TOP_CELL]), [cterm.kast])
            )
        _LOGGER.debug(f'Executing: {cterm}')
        kore = self.kast_to_kore(cterm.kast, GENERATED_TOP_CELL)
        _, kore_client = self.kore_rpc()
        er = kore_client.execute(kore, max_depth=depth, cut_point_rules=cut_point_rules, terminal_rules=terminal_rules)
        depth = er.depth
        next_state = CTerm(self.kore_to_kast(er.state.kore))
        _next_states = er.next_states if er.next_states is not None and len(er.next_states) > 1 else []
        next_states = [CTerm(self.kore_to_kast(ns.kore)) for ns in _next_states]
        return depth, next_state, next_states

    def simplify(self, cterm: CTerm) -> KInner:
        _LOGGER.debug(f'Simplifying: {cterm}')
        kore = self.kast_to_kore(cterm.kast, GENERATED_TOP_CELL)
        _, kore_client = self.kore_rpc()
        kore_simplified = kore_client.simplify(kore)
        kast_simplified = self.kore_to_kast(kore_simplified)
        return kast_simplified

    def implies(
        self, antecedent: CTerm, consequent: CTerm, bind_consequent_variables: bool = True
    ) -> Optional[Tuple[Subst, KInner]]:
        _LOGGER.debug(f'Checking implication: {antecedent} #Implies {consequent}')
        _consequent = consequent.kast
        if bind_consequent_variables:
            _consequent = consequent.kast
            fv_antecedent = free_vars(antecedent.kast)
            unbound_consequent = [v for v in free_vars(_consequent) if v not in fv_antecedent]
            if len(unbound_consequent) > 0:
                _LOGGER.info(f'Binding variables in consequent: {unbound_consequent}')
                for uc in unbound_consequent:
                    _consequent = KApply(KLabel('#Exists', [GENERATED_TOP_CELL]), [KVariable(uc), _consequent])
        antecedent_kore = self.kast_to_kore(antecedent.kast, GENERATED_TOP_CELL)
        consequent_kore = self.kast_to_kore(_consequent, GENERATED_TOP_CELL)
        _, kore_client = self.kore_rpc()
        result = kore_client.implies(antecedent_kore, consequent_kore)
        if type(result.implication) is not Top:
            _LOGGER.warning(
                f'Received a non-trivial implication back from check implication endpoint: {result.implication}'
            )
        if result.substitution is None:
            return None
        ml_subst = self.kore_to_kast(result.substitution)
        ml_pred = self.kore_to_kast(result.predicate) if result.predicate is not None else mlTop()
        if is_top(ml_subst):
            return (Subst({}), ml_pred)
        subst_pattern = mlEquals(KVariable('###VAR'), KVariable('###TERM'))
        _subst: Dict[str, KInner] = {}
        for subst_pred in flatten_label('#And', ml_subst):
            m = subst_pattern.match(subst_pred)
            if m is not None and type(m['###VAR']) is KVariable:
                _subst[m['###VAR'].name] = m['###TERM']
            else:
                raise AssertionError(f'Received a non-substitution from implies endpoint: {subst_pred}')
        return (Subst(_subst), ml_pred)

    def _write_claim_definition(self, claim: KClaim, claim_id: str, lemmas: Iterable[KRule] = ()) -> Tuple[Path, str]:
        tmp_claim = self.use_directory / (claim_id.lower() + '-spec')
        tmp_module_name = claim_id.upper() + '-SPEC'
        tmp_claim = tmp_claim.with_suffix('.k')
        sentences: List[KSentence] = []
        sentences.extend(lemmas)
        sentences.append(claim)
        with open(tmp_claim, 'w') as tc:
            claim_module = KFlatModule(tmp_module_name, sentences, imports=[KImport(self.main_module, True)])
            requires = []
            if self.main_file is not None:
                requires += [KRequire(str(self.main_file))]
            claim_definition = KDefinition(tmp_module_name, [claim_module], requires=requires)
            tc.write(gen_file_timestamp() + '\n')
            tc.write(self.pretty_print(claim_definition) + '\n\n')
            tc.flush()
        _LOGGER.info(f'Wrote claim file: {tmp_claim}.')
        return tmp_claim, tmp_module_name


def _get_rule_log(debug_log_file: Path) -> List[List[Tuple[str, bool, int]]]:

    # rule_loc, is_success, ellapsed_time_since_start
    def _get_rule_line(_line: str) -> Optional[Tuple[str, bool, int]]:
        if _line.startswith('kore-exec: ['):
            time = int(_line.split('[')[1].split(']')[0])
            if _line.find('(DebugTransition): after  apply axioms: ') > 0:
                rule_name = ':'.join(_line.split(':')[-4:]).strip()
                return (rule_name, True, time)
            elif _line.find('(DebugAttemptedRewriteRules): ') > 0:
                rule_name = ':'.join(_line.split(':')[-4:]).strip()
                return (rule_name, False, time)
        return None

    log_lines: List[Tuple[str, bool, int]] = []
    with open(debug_log_file, 'r') as log_file:
        for line in log_file.read().split('\n'):
            if processed_line := _get_rule_line(line):
                log_lines.append(processed_line)

    # rule_loc, is_success, time_delta
    axioms: List[List[Tuple[str, bool, int]]] = [[]]
    just_applied = True
    prev_time = 0
    for rule_name, is_application, rule_time in log_lines:
        rtime = rule_time - prev_time
        prev_time = rule_time
        if not is_application:
            if just_applied:
                axioms.append([])
            just_applied = False
        else:
            just_applied = True
        axioms[-1].append((rule_name, is_application, rtime))

    if len(axioms[-1]) == 0:
        axioms.pop(-1)

    return axioms
