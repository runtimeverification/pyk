from __future__ import annotations

import sys
import time
from concurrent.futures import ProcessPoolExecutor, wait
from typing import TYPE_CHECKING

from pyk.proof.parallel import Proof, Prover
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


class TreeExploreProver(Prover[TreeExploreProof, int, int]):
    def __init__(self) -> None:
        return

    def steps(self, proof: TreeExploreProof) -> Iterable[int]:
        def parents(node_id: int) -> Iterable[int]:
            return [source for source, targets in proof.edges.items() if node_id in targets]

        nodes = set(range(10))

        return [
            node_id
            for node_id in nodes
            if node_id not in proof.reached and all(parent in proof.reached for parent in parents(node_id))
        ]

    def advance(self, proof: TreeExploreProof, step: int) -> int:
        print(f'Advancing node {step}\n', file=sys.stderr)
        time.sleep(5)
        print(f'Done advancing node {step}\n', file=sys.stderr)
        return step

    def commit(self, proof: TreeExploreProof, update: int) -> None:
        proof.reached.add(update)


def prove_parallel(
    proofs: list[Proof],
    # We need a way to map proofs to provers, but for simplicity, I'll assume it as a given
    provers: dict[Proof, Prover],
) -> Iterable[Proof]:
    pending: dict[Future[int], Proof] = {}
    explored: set[int] = set()

    def submit(proof: Proof, pool: Executor) -> None:
        prover = provers[proof]
        for step in prover.steps(proof):  # <-- get next steps (represented by e.g. pending nodes, ...)
            if step in explored:
                continue
            explored.add(step)
            future = pool.submit(prover.advance, proof, step)  # <-- schedule steps for execution
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
                    break
                case ProofStatus.PENDING:
                    ...
                case ProofStatus.PASSED:
                    break

            submit(proof, pool)
            pending.pop(future)
    return proofs


def test_parallel_prove() -> None:
    proof = TreeExploreProof()
    prover = TreeExploreProver()
    results = prove_parallel([proof], {proof: prover})
    assert len(list(results)) == 1
    assert list(results)[0].status == ProofStatus.PASSED
