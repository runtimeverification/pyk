from __future__ import annotations

import json
import logging
from abc import ABC, abstractmethod
from enum import Enum
from itertools import chain
from typing import TYPE_CHECKING

from ..utils import hash_file, hash_str

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
    _subproofs: dict[str, Proof]
    _last_modified: int

    def __init__(self, id: str, proof_dir: Path | None = None, subproof_ids: list[str] | None = None) -> None:
        self.id = id
        self.proof_dir = proof_dir
        self.subproof_ids = subproof_ids if subproof_ids is not None else []
        self._subproofs = {}
        if self.proof_dir is None and len(self.subproof_ids) > 0:
            raise ValueError(f'Cannot read subproofs {self.subproof_ids} of proof {self.id} with no proof_dir')
        if len(self.subproof_ids) > 0:
            assert self.proof_dir
            for proof_id in self.subproof_ids:
                self.fetch_subproof(proof_id)

    def write_proof(self) -> None:
        if not self.proof_dir:
            return
        proof_path = self.proof_dir / f'{hash_str(self.id)}.json'
        if not self.is_uptodate():
            proof_json = json.dumps(self.dict)
            proof_path.write_text(proof_json)
            self._last_modified = proof_path.stat().st_mtime_ns
            _LOGGER.info(f'Updated proof file {self.id}: {proof_path}')

    @staticmethod
    def proof_exists(id: str, proof_dir: Path) -> bool:
        proof_path = proof_dir / f'{hash_str(id)}.json'
        return proof_path.exists() and proof_path.is_file()

    @property
    def checksum(self) -> str:
        return hash_str(json.dumps(self.dict))

    def is_uptodate(self, check_method: str = 'timestamp') -> bool:
        """
        Check that the proof's representation on disk is up-to-date.

        By default, compares the file timestamp to self._last_modified. Use check_method = 'checksum' to compare hashes instead.
        """
        if self.proof_dir is None:
            raise ValueError(f'Cannot check if proof {self.id} with no proof_dir is up-to-date')
        proof_path = self.proof_dir / f'{hash_str(id)}.json'
        if proof_path.exists() and proof_path.is_file():
            match check_method:
                case 'checksum':
                    return self.checksum == hash_file(proof_path)
                case _:  # timestamp
                    return self._last_modified == proof_path.stat().st_mtime_ns
        else:
            return False

    def add_subproof(self, subproof_id: str) -> None:
        if self.proof_dir is None:
            raise ValueError(f'Cannot add subproof to the proof {self.id} with no proof_dir')
        assert self.proof_dir
        if not Proof.proof_exists(subproof_id, self.proof_dir):
            raise ValueError(
                f"Cannot find subproof {subproof_id} in parent proof's {self.id} proof_dir {self.proof_dir}"
            )
        self.subproof_ids.append(subproof_id)
        self.fetch_subproof(subproof_id, force_reread=True)

    def fetch_subproof(
        self, proof_id: str, force_reread: bool = False, uptodate_check_method: str = 'timestamp'
    ) -> Proof:
        """Get a subproof, re-reading from disk if it's not up-to-date"""
        from .utils import read_proof

        if self.proof_dir is not None and (
            force_reread or not self._subproofs[proof_id].is_uptodate(check_method=uptodate_check_method)
        ):
            updated_subproof = read_proof(proof_id, self.proof_dir)
            self._subproofs[proof_id] = updated_subproof
            return updated_subproof
        else:
            return self._subproofs[proof_id]

    @property
    def subproofs(self) -> Iterable[Proof]:
        """Return the subproofs, re-reading from disk the ones that changed"""
        for proof_id in self.subproof_ids:
            yield self.fetch_subproof(proof_id)

    @property
    def subproofs_status(self) -> ProofStatus:
        any_subproof_failed = any([p.status == ProofStatus.FAILED for p in self.subproofs])
        any_subproof_pending = any([p.status == ProofStatus.PENDING for p in self.subproofs])
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
        subproofs_summaries = [subproof.summary for subproof in self.subproofs]
        return chain([f'Proof: {self.id}', f'    status: {self.status}'], *subproofs_summaries)
