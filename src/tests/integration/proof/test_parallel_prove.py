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
    nodes_values: dict[int, int]
    nodes_explored: dict[int, bool]
    edges: dict[int, list[int]]

    def __init__(self) -> None:
        self.nodes_explored = {}
        self.edges = {}
        for i in range(10):
            self.nodes_explored[i] = False

        #         0
        #        / \
        #       1   2
        #          / \
        #         3   4
        #        / \   \
        #       5   6   7
        #              / \
        #             8   9
        self.edges[0] = [1, 2]
        self.edges[1] = []
        self.edges[2] = [3, 4]
        self.edges[3] = [5, 6]
        self.edges[4] = [7]
        self.edges[5] = []
        self.edges[6] = []
        self.edges[7] = [8, 9]
        self.edges[8] = []
        self.edges[9] = []

    @property
    def status(self) -> ProofStatus:
        if all(self.nodes_explored.values()):
            return ProofStatus.PASSED
        else:
            return ProofStatus.PENDING


class TreeExploreProver(Prover[TreeExploreProof, int, int]):
    def __init__(self) -> None:
        return

    def initial_steps(self, proof: TreeExploreProof) -> Iterable[int]:
        return [0]

    def advance(self, proof: TreeExploreProof, step: int) -> int:
        print(f'Advancing node {step}\n', file=sys.stderr)
        time.sleep(5)
        print(f'Done advancing node {step}\n', file=sys.stderr)
        return step

    def commit(self, proof: TreeExploreProof, update: int) -> Iterable[int]:
        proof.nodes_explored[update] = True

        def parents(node_id: int) -> Iterable[int]:
            return [source for source, targets in proof.edges.items() if node_id in targets]

        return proof.edges[update]


def prove_parallel(
    proofs: list[Proof],
    # We need a way to map proofs to provers, but for simplicity, I'll assume it as a given
    provers: dict[Proof, Prover],
) -> Iterable[Proof]:
    pending: dict[Future[int], Proof] = {}

    def submit(proof: Proof, pool: Executor, step: int) -> None:
        prover = provers[proof]
        future = pool.submit(prover.advance, proof, step)  # <-- schedule steps for execution
        pending[future] = proof

    with ProcessPoolExecutor(max_workers=2) as pool:
        for proof in proofs:
            prover = provers[proof]
            for step in prover.initial_steps(proof):  # <-- get next steps (represented by e.g. pending nodes, ...)
                submit(proof, pool, step)

        while pending:
            future = list(wait(pending).done)[0]
            proof = pending[future]
            prover = provers[proof]
            update = future.result()
            next_steps = prover.commit(
                proof, update
            )  # <-- update the proof (can be in-memory, access disk with locking, ...)

            match proof.status:
                # terminate on first failure, yield partial results, etc.
                case ProofStatus.FAILED:
                    break
                case ProofStatus.PENDING:
                    ...
                case ProofStatus.PASSED:
                    break

            for step in next_steps:
                submit(proof, pool, step)
            pending.pop(future)
    return proofs


def test_parallel_prove() -> None:
    proof = TreeExploreProof()
    prover = TreeExploreProver()
    results = prove_parallel([proof], {proof: prover})
    assert len(list(results)) == 1
    assert list(results)[0].status == ProofStatus.PASSED
