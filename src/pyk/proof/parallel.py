from __future__ import annotations

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING, Any, Generic, TypeVar

if TYPE_CHECKING:
    from collections.abc import Iterable

    from pyk.proof.proof import ProofStatus

P = TypeVar('P', bound='Any')
S = TypeVar('S', bound='Any')
U = TypeVar('U', bound='Any')


class Prover(ABC, Generic[P, S, U]):
    @abstractmethod
    def steps(self, proof: P) -> Iterable[S]:
        ...

    @abstractmethod
    def advance(self, proof: P, step: S) -> U:
        ...

    # Should return P to be more flexible, but let's assume this for implicity
    @abstractmethod
    def commit(self, proof: P, update: U) -> None:
        ...


class Proof:
    @property
    @abstractmethod
    def status(self) -> ProofStatus:
        ...
