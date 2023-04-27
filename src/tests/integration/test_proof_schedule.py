from __future__ import annotations

import itertools
from pathlib import Path
from typing import TYPE_CHECKING

import pytest

from pyk.proof.equality import EqualityProof
from pyk.proof.proof import ProofStatus
from pyk.proof.schedule import ProofSchedule

from .utils import KCFGExploreTest

if TYPE_CHECKING:
    from collections.abc import Iterable

    # from pathlib import Path
    from pytest import TempPathFactory

    from pyk.kcfg import KCFGExplore


@pytest.fixture(scope='function')
def proof_dir(tmp_path_factory: TempPathFactory) -> Path:
    return tmp_path_factory.mktemp('proofs')


def equality_proofs(proof_dir: Path | None = None) -> Iterable[EqualityProof]:
    """
    An infinite stream of one-simplification proofs like `3 + 4 = 7`
    """
    for idx in itertools.count(start=0, step=1):
        proof = EqualityProof.from_dict(
            proof_dir=proof_dir,
            dct={
                'type': 'EqualityProof',
                'id': f'equality_proof_{idx}',
                'lhs_body': {
                    'node': 'KApply',
                    'label': {'node': 'KLabel', 'name': '_+Int_', 'params': []},
                    'args': [
                        {'node': 'KToken', 'token': str(idx), 'sort': {'node': 'KSort', 'name': 'Int'}},
                        {'node': 'KToken', 'token': str(idx + 1), 'sort': {'node': 'KSort', 'name': 'Int'}},
                    ],
                    'arity': 2,
                    'variable': False,
                },
                'rhs_body': {'node': 'KToken', 'token': str(idx + idx + 1), 'sort': {'node': 'KSort', 'name': 'Int'}},
                'sort': {'node': 'KSort', 'name': 'Int'},
                'lhs_constraints': [{'node': 'KToken', 'token': 'true', 'sort': {'node': 'KSort', 'name': 'Bool'}}],
                'rhs_constraints': [{'node': 'KToken', 'token': 'true', 'sort': {'node': 'KSort', 'name': 'Bool'}}],
            },
        )
        proof.write_proof()
        yield proof


