from __future__ import annotations

import logging
from itertools import chain
from typing import TYPE_CHECKING, cast

from pyk.kore.rpc import LogEntry

from ..kast.manip import ml_pred_to_bool
from ..kcfg import KCFG
from ..prelude.kbool import BOOL, TRUE
from ..prelude.ml import mlEquals
from ..utils import shorten_hash, shorten_hashes, single
from .equality import RefutationProof, RefutationProver
from .proof import Proof, ProofStatus

if TYPE_CHECKING:
    from collections.abc import Callable, Iterable, Mapping
    from pathlib import Path
    from typing import Any, Final, TypeVar

    from ..cterm import CTerm
    from ..kast.inner import KInner
    from ..kcfg import KCFGExplore

    T = TypeVar('T', bound='Proof')

_LOGGER: Final = logging.getLogger(__name__)


class APRProof(Proof):
    """APRProof and APRProver implement all-path reachability logic,
    as introduced by A. Stefanescu and others in their paper 'All-Path Reachability Logic':
    https://doi.org/10.23638/LMCS-15(2:5)2019
    Note that reachability logic formula `phi =>A psi` has *not* the same meaning
    as CTL/CTL*'s `phi -> AF psi`, since reachability logic ignores infinite traces.
    """

    kcfg: KCFG
    node_refutations: dict[str, str]
    logs: dict[str, tuple[LogEntry, ...]]

    def __init__(
        self,
        id: str,
        kcfg: KCFG,
        logs: dict[str, tuple[LogEntry, ...]],
        proof_dir: Path | None = None,
        node_refutations: dict[str, str] | None = None,
        subproof_ids: list[str] | None = None,
    ):
        super().__init__(id, proof_dir=proof_dir, subproof_ids=subproof_ids)
        self.kcfg = kcfg
        self.logs = logs

        if node_refutations is not None:
            refutations_not_in_subprroofs = set(node_refutations.values()).difference(
                set(subproof_ids if subproof_ids else [])
            )
            if refutations_not_in_subprroofs:
                raise ValueError(
                    f'All node refutations must be included in subproofs, violators are {refutations_not_in_subprroofs}'
                )
        self.node_refutations = node_refutations if node_refutations is not None else {}

    def read_refutations(self) -> Iterable[tuple[str, RefutationProof]]:
        if len(self.node_refutations) == 0:
            return
        else:
            if self.proof_dir is None:
                raise ValueError(f'Cannot read refutations proof {self.id} with no proof_dir')
            for node_id, proof_id in self.node_refutations.items():
                yield node_id, cast('RefutationProof', self.fetch_subproof(proof_id))

    @property
    def stuck_nodes_refuted(self) -> bool:
        stuck_nodes = self.kcfg.stuck
        refutations = dict(self.read_refutations())
        return all(n.id in self.node_refutations.keys() and refutations[n.id].csubst is None for n in stuck_nodes)

    @property
    def status(self) -> ProofStatus:
        all_stuck_refuted = self.stuck_nodes_refuted

        if len(self.kcfg.stuck) > 0 and not all_stuck_refuted:
            return ProofStatus.FAILED
        elif len(self.kcfg.frontier) > 0 or self.subproofs_status == ProofStatus.PENDING:
            return ProofStatus.PENDING
        else:
            if self.subproofs_status == ProofStatus.PASSED:
                return ProofStatus.PASSED
            else:
                return ProofStatus.FAILED

    @classmethod
    def from_dict(cls: type[APRProof], dct: Mapping[str, Any], proof_dir: Path | None = None) -> APRProof:
        cfg = KCFG.from_dict(dct['cfg'])
        id = dct['id']
        subproof_ids = dct['subproof_ids'] if 'subproof_ids' in dct else []
        node_refutations = dct['node_refutations'] if 'node_refutations' in dct else {}
        if 'logs' in dct:
            logs = {k: tuple(LogEntry.from_dict(l) for l in ls) for k, ls in dct['logs'].items()}
        else:
            logs = {}

        return APRProof(
            id, cfg, logs, proof_dir=proof_dir, subproof_ids=subproof_ids, node_refutations=node_refutations
        )

    @property
    def dict(self) -> dict[str, Any]:
        result = {
            'type': 'APRProof',
            'id': self.id,
            'cfg': self.kcfg.to_dict(),
            'subproof_ids': self.subproof_ids,
            'node_refutations': self.node_refutations,
        }
        logs = {k: [l.to_dict() for l in ls] for k, ls in self.logs.items()}
        if logs:
            result['logs'] = logs
        return result

    @property
    def summary(self) -> Iterable[str]:
        subproofs_summaries = chain(subproof.summary for subproof in self.subproofs)
        yield from [
            f'APRProof: {self.id}',
            f'    status: {self.status}',
            f'    nodes: {len(self.kcfg.nodes)}',
            f'    frontier: {len(self.kcfg.frontier)}',
            f'    stuck: {len(self.kcfg.stuck)}',
            f'    refuted: {len(self.node_refutations.keys())}',
            'Subproofs:' if len(self.subproof_ids) else '',
        ]
        for summary in subproofs_summaries:
            yield from summary

    def construct_node_refutation(self, node: KCFG.Node) -> RefutationProof | None:
        """Construct an EqualityProof stating that the node's path condition is unsatisfiable"""
        if not node in self.kcfg.nodes:
            raise ValueError(f'No such node {node.id}')

        # construct the path from the KCFG root to the node to refute
        path = single(self.kcfg.paths_between(source_id=self.kcfg.get_unique_init().id, target_id=node.id))
        # traverse the path back from the node-to-refute and filter-out split nodes and non-deterministic branches
        branches_on_path = list(filter(lambda x: type(x) is KCFG.Split or type(x) is KCFG.NDBranch, reversed(path)))
        if len(branches_on_path) == 0:
            _LOGGER.error(f'Cannot refute node {shorten_hash(node.id)} in linear KCFG')
            return None
        closest_branch = branches_on_path[0]
        assert type(closest_branch) is KCFG.Split or type(closest_branch) is KCFG.NDBranch
        if type(closest_branch) is KCFG.NDBranch:
            _LOGGER.error(
                f'Cannot refute node {shorten_hash(node.id)} following a non-determenistic branch: not yet implemented'
            )
            return None

        assert type(closest_branch) is KCFG.Split
        refuted_branch_root = closest_branch.targets[0]
        csubst = closest_branch.splits[refuted_branch_root.id]
        if len(csubst.subst) > 0:
            _LOGGER.error(
                f'Cannot refute node {shorten_hash(node.id)}: unexpected non-empty substitution {csubst.subst} in Split from {shorten_hash(closest_branch.source.id)}'
            )
            return None
        if len(csubst.constraints) > 1:
            _LOGGER.error(
                f'Cannot refute node {shorten_hash(node.id)}: unexpected non-singleton constraints {csubst.constraints} in Split from {shorten_hash(closest_branch.source.id)}'
            )
            return None

        # extract the path condition prior to the Split that leads to the node-to-refute
        pre_split_constraints = [
            mlEquals(TRUE, ml_pred_to_bool(c), arg_sort=BOOL) for c in closest_branch.source.cterm.constraints
        ]

        # extract the constriant added by the Split that leads to the node-to-refute
        last_constraint = mlEquals(TRUE, ml_pred_to_bool(csubst.constraints[0]), arg_sort=BOOL)

        refutation_id = f'{self.id}.node-infeasible-{shorten_hash(node.id)}'
        _LOGGER.info(f'Adding refutation proof {refutation_id} as subproof of {self.id}')
        refutation = RefutationProof(
            id=refutation_id,
            sort=BOOL,
            constraints=[*pre_split_constraints, last_constraint],
            proof_dir=self.proof_dir,
        )
        return refutation


