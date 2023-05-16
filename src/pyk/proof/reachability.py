from __future__ import annotations

import json
import logging
from typing import TYPE_CHECKING

from pyk.kore.rpc import LogEntry

from ..kast.inner import KRewrite, KSort
from ..kast.manip import ml_pred_to_bool
from ..kast.outer import KClaim
from ..kcfg import KCFG, path_length
from ..prelude.ml import mlAnd
from ..utils import hash_str, shorten_hashes, single
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
    dependencies: list[APRProof]  # list of dependencies other than self
    circularity: bool
    logs: dict[str, tuple[LogEntry, ...]]

    def __init__(
        self,
        id: str,
        kcfg: KCFG,
        logs: dict[str, tuple[LogEntry, ...]],
        proof_dir: Path | None = None,
        dependencies: Iterable[APRProof] = (),
        circularity: bool = False,
    ):
        super().__init__(id, proof_dir=proof_dir)
        self.kcfg = kcfg
        self.logs = logs
        self.dependencies = list(dependencies)
        self.circularity = circularity

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
        dependencies = [APRProof.from_dict(c) for c in dct['dependencies']]
        circularity = dct['circularity']
        if 'logs' in dct:
            logs = {k: tuple(LogEntry.from_dict(l) for l in ls) for k, ls in dct['logs'].items()}
        else:
            logs = {}
        return APRProof(id, cfg, logs=logs, proof_dir=proof_dir, dependencies=dependencies, circularity=circularity)

    @property
    def dict(self) -> dict[str, Any]:
        logs = {k: [l.to_dict() for l in ls] for k, ls in self.logs.items()}
        return {
            'type': 'APRProof',
            'id': self.id,
            'cfg': self.kcfg.to_dict(),
            'dependencies': [c.dict for c in self.dependencies],
            'logs': logs,
            'circularity': self.circularity,
        }

    @property
    def summary(self) -> Iterable[str]:
        return [
            f'APRProof: {self.id}',
            f'    status: {self.status}',
            f'    nodes: {len(self.kcfg.nodes)}',
            f'    frontier: {len(self.kcfg.frontier)}',
            f'    stuck: {len(self.kcfg.stuck)}',
        ]


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
    ):
        super().__init__(id, kcfg, logs, proof_dir=proof_dir)
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
        if 'logs' in dct:
            logs = {k: tuple(LogEntry.from_dict(l) for l in ls) for k, ls in dct['logs'].items()}
        else:
            logs = {}
        return APRBMCProof(id, cfg, logs, bmc_depth, bounded_states=bounded_states, proof_dir=proof_dir)

    @property
    def dict(self) -> dict[str, Any]:
        logs = {k: [l.to_dict() for l in ls] for k, ls in self.logs.items()}
        return {
            'type': 'APRBMCProof',
            'id': self.id,
            'cfg': self.kcfg.to_dict(),
            'logs': logs,
            'bmc_depth': self.bmc_depth,
            'bounded_states': self._bounded_states,
        }

    def bound_state(self, nid: str) -> None:
        self._bounded_states.append(nid)

    @property
    def summary(self) -> Iterable[str]:
        return [
            f'APRBMCProof(depth={self.bmc_depth}): {self.id}',
            f'    status: {self.status}',
            f'    nodes: {len(self.kcfg.nodes)}',
            f'    frontier: {len(self.kcfg.frontier)}',
            f'    stuck: {len([nd for nd in self.kcfg.stuck if nd.id not in self._bounded_states])}',
            f'    bmc-depth-bounded: {len(self._bounded_states)}',
        ]


