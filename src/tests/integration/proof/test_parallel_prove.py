from __future__ import annotations

import time
from concurrent.futures import ProcessPoolExecutor, wait
from copy import deepcopy
from dataclasses import dataclass
from typing import TYPE_CHECKING

import pytest

from pyk.proof.parallel import Proof, ProofResult, ProofStep, Prover
from pyk.proof.proof import ProofStatus

if TYPE_CHECKING:
    from collections.abc import Iterable
    from concurrent.futures import Executor, Future


class TreeExploreProof(Proof):
    init: int
    target: int
    edges: dict[int, set[int]]
    reached: set[int]

    def __init__(self) -> None:
        self.init = 0
        self.reached = set()
        self.target = 9
        self.edges = {}

        #         0
        #        / \
        #       1   2
        #          / \
        #         3   4
        #        / \   \
        #       5   6   7
        #              / \
        #             8   9
        self.edges[0] = {1, 2}
        self.edges[1] = set()
        self.edges[2] = {3, 4}
        self.edges[3] = {5, 6}
        self.edges[4] = {7}
        self.edges[5] = set()
        self.edges[6] = set()
        self.edges[7] = {8, 9}
        self.edges[8] = set()
        self.edges[9] = set()

    @property
    def status(self) -> ProofStatus:
        if self.target in self.reached:
            return ProofStatus.PASSED
        else:
            return ProofStatus.PENDING


@dataclass(frozen=True)
class TreeExploreProofResult(ProofResult):
    node: int


@dataclass(frozen=True)
class TreeExploreProofStep(ProofStep[TreeExploreProofResult]):
    node: int

    def __hash__(self) -> int:
        return self.node.__hash__()

    def exec(self) -> TreeExploreProofResult:
        time.sleep(1)
        return TreeExploreProofResult(self.node)


class TreeExploreProver(Prover[TreeExploreProof, TreeExploreProofStep, TreeExploreProofResult]):
    proofs: dict[TreeExploreProof, TreeExploreProver] = {}

    def __init__(self) -> None:
        return

    def steps(self, proof: TreeExploreProof) -> Iterable[TreeExploreProofStep]:
        def parents(node_id: int) -> Iterable[int]:
            return [source for source, targets in proof.edges.items() if node_id in targets]

        if proof in TreeExploreProver.proofs:
            assert TreeExploreProver.proofs[proof] == self
        else:
            TreeExploreProver.proofs[proof] = self

        if proof.target in proof.reached:
            return []

        nodes = set(range(10))

        return [
            TreeExploreProofStep(node_id)
            for node_id in nodes
            if node_id not in proof.reached and all(parent in proof.reached for parent in parents(node_id))
        ]

    def commit(self, proof: TreeExploreProof, update: TreeExploreProofResult) -> None:
        if proof in TreeExploreProver.proofs:
            assert TreeExploreProver.proofs[proof] == self
        else:
            TreeExploreProver.proofs[proof] = self
        proof.reached.add(update.node)


def prove_parallel(
    proofs: list[TreeExploreProof],
    # We need a way to map proofs to provers, but for simplicity, I'll assume it as a given
    provers: dict[TreeExploreProof, TreeExploreProver],
) -> Iterable[TreeExploreProof]:
    pending: dict[Future[TreeExploreProofResult], TreeExploreProof] = {}
    explored: set[TreeExploreProofStep] = set()

    def submit(proof: TreeExploreProof, pool: Executor) -> None:
        prover = provers[proof]
        for step in prover.steps(proof):  # <-- get next steps (represented by e.g. pending nodes, ...)
            if step in explored:
                continue
            explored.add(step)
            future = pool.submit(step.exec)  # <-- schedule steps for execution
            pending[future] = proof

    with ProcessPoolExecutor(max_workers=2) as pool:
        for proof in proofs:
            submit(proof, pool)

        while pending:
            future = list(wait(pending).done)[0]
            proof = pending[future]
            prover = provers[proof]
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

            submit(proof, pool)
            pending.pop(future)
    return proofs


def test_multiple_provers_fails() -> None:
    prover1 = TreeExploreProver()
    prover2 = TreeExploreProver()
    proof = TreeExploreProof()
    step = list(prover1.steps(proof))[0]
    with pytest.raises(AssertionError):
        prover2.steps(proof)
    with pytest.raises(AssertionError):
        prover2.commit(proof, step.exec())


def test_steps_read_only() -> None:
    def assert_proof_equals(p1: TreeExploreProof, p2: TreeExploreProof) -> None:
        assert p1.edges == p2.edges
        assert p1.init == p2.init
        assert p1.reached == p2.reached
        assert p1.target == p2.target

    prover = TreeExploreProver()
    proof = TreeExploreProof()
    while True:
        initial_proof = deepcopy(proof)
        steps = prover.steps(proof)
        if len(list(steps)) == 0:
            break
        final_proof = deepcopy(proof)
        assert_proof_equals(initial_proof, final_proof)
        for step in steps:
            prover.commit(proof, step.exec())


def test_commit_after_finished() -> None:
    prover = TreeExploreProver()
    proof = TreeExploreProof()
    results: list[TreeExploreProofResult] = []
    while True:
        steps = prover.steps(proof)
        if len(list(steps)) == 0:
            break
        for step in steps:
            result = step.exec()
            results.append(result)
            prover.commit(proof, result)
            prover.commit(proof, result)
    for result in results:
        prover.commit(proof, result)


def test_parallel_prove() -> None:
    prover = TreeExploreProver()
    proof = TreeExploreProof()
    results = prove_parallel([proof], {proof: prover})
    assert len(list(results)) == 1
    assert len(list(prover.steps(proof))) == 0
    assert list(results)[0].status == ProofStatus.PASSED
