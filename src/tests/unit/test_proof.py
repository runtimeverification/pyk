from __future__ import annotations

from typing import TYPE_CHECKING, Any

import pytest

from pyk.kcfg.kcfg import KCFG
from pyk.prelude.kbool import BOOL
from pyk.prelude.kint import intToken
from pyk.proof.equality import EqualityProof
from pyk.proof.reachability import APRBMCProof, APRProof
from pyk.proof.utils import read_proof

from .test_kcfg import node_dicts

if TYPE_CHECKING:
    from pathlib import Path

    from pytest import TempPathFactory


@pytest.fixture(scope='class')
def proof_dir(tmp_path_factory: TempPathFactory) -> Path:
    return tmp_path_factory.mktemp('proofs')


PROOF_TEST_DATA: list[dict[str, Any]] = [
    {
        'proof_type': 'APRProof',
        'proof_param': 1,
    },
    {
        'proof_type': 'APRBMCProof',
        'proof_param': 1,
    },
    {
        'proof_type': 'EqualityProof',
        'proof_param': 1,
    },
]


@pytest.fixture(scope='class', params=PROOF_TEST_DATA)
def sample_proof(
    request: pytest.FixtureRequest,
    proof_dir: Path,
) -> APRProof | APRBMCProof | EqualityProof:
    proof_type = request.param['proof_type']
    proof_param = request.param['proof_param']
    match proof_type:
        case 'APRProof':
            return APRProof(
                id=f'apr_proof_{proof_param}',
                kcfg=KCFG.from_dict({'nodes': node_dicts(proof_param)}),
                logs={},
                proof_dir=proof_dir,
            )
        case 'APRBMCProof':
            return APRBMCProof(
                id=f'aprbmc_proof_{proof_param}',
                bmc_depth=proof_param,
                kcfg=KCFG.from_dict({'nodes': node_dicts(proof_param)}),
                logs={},
                proof_dir=proof_dir,
            )
        case _:  # EqualityProof
            return EqualityProof(
                id=f'equality_proof_{proof_param}',
                lhs_body=intToken(proof_param),
                rhs_body=intToken(proof_param),
                sort=BOOL,
                proof_dir=proof_dir,
            )


class TestProof:
    def test_read_proof(self, sample_proof: APRProof | APRBMCProof | EqualityProof) -> None:
        # Given
        assert sample_proof.proof_dir
        sample_proof.write_proof()

        # When
        proof_from_disk = read_proof(id=sample_proof.id, proof_dir=sample_proof.proof_dir)

        # Then
        assert proof_from_disk.dict == sample_proof.dict
