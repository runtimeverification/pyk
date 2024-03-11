from __future__ import annotations

import logging
from pathlib import Path
from typing import TYPE_CHECKING

from pyk.kast.inner import KApply, KSequence
from pyk.kcfg.semantics import KCFGSemantics
from pyk.proof import APRProof, APRProver, ProofStatus
from pyk.testing import KCFGExploreTest, KProveTest
from pyk.utils import single

from ..utils import K_FILES

if TYPE_CHECKING:
    from typing import Final

    from pytest import TempPathFactory

    from pyk.cterm import CTerm
    from pyk.kast.inner import KInner
    from pyk.kast.outer import KDefinition
    from pyk.kcfg import KCFGExplore
    from pyk.ktool.kprove import KProve

_LOGGER: Final = logging.getLogger(__name__)


class SimpleSemantics(KCFGSemantics):
    def is_terminal(self, c: CTerm) -> bool:
        k_cell = c.cell('K_CELL')
        if type(k_cell) is KSequence and type(k_cell[0]) is KApply and k_cell[0].label.name == 'f_SIMPLE-PROOFS_Step':
            return True
        return False

    def extract_branches(self, c: CTerm) -> list[KInner]:
        return []

    def abstract_node(self, c: CTerm) -> CTerm:
        return c

    def same_loop(self, c1: CTerm, c2: CTerm) -> bool:
        return False


def leaf_number(proof: APRProof) -> int:
    non_target_leaves = [nd for nd in proof.kcfg.leaves if not proof.is_target(nd.id)]
    return len(non_target_leaves) + len(proof.kcfg.predecessors(proof.target))


class TestSimpleProof(KCFGExploreTest, KProveTest):
    KOMPILE_MAIN_FILE = K_FILES / 'simple-proofs.k'
    DISABLE_BOOSTER = True

    def semantics(self, definition: KDefinition) -> KCFGSemantics:
        return SimpleSemantics()

    def test_terminal_node_marking(
        self,
        kprove: KProve,
        kcfg_explore: KCFGExplore,
    ) -> None:
        spec_file = K_FILES / 'simple-proofs-spec.k'
        spec_module = 'SIMPLE-PROOFS-SPEC'

        claim = single(
            kprove.get_claims(spec_file, spec_module_name=spec_module, claim_labels=[f'{spec_module}.a-to-e'])
        )
        proof = APRProof.from_claim(kprove.definition, claim, logs={})
        kcfg_explore.simplify(proof.kcfg, {})
        prover = APRProver(
            kcfg_explore=kcfg_explore,
            execute_depth=1,
        )
        prover.advance_proof(proof)

        assert not proof.is_terminal(proof.target)
        for pred in proof.kcfg.predecessors(proof.target):
            assert not proof.is_terminal(pred.source.id)

        claim = single(
            kprove.get_claims(spec_file, spec_module_name=spec_module, claim_labels=[f'{spec_module}.a-to-f'])
        )
        proof = APRProof.from_claim(kprove.definition, claim, logs={})
        kcfg_explore.simplify(proof.kcfg, {})
        prover = APRProver(
            kcfg_explore=kcfg_explore,
            execute_depth=1,
        )
        prover.advance_proof(proof)

        assert proof.is_terminal(proof.target)
        for pred in proof.kcfg.predecessors(proof.target):
            assert proof.is_terminal(pred.source.id)

    def test_multiple_proofs_one_prover(
        self,
        kprove: KProve,
        kcfg_explore: KCFGExplore,
        tmp_path_factory: TempPathFactory,
    ) -> None:
        spec_file = K_FILES / 'simple-proofs-spec.k'
        spec_module = 'SIMPLE-PROOFS-SPEC'

        with tmp_path_factory.mktemp('apr_tmp_proofs') as proof_dir:
            spec_modules = kprove.get_claim_modules(Path(spec_file), spec_module_name=spec_module)
            proofs = APRProof.from_spec_modules(
                kprove.definition,
                spec_modules,
                logs={},
                proof_dir=proof_dir,
            )
            prover = APRProver(kcfg_explore=kcfg_explore)

            for claim_label in ['use-deps1', 'use-deps2']:
                spec_label = f'{spec_module}.{claim_label}'

                proof = single([p for p in proofs if p.id == spec_label])
                for subproof in proof.subproofs:
                    subproof.admit()
                    subproof.write_proof_data()

                prover.advance_proof(proof)

                assert proof.status == ProofStatus.PASSED
                assert leaf_number(proof) == 1
