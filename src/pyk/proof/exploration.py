from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from typing import TYPE_CHECKING

from pyk.kore.rpc import LogEntry

from ..kast.manip import flatten_label
from ..kcfg import KCFG
from ..prelude.ml import mlAnd, mlTop
from ..utils import hash_str, shorten_hashes
from .equality import ProofSummary
from .proof import CompositeSummary, Proof, ProofStatus, Prover

if TYPE_CHECKING:
    from collections.abc import Iterable, Mapping
    from pathlib import Path
    from typing import Any, Final, TypeVar

    from ..kast.inner import KInner
    from ..kcfg import KCFGExplore
    from ..kcfg.kcfg import NodeIdLike

    T = TypeVar('T', bound='Proof')

_LOGGER: Final = logging.getLogger(__name__)


class ExplorationProof(Proof):
    kcfg: KCFG
    init: NodeIdLike
    logs: dict[int, tuple[LogEntry, ...]]

    _leaf_node_ids: set[int]
    _stuck_node_ids: set[int]
    _terminal_node_ids: set[int]
    _pending_node_ids: set[int]

    def __init__(
        self,
        id: str,
        kcfg: KCFG,
        init: NodeIdLike,
        logs: dict[int, tuple[LogEntry, ...]],
        proof_dir: Path | None = None,
        terminal_node_ids: Iterable[NodeIdLike] | None = None,
    ):
        super().__init__(id, proof_dir=proof_dir, subproof_ids=[], admitted=False)
        self.kcfg = kcfg
        self.init = init
        self.logs = logs

        self._terminal_node_ids = {
            kcfg._resolve(terminal_node_id)
            for terminal_node_id in (terminal_node_ids if terminal_node_ids is not None else [])
        }
        self.update()

    def update(self) -> None:
        self._leaf_node_ids = {node.id for node in self.kcfg.leaves}
        self._stuck_node_ids = {node.id for node in self.kcfg.stuck}
        self._pending_node_ids = self._leaf_node_ids.difference(self._terminal_node_ids).difference(
            self._stuck_node_ids
        )

        # Correctness checks
        assert self._stuck_node_ids.intersection(self._terminal_node_ids) == set()
        assert self._leaf_node_ids == self._stuck_node_ids.union(self._terminal_node_ids).union(self._pending_node_ids)

    def is_terminal(self, node_id: NodeIdLike) -> bool:
        return self.kcfg._resolve(node_id) in self._terminal_node_ids

    def is_pending(self, node_id: NodeIdLike) -> bool:
        return self.kcfg._resolve(node_id) in self._pending_node_ids

    def is_init(self, node_id: NodeIdLike) -> bool:
        return self.kcfg._resolve(node_id) == self.kcfg._resolve(self.init)

    @property
    def pending(self) -> list[KCFG.Node]:
        return [self.kcfg.node(id) for id in self._pending_node_ids]

    def add_terminal(self, node_id: NodeIdLike) -> None:
        resolved_node_id = self.kcfg._resolve(node_id)

        # Correctness checks
        assert resolved_node_id in self._pending_node_ids

        self._terminal_node_ids.add(resolved_node_id)
        self._pending_node_ids.remove(resolved_node_id)

    def shortest_path_to(self, node_id: NodeIdLike) -> tuple[KCFG.Successor, ...]:
        spb = self.kcfg.shortest_path_between(self.init, node_id)
        assert spb is not None
        return spb

    @staticmethod
    def read_proof(id: str, proof_dir: Path) -> ExplorationProof:
        proof_path = proof_dir / f'{hash_str(id)}.json'
        if ExplorationProof.proof_exists(id, proof_dir):
            proof_dict = json.loads(proof_path.read_text())
            _LOGGER.info(f'Reading ExplorationProof from file {id}: {proof_path}')
            return ExplorationProof.from_dict(proof_dict, proof_dir=proof_dir)
        raise ValueError(f'Could not load ExplorationProof from file {id}: {proof_path}')

    @property
    def status(self) -> ProofStatus:
        if len(self._stuck_node_ids) > 0:
            return ProofStatus.FAILED
        elif len(self._pending_node_ids) > 0:
            return ProofStatus.PENDING
        else:
            return ProofStatus.COMPLETED

    @classmethod
    def from_dict(
        cls: type[ExplorationProof], dct: Mapping[str, Any], proof_dir: Path | None = None
    ) -> ExplorationProof:
        cfg = KCFG.from_dict(dct['cfg'])
        init_node = dct['init']
        terminal_node_ids = dct['terminal_node_ids']
        id = dct['id']
        if 'logs' in dct:
            logs = {k: tuple(LogEntry.from_dict(l) for l in ls) for k, ls in dct['logs'].items()}
        else:
            logs = {}

        return ExplorationProof(
            id,
            cfg,
            init_node,
            logs=logs,
            terminal_node_ids=terminal_node_ids,
            proof_dir=proof_dir,
        )

    def path_constraints(self, final_node_id: NodeIdLike) -> KInner:
        path = self.shortest_path_to(final_node_id)
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
        dct = super().dict
        dct['type'] = 'ExplorationProof'
        dct['cfg'] = self.kcfg.to_dict()
        dct['init'] = self.init
        dct['terminal_node_ids'] = self._terminal_node_ids
        logs = {k: [l.to_dict() for l in ls] for k, ls in self.logs.items()}
        dct['logs'] = logs
        return dct

    @property
    def summary(self) -> CompositeSummary:
        return CompositeSummary(
            [
                ExplorationSummary(
                    self.id,
                    self.status,
                    len(self.kcfg.nodes),
                    len(self._pending_node_ids),
                    len(self._stuck_node_ids),
                    len(self._terminal_node_ids),
                ),
            ]
        )

    def get_refutation_id(self, node_id: int) -> str:
        return f'{self.id}.node-infeasible-{node_id}'


