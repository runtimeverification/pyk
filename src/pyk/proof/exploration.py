from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from typing import TYPE_CHECKING

from pyk.kore.rpc import LogEntry

from ..kast.manip import flatten_label
from ..kcfg import KCFG
from ..prelude.ml import mlAnd, mlTop
from ..utils import ensure_dir_path, hash_str, shorten_hashes
from .equality import ProofSummary
from .proof import CompositeSummary, Proof, ProofStatus, Prover

if TYPE_CHECKING:
    from collections.abc import Iterable, Mapping
    from pathlib import Path
    from typing import Any, Final, TypeVar

    from ..kast.inner import KInner
    from ..kast.outer import KClaim
    from ..kcfg import KCFGExplore
    from ..kcfg.kcfg import NodeIdLike

    T = TypeVar('T', bound='Proof')

_LOGGER: Final = logging.getLogger(__name__)


class ExplorationProof(Proof):
    kcfg: KCFG
    init: int
    logs: dict[int, tuple[LogEntry, ...]]

    _terminal_node_ids: set[int]

    def __init__(
        self,
        id: str,
        kcfg: KCFG,
        init: NodeIdLike,
        logs: dict[int, tuple[LogEntry, ...]],
        proof_dir: Path | None = None,
        terminal_node_ids: Iterable[NodeIdLike] | None = None,
        subproof_ids: Iterable[str] = (),
        admitted: bool = False,
    ):
        if type(self) == ExplorationProof:
            if subproof_ids:
                raise ValueError('Subproofs provided for an ExplorationProof')
            if admitted:
                raise ValueError('Admitted ExplorationProof')

        super().__init__(id, proof_dir=proof_dir, subproof_ids=subproof_ids, admitted=admitted)
        self.kcfg = kcfg
        self.init = kcfg._resolve(init)
        self.logs = logs

        self._terminal_node_ids = {
            kcfg._resolve(terminal_node_id)
            for terminal_node_id in (terminal_node_ids if terminal_node_ids is not None else [])
        }

        self.kcfg.cfg_dir = self.proof_subdir / 'kcfg' if self.proof_subdir else None

        if self.proof_dir is not None and self.proof_subdir is not None:
            ensure_dir_path(self.proof_dir)
            ensure_dir_path(self.proof_subdir)

    def is_init(self, node_id: NodeIdLike) -> bool:
        return self.kcfg._resolve(node_id) == self.init

    def is_terminal(self, node_id: NodeIdLike) -> bool:
        return self.kcfg._resolve(node_id) in self._terminal_node_ids

    def is_pending(self, node_id: NodeIdLike) -> bool:
        return self.kcfg.is_leaf(node_id) and not self.is_terminal(node_id) and not self.kcfg.is_stuck(node_id)

    @property
    def pending(self) -> list[KCFG.Node]:
        return [nd for nd in self.kcfg.leaves if self.is_pending(nd.id)]

    @property
    def failing(self) -> list[KCFG.Node]:
        return []

    def add_terminal(self, node_id: NodeIdLike) -> None:
        self._terminal_node_ids.add(self.kcfg._resolve(node_id))

    def remove_terminal(self, node_id: NodeIdLike) -> None:
        node_id = self.kcfg._resolve(node_id)
        if node_id not in self._terminal_node_ids:
            raise ValueError(f'Node is not terminal: {node_id}')
        self._terminal_node_ids.remove(node_id)

    def prune_from(self, node_id: NodeIdLike, keep_nodes: Iterable[NodeIdLike]) -> list[NodeIdLike]:
        pruned_nodes = self.kcfg.prune(node_id, keep_nodes=list(keep_nodes) + [self.init])
        for nid in pruned_nodes:
            self._terminal_node_ids.discard(self.kcfg._resolve(nid))
        return pruned_nodes

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
        if len(self.kcfg.stuck) > 0:
            return ProofStatus.FAILED
        elif len(self.pending) > 0:
            return ProofStatus.PENDING
        else:
            return ProofStatus.PASSED

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
                    len(self.pending),
                    len(self.kcfg.stuck),
                    len(self._terminal_node_ids),
                ),
            ]
        )

    @staticmethod
    def read_proof_data(proof_dir: Path, id: str) -> ExplorationProof:
        proof_subdir = proof_dir / id
        proof_json = proof_subdir / 'proof.json'
        proof_dict = json.loads(proof_json.read_text())
        cfg_dir = proof_subdir / 'kcfg'
        kcfg = KCFG.read_cfg_data(cfg_dir, id)
        init = int(proof_dict['init'])
        terminal_node_ids = proof_dict['terminal_node_ids']
        logs = {int(k): tuple(LogEntry.from_dict(l) for l in ls) for k, ls in proof_dict['logs'].items()}

        return ExplorationProof(
            id=id,
            kcfg=kcfg,
            init=init,
            logs=logs,
            terminal_node_ids=terminal_node_ids,
            proof_dir=proof_dir,
        )

    def write_proof_data(self) -> None:
        if self.proof_dir is None or self.proof_subdir is None:
            _LOGGER.info(f'Skipped saving proof {self.id} since no save dir was specified.')
            return
        ensure_dir_path(self.proof_dir)
        ensure_dir_path(self.proof_subdir)
        proof_json = self.proof_subdir / 'proof.json'
        dct: dict[str, list[int] | list[str] | bool | str | int | dict[int, str] | dict[int, list[dict[str, Any]]]] = {}

        dct['id'] = self.id
        dct['subproof_ids'] = self.subproof_ids
        dct['admitted'] = self.admitted
        dct['type'] = 'ExplorationProof'
        dct['init'] = self.kcfg._resolve(self.init)
        dct['terminal_node_ids'] = sorted(self._terminal_node_ids)
        logs = {int(k): [l.to_dict() for l in ls] for k, ls in self.logs.items()}
        dct['logs'] = logs

        proof_json.write_text(json.dumps(dct))

        self.kcfg.write_cfg_data()


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


