from __future__ import annotations

import logging
from abc import abstractmethod
from enum import Enum
from typing import Any, Dict, Final, Optional, Type, TypeVar

T = TypeVar('T', bound='Proof')

_LOGGER: Final = logging.getLogger(__name__)


class ProofStatus(Enum):
    PASSED = 'passed'
    FAILED = 'failed'
    PENDING = 'pending'


class Proof:
    _PROOF_TYPES: Final = {'AllPathReachabilityProof'}

    @classmethod
    def _check_proof_type(cls: Type[T], dct: Dict[str, Any], expected: Optional[str] = None) -> None:
        expected = expected if expected is not None else cls.__name__
        actual = dct['type']
        if actual != expected:
            raise ValueError(f'Expected "type" value: {expected}, got: {actual}')

    @classmethod
    @abstractmethod
    def from_dict(cls: Type[Proof], dct: Dict[str, Any]) -> Proof:
        proof_type = dct['type']
        if proof_type in Proof._PROOF_TYPES:
            return globals()[proof_type].from_dict(dct)
        raise ValueError(f'Expected "type" value in: {Proof._PROOF_TYPES}, got {proof_type}')

    @property
    @abstractmethod
    def status(self) -> ProofStatus:
        ...

    @abstractmethod
    def to_dict(self) -> Dict[str, Any]:
        ...
