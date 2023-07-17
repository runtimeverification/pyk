from __future__ import annotations

import json

# import json
import logging
from typing import TYPE_CHECKING, Callable

from pyk.kast.inner import Subst
from pyk.kast.manip import ml_pred_to_bool
from pyk.kore.rpc import LogEntry
from pyk.prelude.ml import mlAnd
from pyk.utils import chain, hash_str, shorten_hashes

from ..kcfg import KCFG

# from ..utils import shorten_hashes
from .proof import Proof, ProofStatus, Prover

if TYPE_CHECKING:
    from collections.abc import Iterable, Mapping
    from pathlib import Path
    from typing import Any, Final, TypeVar

    from ..cterm import CTerm
    from ..kast.inner import KInner
    from ..kast.outer import KClaim
    from ..kcfg import KCFGExplore
    from ..kcfg.explore import SubsumptionCheckResult
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
        if len(kcfg.root) != 1:
            raise ValueError('KCFG with zero or multiple root nodes')
        else:
            self.init = kcfg_root[1].id

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


class EquivalenceProof:
    # Proofs of considered programs
    proof_1: KCFGProof
    proof_2: KCFGProof

    # Default constructor
    def __init__(
        self,
        id_1: str,
        kcfg_1: KCFG,
        logs_1: dict[int, tuple[LogEntry, ...]],
        id_2: str,
        kcfg_2: KCFG,
        logs_2: dict[int, tuple[LogEntry, ...]],
        proof_dir_1: Path | None = None,
        proof_dir_2: Path | None = None,
    ):
        self.proof_1 = KCFGProof(id_1, kcfg_1, logs_1, proof_dir_1)
        self.proof_2 = KCFGProof(id_2, kcfg_2, logs_2, proof_dir_2)

    # Constructor from two proofs
    @staticmethod
    def from_proofs(proof_1: KCFGProof, proof_2: KCFGProof) -> EquivalenceProof:
        return EquivalenceProof(
            proof_1.id,
            proof_1.kcfg,
            proof_1.logs,
            proof_2.id,
            proof_2.kcfg,
            proof_2.logs,
            proof_1.proof_dir,
            proof_2.proof_dir,
        )

    @staticmethod
    def read_proof(id_1: str, proof_dir_1: Path, id_2: str, proof_dir_2: Path) -> EquivalenceProof:
        _LOGGER.info('Reading EquivalenceProof')
        proof_1 = KCFGProof.read_proof(id_1, proof_dir_1)
        proof_2 = KCFGProof.read_proof(id_2, proof_dir_2)
        return EquivalenceProof.from_proofs(proof_1, proof_2)

    # The proof status of an equivalence proof says nothing
    # about the actual equivalence, only whether or not there
    # is still progress to be made
    @property
    def status(self) -> ProofStatus:
        if (self.proof_1.status == ProofStatus.FAILED) or (self.proof_2.status == ProofStatus.FAILED):
            return ProofStatus.FAILED
        elif (self.proof_1.status == ProofStatus.PENDING) or (self.proof_2.status == ProofStatus.PENDING):
            return ProofStatus.PENDING
        else:
            return ProofStatus.COMPLETED

    @classmethod
    def from_dict(cls: type[EquivalenceProof], dct: Mapping[str, Any]) -> EquivalenceProof:
        assert dct['type'] == 'EquivalenceProof'
        proof_1 = KCFGProof.from_dict(dct['proof_1'])
        proof_2 = KCFGProof.from_dict(dct['proof_2'])
        return EquivalenceProof.from_proofs(proof_1, proof_2)

    @property
    def dict(self) -> dict[str, Any]:
        dict_1 = self.proof_1.dict
        dict_2 = self.proof_2.dict
        return {'type': 'EquivalenceProof', 'proof_1': dict_1, 'proof_2': dict_2}

    @property
    def summary(self) -> Iterable[str]:
        summary_1 = ['    ' + s for s in self.proof_1.summary]
        summary_2 = ['    ' + s for s in self.proof_2.summary]
        return (
            [
                'EquivalenceProof:',
                f'    status: {self.status}',
            ]
            + summary_1
            + summary_2
        )

    #
    # Equivalence of two programs
    # ===========================
    #
    #   Parameters:
    #   -----------
    #     self:              the equivalence proof being analysed
    #     kcfg_explore:      KCFG explorer required for RPC calls
    #     cell_names:        strings representing the names of the configuration cells
    #     config_comparator: an ML-sorted term that describes what it means for two configurations to be equal
    #                        using the configuration cell names suffixed with `_1` and `_2` to refer to the
    #                        configuration cells of the two programs
    #
    #   Return value:
    #     final_nodes_equivalence: point-wise equivalence between any two final configurations
    #     final_pc_check:          subsumption of path constraints of final nodes
    #     pending_pc_check:       subsumption of path constraints of pending nodes
    #     bounded_pc_check:        subsumption of path constraints of bounded nodes
    #
    def check_equivalence(
        self, kcfg_explore: KCFGExplore, cell_names: Iterable[str], config_comparator: KInner
    ) -> tuple[bool, SubsumptionCheckResult, SubsumptionCheckResult]:
        #
        # Equivalence of two configurations
        # =================================
        #
        #   Parameters:
        #   -----------
        #     config_1: a KCFG node
        #     config_2: a KCFG node
        #
        #   Return value:
        #     True,  if the configurations are equivalent
        #     False, otherwise
        #
        #   Methodology:
        #     Two configurations are equivalent if the conjunction of their path
        #     constraints implies the configuration comparator instantiated with
        #     the contents of the appropriate configuration cells.
        #
        def config_equivalence(config_1: KCFG.Node, config_2: KCFG.Node) -> bool:
            # Extend cell names with configuration suffixes
            cell_names_1, cell_names_2 = ([s + '_1' for s in cell_names], [s + '_2' for s in cell_names])

            # Get the contents of the cells in the configurations
            cell_contents_1 = [config_1.cterm.cell(cell_name) for cell_name in cell_names]
            cell_contents_2 = [config_2.cterm.cell(cell_name) for cell_name in cell_names]

            # Create the substitution mapping the extended cell names to the appropriate contents
            cell_subst = Subst(
                dict(
                    list(zip(cell_names_1, cell_contents_1, strict=True))
                    + list(zip(cell_names_2, cell_contents_2, strict=True))
                )
            )

            # and apply it to the comparator
            comparator = cell_subst.apply(config_comparator)

            # Conjunction of the path constraints of the configurations
            path_constraint = ml_pred_to_bool(mlAnd([config_1.cterm.constraint, config_2.cterm.constraint]))

            print(
                f'Configuration equivalence check:\n{kcfg_explore.kprint.pretty_print(path_constraint)}\n\t#Implies\n{kcfg_explore.kprint.pretty_print(comparator)}'
            )

            # Check validity of implication
            return kcfg_explore.check_implication(path_constraint, comparator)

        kcfg_1 = self.proof_1.kcfg
        kcfg_2 = self.proof_2.kcfg

        # 1. Nodes whose execution cannot proceed further (stuck/final nodes)
        final_1 = kcfg_1.stuck
        final_2 = kcfg_2.stuck

        pc_final_1 = KCFG.multinode_path_constraint(final_1)
        pc_final_2 = KCFG.multinode_path_constraint(final_2)

        print('Checking subsumption of path constraints of final states')

        # Relationship of path conditions
        final_pc_check = kcfg_explore.path_constraint_subsumption(pc_final_1, pc_final_2)

        # Relationship of individual final nodes
        final_nodes_equivalence = [
            config_equivalence(config_1, config_2) for config_1 in final_1 for config_2 in final_2
        ]
        final_nodes_equivalence_summary = not (False in final_nodes_equivalence)

        # 2. Nodes whose execution can proceed further (pending nodes)
        pending_1 = self.proof_1.pending
        pending_2 = self.proof_2.pending

        print('Checking subsumption of path constraints of pending states')
        pc_pending_1 = KCFG.multinode_path_constraint(pending_1)
        pc_pending_2 = KCFG.multinode_path_constraint(pending_2)

        # For these nodes, only the relationship of their path conditions is relevant
        pending_pc_check = kcfg_explore.path_constraint_subsumption(pc_pending_1, pc_pending_2)

        # 3. Nodes whose execution has been stopped due to a bound reached (bounded nodes)
        # bounded_1 = [kcfg_1.get_node_unsafe(id) for id in self.proof_1._bounded_states]
        # bounded_2 = [kcfg_2.get_node_unsafe(id) for id in self.proof_2._bounded_states]

        # print('Checking subsumption of path constraints of bounded states')
        # pc_bounded_1 = KCFG.multinode_path_constraint(bounded_1)
        # pc_bounded_2 = KCFG.multinode_path_constraint(bounded_2)

        # For these nodes, only the relationship of their path conditions is relevant
        # bounded_pc_check = kcfg_explore.path_constraint_subsumption(pc_bounded_1, pc_bounded_2)

        print(
            f'check_equivalence_summary:\n\tFinal nodes equivalent: {final_nodes_equivalence_summary}\n\tPCs of final nodes: {final_pc_check.value}\n\tPCs of pending nodes: {pending_pc_check.value}\n'
        )

        return (final_nodes_equivalence_summary, final_pc_check, pending_pc_check)


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
                self.circularities_module_name if self.nonzero_depth(curr_node) else self.dependencies_module_name
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


class EquivalenceProver:
    prover_1: KCFGProver
    prover_2: KCFGProver

    def __init__(
        self,
        kcfg_explore: KCFGExplore,
        proof: EquivalenceProof,
        is_terminal: Callable[[CTerm], bool] | None = None,
        extract_branches: Callable[[CTerm], Iterable[KInner]] | None = None,
    ) -> None:
        self.prover_1 = KCFGProver(
            kcfg_explore, proof.proof_1, is_terminal=is_terminal, extract_branches=extract_branches
        )
        self.prover_2 = KCFGProver(
            kcfg_explore, proof.proof_2, is_terminal=is_terminal, extract_branches=extract_branches
        )

    def advance_proof(
        self,
        max_iterations: int | None = None,
        execute_depth: int | None = None,
        cut_point_rules: Iterable[str] = (),
        terminal_rules: Iterable[str] = (),
    ) -> None:
        _ = self.prover_1.advance_proof(max_iterations, execute_depth, cut_point_rules, terminal_rules)
        _ = self.prover_2.advance_proof(max_iterations, execute_depth, cut_point_rules, terminal_rules)
