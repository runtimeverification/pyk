from __future__ import annotations

from pyk.kcfg import KCFG
from pyk.prelude.kbool import BOOL
from pyk.prelude.kint import intToken
from pyk.proof.equality import EqualityProof
from pyk.proof.reachability import APRBMCProof, APRProof

from .test_kcfg import node_dicts


def apr_proof(i: int) -> APRProof:
    return APRProof(id=f'apr_proof_{i}', kcfg=KCFG.from_dict({'nodes': node_dicts(i)}))


def aprbmc_proof(i: int) -> APRBMCProof:
    return APRBMCProof(id=f'aprbmc_proof_{i}', bmc_depth=i, kcfg=KCFG.from_dict({'nodes': node_dicts(i)}))


def equality_proof(i: int) -> EqualityProof:
    return EqualityProof(id=f'equality_proof_{i}', lhs_body=intToken(i), rhs_body=intToken(i), sort=BOOL)


#### APRProof


def test_apr_proof_add_subproof() -> None:
    # Given
    proof = apr_proof(1)

    # When
    proof.add_subproof(equality_proof(1))

    # Then
    assert len(proof.subproofs) == 1
    assert proof.subproofs[0].id == 'equality_proof_1'


def test_apr_proof_from_dict_no_subproofs() -> None:
    # Given
    d = {'type': 'APRProof', 'id': 'apr_proof_1', 'cfg': {'nodes': node_dicts(1)}}

    # When
    proof = APRProof.from_dict(d)

    # Then
    assert proof.dict == d


def test_apr_proof_from_dict_one_subproofs() -> None:
    # Given
    d = {
        'type': 'APRProof',
        'id': 'apr_proof_1',
        'cfg': {'nodes': node_dicts(1)},
        'subproofs': [equality_proof(1).dict],
    }

    # When
    proof = APRProof.from_dict(d)

    # Then
    assert proof.dict == d


def test_apr_proof_from_dict_heterogeneous_subproofs() -> None:
    # Given
    d = {
        'type': 'APRProof',
        'id': 'apr_proof_1',
        'cfg': {'nodes': node_dicts(1)},
        'subproofs': [equality_proof(1).dict, apr_proof(2).dict, aprbmc_proof(3).dict],
    }

    # When
    proof = APRProof.from_dict(d)

    # Then
    assert proof.dict == d


def test_apr_proof_from_dict_nested_subproofs() -> None:
    # Given
    d = {
        'type': 'APRProof',
        'id': 'aprbmc_proof_1',
        'cfg': {'nodes': node_dicts(1)},
        'subproofs': [
            {
                'type': 'APRProof',
                'id': 'apr_proof_4',
                'cfg': {'nodes': node_dicts(4)},
                'subproofs': [equality_proof(1).dict, apr_proof(2).dict, aprbmc_proof(3).dict],
            }
        ],
    }

    # When
    proof = APRProof.from_dict(d)

    # Then
    assert proof.dict == d


#### APRBMCProof


def test_aprbmc_proof_add_subproof() -> None:
    # Given
    proof = aprbmc_proof(1)

    # When
    proof.add_subproof(equality_proof(1))

    # Then
    assert len(proof.subproofs) == 1
    assert proof.subproofs[0].id == 'equality_proof_1'


def test_aprbmc_proof_from_dict_no_subproofs() -> None:
    # Given
    d = {
        'type': 'APRBMCProof',
        'id': 'aprbmc_proof_1',
        'bounded_states': [],
        'bmc_depth': 1,
        'cfg': {'nodes': node_dicts(1)},
    }

    # When
    proof = APRBMCProof.from_dict(d)

    # Then
    assert proof.dict == d


def test_aprbmc_proof_from_dict_one_subproofs() -> None:
    # Given
    d = {
        'type': 'APRBMCProof',
        'id': 'aprbmc_proof_1',
        'bounded_states': [],
        'bmc_depth': 1,
        'cfg': {'nodes': node_dicts(1)},
        'subproofs': [equality_proof(1).dict],
    }

    # When
    proof = APRBMCProof.from_dict(d)

    # Then
    assert proof.dict == d


def test_aprbmc_proof_from_dict_heterogeneous_subproofs() -> None:
    # Given
    d = {
        'type': 'APRBMCProof',
        'id': 'aprbmc_proof_1',
        'bounded_states': [],
        'bmc_depth': 1,
        'cfg': {'nodes': node_dicts(1)},
        'subproofs': [equality_proof(1).dict, aprbmc_proof(2).dict, aprbmc_proof(3).dict],
    }

    # When
    proof = APRBMCProof.from_dict(d)

    # Then
    assert proof.dict == d


def test_aprbmc_proof_from_dict_nested_subproofs() -> None:
    # Given
    d = {
        'type': 'APRBMCProof',
        'id': 'aprbmc_proof_1',
        'bounded_states': [],
        'bmc_depth': 1,
        'cfg': {'nodes': node_dicts(1)},
        'subproofs': [
            {
                'type': 'APRBMCProof',
                'id': 'aprbmc_proof_4',
                'bounded_states': [],
                'bmc_depth': 1,
                'cfg': {'nodes': node_dicts(4)},
                'subproofs': [equality_proof(1).dict, aprbmc_proof(2).dict, aprbmc_proof(3).dict],
            }
        ],
    }

    # When
    proof = APRBMCProof.from_dict(d)

    # Then
    assert proof.dict == d
