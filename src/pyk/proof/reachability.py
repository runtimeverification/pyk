from __future__ import annotations

import json
import logging
from typing import TYPE_CHECKING

from pyk.kore.rpc import LogEntry

from ..kast.inner import KRewrite, KSort
from ..kast.manip import flatten_label, ml_pred_to_bool
from ..kast.outer import KClaim
from ..kcfg import KCFG, path_length
from ..prelude.ml import mlAnd, mlTop
from ..utils import hash_str, shorten_hashes, single
from .proof import Proof, ProofStatus

if TYPE_CHECKING:
    from collections.abc import Callable, Iterable, Mapping
    from pathlib import Path
    from typing import Any, Final, TypeVar

    from ..cterm import CTerm
    from ..kast.inner import KInner
    from ..kast.outer import KDefinition
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
    init: NodeIdLike
    target: NodeIdLike
    _terminal_nodes: list[NodeIdLike]
    logs: dict[int, tuple[LogEntry, ...]]
    dependencies: list[APRProof]  # list of dependencies other than self
    circularity: bool

    def __init__(
        self,
        id: str,
        kcfg: KCFG,
        init: NodeIdLike,
        target: NodeIdLike,
        logs: dict[int, tuple[LogEntry, ...]],
        terminal_nodes: Iterable[NodeIdLike] | None = None,
        proof_dir: Path | None = None,
        dependencies: Iterable[APRProof] = (),
        circularity: bool = False,
    ):
        super().__init__(id, proof_dir=proof_dir)
        self.kcfg = kcfg
        self.init = init
        self.target = target
        self.logs = logs
        self.dependencies = list(dependencies)
        self.circularity = circularity
        self._terminal_nodes = list(terminal_nodes) if terminal_nodes is not None else []

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

    def is_terminal(self, node_id: NodeIdLike) -> bool:
        return self.kcfg._resolve(node_id) in (nd.id for nd in self.terminal)

    def is_pending(self, node_id: NodeIdLike) -> bool:
        return self.kcfg._resolve(node_id) in (nd.id for nd in self.pending)

    @staticmethod
    def read_proof(id: str, proof_dir: Path) -> APRProof:
        proof_path = proof_dir / f'{hash_str(id)}.json'
        if APRProof.proof_exists(id, proof_dir):
            proof_dict = json.loads(proof_path.read_text())
            _LOGGER.info(f'Reading APRProof from file {id}: {proof_path}')
            return APRProof.from_dict(proof_dict, proof_dir=proof_dir)
        raise ValueError(f'Could not load APRProof from file {id}: {proof_path}')

    def write_proof(self) -> None:
        for d in self.dependencies:
            d.write_proof()
        super().write_proof()

    @property
    def status(self) -> ProofStatus:
        if len(self.terminal) > 0:
            return ProofStatus.FAILED
        elif len(self.pending) > 0:
            return ProofStatus.PENDING
        else:
            return ProofStatus.PASSED

    @classmethod
    def from_dict(cls: type[APRProof], dct: Mapping[str, Any], proof_dir: Path | None = None) -> APRProof:
        cfg = KCFG.from_dict(dct['cfg'])
        init_node = dct['init']
        target_node = dct['target']
        id = dct['id']
        if len(dct['dependencies']) > 0:
            if proof_dir is None:
                raise ValueError('The serialized proof has dependencies but no proof_dir was specified')
            dependencies = [APRProof.read_proof(id, proof_dir=proof_dir) for id in dct['dependencies']]
        circularity = dct.get('circularity', False)
        if 'logs' in dct:
            logs = {k: tuple(LogEntry.from_dict(l) for l in ls) for k, ls in dct['logs'].items()}
        else:
            logs = {}

        return APRProof(
            id,
            cfg,
            init_node,
            target_node,
            logs=logs,
            proof_dir=proof_dir,
            dependencies=dependencies,
            circularity=circularity,
        )

    @staticmethod
    def from_claim(defn: KDefinition, claim: KClaim, *args: Any, **kwargs: Any) -> APRProof:
        cfg, init_node, target_node = KCFG.from_claim(defn, claim)
        return APRProof(claim.label, cfg, init=init_node, target=target_node, logs={}, **kwargs)

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
            'dependencies': [c.id for c in self.dependencies],
            'circularity': self.circularity,
            'logs': logs,
        }

    def add_terminal(self, nid: NodeIdLike) -> None:
        self._terminal_nodes.append(self.kcfg._resolve(nid))

    @property
    def summary(self) -> Iterable[str]:
        return [
            f'APRProof: {self.id}',
            f'    status: {self.status}',
            f'    nodes: {len(self.kcfg.nodes)}',
            f'    pending: {len(self.pending)}',
            f'    terminal: {len(self.terminal)}',
        ]


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
        dependencies: Iterable[APRProof] = (),
        circularity: bool = False,
    ):
        super().__init__(
            id, kcfg, init, target, logs, proof_dir=proof_dir, dependencies=dependencies, circularity=circularity
        )
        self.bmc_depth = bmc_depth
        self._bounded_nodes = list(bounded_nodes) if bounded_nodes is not None else []

    @staticmethod
    def read_proof(id: str, proof_dir: Path) -> APRBMCProof:
        proof_path = proof_dir / f'{hash_str(id)}.json'
        if APRBMCProof.proof_exists(id, proof_dir):
            proof_dict = json.loads(proof_path.read_text())
            _LOGGER.info(f'Reading APRBMCProof from file {id}: {proof_path}')
            return APRBMCProof.from_dict(proof_dict, proof_dir=proof_dir)
        raise ValueError(f'Could not load APRBMCProof from file {id}: {proof_path}')

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

    def is_bounded(self, node_id: NodeIdLike) -> bool:
        return self.kcfg._resolve(node_id) in (nd.id for nd in self.bounded)

    @property
    def status(self) -> ProofStatus:
        if len(self.terminal) > 0:
            return ProofStatus.FAILED
        elif len(self.pending) > 0:
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
        dependencies = [APRProof.from_dict(c) for c in dct['dependencies']]
        circularity = dct.get('circularity', False)
        bmc_depth = dct['bmc_depth']
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
            dependencies=dependencies,
            circularity=circularity,
        )

    @staticmethod
    def from_claim_with_bmc_depth(defn: KDefinition, claim: KClaim, bmc_depth: int) -> APRBMCProof:
        cfg, init_node, target_node = KCFG.from_claim(defn, claim)
        return APRBMCProof(claim.label, cfg, init_node, target_node, {}, bmc_depth)

    @property
    def dict(self) -> dict[str, Any]:
        logs = {k: [l.to_dict() for l in ls] for k, ls in self.logs.items()}
        dct = super().dict
        dct['type'] = 'APRBMCProof'
        dct['bmc_depth'] = self.bmc_depth
        dct['bounded_nodes'] = self._bounded_nodes
        dct['logs'] = logs
        dct['dependencies'] = [c.dict for c in self.dependencies]
        dct['circularity'] = self.circularity
        return dct

    def add_bounded(self, nid: NodeIdLike) -> None:
        self._bounded_nodes.append(self.kcfg._resolve(nid))

    @property
    def summary(self) -> Iterable[str]:
        return [
            f'APRBMCProof(depth={self.bmc_depth}): {self.id}',
            f'    status: {self.status}',
            f'    nodes: {len(self.kcfg.nodes)}',
            f'    pending: {len(self.pending)}',
            f'    terminal: {len(self.terminal)}',
            f'    bounded: {len(self.bounded)}',
        ]


