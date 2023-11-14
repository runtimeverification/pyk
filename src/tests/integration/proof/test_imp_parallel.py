from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

import pytest

from pyk.proof.parallel import prove_parallel
from pyk.proof.proof import ProofStatus
from pyk.proof.reachability import APRProof, APRProofExtendData, APRProver, ParallelAPRProver
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


@pytest.fixture(scope='function')
def proof_dir(tmp_path_factory: TempPathFactory) -> Path:
    return tmp_path_factory.mktemp('proofs')


class TestImpParallelProve(KCFGExploreTest, KProveTest, KPrintTest):
    KOMPILE_MAIN_FILE = K_FILES / 'imp-verification.k'

    def semantics(self, definition: KDefinition) -> KCFGSemantics:
        return ImpSemantics(definition)

    def test_imp_parallel_prove(
        self, kcfg_explore: KCFGExplore, proof_dir: Path, kprove: KProve, kprint: KPrint
    ) -> None:
        #          claim_id = 'addition-1'
        claim_id = 'failing-if'
        spec_file = K_FILES / 'imp-simple-spec.k'
        spec_module = 'IMP-SIMPLE-SPEC'

        claim = single(
            kprove.get_claims(Path(spec_file), spec_module_name=spec_module, claim_labels=[f'{spec_module}.{claim_id}'])
        )

        proof = APRProof.from_claim(kprove.definition, claim, logs={}, proof_dir=proof_dir)
        prover = APRProver(
            proof,
            kcfg_explore=kcfg_explore,
        )

        process_data = APRProofExtendData(
            cut_point_rules=[],
            terminal_rules=[],
            execute_depth=1000,
            definition_dir=kprove.definition_dir,
            module_name=kprove.main_module,
            kprint=kprint,
        )

        parallel_prover = ParallelAPRProver(prover=prover)

        results = prove_parallel(
            proofs={'proof1': proof},
            provers={'proof1': parallel_prover},
            max_workers=2,
            process_data=process_data,
        )

        assert len(list(results)) == 1
        assert list(results)[0].status == ProofStatus.FAILED
