from __future__ import annotations

# import json
import logging
from typing import TYPE_CHECKING

from ..kcfg import KCFG

# from ..utils import shorten_hashes
from .proof import Proof, ProofStatus
from .reachability import APRBMCProof, APRBMCProver

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
    proof_1: APRBMCProof
    proof_2: APRBMCProof

    # Default constructor
    def __init__(
        self,
        id_1: str,
        kcfg_1: KCFG,
        logs_1: dict[int, tuple[LogEntry, ...]],
        bmc_depth_1: int,
        id_2: str,
        kcfg_2: KCFG,
        logs_2: dict[int, tuple[LogEntry, ...]],
        bmc_depth_2: int,
        bounded_states_1: Iterable[int] | None = None,
        proof_dir_1: Path | None = None,
        bounded_states_2: Iterable[int] | None = None,
        proof_dir_2: Path | None = None,
    ):
        self.proof_1 = APRBMCProof(id_1, kcfg_1, logs_1, bmc_depth_1, False, bounded_states_1, proof_dir_1)
        self.proof_2 = APRBMCProof(id_2, kcfg_2, logs_2, bmc_depth_2, False, bounded_states_2, proof_dir_2)

    @staticmethod
    def from_proofs(proof_1: APRBMCProof, proof_2: APRBMCProof) -> EquivalenceProof:
        return EquivalenceProof(
            proof_1.id,
            proof_1.kcfg,
            proof_1.logs,
            proof_1.bmc_depth,
            proof_2.id,
            proof_2.kcfg,
            proof_2.logs,
            proof_2.bmc_depth,
            proof_1._bounded_states,
            proof_1.proof_dir,
            proof_2._bounded_states,
            proof_2.proof_dir,
        )

    @staticmethod
    def read_proof(id_1: str, proof_dir_1: Path, id_2: str, proof_dir_2: Path) -> EquivalenceProof:
        _LOGGER.info('Reading EquivalenceProof')
        proof_1 = APRBMCProof.read_proof(id_1, proof_dir_1)
        proof_2 = APRBMCProof.read_proof(id_2, proof_dir_2)
        return EquivalenceProof.from_proofs(proof_1, proof_2)

    # The proof status of an equivalence proof says nothing
    # about the actual equivalence, only whether or not there
    # is still progress to be made
    @property
    def status(self) -> ProofStatus:
        if len(self.proof_1.kcfg.frontier) > 0 or len(self.proof_2.kcfg.frontier) > 0:
            return ProofStatus.PENDING
        else:
            return ProofStatus.COMPLETED

    @classmethod
    def from_dict(cls: type[EquivalenceProof], dct: Mapping[str, Any]) -> EquivalenceProof:
        assert dct['type'] == 'EquivalenceProof'
        proof_1 = APRBMCProof.from_dict(dct['proof_1'])
        proof_2 = APRBMCProof.from_dict(dct['proof_2'])
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

    def check_equivalence(
        self, kcfg_explore: KCFGExplore
    ) -> tuple[SubsumptionCheckResult, SubsumptionCheckResult, SubsumptionCheckResult]:
        kcfg_1 = self.proof_1.kcfg
        kcfg_2 = self.proof_2.kcfg

        # 1. Nodes whose execution cannot proceed further (stuck nodes)
        stuck_1 = kcfg_1.stuck
        stuck_2 = kcfg_2.stuck

        pc_stuck_1 = KCFG.multinode_path_constraint(stuck_1)
        pc_stuck_2 = KCFG.multinode_path_constraint(stuck_2)

        stuck_pc_check = kcfg_explore.path_constraint_subsumption(pc_stuck_1, pc_stuck_2)

        # 2. Nodes whose execution can proceed further (frontier nodes)
        frontier_1 = kcfg_1.frontier
        frontier_2 = kcfg_2.frontier

        pc_frontier_1 = KCFG.multinode_path_constraint(frontier_1)
        pc_frontier_2 = KCFG.multinode_path_constraint(frontier_2)

        # For these nodes, only the equivalence of their path conditions is relevant
        frontier_pc_check = kcfg_explore.path_constraint_subsumption(pc_frontier_1, pc_frontier_2)

        # 3. Nodes whose execution has been stopped due to a bound reached (bounded nodes)
        bounded_1 = [kcfg_1.get_node_unsafe(id) for id in self.proof_1._bounded_states]
        bounded_2 = [kcfg_2.get_node_unsafe(id) for id in self.proof_2._bounded_states]

        pc_bounded_1 = KCFG.multinode_path_constraint(bounded_1)
        pc_bounded_2 = KCFG.multinode_path_constraint(bounded_2)

        # For these nodes, only the equivalence of their path conditions is relevant
        bounded_pc_check = kcfg_explore.path_constraint_subsumption(pc_bounded_1, pc_bounded_2)

        return (stuck_pc_check, frontier_pc_check, bounded_pc_check)


class EquivalenceProver:
    prover_1: APRBMCProver
    prover_2: APRBMCProver

    def __init__(
        self,
        proof: EquivalenceProof,
        same_loop: Callable[[CTerm, CTerm], bool],
        is_terminal: Callable[[CTerm], bool] | None = None,
        extract_branches: Callable[[CTerm], Iterable[KInner]] | None = None,
    ) -> None:
        self.prover_1 = APRBMCProver(
            proof.proof_1, same_loop, is_terminal=is_terminal, extract_branches=extract_branches
        )
        self.prover_2 = APRBMCProver(
            proof.proof_2, same_loop, is_terminal=is_terminal, extract_branches=extract_branches
        )

    def advance_proof(
        self,
        kcfg_explore: KCFGExplore,
        max_iterations: int | None = None,
        execute_depth: int | None = None,
        cut_point_rules: Iterable[str] = (),
        terminal_rules: Iterable[str] = (),
        implication_every_block: bool = True,
    ) -> None:
        _ = self.prover_1.advance_proof(
            kcfg_explore, max_iterations, execute_depth, cut_point_rules, terminal_rules, implication_every_block
        )
        _ = self.prover_2.advance_proof(
            kcfg_explore, max_iterations, execute_depth, cut_point_rules, terminal_rules, implication_every_block
        )
