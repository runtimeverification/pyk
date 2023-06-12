from __future__ import annotations

import json
import logging
from abc import ABC, abstractmethod
from enum import Enum
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
    COMPLETED = 'completed'


class Proof(ABC):
    _PROOF_TYPES: Final = {'APRProof', 'APRBMCProof', 'EqualityProof'}

    id: str
    has_target: bool
    proof_dir: Path | None

    def __init__(self, id: str, has_target: bool = True, proof_dir: Path | None = None) -> None:
        self.id = id
        self.has_target = has_target
        self.proof_dir = proof_dir

    def write_proof(self) -> None:
        if not self.proof_dir:
            return
        proof_path = self.proof_dir / f'{hash_str(self.id)}.json'
        if not self.up_to_date():
            proof_json = json.dumps(self.dict)
            proof_path.write_text(proof_json)
            self._last_modified = proof_path.stat().st_mtime_ns
            _LOGGER.info(f'Updated proof file {self.id}: {proof_path}')

    @staticmethod
    def proof_exists(id: str, proof_dir: Path) -> bool:
        proof_path = proof_dir / f'{hash_str(id)}.json'
        return proof_path.exists() and proof_path.is_file()

    @property
    def digest(self) -> str:
        return hash_str(json.dumps(self.dict))

    def up_to_date(self, check_method: str = 'checksum') -> bool:
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
                    return self.digest == hash_file(proof_path)
                case _:  # timestamp
                    return self._last_modified == proof_path.stat().st_mtime_ns
        else:
            return False

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

    @classmethod
    def read_proof(cls: type[Proof], id: str, proof_dir: Path) -> Proof:
        # these local imports allow us to call .to_dict() based on the proof type we read from JSON
        from .equality import EqualityProof  # noqa
        from .reachability import APRBMCProof, APRProof  # noqa

        proof_path = proof_dir / f'{hash_str(id)}.json'
        if Proof.proof_exists(id, proof_dir):
            proof_dict = json.loads(proof_path.read_text())
            proof_type = proof_dict['type']
            _LOGGER.info(f'Reading {proof_type} from file {id}: {proof_path}')
            if proof_type in Proof._PROOF_TYPES:
                return locals()[proof_type].from_dict(proof_dict, proof_dir)

        raise ValueError(f'Could not load Proof from file {id}: {proof_path}')

    @property
    def summary(self) -> Iterable[str]:
        return [
            f'Proof: {self.id}',
            f'    status: {self.status}',
        ]
