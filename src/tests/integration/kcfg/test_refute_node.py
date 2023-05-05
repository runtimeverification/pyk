from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

import pytest

from pyk.kast.inner import KApply, KSequence, KVariable
from pyk.kcfg import KCFG, KCFGShow
from pyk.prelude.kbool import andBool
from pyk.prelude.kint import eqInt, gtInt, intToken, leInt
from pyk.prelude.ml import mlEqualsTrue
from pyk.proof import APRProof, APRProver, ProofStatus
from pyk.utils import single

from ..utils import KCFGExploreTest

if TYPE_CHECKING:
    from collections.abc import Iterable
    from typing import Union

    from pytest import TempPathFactory

    from pyk.cterm import CTerm
    from pyk.kast.inner import KInner
    from pyk.kcfg import KCFGExplore
    from pyk.ktool.kprove import KProve

    STATE = Union[tuple[str, str], tuple[str, str, str]]

REFUTE_NODE_TEST_DATA: Iterable[tuple[str, KInner | None, ProofStatus]] = (
    ('refute-node-fail', None, ProofStatus.FAILED),
    ('refute-node-success-concrete-N', mlEqualsTrue(eqInt(KVariable('N'), intToken(-1))), ProofStatus.PASSED),
    (
        'refute-node-success-range-N',
        mlEqualsTrue(andBool([gtInt(KVariable('N'), intToken(-100)), leInt(KVariable('N'), intToken(-10))])),
        ProofStatus.PASSED,
    ),
)


class TestAPRProof(KCFGExploreTest):
    KOMPILE_MAIN_FILE = 'k-files/refute-node.k'

    @pytest.fixture(scope='function')
    def proof_dir(self, tmp_path_factory: TempPathFactory) -> Path:
        return tmp_path_factory.mktemp('proofs')

    @staticmethod
    def _extract_branches(cterm: CTerm) -> list[KInner]:
        k_cell = cterm.cell('K_CELL')
        if type(k_cell) is KSequence and len(k_cell) > 0:
            k_cell = k_cell[0]
        if type(k_cell) is KApply and k_cell.label.name == 'd(_)_REFUTE-NODE-SYNTAX_A_Int':
            discriminant = k_cell.args[0]
            return [mlEqualsTrue(gtInt(discriminant, intToken(0))), mlEqualsTrue(leInt(discriminant, intToken(0)))]
        return []

    @pytest.mark.parametrize(
        'test_id,extra_constraint,expected_status',
        REFUTE_NODE_TEST_DATA,
        ids=[test_id for test_id, *_ in REFUTE_NODE_TEST_DATA],
    )
    def test_apr_proof_refute_node(
        self,
        kprove: KProve,
        kcfg_explore: KCFGExplore,
        proof_dir: Path,
        test_id: str,
        extra_constraint: KInner,
        expected_status: ProofStatus,
    ) -> None:
        # Given
        spec_file = 'k-files/refute-node-spec.k'
        spec_module = 'REFUTE-NODE-SPEC'
        claim_id = 'split-int-fail'

        claim = single(
            kprove.get_claims(Path(spec_file), spec_module_name=spec_module, claim_labels=[f'{spec_module}.{claim_id}'])
        )
        kcfg_pre = KCFG.from_claim(kprove.definition, claim)
        proof = APRProof(f'{spec_module}.{claim_id}', kcfg_pre, proof_dir=proof_dir)
        prover = APRProver(proof, extract_branches=TestAPRProof._extract_branches)
        shower = KCFGShow(kcfg_explore.kprint)

        def _node_printer(cterm: CTerm) -> Iterable[str]:
            return kprove.pretty_print(cterm.cell('K_CELL')).split('\n')

        # When
        kcfg_post = prover.advance_proof(
            kcfg_explore,
        )
        assert prover.proof.status == ProofStatus.FAILED

        stuck_node = single(kcfg_post.stuck)
        prover.refute_node(kcfg_explore, stuck_node, extra_constraint=extra_constraint)
        print('\n'.join(shower.show('dummy', kcfg_post, node_printer=_node_printer)))
        print('\n'.join(prover.proof.summary))
        print('\n'.join(list(dict(prover.proof.read_refutations()).values())[0].pretty(kprove)))
        # stuck_node_refutation = single(prover.proof.read_subproofs())
        # assert type(stuck_node_refutation) is EqualityProof

        # eq_prover = EqualityProver(stuck_node_refutation)
        # eq_prover.advance_proof(kcfg_explore)
        # print('\n'.join(stuck_node_refutation.pretty(kprove)))

        # Then
        assert prover.proof.status == expected_status


# class TestSimpleProof(KCFGExploreTest):
#     KOMPILE_MAIN_FILE = 'k-files/simple-proofs.k'

#     # @pytest.mark.parametrize(
#     #     'test_id,pre,expected_post',
#     #     SIMPLIFY_TEST_DATA,
#     #     ids=[test_id for test_id, *_ in SIMPLIFY_TEST_DATA],
#     # )
#     def test_apr_proof(
#         self,
#         kprove: KProve,
#         kcfg_explore: KCFGExplore,
#         # test_id: str,
#         # pre: tuple[str, str],
#         # expected_post: tuple[str, str],
#     ) -> None:
#         # Given
#         spec_file = 'k-files/simple-proofs-spec.k'
#         spec_module = 'SIMPLE-PROOFS-SPEC'
#         claim_id = 'test-foo-to-bar'

#         claim = single(
#             kprove.get_claims(Path(spec_file), spec_module_name=spec_module, claim_labels=[f'{spec_module}.{claim_id}'])
#         )
#         kcfg_pre = KCFG.from_claim(kprove.definition, claim)
#         proof = APRProof(f'{spec_module}.{claim_id}', kcfg_pre)
#         prover = APRProver(
#             proof,
#         )
#         shower = KCFGShow(kcfg_explore.kprint)

#         def _node_printer(cterm: CTerm) -> Iterable[str]:
#             return kprove.pretty_print(cterm.kast).split('\n')

#         # When
#         kcfg_post = prover.advance_proof(
#             kcfg_explore,
#         )
#         print('\n'.join(shower.show('dummy', kcfg_post, node_printer=_node_printer)))
#         for stuck_node in kcfg_post.stuck:
#             prover.proof.refute_node(stuck_node)
#             # print('\n'.join(_node_printer(stuck_node.cterm)))
#             # print('\n'.join(_node_printer(stuck_node.cterm)))
#         print('\n'.join(prover.proof.summary))

#         assert False
#         # Then
#         assert actual_k == expected_k
#         assert actual_state == expected_state
