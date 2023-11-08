from __future__ import annotations

import time
from dataclasses import dataclass
from typing import TYPE_CHECKING

import pytest

from pyk.proof.parallel import Proof, ProofStep, Prover, prove_parallel
from pyk.proof.proof import ProofStatus

if TYPE_CHECKING:
    from collections.abc import Iterable


class TreeExploreProof(Proof):
    init: int
    target: int
    edges: dict[int, set[int]]
    reached: set[int]

    def __init__(self, init: int, target: int, edges: dict[int, set[int]]) -> None:
        self.init = init
        self.reached = set()
        self.target = target
        self.edges = edges

    @property
    def status(self) -> ProofStatus:
        if self.target in self.reached:
            return ProofStatus.PASSED
        else:
            return ProofStatus.PENDING


@dataclass(frozen=True)
class TreeExploreProofStep(ProofStep[int]):
    node: int

    def __hash__(self) -> int:
        return self.node.__hash__()

    def exec(self) -> int:
        time.sleep(1)
        return self.node


class TreeExploreProver(Prover[TreeExploreProof, int]):
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

    def commit(self, proof: TreeExploreProof, update: int) -> None:
        if proof in TreeExploreProver.proofs:
            assert TreeExploreProver.proofs[proof] == self
        else:
            TreeExploreProver.proofs[proof] = self
        proof.reached.add(update)


def simple_tree() -> dict[int, set[int]]:
    #         0
    #        / \
    #       1   2
    #          / \
    #         3   4
    #        / \   \
    #       5   6   7
    #              / \
    #             8   9
    return {0: {1, 2}, 1: set(), 2: {3, 4}, 3: {5, 6}, 4: {7}, 5: set(), 6: set(), 7: {8, 9}, 8: set(), 9: set()}


def test_multiple_provers_fails() -> None:
    prover1 = TreeExploreProver()
    prover2 = TreeExploreProver()
    proof = TreeExploreProof(0, 9, simple_tree())
    step = list(prover1.steps(proof))[0]
    with pytest.raises(AssertionError):
        prover2.steps(proof)
    with pytest.raises(AssertionError):
        prover2.commit(proof, step.exec())


def test_parallel_prove() -> None:
    prover = TreeExploreProver()
    proof = TreeExploreProof(0, 9, simple_tree())
    results = prove_parallel({'proof1': proof}, {'proof1': prover})
    assert len(list(results)) == 1
    assert len(list(prover.steps(proof))) == 0
    assert list(results)[0].status == ProofStatus.PASSED
