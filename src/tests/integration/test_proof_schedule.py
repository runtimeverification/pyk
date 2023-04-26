from __future__ import annotations

import itertools
from typing import TYPE_CHECKING

import pytest

from pyk.prelude.kbool import BOOL
from pyk.prelude.kint import intToken
from pyk.proof.equality import EqualityProof
from pyk.proof.schedule import ProofSchedule

from .utils import KCFGExploreTest

if TYPE_CHECKING:
    from collections.abc import Iterable
    from pathlib import Path
    from pytest import TempPathFactory


@pytest.fixture(scope='function')
def proof_dir(tmp_path_factory: TempPathFactory) -> Path:
    return tmp_path_factory.mktemp('proofs')


def equality_proofs(proof_dir: Path | None = None) -> Iterable[EqualityProof]:
    for idx in itertools.count(start=1, step=1):
        proof = EqualityProof(
            id=f'equality_proof_{idx}',
            lhs_body=intToken(idx),
            rhs_body=intToken(idx),
            sort=BOOL,
            proof_dir=proof_dir,
        )
        proof.write_proof()
        yield proof


class TestProofSchedule(KCFGExploreTest):
    TEST_DATA: Iterable[tuple[str, int, list[tuple[str, str]]]] = [
        (
            'init_linear',
            3,
            [('equality_proof_1', 'equality_proof_2'), ('equality_proof_2', 'equality_proof_3')],
        ),
        (
            'init_fork',
            3,
            [('equality_proof_1', 'equality_proof_2'), ('equality_proof_1', 'equality_proof_3')],
        ),
    ]

    @pytest.mark.parametrize(
        'test_id,nproofs,proof_dag_edges',
        TEST_DATA,
        ids=[test_id for test_id, *_ in TEST_DATA],
    )
    def test_init(
        self,
        proof_dir,
        test_id,
        nproofs,
        proof_dag_edges,
    ) -> None:
        # Given
        proofs = list(itertools.islice(equality_proofs(proof_dir), nproofs))

        # When
        proof_schedule = ProofSchedule(id='test', proof_dir=proof_dir, proof_dag_edges=proof_dag_edges)

        # Then
        assert len(proof_schedule._proofs.items()) == nproofs
        for i in range(nproofs):
            assert proof_schedule._proofs[proofs[i].id].id == proofs[i].id

    def test_init_fail_cycle(self, proof_dir: Path) -> None:
        # Given
        proof1, proof2 = itertools.islice(equality_proofs(proof_dir), 2)

        # When
        proof_dag_edges = [(proof1.id, proof2.id), (proof2.id, proof1.id)]

        # Then
        with pytest.raises(ValueError):
            _ = ProofSchedule(id='test', proof_dir=proof_dir, proof_dag_edges=proof_dag_edges)

    def test_dict(self, proof_dir: Path) -> None:
        # Given
        proof1, proof2, proof3 = itertools.islice(equality_proofs(proof_dir=proof_dir), 3)
        proof_dag_edges = [(proof1.id, proof2.id), (proof2.id, proof3.id)]

        # When
        proof_schedule = ProofSchedule(id='test', proof_dir=proof_dir, proof_dag_edges=proof_dag_edges)

        # Then
        assert proof_schedule.dict == {
            'type': 'ProofSchedule',
            'id': 'test',
            'proof_dag_edges': [('equality_proof_1', 'equality_proof_2'), ('equality_proof_2', 'equality_proof_3')],
            'proof_dir': str(proof_dir),
        }

    def test_read_write(self, proof_dir: Path) -> None:
        proof1, proof2, proof3 = itertools.islice(equality_proofs(proof_dir=proof_dir), 3)
        proof_dag_edges = [(proof1.id, proof2.id), (proof2.id, proof3.id)]

        # When
        proof_schedule = ProofSchedule(id='test', proof_dir=proof_dir, proof_dag_edges=proof_dag_edges)
        proof_schedule.write_proof_schedule()
        actual = ProofSchedule.read_proof_schedule(proof_schedule.id, proof_dir=proof_dir)

        # Then
        assert proof_schedule.dict == actual.dict

    def test_topological_sorting_linear(self, proof_dir: Path) -> None:
        # Given
        proof1, proof2, proof3 = itertools.islice(equality_proofs(proof_dir=proof_dir), 3)
        proof_dag_edges = [(proof1.id, proof2.id), (proof2.id, proof3.id)]

        # When
        proof_schedule = ProofSchedule(id='test', proof_dir=proof_dir, proof_dag_edges=proof_dag_edges)

        # Then
        assert [proof.id for proof in proof_schedule.topological_sorting] == [
            'equality_proof_1',
            'equality_proof_2',
            'equality_proof_3',
        ]

    def test_topological_sorting_binary_tree(self, proof_dir: Path) -> None:
        # Given
        proof1, proof2, proof3 = itertools.islice(equality_proofs(proof_dir=proof_dir), 3)
        proof_dag_edges = [(proof1.id, proof2.id), (proof1.id, proof3.id)]

        # When
        proof_schedule = ProofSchedule(id='test', proof_dir=proof_dir, proof_dag_edges=proof_dag_edges)

        # Then
        assert [proof.id for proof in proof_schedule.topological_sorting] == [
            'equality_proof_1',
            'equality_proof_2',
            'equality_proof_3',
        ]
