from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

import pytest

from pyk.proof.parallel import prove_parallel
from pyk.proof.proof import ProofStatus
from pyk.proof.reachability import APRProof, APRProofProcessData, ParallelAPRProver
from pyk.testing import KCFGExploreTest, KPrintTest, KProveTest
from pyk.utils import single

from ..utils import K_FILES
from .test_imp import ImpSemantics

if TYPE_CHECKING:
    from pytest import TempPathFactory

    from pyk.kast.outer import KDefinition
    from pyk.kcfg.explore import KCFGExplore
    from pyk.kcfg.semantics import KCFGSemantics
    from pyk.ktool.kprint import KPrint
    from pyk.ktool.kprove import KProve

PARALLEL_PROVE_TEST_DATA = (
    ('addition-1', ProofStatus.PASSED),
    ('sum-10', ProofStatus.PASSED),
    ('failing-if', ProofStatus.FAILED),
)


@pytest.fixture(scope='function')
def proof_dir(tmp_path_factory: TempPathFactory) -> Path:
    return tmp_path_factory.mktemp('proofs')


class TestImpParallelProve(KCFGExploreTest, KProveTest, KPrintTest):
    KOMPILE_MAIN_FILE = K_FILES / 'imp-verification.k'

    def semantics(self, definition: KDefinition) -> KCFGSemantics:
        return ImpSemantics(definition)

    @pytest.mark.parametrize(
        'claim_id,expected_status',
        PARALLEL_PROVE_TEST_DATA,
        ids=[test_id for test_id, *_ in PARALLEL_PROVE_TEST_DATA],
    )
    def test_imp_parallel_prove(
        self,
        claim_id: str,
        expected_status: ProofStatus,
        kcfg_explore: KCFGExplore,
        proof_dir: Path,
        kprove: KProve,
        kprint: KPrint,
    ) -> None:
        #          claim_id = 'addition-1'
        spec_file = K_FILES / 'imp-simple-spec.k'
        spec_module = 'IMP-SIMPLE-SPEC'

        claim = single(
            kprove.get_claims(Path(spec_file), spec_module_name=spec_module, claim_labels=[f'{spec_module}.{claim_id}'])
        )

        proof = APRProof.from_claim(kprove.definition, claim, logs={}, proof_dir=proof_dir)

        semantics = self.semantics(kprove.definition)
        parallel_prover = ParallelAPRProver(
            proof=proof,
            module_name=kprove.main_module,
            definition_dir=kprove.definition_dir,
            execute_depth=1000,
            kprint=kprint,
            kcfg_semantics=semantics,
            id=claim_id,
            trace_rewrites=False,
            cut_point_rules=(),
            terminal_rules=(),
            bug_report=None,
            bug_report_id=None,
        )

        process_data = APRProofProcessData(
            kprint=kprint,
            kcfg_semantics=semantics,
            definition_dir=kprove.definition_dir,
            module_name=kprove.main_module,
        )

        results = prove_parallel(
            proofs={'proof1': proof},
            provers={'proof1': parallel_prover},
            max_workers=2,
            process_data=process_data,
        )

        assert len(list(results)) == 1
        assert list(results)[0].status == expected_status