class APRBMCProof(APRProof):
    """APRBMCProof and APRBMCProver perform bounded model-checking of an all-path reachability logic claim."""

    bmc_depth: int
    _bounded_states: list[str]

    def __init__(
        self,
        id: str,
        kcfg: KCFG,
        logs: dict[str, tuple[LogEntry, ...]],
        bmc_depth: int,
        bounded_states: Iterable[str] | None = None,
        proof_dir: Path | None = None,
        subproof_ids: list[str] | None = None,
        node_refutations: dict[str, str] | None = None,
    ):
        super().__init__(
            id, kcfg, logs, proof_dir=proof_dir, subproof_ids=subproof_ids, node_refutations=node_refutations
        )
        self.bmc_depth = bmc_depth
        self._bounded_states = list(bounded_states) if bounded_states is not None else []

    @property
    def status(self) -> ProofStatus:
        if (
            any(nd.id not in self._bounded_states for nd in self.kcfg.stuck)
            or self.subproofs_status == ProofStatus.FAILED
        ):
            return ProofStatus.FAILED
        elif len(self.kcfg.frontier) > 0 or self.subproofs_status == ProofStatus.PENDING:
            return ProofStatus.PENDING
        else:
            return ProofStatus.PASSED

    @classmethod
    def from_dict(cls: type[APRBMCProof], dct: Mapping[str, Any], proof_dir: Path | None = None) -> APRBMCProof:
        cfg = KCFG.from_dict(dct['cfg'])
        id = dct['id']
        bounded_states = dct['bounded_states']
        bmc_depth = dct['bmc_depth']
        subproof_ids = dct['subproof_ids'] if 'subproof_ids' in dct else []
        node_refutations = dct['node_refutations'] if 'node_refutations' in dct else {}
        if 'logs' in dct:
            logs = {k: tuple(LogEntry.from_dict(l) for l in ls) for k, ls in dct['logs'].items()}
        else:
            logs = {}
        return APRBMCProof(
            id,
            cfg,
            logs,
            bmc_depth,
            bounded_states=bounded_states,
            proof_dir=proof_dir,
            subproof_ids=subproof_ids,
            node_refutations=node_refutations,
        )

    @property
    def dict(self) -> dict[str, Any]:
        result = {
            'type': 'APRBMCProof',
            'id': self.id,
            'cfg': self.kcfg.to_dict(),
            'bmc_depth': self.bmc_depth,
            'bounded_states': self._bounded_states,
            'subproof_ids': self.subproof_ids,
            'node_refutations': self.node_refutations,
        }
        logs = {k: [l.to_dict() for l in ls] for k, ls in self.logs.items()}
        if logs:
            result['logs'] = logs
        return result

    def bound_state(self, nid: str) -> None:
        self._bounded_states.append(nid)

    @property
    def summary(self) -> Iterable[str]:
        subproofs_summaries = chain(subproof.summary for subproof in self.subproofs)
        yield from [
            f'APRBMCProof(depth={self.bmc_depth}): {self.id}',
            f'    status: {self.status}',
            f'    nodes: {len(self.kcfg.nodes)}',
            f'    frontier: {len(self.kcfg.frontier)}',
            f'    stuck: {len([nd for nd in self.kcfg.stuck if nd.id not in self._bounded_states])}',
            f'    bmc-depth-bounded: {len(self._bounded_states)}',
            'Subproofs' if len(self.subproof_ids) else '',
        ]
        for summary in subproofs_summaries:
            yield from summary