class ExplorationProver(Prover):
    proof: ExplorationProof

    main_module_name: str
    dependencies_module_name: str

    def __init__(
        self,
        proof: ExplorationProof,
        kcfg_explore: KCFGExplore,
    ) -> None:
        super().__init__(kcfg_explore)
        self.proof = proof
        self.main_module_name = self.kcfg_explore.kprint.definition.main_module_name

        self.dependencies_module_name = self.main_module_name + '-DEPENDS-MODULE'
        self.kcfg_explore.add_dependencies_module(
            self.main_module_name,
            self.dependencies_module_name,
            [],
            priority=1,
        )

        self.update()

    def update(self) -> None:
        self.proof.update()
        pending_node_ids = sorted(self.proof._pending_node_ids)
        for id in pending_node_ids:
            self._check_terminal(id)

        # Correctness checks
        for id in self.proof._terminal_node_ids:
            assert self.kcfg_explore.kcfg_semantics.is_terminal(self.proof.kcfg.node(id).cterm)
        for id in self.proof._pending_node_ids.union(self.proof._stuck_node_ids):
            assert not (self.kcfg_explore.kcfg_semantics.is_terminal(self.proof.kcfg.node(id).cterm))

    def get_module_name(self, node: KCFG.Node) -> str:
        return self.dependencies_module_name

    def _check_terminal(self, node_id: int) -> None:
        _LOGGER.info(f'Checking terminal: {shorten_hashes(node_id)}')
        if self.kcfg_explore.kcfg_semantics.is_terminal(self.proof.kcfg.node(node_id).cterm):
            _LOGGER.info(f'Terminal node: {shorten_hashes(node_id)}.')
            self.proof.add_terminal(node_id)

    def advance_pending_node(
        self,
        node: KCFG.Node,
        module_name: str,
        execute_depth: int | None = None,
        cut_point_rules: Iterable[str] = (),
        terminal_rules: Iterable[str] = (),
    ) -> None:
        self.kcfg_explore.extend(
            self.proof.kcfg,
            node,
            self.proof.logs,
            execute_depth=execute_depth,
            cut_point_rules=cut_point_rules,
            terminal_rules=terminal_rules,
            module_name=module_name,
        )

    def advance_proof(
        self,
        max_iterations: int | None = None,
        execute_depth: int | None = None,
        cut_point_rules: Iterable[str] = (),
        terminal_rules: Iterable[str] = (),
    ) -> KCFG:
        iterations = 0

        while self.proof._pending_node_ids:
            self.proof.write_proof()

            if max_iterations is not None and max_iterations <= iterations:
                _LOGGER.warning(f'Reached iteration bound {self.proof.id}: {max_iterations}')
                break
            iterations += 1
            curr_node = self.proof.kcfg.node(next(iter(self.proof._pending_node_ids)))

            module_name = self.get_module_name(curr_node)

            self.advance_pending_node(
                node=curr_node,
                module_name=module_name,
                execute_depth=execute_depth,
                cut_point_rules=cut_point_rules,
                terminal_rules=terminal_rules,
            )
            self.update()

        self.proof.write_proof()
        return self.proof.kcfg


@dataclass(frozen=True)
class ExplorationSummary(ProofSummary):
    id: str
    status: ProofStatus
    nodes: int
    pending: int
    stuck: int
    terminal: int

    @property
    def lines(self) -> list[str]:
        return [
            f'ExplorationProof: {self.id}',
            f'    status: {self.status}',
            f'    nodes: {self.nodes}',
            f'    pending: {self.pending}',
            f'    stuck: {self.stuck}',
            f'    terminal: {self.terminal}',
        ]
