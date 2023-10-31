from __future__ import annotations

import time
import sys
from concurrent.futures import ProcessPoolExecutor, wait
from typing import TYPE_CHECKING, Any, Mapping

from pyk.proof.proof import Proof, ProofStatus, Prover

if TYPE_CHECKING:
    from collections.abc import Iterable
    from concurrent.futures import Executor, Future
    from pathlib import Path


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

    @classmethod
    def from_dict(cls: type[Proof], dct: Mapping[str, Any], proof_dir: Path | None = None) -> TreeExploreProof:
        return TreeExploreProof()

    def write_proof_data(self) -> None:
        return


class TreeExploreProver(Prover[TreeExploreProof, int, int]):
    def __init__(self) -> None:
        return

    def steps(self, proof: TreeExploreProof) -> Iterable[int]:
        def parents(node_id: int) -> Iterable[int]:
            return [source for source, targets in proof.edges.items() if node_id in targets]

        return [
            node_id
            for node_id, explored in proof.nodes_explored.items()
            if not explored and all(proof.nodes_explored[parent] for parent in parents(node_id))
        ]

    def advance(self, proof: TreeExploreProof, step: int) -> int:
        print(f'Advancing node {step}\n', file=sys.stderr)
        time.sleep(5)
        print(f'Done advancing node {step}\n', file=sys.stderr)
        return step

    # Should return P to be more flexible, but let's assume this for implicity
    def commit(self, proof: TreeExploreProof, update: int) -> None:
        proof.nodes_explored[update] = True


def prove_parallel(
    proofs: list[Proof],
    # We need a way to map proofs to provers, but for simplicity, I'll assume it as a given
    provers: dict[Proof, Prover],
) -> Iterable[Proof]:
    pending: dict[Future[int], Proof] = {}

    def submit(proof: Proof, pool: Executor) -> None:
        prover = provers[proof]
        for step in prover.steps(proof):  # <-- get next steps (represented by e.g. pending nodes, ...)
            future = pool.submit(prover.advance, proof, step)  # <-- schedule steps for execution
            pending[future] = proof

    with ProcessPoolExecutor(max_workers=3) as pool:
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
