from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Hashable
from typing import TYPE_CHECKING, Generic, TypeVar

if TYPE_CHECKING:
    from collections.abc import Iterable

    from pyk.proof.proof import ProofStatus

P = TypeVar('P', bound='Proof')
S = TypeVar('S', bound='ProofStep')
U = TypeVar('U', bound='ProofResult')


class Prover(ABC, Generic[P, S, U]):
    """
    Should contain all data needed to make progress on a `P` (proof).
    May be specific to a single `P` (proof) or may be able to handle multiple.
    """

    @abstractmethod
    def steps(self, proof: P) -> Iterable[S]:
        """
        Return a list of `ProofStep[U]` which represents all the computation jobs as defined by `ProofStep`, which have not yet been computed and committed, and are available given the current state of `proof`. Note that this is a requirement which is not enforced by the type system.
        If `steps()` or `commit()` has been called on a proof `proof`, `steps()` may never again be called on `proof`.
        Must not modify `self` or `proof`.
        The output of this function must only change with calls to `self.commit()`.
        """
        ...

    @abstractmethod
    def commit(self, proof: P, update: U) -> None:
        """
        Should update `proof` according to `update`.
        If `steps()` or `commit()` has been called on a proof `proof`, `commit()` may never again be called on `proof`.
        Must only be called with an `update` that was returned by `step.execute()` where `step` was returned by `self.steps(proof)`.
        Steps for a proof `proof` can have their results submitted any time after they are made available by `self.steps(proof)`, including in any order and multiple times, and the Prover must be able to handle this.
        """
        ...


class Proof(ABC):
    """Should represent a computer proof of a single claim"""

    @property
    @abstractmethod
    def status(self) -> ProofStatus:
        """
        ProofStatus.PASSED: the claim has been proven
        ProofStatus.FAILED: the claim has not been proven, but the proof cannot advance further.
        ProofStatus.PENDING: the claim has not yet been proven, but the proof can advance further.
        Must not change, except with calls to `prover.commit(self, update)` for some `prover,update`.
        """
        ...


class ProofStep(ABC, Hashable, Generic[U]):
    """
    Should be a description of a computation needed to make progress on a `Proof`.
    Must be frozen dataclass.
    Must be pickable.
    Should be small.
    """

    @abstractmethod
    def exec(self) -> U:
        """
        Should perform some nontrivial computation given by `self`, which can be done independently of other calls to `exec()`.
        Allowed to be nondeterministic.
        Able to be called on any `ProofStep` returned by `prover.steps(proof)`.
        """
        ...


class ProofResult(ABC):
    """
    Should be a description of how to make a small update to a `Proof` based on the results of a computation specified by a `ProofStep`.
    Must be picklable.
    Must be frozen dataclass.
    Should be small.
    """
    ...
