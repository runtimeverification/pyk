from __future__ import annotations

import time
import sys
from abc import ABC, abstractmethod
from multiprocessing import Process, Queue

#  from concurrent.futures import CancelledError, ProcessPoolExecutor, wait
from typing import TYPE_CHECKING, Generic, TypeVar

from pyk.proof.proof import ProofStatus

if TYPE_CHECKING:
    from collections.abc import Iterable, Mapping


P = TypeVar('P', bound='Proof')
U = TypeVar('U')
D = TypeVar('D', bound='ProcessData')


class Prover(ABC, Generic[P, U, D]):
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
    def steps(self, proof: P) -> Iterable[ProofStep[U, D]]:
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
        If proof.status() is ProofStatus.PENDING, prover.steps(proof) must be nonempty.
        If proof.status() is ProofStatus.PASSED, prover.steps(proof) must be empty.
        Once proof.status() is ProofStatus.PASSED or ProofStatus.FAILED, it must remain so.
        """
        ...


class ProcessData(ABC):
    ...


#      @abstractmethod
#      def cleanup(self) -> None:
#          ...


class ProofStep(ABC, Generic[U, D]):
    """
    Should be a description of a computation needed to make progress on a `Proof`.
    Must be hashable.
    Must be frozen dataclass.
    Must be pickable.
    Should be small.
    """

    @abstractmethod
    def exec(self, data: D) -> U:
        """
        Should perform some nontrivial computation given by `self`, which can be done independently of other calls to `exec()`.
        Allowed to be nondeterministic.
        Able to be called on any `ProofStep` returned by `prover.steps(proof)`.
        """
        ...


def prove_parallel(
    proofs: Mapping[str, Proof],
    provers: Mapping[str, Prover],
    max_workers: int,
    process_data: ProcessData,
) -> Iterable[Proof]:
    explored: set[tuple[str, ProofStep]] = set()

    in_queue: Queue = Queue()
    out_queue: Queue = Queue()

    pending_jobs: int = 0

    total_commit_time = 0
    total_steps_time = 0
    total_process_time = 0
    total_time = 0

    total_init_time = time.time_ns()
    print('d', file=sys.stderr)

    def run_process(data: ProcessData) -> None:
        while True:
            dequeued = in_queue.get()
            if dequeued == 0:
                break
            proof_id, proof_step = dequeued
            update = proof_step.exec(data)
            out_queue.put((proof_id, update))

    #          data.cleanup()

    def submit(proof_id: str) -> None:
        proof = proofs[proof_id]
        prover = provers[proof_id]
        steps_init_time = time.time_ns()
        steps = prover.steps(proof)
        nonlocal total_steps_time
        total_steps_time += time.time_ns() - steps_init_time
        for step in steps:  # <-- get next steps (represented by e.g. pending nodes, ...)
            if (proof_id, step) in explored:
                continue
            explored.add((proof_id, step))
            in_queue.put((proof_id, step))
            nonlocal pending_jobs
            pending_jobs += 1

    processes = [Process(target=run_process, args=(process_data,)) for _ in range(max_workers)]
    for process in processes:
        process.start()
    print('e', file=sys.stderr)

    for proof_id in proofs.keys():
        submit(proof_id)
        print('f', file=sys.stderr)

    while pending_jobs > 0:
        wait_init_time = time.time_ns()
        proof_id, update = out_queue.get()
        total_process_time += time.time_ns() - wait_init_time
        print('g', file=sys.stderr)
        pending_jobs -= 1

        proof = proofs[proof_id]
        prover = provers[proof_id]

        commit_init_time = time.time_ns()
        prover.commit(proof, update)  # <-- update the proof (can be in-memory, access disk with locking, ...)
        total_commit_time += time.time_ns() - commit_init_time

        match proof.status:
            # terminate on first failure, yield partial results, etc.
            case ProofStatus.FAILED:
                ...
            case ProofStatus.PENDING:
                steps_init_time = time.time_ns()
                if not list(prover.steps(proof)):
                    raise ValueError('Prover violated expectation. status is pending with no further steps.')
                total_steps_time += time.time_ns() - steps_init_time
            case ProofStatus.PASSED:
                steps_init_time = time.time_ns()
                if list(prover.steps(proof)):
                    raise ValueError('Prover violated expectation. status is passed with further steps.')
                total_steps_time += time.time_ns() - steps_init_time

        submit(proof_id)

    for _ in range(max_workers):
        in_queue.put(0)

    for process in processes:
        process.join()

    total_time = time.time_ns() - total_init_time

    print(f'total time: {total_time / 1000000000}')
    print(f'steps time: {total_steps_time / 1000000000}')
    print(f'commit time: {total_commit_time / 1000000000}')
    print(f'process time: {total_process_time / 1000000000}')

    return proofs.values()