class APRProver:
    proof: APRProof
    kcfg_explore: KCFGExplore
    _is_terminal: Callable[[CTerm], bool] | None
    _extract_branches: Callable[[CTerm], Iterable[KInner]] | None

    main_module_name: str
    some_dependencies_module_name: str
    all_dependencies_module_name: str

    def __init__(
        self,
        proof: APRProof,
        kcfg_explore: KCFGExplore,
        is_terminal: Callable[[CTerm], bool] | None = None,
        extract_branches: Callable[[CTerm], Iterable[KInner]] | None = None,
    ) -> None:
        self.proof = proof
        self.kcfg_explore = kcfg_explore
        self._is_terminal = is_terminal
        self._extract_branches = extract_branches
        self.main_module_name = self.kcfg_explore.kprint.definition.main_module_name

        def build_claim(pf: APRProof) -> KClaim:
            fr: CTerm = single(pf.kcfg.init).cterm
            to: CTerm = single(pf.kcfg.target).cterm
            fr_config_sorted = self.kcfg_explore.kprint.definition.sort_vars(fr.config, sort=KSort('GeneratedTopCell'))
            to_config_sorted = self.kcfg_explore.kprint.definition.sort_vars(to.config, sort=KSort('GeneratedTopCell'))
            kc = KClaim(
                body=KRewrite(fr_config_sorted, to_config_sorted),
                requires=ml_pred_to_bool(mlAnd(fr.constraints)),
                ensures=ml_pred_to_bool(mlAnd(to.constraints)),
            )
            return kc

        dependencies_as_claims: list[KClaim] = [build_claim(d) for d in proof.dependencies]
        self.some_dependencies_module_name = self.main_module_name + '-DEPENDS-MODULE'
        self.kcfg_explore.add_dependencies_module(
            self.main_module_name,
            self.some_dependencies_module_name,
            dependencies_as_claims,
            priority=1,
        )
        self.all_dependencies_module_name = self.main_module_name + '-CIRCULARITIES-MODULE'
        self.kcfg_explore.add_dependencies_module(
            self.main_module_name,
            self.all_dependencies_module_name,
            dependencies_as_claims + ([build_claim(proof)] if proof.circularity else []),
            priority=1,
        )

    def _check_terminal(self, curr_node: KCFG.Node) -> bool:
        if self._is_terminal is not None:
            _LOGGER.info(f'Checking terminal {self.proof.id}: {shorten_hashes(curr_node.id)}')
            if self._is_terminal(curr_node.cterm):
                _LOGGER.info(f'Terminal node {self.proof.id}: {shorten_hashes(curr_node.id)}.')
                self.proof.kcfg.add_expanded(curr_node.id)
                return True
        return False

    def nonzero_depth(self, node: KCFG.Node) -> bool:
        init = self.proof.kcfg.get_unique_init()
        p = self.proof.kcfg.shortest_path_between(init.id, node.id)
        if p is None:
            return False
        return path_length(p) > 0

    def advance_proof(
        self,
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

            if self.kcfg_explore.target_subsume(self.proof.kcfg, curr_node):
                continue

            if self._check_terminal(curr_node):
                continue

            if self._extract_branches is not None and len(self.proof.kcfg.splits(target_id=curr_node.id)) == 0:
                branches = list(self._extract_branches(curr_node.cterm))
                if len(branches) > 0:
                    self.proof.kcfg.split_on_constraints(curr_node.id, branches)
                    _LOGGER.info(
                        f'Found {len(branches)} branches using heuristic for node {self.proof.id}: {shorten_hashes(curr_node.id)}: {[self.kcfg_explore.kprint.pretty_print(bc) for bc in branches]}'
                    )
                    continue

            module_name = (
                self.all_dependencies_module_name
                if self.nonzero_depth(curr_node)
                else self.some_dependencies_module_name
            )
            self.kcfg_explore.extend(
                self.proof.kcfg,
                curr_node,
                self.proof.logs,
                execute_depth=execute_depth,
                cut_point_rules=cut_point_rules,
                terminal_rules=terminal_rules,
                module_name=module_name,
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
        kcfg_explore: KCFGExplore,
        same_loop: Callable[[CTerm, CTerm], bool],
        is_terminal: Callable[[CTerm], bool] | None = None,
        extract_branches: Callable[[CTerm], Iterable[KInner]] | None = None,
    ) -> None:
        super().__init__(
            proof,
            kcfg_explore=kcfg_explore,
            is_terminal=is_terminal,
            extract_branches=extract_branches,
        )
        self._same_loop = same_loop
        self._checked_nodes = []

    def advance_proof(
        self,
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
                max_iterations=1,
                execute_depth=execute_depth,
                cut_point_rules=cut_point_rules,
                terminal_rules=terminal_rules,
                implication_every_block=implication_every_block,
            )

        self.proof.write_proof()
        return self.proof.kcfg
