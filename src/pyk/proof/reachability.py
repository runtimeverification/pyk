from __future__ import annotations

import logging
from itertools import chain
from typing import TYPE_CHECKING, cast

from pyk.kore.rpc import LogEntry

from ..kast.manip import flatten_label, ml_pred_to_bool
from ..kcfg import KCFG
from ..prelude.kbool import BOOL, TRUE
from ..prelude.ml import mlAnd, mlEquals, mlTop
from ..utils import keys_to_int, shorten_hashes, single
from .equality import RefutationProof, RefutationProver
from .proof import Proof, ProofStatus

if TYPE_CHECKING:
    from collections.abc import Callable, Iterable, Mapping
    from pathlib import Path
    from typing import Any, Final, TypeVar

    from ..cterm import CTerm
    from ..kast.inner import KInner
    from ..kast.outer import KClaim, KDefinition
    from ..kcfg import KCFGExplore
    from ..kcfg.kcfg import NodeIdLike

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
    node_refutations: dict[int, str]
    init: NodeIdLike
    target: NodeIdLike
    _terminal_nodes: list[NodeIdLike]
    logs: dict[int, tuple[LogEntry, ...]]

    def __init__(
        self,
        id: str,
        kcfg: KCFG,
        init: NodeIdLike,
        target: NodeIdLike,
        logs: dict[int, tuple[LogEntry, ...]],
        proof_dir: Path | None = None,
        node_refutations: dict[int, str] | None = None,
        subproof_ids: list[str] | None = None,
        terminal_nodes: Iterable[NodeIdLike] | None = None,
    ):
        super().__init__(id, proof_dir=proof_dir, subproof_ids=subproof_ids)
        self.kcfg = kcfg
        self.init = init
        self.target = target
        self.logs = logs
        self._terminal_nodes = list(terminal_nodes) if terminal_nodes is not None else []

        if node_refutations is not None:
            refutations_not_in_subprroofs = set(node_refutations.values()).difference(
                set(subproof_ids if subproof_ids else [])
            )
            if refutations_not_in_subprroofs:
                raise ValueError(
                    f'All node refutations must be included in subproofs, violators are {refutations_not_in_subprroofs}'
                )
        self.node_refutations = node_refutations if node_refutations is not None else {}

    @property
    def terminal(self) -> list[KCFG.Node]:
        return [self.kcfg.node(nid) for nid in self._terminal_nodes]

    @property
    def pending(self) -> list[KCFG.Node]:
        return [
            nd
            for nd in self.kcfg.leaves
            if nd not in self.terminal + self.kcfg.target and not self.kcfg.is_covered(nd.id)
        ]

    def read_refutations(self) -> Iterable[tuple[int, RefutationProof]]:
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

        if len(self.terminal) > 0 and not all_stuck_refuted:
            return ProofStatus.FAILED
        elif len(self.pending) > 0 or self.subproofs_status == ProofStatus.PENDING:
            return ProofStatus.PENDING
        else:
            if self.subproofs_status == ProofStatus.PASSED:
                return ProofStatus.PASSED
            else:
                return ProofStatus.FAILED

    @classmethod
    def from_dict(cls: type[APRProof], dct: Mapping[str, Any], proof_dir: Path | None = None) -> APRProof:
        cfg = KCFG.from_dict(dct['cfg'])
        terminal_nodes = dct['terminal_nodes']
        init_node = dct['init']
        target_node = dct['target']
        id = dct['id']
        subproof_ids = dct['subproof_ids'] if 'subproof_ids' in dct else []
        node_refutations = keys_to_int(dct['node_refutations']) if 'node_refutations' in dct else {}
        if 'logs' in dct:
            logs = {k: tuple(LogEntry.from_dict(l) for l in ls) for k, ls in dct['logs'].items()}
        else:
            logs = {}

        return APRProof(
            id,
            cfg,
            init_node,
            target_node,
            logs,
            terminal_nodes=terminal_nodes,
            proof_dir=proof_dir,
            subproof_ids=subproof_ids,
            node_refutations=node_refutations,
        )

    @staticmethod
    def from_claim(defn: KDefinition, claim: KClaim, *args: Any, **kwargs: Any) -> APRProof:
        cfg, init_node, target_node = KCFG.from_claim(defn, claim)
        return APRProof(claim.label, cfg, init_node, target_node, {})

    def path_constraints(self, final_node_id: NodeIdLike) -> KInner:
        path = self.kcfg.shortest_path_between(self.init, final_node_id)
        if path is None:
            raise ValueError(f'No path found to specified node: {final_node_id}')
        curr_constraint: KInner = mlTop()
        for edge in reversed(path):
            if type(edge) is KCFG.Split:
                assert len(edge.targets) == 1
                csubst = edge.splits[edge.targets[0].id]
                curr_constraint = mlAnd([csubst.subst.ml_pred, csubst.constraint, curr_constraint])
            if type(edge) is KCFG.Cover:
                curr_constraint = mlAnd([edge.csubst.constraint, edge.csubst.subst.apply(curr_constraint)])
        return mlAnd(flatten_label('#And', curr_constraint))

    @property
    def dict(self) -> dict[str, Any]:
        logs = {k: [l.to_dict() for l in ls] for k, ls in self.logs.items()}
        return {
            'type': 'APRProof',
            'id': self.id,
            'cfg': self.kcfg.to_dict(),
            'init': self.init,
            'target': self.target,
            'terminal_nodes': self._terminal_nodes,
            'subproof_ids': self.subproof_ids,
            'node_refutations': self.node_refutations,
            'logs': logs,
        }

    def add_terminal(self, nid: NodeIdLike) -> None:
        self._terminal_nodes.append(self.kcfg._resolve(nid))

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
            f'    pending: {len(self.pending)}',
            f'    terminal: {len(self.terminal)}',
        ]
        for summary in subproofs_summaries:
            yield from summary

    def get_refutation_id(self, node_id: int) -> str:
        return f'{self.id}.node-infeasible-{node_id}'

    def construct_node_refutation(self, node: KCFG.Node) -> RefutationProof | None:
        """Construct an EqualityProof stating that the node's path condition is unsatisfiable"""
        if not node in self.kcfg.nodes:
            raise ValueError(f'No such node {node.id}')

        # construct the path from the KCFG root to the node to refute
        try:
            path = single(self.kcfg.paths_between(source_id=self.kcfg.get_unique_init().id, target_id=node.id))
        except ValueError:
            _LOGGER.error(f'Node {node.id} is not reachable from the initial node.')
            return None
        # traverse the path back from the node-to-refute and choose only split nodes and non-deterministic branches
        branches_on_path = list(filter(lambda x: type(x) is KCFG.Split or type(x) is KCFG.NDBranch, reversed(path)))
        if len(branches_on_path) == 0:
            _LOGGER.error(f'Cannot refute node {node.id} in linear KCFG')
            return None
        closest_branch = branches_on_path[0]
        assert type(closest_branch) is KCFG.Split or type(closest_branch) is KCFG.NDBranch
        if type(closest_branch) is KCFG.NDBranch:
            _LOGGER.error(f'Cannot refute node {node.id} following a non-deterministic branch: not yet implemented')
            return None

        assert type(closest_branch) is KCFG.Split
        refuted_branch_root = closest_branch.targets[0]
        csubst = closest_branch.splits[refuted_branch_root.id]
        if len(csubst.subst) > 0:
            _LOGGER.error(
                f'Cannot refute node {node.id}: unexpected non-empty substitution {csubst.subst} in Split from {closest_branch.source.id}'
            )
            return None
        if len(csubst.constraints) > 1:
            _LOGGER.error(
                f'Cannot refute node {node.id}: unexpected non-singleton constraints {csubst.constraints} in Split from {closest_branch.source.id}'
            )
            return None

        # extract the path condition prior to the Split that leads to the node-to-refute
        pre_split_constraints = [
            mlEquals(TRUE, ml_pred_to_bool(c), arg_sort=BOOL) for c in closest_branch.source.cterm.constraints
        ]

        # extract the constriant added by the Split that leads to the node-to-refute
        last_constraint = mlEquals(TRUE, ml_pred_to_bool(csubst.constraints[0]), arg_sort=BOOL)

        refutation_id = self.get_refutation_id(node.id)
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
    _bounded_nodes: list[NodeIdLike]

    def __init__(
        self,
        id: str,
        kcfg: KCFG,
        init: NodeIdLike,
        target: NodeIdLike,
        logs: dict[int, tuple[LogEntry, ...]],
        bmc_depth: int,
        bounded_nodes: Iterable[int] | None = None,
        proof_dir: Path | None = None,
        subproof_ids: list[str] | None = None,
        node_refutations: dict[int, str] | None = None,
    ):
        super().__init__(
            id,
            kcfg,
            init,
            target,
            logs,
            proof_dir=proof_dir,
            subproof_ids=subproof_ids,
            node_refutations=node_refutations,
        )
        self.bmc_depth = bmc_depth
        self._bounded_nodes = list(bounded_nodes) if bounded_nodes is not None else []

    @property
    def bounded(self) -> list[KCFG.Node]:
        return [self.kcfg.node(nid) for nid in self._bounded_nodes]

    @property
    def pending(self) -> list[KCFG.Node]:
        return [
            nd
            for nd in self.kcfg.leaves
            if nd not in self.terminal + self.kcfg.target + self.bounded and not self.kcfg.is_covered(nd.id)
        ]

    @property
    def status(self) -> ProofStatus:
        if (
            any(nd.id not in self._bounded_nodes for nd in self.kcfg.stuck)
            or self.subproofs_status == ProofStatus.FAILED
        ):
            return ProofStatus.FAILED
        elif len(self.pending) > 0 or self.subproofs_status == ProofStatus.PENDING:
            return ProofStatus.PENDING
        else:
            return ProofStatus.PASSED

    @classmethod
    def from_dict(cls: type[APRBMCProof], dct: Mapping[str, Any], proof_dir: Path | None = None) -> APRBMCProof:
        cfg = KCFG.from_dict(dct['cfg'])
        id = dct['id']
        init = dct['init']
        target = dct['target']
        bounded_nodes = dct['bounded_nodes']
        bmc_depth = dct['bmc_depth']
        subproof_ids = dct['subproof_ids'] if 'subproof_ids' in dct else []
        node_refutations = keys_to_int(dct['node_refutations']) if 'node_refutations' in dct else {}
        if 'logs' in dct:
            logs = {k: tuple(LogEntry.from_dict(l) for l in ls) for k, ls in dct['logs'].items()}
        else:
            logs = {}
        return APRBMCProof(
            id,
            cfg,
            init,
            target,
            logs,
            bmc_depth,
            bounded_nodes=bounded_nodes,
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
            'init': self.init,
            'target': self.target,
            'bmc_depth': self.bmc_depth,
            'bounded_nodes': self._bounded_nodes,
            'subproof_ids': self.subproof_ids,
            'node_refutations': self.node_refutations,
        }
        logs = {k: [l.to_dict() for l in ls] for k, ls in self.logs.items()}
        if logs:
            result['logs'] = logs
        return result

    @staticmethod
    def from_claim_with_bmc_depth(defn: KDefinition, claim: KClaim, bmc_depth: int) -> APRBMCProof:
        cfg, init_node, target_node = KCFG.from_claim(defn, claim)
        return APRBMCProof(claim.label, cfg, init_node, target_node, {}, bmc_depth)

    def add_bounded(self, nid: NodeIdLike) -> None:
        self._bounded_nodes.append(self.kcfg._resolve(nid))

    @property
    def summary(self) -> Iterable[str]:
        subproofs_summaries = chain(subproof.summary for subproof in self.subproofs)
        yield from [
            f'APRBMCProof(depth={self.bmc_depth}): {self.id}',
            f'    status: {self.status}',
            f'    nodes: {len(self.kcfg.nodes)}',
            f'    frontier: {len(self.kcfg.frontier)}',
            f'    stuck: {len([nd for nd in self.kcfg.stuck if nd.id not in self._bounded_nodes])}',
            f'    bmc-depth-bounded: {len(self._bounded_nodes)}',
            'Subproofs' if len(self.subproof_ids) else '',
            f'    pending: {len(self.pending)}',
            f'    terminal: {len(self.terminal)}',
            f'    bounded: {len(self.bounded)}',
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
                self.proof.add_terminal(curr_node.id)
                self.proof.kcfg.add_expanded(curr_node.id)
                return True
        return False

    def _check_subsume(self, kcfg_explore: KCFGExplore, node: KCFG.Node) -> bool:
        target_node = self.proof.kcfg.node(self.proof.target)
        _LOGGER.info(
            f'Checking subsumption into target state {self.proof.id}: {shorten_hashes((node.id, target_node.id))}'
        )
        csubst = kcfg_explore.cterm_implies(node.cterm, target_node.cterm)
        if csubst is not None:
            self.proof.kcfg.create_cover(node.id, target_node.id, csubst=csubst)
            _LOGGER.info(f'Subsumed into target node {self.proof.id}: {shorten_hashes((node.id, target_node.id))}')
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

        while self.proof.pending:
            self.proof.write_proof()

            if max_iterations is not None and max_iterations <= iterations:
                _LOGGER.warning(f'Reached iteration bound {self.proof.id}: {max_iterations}')
                break
            iterations += 1
            curr_node = self.proof.pending[0]

            if self._check_subsume(kcfg_explore, curr_node):
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
        _LOGGER.info(f'Attempting to refute node {node.id}')
        refutation = self.proof.construct_node_refutation(node)
        if refutation is None:
            _LOGGER.error(f'Failed to refute node {node.id}')
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
            _LOGGER.info(f'Successfully refuted node {node.id} by proof {eq_prover.proof.id}')
        else:
            _LOGGER.error(f'Failed to refute node {node.id} by proof {eq_prover.proof.id}')
        self.proof.node_refutations[node.id] = eq_prover.proof.id

    def unrefute_node(self, node: KCFG.Node) -> None:
        self.proof.kcfg.remove_expanded(node.id)
        self.proof.remove_subproof(self.proof.get_refutation_id(node.id))
        del self.proof.node_refutations[node.id]
        _LOGGER.info(f'Disabled refutation of node {node.id}.')


class APRBMCProver(APRProver):
    proof: APRBMCProof
    _same_loop: Callable[[CTerm, CTerm], bool]
    _checked_nodes: list[int]

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

        while self.proof.pending:
            self.proof.write_proof()

            if max_iterations is not None and max_iterations <= iterations:
                _LOGGER.warning(f'Reached iteration bound {self.proof.id}: {max_iterations}')
                break
            iterations += 1

            for f in self.proof.pending:
                if f.id not in self._checked_nodes:
                    self._checked_nodes.append(f.id)
                    prior_loops = [
                        nd.id
                        for nd in self.proof.kcfg.reachable_nodes(f.id, reverse=True)
                        if nd.id != f.id and self._same_loop(nd.cterm, f.cterm)
                    ]
                    if len(prior_loops) >= self.proof.bmc_depth:
                        self.proof.kcfg.add_expanded(f.id)
                        self.proof.add_bounded(f.id)

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
