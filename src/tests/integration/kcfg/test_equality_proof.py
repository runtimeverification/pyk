from __future__ import annotations

import logging
from pathlib import Path
from typing import TYPE_CHECKING

import pytest

from pyk.proof import EqualityProof, EqualityProver, ProofStatus
from pyk.utils import single

from ..utils import K_FILES, KCFGExploreTest

if TYPE_CHECKING:
    from collections.abc import Iterable
    from typing import Final

    from pyk.kcfg import KCFGExplore
    from pyk.ktool.kprint import SymbolTable
    from pyk.ktool.kprove import KProve


_LOGGER: Final = logging.getLogger(__name__)

FUNC_PROVE_TEST_DATA: Iterable[tuple[str, Path, str, str, ProofStatus]] = (
    (
        'func-spec-concrete',
        K_FILES / 'imp-simple-spec.k',
        'IMP-FUNCTIONAL-SPEC',
        'concrete-addition',
        ProofStatus.PASSED,
    ),
    (
        'func-spec-concrete-fail',
        K_FILES / 'imp-simple-spec.k',
        'IMP-FUNCTIONAL-SPEC',
        'concrete-addition-fail',
        ProofStatus.FAILED,
    ),
    (
        'func-spec-concrete-identity',
        K_FILES / 'imp-simple-spec.k',
        'IMP-FUNCTIONAL-SPEC',
        'concrete-identity',
        ProofStatus.PASSED,
    ),
    (
        'func-spec-concrete-nonsense',
        K_FILES / 'imp-simple-spec.k',
        'IMP-FUNCTIONAL-SPEC',
        'concrete-nonsense',
        ProofStatus.FAILED,
    ),
    (
        'func-spec-concrete-requires-trivial-false-identity',
        K_FILES / 'imp-simple-spec.k',
        'IMP-FUNCTIONAL-SPEC',
        'concrete-requires-trivial-false-identity',
        ProofStatus.PASSED,
    ),
    (
        'func-spec-concrete-requires-nontrivial-false-identity',
        K_FILES / 'imp-simple-spec.k',
        'IMP-FUNCTIONAL-SPEC',
        'concrete-requires-nontrivial-false-identity',
        ProofStatus.PASSED,
    ),
    # TODO: this should be trivially passing but it fails because cterm_implies returns None
    # (
    #     'func-spec-concrete-requires-trivial-false-nonsense',
    #     K_FILES / 'imp-simple-spec.k',
    #     'IMP-FUNCTIONAL-SPEC',
    #     'concrete-requires-trivial-false-nonsense',
    #     ProofStatus.PASSED,
    # ),
    (
        'func-spec-concrete-requires-nontrivial-false-nonsense',
        K_FILES / 'imp-simple-spec.k',
        'IMP-FUNCTIONAL-SPEC',
        'concrete-requires-nontrivial-false-nonsense',
        ProofStatus.PASSED,
    ),
    (
        'func-spec-symbolic-add-comm',
        K_FILES / 'imp-simple-spec.k',
        'IMP-FUNCTIONAL-SPEC',
        'symbolic-addition-commutativity',
        ProofStatus.PASSED,
    ),
)


class TestImpEqualityProof(KCFGExploreTest):
    KOMPILE_MAIN_FILE = K_FILES / 'imp-verification.k'

    @staticmethod
    def _update_symbol_table(symbol_table: SymbolTable) -> None:
        symbol_table['.List{"_,_"}_Ids'] = lambda: '.Ids'

    @pytest.mark.parametrize(
        'test_id,spec_file,spec_module,claim_id, proof_status',
        FUNC_PROVE_TEST_DATA,
        ids=[test_id for test_id, *_ in FUNC_PROVE_TEST_DATA],
    )
    def test_functional_prove(
        self,
        kprove: KProve,
        kcfg_explore: KCFGExplore,
        test_id: str,
        spec_file: Path,
        spec_module: str,
        claim_id: str,
        proof_status: ProofStatus,
    ) -> None:
        claim = single(
            kprove.get_claims(Path(spec_file), spec_module_name=spec_module, claim_labels=[f'{spec_module}.{claim_id}'])
        )

        equality_proof = EqualityProof.from_claim(claim, kprove.definition)
        equality_prover = EqualityProver(equality_proof)
        equality_prover.advance_proof(kcfg_explore)

        assert equality_proof.status == proof_status
