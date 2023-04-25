from __future__ import annotations

import json
import logging
from itertools import chain
from typing import TYPE_CHECKING, List

from ..kcfg import KCFG
from ..utils import hash_str, shorten_hashes
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

    def __init__(self, id: str, kcfg: KCFG, proof_dir: Path | None = None, subproofs: List[Proof] | None = None):
        super().__init__(id, proof_dir=proof_dir, subproofs=subproofs)
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
        if len(self.kcfg.stuck) > 0:
            return ProofStatus.FAILED
        elif len(self.kcfg.frontier) > 0:
            return ProofStatus.PENDING
        else:
            return ProofStatus.PASSED

    @classmethod
    def from_dict(cls: type[APRProof], dct: Mapping[str, Any], proof_dir: Path | None = None) -> APRProof:
        cfg = KCFG.from_dict(dct['cfg'])
        id = dct['id']
        subproof_dicts = dct['subproofs'] if 'subproofs' in dct else []
        subproofs: List[Proof] = []
        for subproof_dict in subproof_dicts:
            match subproof_dict['type']:
                case 'APRProof':
                    subproofs.append(APRProof.from_dict(subproof_dict))
                case 'APRBMCProof':
                    subproofs.append(APRBMCProof.from_dict(subproof_dict))
                case 'EqualityProof':
                    subproofs.append(EqualityProof.from_dict(subproof_dict))
        return APRProof(id, cfg, proof_dir=proof_dir, subproofs=subproofs)

    @property
    def dict(self) -> dict[str, Any]:
        result: dict[str, Any] = {'type': 'APRProof', 'id': self.id, 'cfg': self.kcfg.to_dict()}
        if len(self.subproofs):
            result['subproofs'] = [subproof.dict for subproof in self.subproofs]
        return result

    @property
    def summary(self) -> Iterable[str]:
        subproofs_summaries = [subproof.summary for subproof in self.subproofs]
        return chain(
            f'APRProof: {self.id}',
            f'    status: {self.status}',
            f'    nodes: {len(self.kcfg.nodes)}',
            f'    frontier: {len(self.kcfg.frontier)}',
            f'    stuck: {len(self.kcfg.stuck)}',
            *subproofs_summaries,
        )


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
        subproofs: List[Proof] | None = None,
    ):
        super().__init__(id, kcfg, proof_dir=proof_dir, subproofs=subproofs)
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
        if any(nd.id not in self._bounded_states for nd in self.kcfg.stuck):
            return ProofStatus.FAILED
        elif len(self.kcfg.frontier) > 0:
            return ProofStatus.PENDING
        else:
            return ProofStatus.PASSED

    @classmethod
    def from_dict(cls: type[APRBMCProof], dct: Mapping[str, Any], proof_dir: Path | None = None) -> APRBMCProof:
        cfg = KCFG.from_dict(dct['cfg'])
        id = dct['id']
        bounded_states = dct['bounded_states']
        bmc_depth = dct['bmc_depth']
        subproof_dicts = dct['subproofs'] if 'subproofs' in dct else []
        subproofs: List[Proof] = []
        for subproof_dict in subproof_dicts:
            match subproof_dict['type']:
                case 'APRProof':
                    subproofs.append(APRProof.from_dict(subproof_dict))
                case 'APRBMCProof':
                    subproofs.append(APRBMCProof.from_dict(subproof_dict))
                case 'EqualityProof':
                    subproofs.append(EqualityProof.from_dict(subproof_dict))
        return APRBMCProof(id, cfg, bmc_depth, bounded_states=bounded_states, proof_dir=proof_dir, subproofs=subproofs)

    @property
    def dict(self) -> dict[str, Any]:
        result = {
            'type': 'APRBMCProof',
            'id': self.id,
            'cfg': self.kcfg.to_dict(),
            'bmc_depth': self.bmc_depth,
            'bounded_states': self._bounded_states,
        }
        if len(self.subproofs):
            result['subproofs'] = [subproof.dict for subproof in self.subproofs]
        return result

    def bound_state(self, nid: str) -> None:
        self._bounded_states.append(nid)

    @property
    def summary(self) -> Iterable[str]:
        subproofs_summaries = [subproof.summary for subproof in self.subproofs]
        return chain(
            f'APRBMCProof(depth={self.bmc_depth}): {self.id}',
            f'    status: {self.status}',
            f'    nodes: {len(self.kcfg.nodes)}',
            f'    frontier: {len(self.kcfg.frontier)}',
            f'    stuck: {len([nd for nd in self.kcfg.stuck if nd.id not in self._bounded_states])}',
            f'    bmc-depth-bounded: {len(self._bounded_states)}',
            *subproofs_summaries,
        )


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
