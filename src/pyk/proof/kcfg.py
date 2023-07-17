from __future__ import annotations

import json

# import json
import logging
from typing import TYPE_CHECKING

from pyk.kore.rpc import LogEntry
from pyk.utils import chain, hash_str, shorten_hashes

from ..kcfg import KCFG

# from ..utils import shorten_hashes
from .proof import Proof, ProofStatus, Prover

if TYPE_CHECKING:
    from collections.abc import Callable, Iterable, Mapping
    from pathlib import Path
    from typing import Any, Final, TypeVar

    from ..cterm import CTerm
    from ..kast.inner import KInner
    from ..kast.outer import KClaim
    from ..kcfg import KCFGExplore
    from ..kcfg.kcfg import NodeIdLike
    from ..ktool.kprint import KPrint

    T = TypeVar('T', bound='Proof')

_LOGGER: Final = logging.getLogger(__name__)


class KCFGProof(Proof):
    kcfg: KCFG
    init: NodeIdLike
    _terminal_nodes: list[NodeIdLike]
    logs: dict[int, tuple[LogEntry, ...]]
    circularity: bool

    def __init__(
        self,
        id: str,
        kcfg: KCFG,
        logs: dict[int, tuple[LogEntry, ...]],
        enforce_single_root: bool = True,
        proof_dir: Path | None = None,
        terminal_nodes: Iterable[NodeIdLike] | None = None,
        subproof_ids: Iterable[str] = (),
        circularity: bool = False,
        admitted: bool = False,
    ):
        super().__init__(id, proof_dir=proof_dir, subproof_ids=subproof_ids, admitted=admitted)
        self.kcfg = kcfg
        self.logs = logs
        self._terminal_nodes = list(terminal_nodes) if terminal_nodes is not None else []
        self.circularity = circularity

        kcfg_root: list[KCFG.Node] = kcfg.root
        if not enforce_single_root and len(kcfg.root) != 1:
            self.init = 'dummy-root-node'
        elif len(kcfg.root) != 1:
            raise ValueError('KCFG with zero or multiple root nodes')
        else:
            self.init = kcfg_root[0].id

    @property
    def terminal(self) -> list[KCFG.Node]:
        return [self.kcfg.node(nid) for nid in self._terminal_nodes]

    @property
    def pending(self) -> list[KCFG.Node]:
        return [nd for nd in self.kcfg.leaves if self.is_pending(nd.id)]

    @property
    def failing(self) -> list[KCFG.Node]:
        return [nd for nd in self.kcfg.leaves if self.is_failing(nd.id)]

    def is_terminal(self, node_id: NodeIdLike) -> bool:
        return self.kcfg._resolve(node_id) in (self.kcfg._resolve(nid) for nid in self._terminal_nodes)

    def is_pending(self, node_id: NodeIdLike) -> bool:
        return self.kcfg.is_leaf(node_id) and not (self.is_terminal(node_id) or self.kcfg.is_stuck(node_id))

    def is_failing(self, node_id: NodeIdLike) -> bool:
        return self.kcfg.is_leaf(node_id) and not (self.is_pending(node_id))

    @staticmethod
    def read_proof(id: str, proof_dir: Path) -> KCFGProof:
        proof_path = proof_dir / f'{hash_str(id)}.json'
        if KCFGProof.proof_exists(id, proof_dir):
            proof_dict = json.loads(proof_path.read_text())
            _LOGGER.info(f'Reading KCFGProof from file {id}: {proof_path}')
            return KCFGProof.from_dict(proof_dict, proof_dir=proof_dir)
        raise ValueError(f'Could not load KCFGProof from file {id}: {proof_path}')

    @property
    def status(self) -> ProofStatus:
        if self.admitted:
            return ProofStatus.COMPLETED
        if len(self.failing) > 0 or self.subproofs_status == ProofStatus.FAILED:
            return ProofStatus.FAILED
        elif len(self.pending) > 0 or self.subproofs_status == ProofStatus.PENDING:
            return ProofStatus.PENDING
        else:
            return ProofStatus.COMPLETED

    @classmethod
    def from_dict(cls: type[KCFGProof], dct: Mapping[str, Any], proof_dir: Path | None = None) -> KCFGProof:
        cfg = KCFG.from_dict(dct['cfg'])
        terminal_nodes = dct['terminal_nodes']
        id = dct['id']
        circularity = dct.get('circularity', False)
        admitted = dct.get('admitted', False)
        subproof_ids = dct['subproof_ids'] if 'subproof_ids' in dct else []
        if 'logs' in dct:
            logs = {k: tuple(LogEntry.from_dict(l) for l in ls) for k, ls in dct['logs'].items()}
        else:
            logs = {}

        return KCFGProof(
            id,
            cfg,
            logs=logs,
            terminal_nodes=terminal_nodes,
            circularity=circularity,
            admitted=admitted,
            proof_dir=proof_dir,
            subproof_ids=subproof_ids,
        )

    @property
    def dict(self) -> dict[str, Any]:
        dct = super().dict
        dct['type'] = 'KCFGProof'
        dct['cfg'] = self.kcfg.to_dict()
        dct['terminal_nodes'] = self._terminal_nodes
        logs = {k: [l.to_dict() for l in ls] for k, ls in self.logs.items()}
        dct['logs'] = logs
        dct['circularity'] = self.circularity
        return dct

    def add_terminal(self, nid: NodeIdLike) -> None:
        self._terminal_nodes.append(self.kcfg._resolve(nid))  # TODO remove

    def remove_terminal(self, nid: NodeIdLike) -> None:
        self._terminal_nodes.remove(self.kcfg._resolve(nid))  # TODO remove

    @classmethod
    def as_claim(cls, kprint: KPrint) -> KClaim | None:
        return None

    @property
    def summary(self) -> Iterable[str]:
        subproofs_summaries = chain(subproof.summary for subproof in self.subproofs)
        yield from [
            f'KCFGProof: {self.id}',
            f'    status: {self.status}',
            f'    admitted: {self.admitted}',
            f'    nodes: {len(self.kcfg.nodes)}',
            f'    pending: {len(self.pending)}',
            f'    failing: {len(self.failing)}',
            f'    stuck: {len(self.kcfg.stuck)}',
            f'    terminal: {len(self.terminal)}',
            f'Subproofs: {len(self.subproof_ids)}',
        ]
        for summary in subproofs_summaries:
            yield from summary


