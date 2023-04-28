from __future__ import annotations

import json
import logging
from abc import ABC, abstractmethod
from enum import Enum
from itertools import chain
from typing import TYPE_CHECKING

from ..utils import hash_str

if TYPE_CHECKING:
    from collections.abc import Iterable, Mapping
    from pathlib import Path
    from typing import Any, Final, TypeVar

    T = TypeVar('T', bound='Proof')

_LOGGER: Final = logging.getLogger(__name__)


class ProofStatus(Enum):
    PASSED = 'passed'
    FAILED = 'failed'
    PENDING = 'pending'


class Proof(ABC):
    id: str
    proof_dir: Path | None
    subproof_ids: list[str]

    def __init__(self, id: str, proof_dir: Path | None = None, subproof_ids: list[str] | None = None) -> None:
        self.id = id
        self.proof_dir = proof_dir
        self.subproof_ids = subproof_ids if subproof_ids is not None else []

    def write_proof(self) -> None:
        if not self.proof_dir:
            return
        proof_path = self.proof_dir / f'{hash_str(self.id)}.json'
        proof_path.write_text(json.dumps(self.dict))
        _LOGGER.info(f'Updated proof file {self.id}: {proof_path}')

    @staticmethod
    def proof_exists(id: str, proof_dir: Path) -> bool:
        proof_path = proof_dir / f'{hash_str(id)}.json'
        return proof_path.exists() and proof_path.is_file()

    def add_subproof(self, subproof_id: str) -> None:
        if self.proof_dir is None:
            raise ValueError(f'Cannot subproofs to the proof {self.id} with no proof_dir')
        if not Proof.proof_exists(subproof_id, self.proof_dir):
            raise ValueError(
                f"Cannot find subproof {subproof_id} in parent proof's {self.id} proof_dir {self.proof_dir}"
            )
        self.subproof_ids.append(subproof_id)

    def read_subproofs(self) -> Iterable[Proof]:
        from .utils import read_proof

        if self.proof_dir is None and len(self.subproof_ids) > 0:
            raise ValueError(f'Cannot read subproofs {self.subproof_ids} of proof {self.id} with no proof_dir')
        if len(self.subproof_ids) == 0:
            yield from ()
        else:
            assert self.proof_dir
            for proof_id in self.subproof_ids:
                yield read_proof(proof_id, self.proof_dir)

    @property
    def subproofs_status(self) -> ProofStatus:
        any_subproof_failed = any([p.status == ProofStatus.FAILED for p in self.read_subproofs()])
        any_subproof_pending = any([p.status == ProofStatus.PENDING for p in self.read_subproofs()])
        if any_subproof_failed:
            return ProofStatus.FAILED
        elif any_subproof_pending:
            return ProofStatus.PENDING
        else:
            return ProofStatus.PASSED

    @property
    @abstractmethod
    def status(self) -> ProofStatus:
        ...

    @property
    @abstractmethod
    def dict(self) -> dict[str, Any]:
        ...

    @classmethod
    @abstractmethod
    def from_dict(cls: type[Proof], dct: Mapping[str, Any]) -> Proof:
        ...

    @property
    def summary(self) -> Iterable[str]:
        subproofs_summaries = [subproof.summary for subproof in self.read_subproofs()]
        return chain([f'Proof: {self.id}', f'    status: {self.status}'], *subproofs_summaries)