class TestProofSchedule(KCFGExploreTest):
    KOMPILE_MAIN_FILE = 'k-files/imp-verification.k'

    TEST_DATA: Iterable[tuple[str, int, list[tuple[str, str]]]] = [
        (
            'init_linear',
            3,
            [('equality_proof_0', 'equality_proof_1'), ('equality_proof_1', 'equality_proof_2')],
        ),
        (
            'init_fork',
            3,
            [('equality_proof_0', 'equality_proof_1'), ('equality_proof_0', 'equality_proof_2')],
        ),
    ]

    @pytest.mark.parametrize(
        'test_id,nproofs,proof_dag_edges',
        TEST_DATA,
        ids=[test_id for test_id, *_ in TEST_DATA],
    )
    def test_init(
        self,
        proof_dir: Path,
        test_id: str,
        nproofs: int,
        proof_dag_edges: list[tuple[str, str]],
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
            'proof_dag_edges': [('equality_proof_0', 'equality_proof_1'), ('equality_proof_1', 'equality_proof_2')],
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
            'equality_proof_0',
            'equality_proof_1',
            'equality_proof_2',
        ]

    def test_topological_sorting_binary_tree(self, proof_dir: Path) -> None:
        # Given
        proof1, proof2, proof3 = itertools.islice(equality_proofs(proof_dir=proof_dir), 3)
        proof_dag_edges = [(proof1.id, proof2.id), (proof1.id, proof3.id)]

        # When
        proof_schedule = ProofSchedule(id='test', proof_dir=proof_dir, proof_dag_edges=proof_dag_edges)

        # Then
        assert [proof.id for proof in proof_schedule.topological_sorting] == [
            'equality_proof_0',
            'equality_proof_1',
            'equality_proof_2',
        ]

    def test_roots(self, proof_dir: Path) -> None:
        proof1, proof2, proof3 = itertools.islice(equality_proofs(proof_dir=proof_dir), 3)
        proof_dag_edges = [(proof1.id, proof2.id), (proof1.id, proof3.id)]

        # When
        proof_schedule = ProofSchedule(id='test', proof_dir=proof_dir, proof_dag_edges=proof_dag_edges)

        # Then
        assert proof_schedule.roots == [proof1.id]

    def test_leafs(self, proof_dir: Path) -> None:
        proof1, proof2, proof3 = itertools.islice(equality_proofs(proof_dir=proof_dir), 3)
        proof_dag_edges = [(proof1.id, proof2.id), (proof1.id, proof3.id)]

        # When
        proof_schedule = ProofSchedule(id='test', proof_dir=proof_dir, proof_dag_edges=proof_dag_edges)

        # Then
        assert proof_schedule.leafs == [proof2.id, proof3.id]

    def test_direct_dependencies(self, proof_dir: Path) -> None:
        proof1, proof2, proof3 = itertools.islice(equality_proofs(proof_dir=proof_dir), 3)
        proof_dag_edges = [(proof1.id, proof2.id), (proof1.id, proof3.id)]

        # When
        proof_schedule = ProofSchedule(id='test', proof_dir=proof_dir, proof_dag_edges=proof_dag_edges)

        # Then
        assert proof_schedule.direct_dependencies(proof2.id) == [proof1.id]
        assert proof_schedule.direct_dependencies(proof3.id) == [proof1.id]

    def test_dependencies(self, proof_dir: Path) -> None:
        proofs = list(itertools.islice(equality_proofs(proof_dir=proof_dir), 5))
        proof_dag_edges = [
            (proofs[0].id, proofs[1].id),
            (proofs[1].id, proofs[2].id),
            (proofs[0].id, proofs[3].id),
            (proofs[3].id, proofs[4].id),
        ]

        # When
        proof_schedule = ProofSchedule(id='test', proof_dir=proof_dir, proof_dag_edges=proof_dag_edges)

        # Then
        assert set(proof_schedule._dependencies(proofs[2].id)) == {proofs[0].id, proofs[1].id, proofs[2].id}
        assert set(proof_schedule._dependencies(proofs[4].id)) == {proofs[4].id, proofs[3].id, proofs[0].id}

    def test_fire_proof(self, proof_dir: Path, kcfg_explore: KCFGExplore) -> None:
        proofs = list(itertools.islice(equality_proofs(proof_dir=proof_dir), 5))
        proof_dag_edges = [
            (proofs[0].id, proofs[1].id),
            (proofs[1].id, proofs[2].id),
            (proofs[0].id, proofs[3].id),
            (proofs[3].id, proofs[4].id),
        ]

        # When
        proof_schedule = ProofSchedule(id='test', proof_dir=proof_dir, proof_dag_edges=proof_dag_edges)

        proof_schedule.fire_proof(proofs[2].id, kcfg_explore)

        for i in [0, 1, 2]:
            assert proof_schedule._proofs[proofs[i].id].status == ProofStatus.PASSED
        for i in [3, 4]:
            assert proof_schedule._proofs[proofs[i].id].status == ProofStatus.PENDING

    def test_fire_two_proofs(self, proof_dir: Path, kcfg_explore: KCFGExplore) -> None:
        proofs = list(itertools.islice(equality_proofs(proof_dir=proof_dir), 5))
        proof_dag_edges = [
            (proofs[0].id, proofs[1].id),
            (proofs[1].id, proofs[2].id),
            (proofs[0].id, proofs[3].id),
            (proofs[3].id, proofs[4].id),
        ]

        # When
        proof_schedule = ProofSchedule(id='test', proof_dir=proof_dir, proof_dag_edges=proof_dag_edges)
        proof_schedule.fire_proof(proofs[2].id, kcfg_explore)

        # Then
        for i in [0, 1, 2]:
            assert proof_schedule._proofs[proofs[i].id].status == ProofStatus.PASSED
        for i in [3, 4]:
            assert proof_schedule._proofs[proofs[i].id].status == ProofStatus.PENDING

        proof_schedule.fire_proof(proofs[4].id, kcfg_explore)
        for i in [0, 1, 2, 3, 4]:
            assert proof_schedule._proofs[proofs[i].id].status == ProofStatus.PASSED

        f = Path('/home/geo2a/Desktop/t.dot')
        f.write_text(proof_schedule.dot)
