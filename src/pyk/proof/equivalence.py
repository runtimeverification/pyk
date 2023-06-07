from __future__ import annotations

import json
import logging
from typing import TYPE_CHECKING

from pyk.kore.rpc import LogEntry

from ..kcfg import KCFG
from ..utils import shorten_hashes
from .proof import Proof, ProofStatus
from .reachability import APRBMCProof, APRBMCProver

if TYPE_CHECKING:
    from collections.abc import Callable, Iterable, Mapping
    from pathlib import Path
    from typing import Any, Final, TypeVar

    from ..cterm import CTerm
    from ..kast.inner import KInner
    from ..kcfg import KCFGExplore

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
        self.proof_1.__init__(id_1, kcfg_1, logs_1, bmc_depth_1, bounded_states_1, proof_dir_1)
        self.proof_2.__init__(id_2, kcfg_2, logs_2, bmc_depth_2, bounded_states_2, proof_dir_2)

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

    @property
    def status(self) -> ProofStatus:
        if len(self.kcfg.stuck) > 0:
            return ProofStatus.FAILED
        elif len(self.kcfg.frontier) > 0:
            return ProofStatus.PENDING
        else:
            return ProofStatus.PASSED

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
        return [
            'EquivalenceProof:',
            f'    Proof 1: {self.proof_1.id}',
            f'        status: {self.proof_1.status}',
            f'        nodes: {len(self.proof_1.kcfg.nodes)}',
            f'        frontier: {len(self.proof_1.kcfg.frontier)}',
            f'        stuck: {len(self.proof_1.kcfg.stuck)}',
            f'    Proof 2: {self.proof_2.id}',
            f'        status: {self.proof_2.status}',
            f'        nodes: {len(self.proof_2.kcfg.nodes)}',
            f'        frontier: {len(self.proof_2.kcfg.frontier)}',
            f'        stuck: {len(self.proof_2.kcfg.stuck)}',
        ]