class KCFGProver(Prover):
    kcfg_explore: KCFGExplore
    proof: KCFGProof
    _is_terminal: Callable[[CTerm], bool] | None
    _extract_branches: Callable[[CTerm], Iterable[KInner]] | None
    _abstract_node: Callable[[CTerm], CTerm] | None

    main_module_name: str
    dependencies_module_name: str
    circularities_module_name: str

    def __init__(
        self,
        kcfg_explore: KCFGExplore,
        proof: KCFGProof,
        is_terminal: Callable[[CTerm], bool] | None = None,
        extract_branches: Callable[[CTerm], Iterable[KInner]] | None = None,
        abstract_node: Callable[[CTerm], CTerm] | None = None,
    ) -> None:
        super().__init__(kcfg_explore)
        self.proof = proof
        self.kcfg_explore = kcfg_explore
        self._is_terminal = is_terminal
        self._extract_branches = extract_branches
        self._abstract_node = abstract_node
        self.main_module_name = self.kcfg_explore.kprint.definition.main_module_name

        subproofs: list[Proof] = (
            [Proof.read_proof(i, proof_dir=proof.proof_dir) for i in proof.subproof_ids]
            if proof.proof_dir is not None
            else []
        )

        dependencies_as_claims: list[KClaim] = [
            d for d in [d.as_claim(self.kcfg_explore.kprint) for d in subproofs] if d is not None
        ]

        self.dependencies_module_name = self.main_module_name + '-DEPENDS-MODULE'
        self.kcfg_explore.add_dependencies_module(
            self.main_module_name,
            self.dependencies_module_name,
            dependencies_as_claims,
            priority=1,
        )
        self.circularities_module_name = self.main_module_name + '-CIRCULARITIES-MODULE'
        self.kcfg_explore.add_dependencies_module(
            self.main_module_name,
            self.circularities_module_name,
            dependencies_as_claims
            + [c for c in ([proof.as_claim(self.kcfg_explore.kprint)] if proof.circularity else []) if c is not None],
            priority=1,
        )

    def _check_terminal(self, curr_node: KCFG.Node) -> bool:
        if self._is_terminal is not None:
            _LOGGER.info(f'Checking terminal {self.proof.id}: {shorten_hashes(curr_node.id)}')
            if self._is_terminal(curr_node.cterm):
                _LOGGER.info(f'Terminal node {self.proof.id}: {shorten_hashes(curr_node.id)}.')
                self.proof.add_terminal(curr_node.id)
                return True
        return False

    def nonzero_depth(self, node: KCFG.Node) -> bool:
        return not self.proof.kcfg.zero_depth_between(self.proof.init, node.id)

    def _check_abstract(self, node: KCFG.Node) -> bool:
        if self._abstract_node is None:
            return False

        new_cterm = self._abstract_node(node.cterm)
        if new_cterm == node.cterm:
            return False

        new_node = self.proof.kcfg.create_node(new_cterm)
        self.proof.kcfg.create_cover(node.id, new_node.id)
        return True

    def advance_proof_single_iteration(
        self,
        curr_node: KCFG.Node,
        module_name: str,
        execute_depth: int | None = None,
        cut_point_rules: Iterable[str] = (),
        terminal_rules: Iterable[str] = (),
    ) -> None:
        if self._check_terminal(curr_node):
            return

        if self._check_abstract(curr_node):
            return

        if self._extract_branches is not None and len(self.proof.kcfg.splits(target_id=curr_node.id)) == 0:
            branches = list(self._extract_branches(curr_node.cterm))
            if len(branches) > 0:
                self.proof.kcfg.split_on_constraints(curr_node.id, branches)
                _LOGGER.info(
                    f'Found {len(branches)} branches using heuristic for node {self.proof.id}: {shorten_hashes(curr_node.id)}: {[self.kcfg_explore.kprint.pretty_print(bc) for bc in branches]}'
                )
                return

        self.kcfg_explore.extend(
            self.proof.kcfg,
            curr_node,
            self.proof.logs,
            execute_depth=execute_depth,
            cut_point_rules=cut_point_rules,
            terminal_rules=terminal_rules,
            module_name=module_name,
        )
        return

    def advance_proof(
        self,
        max_iterations: int | None = None,
        execute_depth: int | None = None,
        cut_point_rules: Iterable[str] = (),
        terminal_rules: Iterable[str] = (),
    ) -> KCFG:
        iterations = 0

        while self.proof.pending:
            self.proof.write_proof()

            if max_iterations is not None and max_iterations <= iterations:
                _LOGGER.warning(f'Reached iteration bound {self.proof.id}: {max_iterations}')
                break
            iterations += 1
            curr_node = self.proof.pending[0]

            module_name = (
                self.circularities_module_name if self.nonzero_depth(curr_node) else self.dependencies_module_name
            )

            self.advance_proof_single_iteration(curr_node, module_name, execute_depth, cut_point_rules, terminal_rules)

        self.proof.write_proof()
        return self.proof.kcfg
