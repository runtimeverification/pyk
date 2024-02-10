from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

import pytest

from pyk.proof.parallel import prove_parallel
from pyk.proof.proof import ProofStatus
from pyk.proof.reachability import APRBMCProof, APRProof, APRProofProcessData, ParallelAPRBMCProver, ParallelAPRProver
from pyk.testing import KCFGExploreTest, KPrintTest, KProveTest
from pyk.utils import single

from ..utils import K_FILES
from .test_imp import ImpSemantics

if TYPE_CHECKING:
    from pytest import TempPathFactory

    from pyk.kast.outer import KDefinition
    from pyk.kcfg.explore import KCFGExplore
    from pyk.kcfg.semantics import KCFGSemantics
    from pyk.kore.rpc import KoreServer
    from pyk.ktool.kprove import KProve

PARALLEL_PROVE_TEST_DATA = (
    ('addition-1', ProofStatus.PASSED, False),
    ('sum-10', ProofStatus.PASSED, False),
    ('dep-fail-1', ProofStatus.PASSED, True),
    ('sum-N', ProofStatus.PASSED, True),
    ('sum-loop', ProofStatus.PASSED, False),
    ('failing-if', ProofStatus.FAILED, False),
    ('long-branches', ProofStatus.PASSED, False),
)


@pytest.fixture(scope='function')
def proof_dir(tmp_path_factory: TempPathFactory) -> Path:
    return tmp_path_factory.mktemp('proofs')


class TestImpParallelProve(KCFGExploreTest, KProveTest, KPrintTest):
    KOMPILE_MAIN_FILE = K_FILES / 'imp-verification.k'

    def semantics(self, definition: KDefinition) -> KCFGSemantics:
        return ImpSemantics(definition)

    @pytest.mark.parametrize(
        'claim_id,expected_status,admit_deps',
        PARALLEL_PROVE_TEST_DATA,
        ids=[test_id for test_id, *_ in PARALLEL_PROVE_TEST_DATA],
    )
    def test_imp_parallel_prove(
        self,
        claim_id: str,
        expected_status: ProofStatus,
        admit_deps: bool,
        kcfg_explore: KCFGExplore,
        kprove: KProve,
        proof_dir: Path,
        _kore_server: KoreServer,
    ) -> None:
        spec_file = K_FILES / 'imp-simple-spec.k'
        spec_module = 'IMP-SIMPLE-SPEC'

        spec_modules = kprove.get_claim_modules(Path(spec_file), spec_module_name=spec_module)
        spec_label = f'{spec_module}.{claim_id}'
        proofs = APRProof.from_spec_modules(
            kprove.definition,
            spec_modules,
            spec_labels=[spec_label],
            logs={},
            proof_dir=proof_dir,
        )
        proof = single([p for p in proofs if p.id == spec_label])

        if admit_deps:
            for subproof in proof.subproofs:
                subproof.admit()
                subproof.write_proof_data()

        semantics = self.semantics(kprove.definition)
        parallel_prover = ParallelAPRProver(
            proof=proof,
            module_name=kprove.main_module,
            definition_dir=kprove.definition_dir,
            execute_depth=100,
            kprint=kprove,
            kcfg_semantics=semantics,
            id=claim_id,
            trace_rewrites=False,
            cut_point_rules=(),
            terminal_rules=(),
            bug_report=None,
            bug_report_id=None,
            port=_kore_server.port,
        )

        process_data = APRProofProcessData(
            kprint=kprove,
            kcfg_semantics=semantics,
            definition_dir=kprove.definition_dir,
            module_name=kprove.main_module,
        )

        results, _ = prove_parallel(
            proofs={'proof1': proof},
            provers={'proof1': parallel_prover},
            max_workers=1,
            process_data=process_data,
        )

        assert len(list(results)) == 1
        assert list(results)[0].status == expected_status

    def test_imp_bmc_parallel_prove(
        self,
        kcfg_explore: KCFGExplore,
        kprove: KProve,
        proof_dir: Path,
        _kore_server: KoreServer,
    ) -> None:
        claim_id = 'bmc-infinite-loop'
        expected_status = ProofStatus.PASSED

        spec_file = K_FILES / 'imp-simple-spec.k'
        spec_module = 'IMP-SIMPLE-SPEC'

        spec_label = f'{spec_module}.{claim_id}'

        claim = single(kprove.get_claims(Path(spec_file), spec_module_name=spec_module, claim_labels=[spec_label]))
        proof = APRBMCProof.from_claim_with_bmc_depth(kprove.definition, claim, 5)

        semantics = self.semantics(kprove.definition)
        parallel_prover = ParallelAPRBMCProver(
            proof=proof,
            module_name=kprove.main_module,
            definition_dir=kprove.definition_dir,
            execute_depth=100,
            kprint=kprove,
            kcfg_semantics=semantics,
            id=claim_id,
            trace_rewrites=False,
            cut_point_rules=['IMP.while'],
            terminal_rules=(),
            bug_report=None,
            bug_report_id=None,
            port=_kore_server.port,
        )

        process_data = APRProofProcessData(
            kprint=kprove,
            kcfg_semantics=semantics,
            definition_dir=kprove.definition_dir,
            module_name=kprove.main_module,
        )

        results, _ = prove_parallel(
            proofs={'proof1': proof},
            provers={'proof1': parallel_prover},
            max_workers=1,
            process_data=process_data,
        )

        assert len(list(results)) == 1
        assert list(results)[0].status == expected_status