class APRProver:
    proof: APRProof
    _is_terminal: Callable[[CTerm], bool] | None
    _extract_branches: Callable[[CTerm], Iterable[KInner]] | None

    def __init__(
        self,
        proof: APRProof,
        is_terminal: Callable[[CTerm], bool] | None = None,
        extract_branches: Callable[[CTerm], Iterable[KInner]] | None = None,
    ) -> None:
        self.proof = proof
        self._is_terminal = is_terminal
        self._extract_branches = extract_branches

    def _check_terminal(self, curr_node: KCFG.Node) -> bool:
        if self._is_terminal is not None:
            _LOGGER.info(f'Checking terminal {self.proof.id}: {shorten_hashes(curr_node.id)}')
            if self._is_terminal(curr_node.cterm):
                _LOGGER.info(f'Terminal node {self.proof.id}: {shorten_hashes(curr_node.id)}.')
                self.proof.kcfg.add_expanded(curr_node.id)
                return True
        return False

    def advance_proof(
        self,
        kcfg_explore: KCFGExplore,
        max_iterations: int | None = None,
        execute_depth: int | None = None,
        cut_point_rules: Iterable[str] = (),
        terminal_rules: Iterable[str] = (),
        implication_every_block: bool = True,
    ) -> KCFG:
        iterations = 0

        while self.proof.kcfg.frontier:
            self.proof.write_proof()

            if max_iterations is not None and max_iterations <= iterations:
                _LOGGER.warning(f'Reached iteration bound {self.proof.id}: {max_iterations}')
                break
            iterations += 1
            curr_node = self.proof.kcfg.frontier[0]

            if kcfg_explore.target_subsume(self.proof.kcfg, curr_node):
                continue

            if self._check_terminal(curr_node):
                continue

            if self._extract_branches is not None and len(self.proof.kcfg.splits(target_id=curr_node.id)) == 0:
                branches = list(self._extract_branches(curr_node.cterm))
                if len(branches) > 0:
                    self.proof.kcfg.split_on_constraints(curr_node.id, branches)
                    _LOGGER.info(
                        f'Found {len(branches)} branches using heuristic for node {self.proof.id}: {shorten_hashes(curr_node.id)}: {[kcfg_explore.kprint.pretty_print(bc) for bc in branches]}'
                    )
                    continue

            kcfg_explore.extend(
                self.proof.kcfg,
                curr_node,
                self.proof.logs,
                execute_depth=execute_depth,
                cut_point_rules=cut_point_rules,
                terminal_rules=terminal_rules,
            )

        self.proof.write_proof()
        return self.proof.kcfg

    def refute_node(self, kcfg_explore: KCFGExplore, node: KCFG.Node, extra_constraint: KInner | None = None) -> None:
        _LOGGER.info(f'Attempting to refute node {shorten_hash(node.id)}')
        refutation = self.proof.construct_node_refutation(node)
        if refutation is None:
            _LOGGER.error(f'Failed to refute node {shorten_hash(node.id)}')
            return None
        if extra_constraint is not None:
            _LOGGER.info(f'Adding the provided extra cosntraint {extra_constraint} to refutation {refutation.id}')
            refutation.add_constraint(extra_constraint)
        refutation.write_proof()

        # mark the node-to-refute as expanded to prevent further exploration
        self.proof.kcfg.add_expanded(node.id)

        if refutation.id in self.proof.subproof_ids:
            _LOGGER.warning(f'{refutation.id} is already a subproof of {self.proof.id}, overriding.')
        else:
            self.proof.add_subproof(refutation.id)
        self.proof.write_proof()

        eq_prover = RefutationProver(refutation)
        eq_prover.advance_proof(kcfg_explore)

        if eq_prover.proof.csubst is None:
            _LOGGER.info(f'Successfully refuted node {shorten_hash(node.id)} by proof {eq_prover.proof.id}')
        else:
            _LOGGER.error(f'Failed to refute node {shorten_hash(node.id)} by proof {eq_prover.proof.id}')
        self.proof.node_refutations[node.id] = eq_prover.proof.id


