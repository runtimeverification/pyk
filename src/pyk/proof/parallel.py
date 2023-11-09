from __future__ import annotations

from abc import ABC, abstractmethod
from concurrent.futures import ProcessPoolExecutor, wait
from typing import TYPE_CHECKING, Any, Generic, TypeVar

from pyk.proof.proof import ProofStatus

if TYPE_CHECKING:
    from collections.abc import Iterable
    from concurrent.futures import Executor, Future


P = TypeVar('P', bound='Proof')
U = TypeVar('U')


class Prover(ABC, Generic[P, U]):
    """
    Should contain all data needed to make progress on a `P` (proof).
    May be specific to a single `P` (proof) or may be able to handle multiple.

    Type parameter requirements:
    `U` should be a description of how to make a small update to a `Proof` based on the results of a computation specified by a `ProofStep`.
    `U` must be picklable.
    `U` must be frozen dataclass.
    `U` should be small.
    """

    @abstractmethod
    def steps(self, proof: P) -> Iterable[ProofStep[U]]:
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


class ProofStep(ABC, Generic[U]):
    """
    Should be a description of a computation needed to make progress on a `Proof`.
    Must be hashable.
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


def prove_parallel(
    proofs: dict[str, Proof],
    provers: dict[str, Prover],
) -> Iterable[Proof]:
    pending: dict[Future[Any], str] = {}
    explored: set[ProofStep] = set()

    def submit(proof_id: str, pool: Executor) -> None:
        proof = proofs[proof_id]
        prover = provers[proof_id]
        for step in prover.steps(proof):  # <-- get next steps (represented by e.g. pending nodes, ...)
            if step in explored:
                continue
            explored.add(step)
            future = pool.submit(step.exec)  # <-- schedule steps for execution
            pending[future] = proof_id

    with ProcessPoolExecutor(max_workers=2) as pool:
        for proof_id in proofs:
            submit(proof_id, pool)

        while pending:
            done, _ = wait(pending, return_when='FIRST_COMPLETED')
            future = done.pop()
            proof_id = pending[future]
            proof = proofs[proof_id]
            prover = provers[proof_id]
            update = future.result()
            prover.commit(proof, update)  # <-- update the proof (can be in-memory, access disk with locking, ...)

            match proof.status:
                # terminate on first failure, yield partial results, etc.
                case ProofStatus.FAILED:
                    assert len(list(prover.steps(proof))) == 0
                    break
                case ProofStatus.PENDING:
                    assert len(list(prover.steps(proof))) > 0
                case ProofStatus.PASSED:
                    assert len(list(prover.steps(proof))) == 0
                    break

            submit(proof_id, pool)
            pending.pop(future)
    return proofs.values()
