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

    # Return first available step(s) of proof
    @abstractmethod
    def initial_steps(self, proof: P) -> Iterable[S]:
        ...

    # Applies step to proof
    @abstractmethod
    def advance(self, proof: P, step: S) -> U:
        ...

    # Returns steps that were made available by this commit
    @abstractmethod
    def commit(self, proof: P, update: U) -> Iterable[S]:
        ...


class Proof:
    @property
    @abstractmethod
    def status(self) -> ProofStatus:
        ...