class APRBMCProver(APRProver):
    proof: APRBMCProof
    _same_loop: Callable[[CTerm, CTerm], bool]
    _checked_nodes: list[str]

    def __init__(
        self,
        proof: APRBMCProof,
        same_loop: Callable[[CTerm, CTerm], bool],
        is_terminal: Callable[[CTerm], bool] | None = None,
        extract_branches: Callable[[CTerm], Iterable[KInner]] | None = None,
    ) -> None:
        super().__init__(proof, is_terminal=is_terminal, extract_branches=extract_branches)
        self._same_loop = same_loop
        self._checked_nodes = []

    def advance_proof(
        self,
        kcfg_explore: KCFGExplore,
        max_iterations: int | None = None,
        execute_depth: int | None = None,
        cut_point_rules: Iterable[str] = (),
        terminal_rules: Iterable[str] = (),
        implication_every_block: bool = True,
    ) -> KCFG:
        iterations = 0

        while self.proof.kcfg.frontier:
            self.proof.write_proof()

            if max_iterations is not None and max_iterations <= iterations:
                _LOGGER.warning(f'Reached iteration bound {self.proof.id}: {max_iterations}')
                break
            iterations += 1

            for f in self.proof.kcfg.frontier:
                if f.id not in self._checked_nodes:
                    self._checked_nodes.append(f.id)
                    prior_loops = [
                        nd.id
                        for nd in self.proof.kcfg.reachable_nodes(f.id, reverse=True, traverse_covers=True)
                        if nd.id != f.id and self._same_loop(nd.cterm, f.cterm)
                    ]
                    if len(prior_loops) >= self.proof.bmc_depth:
                        self.proof.kcfg.add_expanded(f.id)
                        self.proof.bound_state(f.id)

            super().advance_proof(
                kcfg_explore,
                max_iterations=1,
                execute_depth=execute_depth,
                cut_point_rules=cut_point_rules,
                terminal_rules=terminal_rules,
                implication_every_block=implication_every_block,
            )

        self.proof.write_proof()
        return self.proof.kcfg
