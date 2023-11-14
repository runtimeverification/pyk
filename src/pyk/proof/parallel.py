from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from multiprocessing import Process, Queue
from typing import TYPE_CHECKING, Generic, TypeVar

from pyk.kcfg.explore import KCFGExplore
from pyk.kore.rpc import KoreClient, TransportType, kore_server
from pyk.proof.proof import ProofStatus

from ..ktool.kprove import KoreExecLogFormat

if TYPE_CHECKING:
    from collections.abc import Iterable, Mapping
    from pathlib import Path

    from pyk.kcfg.semantics import KCFGSemantics
    from pyk.ktool.kprint import KPrint

    from ..utils import BugReport


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
        If proof.status() is ProofStatus.PENDING, prover.steps(proof) must be nonempty.
        If proof.status() is ProofStatus.PASSED, prover.steps(proof) must be empty.
        Once proof.status() is ProofStatus.PASSED or ProofStatus.FAILED, it must remain so.
        """
        ...


class ProcessData(ABC):
    ...


@dataclass(frozen=True)
class APRProofExtendData(ProcessData):
    #      kcfg_explore: KCFGExplore
    cut_point_rules: Iterable[str]
    terminal_rules: Iterable[str]
    execute_depth: int

    definition_dir: str | Path
    module_name: str

    kprint: KPrint

    llvm_definition_dir: Path | None = None
    port: int | None = None
    command: str | Iterable[str] | None = None
    bug_report: BugReport | None = None
    smt_timeout: int | None = None
    smt_retry_limit: int | None = None
    smt_tactic: str | None = None
    haskell_log_format: KoreExecLogFormat = KoreExecLogFormat.ONELINE
    haskell_log_entries: Iterable[str] = ()
    log_axioms_file: Path | None = None

    timeout: int | None = None
    bug_report_id: str | None = None
    transport: TransportType = TransportType.SINGLE_SOCKET
    dispatch: dict[str, list[tuple[str, int, TransportType]]] | None = None

    kcfg_semantics: KCFGSemantics | None = None
    id: str | None = None
    trace_rewrites: bool = False


@dataclass(frozen=True)
class APRProofExtendData2(ProcessData):
    kcfg_explore: KCFGExplore
    cut_point_rules: Iterable[str]
    terminal_rules: Iterable[str]
    execute_depth: int


class ProofStep(ABC, Generic[U]):
    """
    Should be a description of a computation needed to make progress on a `Proof`.
    Must be hashable.
    Must be frozen dataclass.
    Must be pickable.
    Should be small.
    """

    @abstractmethod
    def exec(self, data: APRProofExtendData2) -> U:
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
    fail_fast: bool = False,
    max_iterations: int | None = None,
    process_data: ProcessData | None = None,
) -> Iterable[Proof]:
    explored: set[tuple[str, ProofStep]] = set()
    iterations: dict[str, int] = {}

    in_queue: Queue = Queue()
    out_queue: Queue = Queue()

    pending_jobs: int = 0

    def run_process(data: APRProofExtendData) -> None:
        with kore_server(
            definition_dir=data.definition_dir,
            llvm_definition_dir=data.llvm_definition_dir,
            module_name=data.module_name,
            command=data.command,
            bug_report=data.bug_report,
            smt_timeout=data.smt_timeout,
            smt_retry_limit=data.smt_retry_limit,
            smt_tactic=data.smt_tactic,
            haskell_log_format=data.haskell_log_format,
            haskell_log_entries=data.haskell_log_entries,
            log_axioms_file=data.log_axioms_file,
        ) as server:
            with KoreClient(
                'localhost', server.port, bug_report=data.bug_report, bug_report_id=data.bug_report_id
            ) as client:
                kcfg_explore = KCFGExplore(
                    kprint=data.kprint,
                    kore_client=client,
                    kcfg_semantics=data.kcfg_semantics,
                    id=data.id,
                    trace_rewrites=data.trace_rewrites,
                )

                data2 = APRProofExtendData2(
                    kcfg_explore=kcfg_explore,
                    cut_point_rules=data.cut_point_rules,
                    execute_depth=data.execute_depth,
                    terminal_rules=data.terminal_rules,
                )

                kcfg_explore.add_dependencies_module(
                    data.module_name,
                    data.module_name + '-DEPENDS-MODULE',
                    [],
                    priority=1,
                )
                kcfg_explore.add_dependencies_module(
                    data.module_name,
                    data.module_name + '-CIRCULARITIES-MODULE',
                    [],
                    priority=1,
                )

                while True:
                    dequeued = in_queue.get()
                    if dequeued == 0:
                        break
                    proof_id, proof_step = dequeued
                    update = proof_step.exec(data2)
                    out_queue.put((proof_id, update))

    def submit(proof_id: str) -> None:
        proof = proofs[proof_id]
        prover = provers[proof_id]
        for step in prover.steps(proof):  # <-- get next steps (represented by e.g. pending nodes, ...)
            if (proof_id, step) in explored:
                continue
            explored.add((proof_id, step))
            in_queue.put((proof_id, step))
            nonlocal pending_jobs
            pending_jobs += 1

    processes = [Process(target=run_process, args=(process_data,)) for _ in range(max_workers)]
    for process in processes:
        process.start()

    for proof_id in proofs.keys():
        submit(proof_id)
        iterations[proof_id] = 0

    while pending_jobs > 0:
        proof_id, update = out_queue.get()
        pending_jobs -= 1

        proof = proofs[proof_id]
        prover = provers[proof_id]

        if max_iterations is not None and iterations[proof_id] >= max_iterations:
            continue

        prover.commit(proof, update)  # <-- update the proof (can be in-memory, access disk with locking, ...)

        iterations[proof_id] += 1

        match proof.status:
            # terminate on first failure, yield partial results, etc.
            case ProofStatus.FAILED:
                if fail_fast:
                    continue
            case ProofStatus.PENDING:
                assert len(list(prover.steps(proof))) > 0
            case ProofStatus.PASSED:
                assert len(list(prover.steps(proof))) == 0

        submit(proof_id)

    for _ in range(max_workers):
        in_queue.put(0)

    for process in processes:
        process.join()

    return proofs.values()