class ExplorationProver(Prover):
    proof: ExplorationProof

    main_module_name: str
    dependencies_module_name: str

    _checked_terminals: dict[int, bool]

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
            self.dependencies_as_claims(),
            priority=1,
        )

        self._checked_terminals = {}

    def dependencies_as_claims(self) -> list[KClaim]:
        return []

    def get_module_name(self, node: KCFG.Node) -> str:
        return self.dependencies_module_name

    def _check_terminal(self, node: KCFG.Node) -> bool:
        if node.id not in self._checked_terminals:
            _LOGGER.info(f'Checking terminal: {shorten_hashes(node.id)}')
            if self.kcfg_explore.kcfg_semantics.is_terminal(node.cterm):
                _LOGGER.info(f'Terminal node: {shorten_hashes(node.id)}.')
                self.proof.add_terminal(node.id)
                self._checked_terminals[node.id] = True
            else:
                self._checked_terminals[node.id] = False

        return self._checked_terminals[node.id]

    def _update_terminals(self) -> None:
        pending = self.proof.pending
        for node in pending:
            self._check_terminal(node)

    def advance_pending_node(
        self,
        node: KCFG.Node,
        module_name: str,
        execute_depth: int | None = None,
        cut_point_rules: Iterable[str] = (),
        terminal_rules: Iterable[str] = (),
        implication_every_block: bool = True,
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
        implication_every_block: bool = True,
        fail_fast: bool = False,
    ) -> None:
        if self.proof.admitted:
            raise ValueError('Attempting to advance an admitted proof')

        iterations = 0

        self._update_terminals()

        while not (fail_fast and self.proof.status == ProofStatus.FAILED) and self.proof.pending:
            self.proof.write_proof_data()

            if max_iterations is not None and max_iterations <= iterations:
                _LOGGER.warning(f'Reached iteration bound {self.proof.id}: {max_iterations}')
                break
            iterations += 1
            curr_node = self.proof.pending[0]

            module_name = self.get_module_name(curr_node)

            self.advance_pending_node(
                node=curr_node,
                module_name=module_name,
                execute_depth=execute_depth,
                cut_point_rules=cut_point_rules,
                terminal_rules=terminal_rules,
                implication_every_block=implication_every_block,
            )

            self._update_terminals()

        self.proof.write_proof_data()
