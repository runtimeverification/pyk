from __future__ import annotations

# import json
import logging
from typing import TYPE_CHECKING

from pyk.kast.inner import Subst
from pyk.kast.manip import ml_pred_to_bool
from pyk.prelude.ml import mlAnd
from pyk.proof.kcfg import KCFGProof, KCFGProver

from ..kcfg import KCFG

# from ..utils import shorten_hashes
from .proof import Proof, ProofStatus

if TYPE_CHECKING:
    from collections.abc import Callable, Iterable, Mapping
    from pathlib import Path
    from typing import Any, Final, TypeVar

    from ..cterm import CTerm
    from ..kast.inner import KInner
    from ..kcfg import KCFGExplore
    from ..kcfg.explore import SubsumptionCheckResult
    from ..kore.rpc import LogEntry

    T = TypeVar('T', bound='Proof')

_LOGGER: Final = logging.getLogger(__name__)


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
        self.proof_1 = KCFGProof(id_1, kcfg_1, logs_1, proof_dir=proof_dir_1)
        self.proof_2 = KCFGProof(id_2, kcfg_2, logs_2, proof_dir=proof_dir_2)

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

        # 1. Nodes whose execution cannot proceed further (terminal nodes)
        terminal_1 = [kcfg_1.node(id) for id in self.proof_1._terminal_nodes]
        terminal_2 = [kcfg_2.node(id) for id in self.proof_2._terminal_nodes]

        pc_terminal_1 = KCFG.multinode_path_constraint(terminal_1)
        pc_terminal_2 = KCFG.multinode_path_constraint(terminal_2)

        print('Checking subsumption of path constraints of final states')

        # Relationship of path conditions
        final_pc_check = kcfg_explore.path_constraint_subsumption(pc_terminal_1, pc_terminal_2)

        # Relationship of individual final nodes
        final_nodes_equivalence = [
            config_equivalence(config_1, config_2) for config_1 in terminal_1 for config_2 in terminal_2
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
        # bounded_1 = [kcfg_1.node(id) for id in self.proof_1._bounded_states]
        # bounded_2 = [kcfg_2.node(id) for id in self.proof_2._bounded_states]

        # print('Checking subsumption of path constraints of bounded states')
        # pc_bounded_1 = KCFG.multinode_path_constraint(bounded_1)
        # pc_bounded_2 = KCFG.multinode_path_constraint(bounded_2)

        # For these nodes, only the relationship of their path conditions is relevant
        # bounded_pc_check = kcfg_explore.path_constraint_subsumption(pc_bounded_1, pc_bounded_2)

        print(
            f'check_equivalence_summary:\n\tFinal nodes equivalent: {final_nodes_equivalence_summary}\n\tPCs of final nodes: {final_pc_check.value}\n\tPCs of pending nodes: {pending_pc_check.value}\n'
        )

        return (final_nodes_equivalence_summary, final_pc_check, pending_pc_check)


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