class APRProver:
    proof: APRProof
    kcfg_explore: KCFGExplore
    _is_terminal: Callable[[CTerm], bool] | None
    _extract_branches: Callable[[CTerm], Iterable[KInner]] | None
    _abstract_node: Callable[[CTerm], CTerm] | None

    main_module_name: str
    some_dependencies_module_name: str
    all_dependencies_module_name: str

    def __init__(
        self,
        proof: APRProof,
        kcfg_explore: KCFGExplore,
        is_terminal: Callable[[CTerm], bool] | None = None,
        extract_branches: Callable[[CTerm], Iterable[KInner]] | None = None,
        abstract_node: Callable[[CTerm], CTerm] | None = None,
    ) -> None:
        self.proof = proof
        self.kcfg_explore = kcfg_explore
        self._is_terminal = is_terminal
        self._extract_branches = extract_branches
        self._abstract_node = abstract_node
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
                self.proof.add_terminal(curr_node.id)
                self.proof.kcfg.add_expanded(curr_node.id)
                return True
        return False

    def nonzero_depth(self, node: KCFG.Node) -> bool:
        init = self.proof.kcfg.get_unique_init()
        p = self.proof.kcfg.shortest_path_between(init.id, node.id)
        if p is None:
            return False
        return path_length(p) > 0

    def _check_subsume(self, node: KCFG.Node) -> bool:
        target_node = self.proof.kcfg.node(self.proof.target)
        _LOGGER.info(
            f'Checking subsumption into target state {self.proof.id}: {shorten_hashes((node.id, target_node.id))}'
        )
        csubst = self.kcfg_explore.cterm_implies(node.cterm, target_node.cterm)
        if csubst is not None:
            self.proof.kcfg.create_cover(node.id, target_node.id, csubst=csubst)
            _LOGGER.info(f'Subsumed into target node {self.proof.id}: {shorten_hashes((node.id, target_node.id))}')
            return True
        return False

    def _check_abstract(self, node: KCFG.Node) -> bool:
        if self._abstract_node is None:
            return False

        new_cterm = self._abstract_node(node.cterm)
        if new_cterm == node.cterm:
            return False

        new_node = self.proof.kcfg.create_node(new_cterm)
        self.proof.kcfg.create_cover(node.id, new_node.id)
        return True

    def advance_proof(
        self,
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

            if self._check_subsume(curr_node):
                continue

            if self._check_terminal(curr_node):
                continue

            if self._check_abstract(curr_node):
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
    _checked_nodes: list[int]

    def __init__(
        self,
        proof: APRBMCProof,
        kcfg_explore: KCFGExplore,
        same_loop: Callable[[CTerm, CTerm], bool],
        is_terminal: Callable[[CTerm], bool] | None = None,
        extract_branches: Callable[[CTerm], Iterable[KInner]] | None = None,
        abstract_node: Callable[[CTerm], CTerm] | None = None,
    ) -> None:
        super().__init__(
            proof,
            kcfg_explore=kcfg_explore,
            is_terminal=is_terminal,
            extract_branches=extract_branches,
            abstract_node=abstract_node,
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
                max_iterations=1,
                execute_depth=execute_depth,
                cut_point_rules=cut_point_rules,
                terminal_rules=terminal_rules,
                implication_every_block=implication_every_block,
            )

        self.proof.write_proof()
        return self.proof.kcfg
