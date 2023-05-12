from __future__ import annotations

import json
import logging
from typing import TYPE_CHECKING, Final

from ..utils import hash_str
from .equality import EqualityProof, RefutationProof
from .proof import Proof
from .reachability import APRBMCProof, APRProof

if TYPE_CHECKING:
    from pathlib import Path

_LOGGER: Final = logging.getLogger(__name__)


def read_proof(id: str, proof_dir: Path) -> APRProof | APRBMCProof | EqualityProof | RefutationProof:
    proof_path = proof_dir / f'{hash_str(id)}.json'
    if Proof.proof_exists(id, proof_dir):
        proof_dict = json.loads(proof_path.read_text())
        proof_type = proof_dict['type']
        _LOGGER.info(f'Reading {proof_type} from file {id}: {proof_path}')
        match proof_type:
            case 'APRProof':
                return APRProof.from_dict(proof_dict, proof_dir=proof_dir)
            case 'APRBMCProof':
                return APRBMCProof.from_dict(proof_dict, proof_dir=proof_dir)
            case 'EqualityProof':
                return EqualityProof.from_dict(proof_dict, proof_dir=proof_dir)
            case 'RefutationProof':
                return RefutationProof.from_dict(proof_dict, proof_dir=proof_dir)

    raise ValueError(f'Could not load APRBMCProof from file {id}: {proof_path}')
