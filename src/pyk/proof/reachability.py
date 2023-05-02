from __future__ import annotations

import json
import logging
from itertools import chain
from typing import TYPE_CHECKING

from ..kast.manip import ml_pred_to_bool
from ..kcfg import KCFG
from ..prelude.kbool import BOOL, FALSE, TRUE, andBool
from ..prelude.ml import mlEquals
from ..utils import hash_str, shorten_hash, shorten_hashes, single
from .equality import EqualityProof
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

    def __init__(self, id: str, kcfg: KCFG, proof_dir: Path | None = None, subproof_ids: list[str] | None = None):
        super().__init__(id, proof_dir=proof_dir, subproof_ids=subproof_ids)
        self.kcfg = kcfg

    @staticmethod
    def read_proof(id: str, proof_dir: Path) -> APRProof:
        proof_path = proof_dir / f'{hash_str(id)}.json'
        if APRProof.proof_exists(id, proof_dir):
            proof_dict = json.loads(proof_path.read_text())
            _LOGGER.info(f'Reading APRProof from file {id}: {proof_path}')
            return APRProof.from_dict(proof_dict, proof_dir=proof_dir)
        raise ValueError(f'Could not load APRProof from file {id}: {proof_path}')

    @property
    def status(self) -> ProofStatus:
        if len(self.kcfg.stuck) > 0 or self.subproofs_status == ProofStatus.FAILED:
            return ProofStatus.FAILED
        elif len(self.kcfg.frontier) > 0 or self.subproofs_status == ProofStatus.PENDING:
            return ProofStatus.PENDING
        else:
            return ProofStatus.PASSED

    @classmethod
    def from_dict(cls: type[APRProof], dct: Mapping[str, Any], proof_dir: Path | None = None) -> APRProof:
        cfg = KCFG.from_dict(dct['cfg'])
        id = dct['id']
        subproof_ids = dct['subproof_ids'] if 'subproof_ids' in dct else []
        return APRProof(id, cfg, proof_dir=proof_dir, subproof_ids=subproof_ids)

    @property
    def dict(self) -> dict[str, Any]:
        result: dict[str, Any] = {
            'type': 'APRProof',
            'id': self.id,
            'cfg': self.kcfg.to_dict(),
            'subproof_ids': self.subproof_ids,
        }
        return result

    @property
    def summary(self) -> Iterable[str]:
        subproofs_summaries = chain(subproof.summary for subproof in self.read_subproofs())
        yield from [
            f'APRProof: {self.id}',
            f'    status: {self.status}',
            f'    nodes: {len(self.kcfg.nodes)}',
            f'    frontier: {len(self.kcfg.frontier)}',
            f'    stuck: {len(self.kcfg.stuck)}',
            'Subproofs' if len(self.subproof_ids) else '',
        ]
        for summary in subproofs_summaries:
            yield from summary

    def refute_edge(self, edge: KCFG.Edge) -> str:
        """Refute an edge by constructing a subproof of the edge target's path condition being equivalent to False"""
        if not edge in self.kcfg.edges():
            raise ValueError(f'No edge between {edge.source.id} and {edge.target.id}')

        self.kcfg.add_expanded(edge.target.id)

        target_condition = andBool([ml_pred_to_bool(expr) for expr in edge.target.cterm.constraints])
        refutation = EqualityProof(
            id=f'infeasible-{shorten_hash(edge.source.id)}-to-{shorten_hash(edge.target.id)}',
            lhs_body=target_condition,
            rhs_body=FALSE,
            sort=BOOL,
            proof_dir=self.proof_dir,
        )
        refutation.write_proof()
        self.add_subproof(refutation.id)
        return refutation.id

    def refute_node(self, node: KCFG.Node, assuming: KInner | None = None) -> str:
        """Refute a node by constructing a subproof of the node's path condition being False"""
        if not node in self.kcfg.nodes:
            raise ValueError(f'No such node {node.id}')

        self.kcfg.add_expanded(node.id)

        path = single(self.kcfg.paths_between(source_id=self.kcfg.get_unique_init().id, target_id=node.id))
        closest_split = list(filter(lambda x: type(x) is KCFG.Split, reversed(path)))[0]

        assert type(closest_split) is KCFG.Split
        _, csubst = closest_split.targets[0]
        # assert csubst.subst is empty
        assert len(csubst.constraints) == 1
        last_constraint = ml_pred_to_bool(csubst.constraints[0])

        # constraints = closest_split.source.cterm.constraints
        constraints = [
            mlEquals(TRUE, ml_pred_to_bool(c), arg_sort=BOOL) for c in closest_split.source.cterm.constraints
        ]

        assert assuming
        constraints.append(mlEquals(TRUE, assuming, arg_sort=BOOL))
        # condition = andBool([ml_pred_to_bool(expr) for expr in node.cterm.constraints])
        # if assuming is not None:
        #     condition = andBool([assuming, condition])
        refutation = EqualityProof(
            id=f'infeasible-{shorten_hash(node.id)}',
            lhs_body=last_constraint,
            constraints=constraints,
            rhs_body=FALSE,
            sort=BOOL,
            proof_dir=self.proof_dir,
        )
        refutation.write_proof()
        self.add_subproof(refutation.id)
        self.write_proof()
        return refutation.id


class APRBMCProof(APRProof):
    """APRBMCProof and APRBMCProver perform bounded model-checking of an all-path reachability logic claim."""

    bmc_depth: int
    _bounded_states: list[str]

    def __init__(
        self,
        id: str,
        kcfg: KCFG,
        bmc_depth: int,
        bounded_states: Iterable[str] | None = None,
        proof_dir: Path | None = None,
        subproof_ids: list[str] | None = None,
    ):
        super().__init__(id, kcfg, proof_dir=proof_dir, subproof_ids=subproof_ids)
        self.bmc_depth = bmc_depth
        self._bounded_states = list(bounded_states) if bounded_states is not None else []

    @staticmethod
    def read_proof(id: str, proof_dir: Path) -> APRBMCProof:
        proof_path = proof_dir / f'{hash_str(id)}.json'
        if APRBMCProof.proof_exists(id, proof_dir):
            proof_dict = json.loads(proof_path.read_text())
            _LOGGER.info(f'Reading APRBMCProof from file {id}: {proof_path}')
            return APRBMCProof.from_dict(proof_dict, proof_dir=proof_dir)
        raise ValueError(f'Could not load APRBMCProof from file {id}: {proof_path}')

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
        return APRBMCProof(
            id, cfg, bmc_depth, bounded_states=bounded_states, proof_dir=proof_dir, subproof_ids=subproof_ids
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
        }
        return result

    def bound_state(self, nid: str) -> None:
        self._bounded_states.append(nid)

    @property
    def summary(self) -> Iterable[str]:
        subproofs_summaries = chain(subproof.summary for subproof in self.read_subproofs())
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
                execute_depth=execute_depth,
                cut_point_rules=cut_point_rules,
                terminal_rules=terminal_rules,
            )

        self.proof.write_proof()
        return self.proof.kcfg


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
