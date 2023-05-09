from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from pyk.kcfg.kcfg import KCFG
from pyk.prelude.kbool import BOOL
from pyk.prelude.kint import intToken
from pyk.proof.equality import EqualityProof
from pyk.proof.reachability import APRBMCProof, APRProof

from .test_kcfg import node_dicts

if TYPE_CHECKING:
    from pathlib import Path

    from pytest import TempPathFactory


@pytest.fixture(scope='function')
def proof_dir(tmp_path_factory: TempPathFactory) -> Path:
    return tmp_path_factory.mktemp('proofs')


def apr_proof(i: int, proof_dir: Path) -> APRProof:
    return APRProof(id=f'apr_proof_{i}', kcfg=KCFG.from_dict({'nodes': node_dicts(i)}), proof_dir=proof_dir)


def aprbmc_proof(i: int, proof_dir: Path) -> APRBMCProof:
    return APRBMCProof(
        id=f'aprbmc_proof_{i}', bmc_depth=i, kcfg=KCFG.from_dict({'nodes': node_dicts(i)}), proof_dir=proof_dir
    )


def equality_proof(i: int, proof_dir: Path) -> EqualityProof:
    return EqualityProof(
        id=f'equality_proof_{i}', lhs_body=intToken(i), rhs_body=intToken(i), sort=BOOL, proof_dir=proof_dir
    )


#### APRProof


def test_apr_proof_add_subproof(proof_dir: Path) -> None:
    # Given
    proof = apr_proof(1, proof_dir)
    proof.write_proof()
    eq_proof = equality_proof(1, proof_dir)
    eq_proof.write_proof()

    # When
    proof.add_subproof(eq_proof.id)

    # Then
    assert len(proof.subproof_ids) == 1
    assert len(list(proof.subproofs)) == 1
    assert list(proof.subproofs)[0].id == 'equality_proof_1'


def test_apr_proof_from_dict_no_subproofs() -> None:
    # Given
    d = {
        'type': 'APRProof',
        'id': 'apr_proof_1',
        'cfg': {'nodes': node_dicts(1)},
        'subproof_ids': [],
        'node_refutations': {},
    }

    # When
    proof = APRProof.from_dict(d)

    # Then
    assert proof.dict == d


def test_apr_proof_from_dict_one_subproofs(proof_dir: Path) -> None:
    # Given
    d = {
        'type': 'APRProof',
        'id': 'apr_proof_1',
        'cfg': {'nodes': node_dicts(1)},
        'subproof_ids': [equality_proof(1, proof_dir).id],
        'node_refutations': {},
    }

    # When
    proof = APRProof.from_dict(d)

    # Then
    assert proof.dict == d


def test_apr_proof_from_dict_heterogeneous_subproofs(proof_dir: Path) -> None:
    # Given
    d = {
        'type': 'APRProof',
        'id': 'apr_proof_1',
        'cfg': {'nodes': node_dicts(1)},
        'subproof_ids': [equality_proof(1, proof_dir).id, apr_proof(2, proof_dir).id, aprbmc_proof(3, proof_dir).id],
        'node_refutations': {},
    }

    # When
    proof = APRProof.from_dict(d)

    # Then
    assert proof.dict == d


#### APRBMCProof


def test_aprbmc_proof_add_subproof(proof_dir: Path) -> None:
    # Given
    proof = aprbmc_proof(1, proof_dir)
    proof.write_proof()
    subproof = equality_proof(1, proof_dir)
    subproof.write_proof()

    # When
    proof.add_subproof(subproof.id)

    # Then
    assert len(proof.subproof_ids) == 1
    assert list(proof.subproofs)[0].id == 'equality_proof_1'


def test_aprbmc_proof_from_dict_no_subproofs() -> None:
    # Given
    d = {
        'type': 'APRBMCProof',
        'id': 'aprbmc_proof_1',
        'subproof_ids': [],
        'bounded_states': [],
        'bmc_depth': 1,
        'cfg': {'nodes': node_dicts(1)},
        'node_refutations': {},
    }

    # When
    proof = APRBMCProof.from_dict(d)

    # Then
    assert proof.dict == d


def test_aprbmc_proof_from_dict_one_subproofs(proof_dir: Path) -> None:
    # Given
    d = {
        'type': 'APRBMCProof',
        'id': 'aprbmc_proof_1',
        'bounded_states': [],
        'bmc_depth': 1,
        'cfg': {'nodes': node_dicts(1)},
        'subproof_ids': [equality_proof(1, proof_dir).id],
        'node_refutations': {},
    }

    # When
    proof = APRBMCProof.from_dict(d)

    # Then
    assert proof.dict == d


def test_aprbmc_proof_from_dict_heterogeneous_subproofs(proof_dir: Path) -> None:
    # Given
    d = {
        'type': 'APRBMCProof',
        'id': 'aprbmc_proof_1',
        'bounded_states': [],
        'bmc_depth': 1,
        'cfg': {'nodes': node_dicts(1)},
        'subproof_ids': [equality_proof(1, proof_dir).id, aprbmc_proof(2, proof_dir).id, aprbmc_proof(3, proof_dir).id],
        'node_refutations': {},
    }

    # When
    proof = APRBMCProof.from_dict(d)

    # Then
    assert proof.dict == d
