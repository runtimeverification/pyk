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

    @classmethod
    @abstractmethod
    def advance(cls, step: S) -> U:
        ...

    @abstractmethod
    def commit(self, proof: P, update: U) -> None:
        ...


class Proof:
    @property
    @abstractmethod
    def status(self) -> ProofStatus:
        ...
