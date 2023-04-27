from __future__ import annotations

import logging
from pathlib import Path
from typing import TYPE_CHECKING

import pytest

from pyk.cterm import CSubst, CTerm
from pyk.kast.inner import KApply, KSequence, KSort, KToken, KVariable, Subst
from pyk.kcfg import KCFG
from pyk.prelude.kbool import BOOL, notBool
from pyk.prelude.kint import intToken
from pyk.prelude.ml import mlAnd, mlBottom, mlEqualsTrue
from pyk.proof import APRProof, APRProver, ProofStatus
from pyk.utils import single

from ..utils import KCFGExploreTest

if TYPE_CHECKING:
    from collections.abc import Iterable
    from typing import Final

    from pyk.kast.inner import KInner
    from pyk.kast.outer import KDefinition
    from pyk.kcfg import KCFGExplore
    from pyk.ktool.kprint import KPrint, SymbolTable
    from pyk.ktool.kprove import KProve


_LOGGER: Final = logging.getLogger(__name__)


APR_PROVE_TEST_DATA: Iterable[
    tuple[str, str, str, str, int | None, int | None, Iterable[str], Iterable[str], ProofStatus, int]
] = (
    (
        'a-to-d',
        'k-files/conditionless-branch-spec.k',
        'CONDITIONLESS-BRANCH-SPEC',
        'a-to-d',
        None,
        None,
        [],
        [],
        ProofStatus.PASSED,
        1,
    ),
)


def leaf_number(kcfg: KCFG) -> int:
    target_id = kcfg.get_unique_target().id
    target_subsumed_nodes = (
        len(kcfg.edges(target_id=target_id))
        + len(kcfg.covers(target_id=target_id))
        + len(kcfg.splits(target_id=target_id))
    )
    frontier_nodes = len(kcfg.frontier)
    stuck_nodes = len(kcfg.stuck)
    return target_subsumed_nodes + frontier_nodes + stuck_nodes


class TestImpProof(KCFGExploreTest):
    KOMPILE_MAIN_FILE = 'k-files/conditionless-branch-verification.k'

#      @staticmethod
#      def _update_symbol_table(symbol_table: SymbolTable) -> None:
#          symbol_table['.List{"_,_"}_Ids'] = lambda: '.Ids'

#      @staticmethod
#      def _is_terminal(cterm1: CTerm) -> bool:
#          k_cell = cterm1.cell('K_CELL')
#          if type(k_cell) is KSequence:
#              if len(k_cell) == 0:
#                  return True
#              if len(k_cell) == 1 and type(k_cell[0]) is KVariable:
#                  return True
#          if type(k_cell) is KVariable:
#              return True
#          return False

#      @staticmethod
#      def _extract_branches(defn: KDefinition, cterm: CTerm) -> list[KInner]:
#          k_cell = cterm.cell('K_CELL')
#          if type(k_cell) is KSequence and len(k_cell) > 0:
#              k_cell = k_cell[0]
#          if type(k_cell) is KApply and k_cell.label.name == 'if(_)_else_':
#              condition = k_cell.args[0]
#              if (type(condition) is KVariable and condition.sort == BOOL) or (
#                  type(condition) is KApply and defn.return_sort(condition.label) == BOOL
#              ):
#                  return [mlEqualsTrue(condition), mlEqualsTrue(notBool(condition))]
#          return []

    @staticmethod
    def config(kprint: KPrint, k: str, state: str, constraint: KInner | None = None) -> CTerm:
        k_parsed = kprint.parse_token(KToken(k, 'Pgm'), as_rule=True)
        state_parsed = kprint.parse_token(KToken(state, 'Map'), as_rule=True)
        _config = CTerm(
            KApply(
                '<generatedTop>',
                KApply(
                    '<T>',
                    (
                        KApply('<k>', KSequence(k_parsed)),
                        KApply('<state>', state_parsed),
                    ),
                ),
                KVariable('GENERATED_COUNTER_CELL'),
            ),
            (),
        )
        if constraint is not None:
            _config = _config.add_constraint(constraint)
        return _config

#      @pytest.mark.parametrize(
#          'test_id,depth,pre,expected_depth,expected_post,expected_next_states',
#          EXECUTE_TEST_DATA,
#          ids=[test_id for test_id, *_ in EXECUTE_TEST_DATA],
#      )
#      def test_execute(
#          self,
#          kcfg_explore: KCFGExplore,
#          test_id: str,
#          depth: int,
#          pre: tuple[str, str],
#          expected_depth: int,
#          expected_post: tuple[str, str],
#          expected_next_states: Iterable[tuple[str, str]],
#      ) -> None:
#          # Given
#          k, state = pre
#          expected_k, expected_state = expected_post
#  
#          # When
#          actual_depth, actual_post_term, actual_next_terms = kcfg_explore.cterm_execute(
#              self.config(kcfg_explore.kprint, k, state), depth=depth
#          )
#          actual_k = kcfg_explore.kprint.pretty_print(actual_post_term.cell('K_CELL'))
#          actual_state = kcfg_explore.kprint.pretty_print(actual_post_term.cell('STATE_CELL'))
#  
#          actual_next_states = [
#              (
#                  kcfg_explore.kprint.pretty_print(s.cell('K_CELL')),
#                  kcfg_explore.kprint.pretty_print(s.cell('STATE_CELL')),
#              )
#              for s in actual_next_terms
#          ]
#  
#          # Then
#          assert actual_k == expected_k
#          assert actual_state == expected_state
#          assert actual_depth == expected_depth
#          assert set(actual_next_states) == set(expected_next_states)

    @pytest.mark.parametrize(
        'test_id,spec_file,spec_module,claim_id,max_iterations,max_depth,terminal_rules,cut_rules,proof_status,expected_leaf_number',
        APR_PROVE_TEST_DATA,
        ids=[test_id for test_id, *_ in APR_PROVE_TEST_DATA],
    )
    def test_all_path_reachability_prove(
        self,
        kprove: KProve,
        kcfg_explore: KCFGExplore,
        test_id: str,
        spec_file: str,
        spec_module: str,
        claim_id: str,
        max_iterations: int | None,
        max_depth: int | None,
        terminal_rules: Iterable[str],
        cut_rules: Iterable[str],
        proof_status: ProofStatus,
        expected_leaf_number: int,
    ) -> None:
        claim = single(
            kprove.get_claims(Path(spec_file), spec_module_name=spec_module, claim_labels=[f'{spec_module}.{claim_id}'])
        )

        kcfg = KCFG.from_claim(kprove.definition, claim)
        proof = APRProof(f'{spec_module}.{claim_id}', kcfg)
        prover = APRProver(
            proof,
#              is_terminal=TestImpProof._is_terminal,
#              extract_branches=lambda cterm: TestImpProof._extract_branches(kprove.definition, cterm),
        )
        kcfg = prover.advance_proof(
            kcfg_explore,
#              max_iterations=max_iterations,
#              execute_depth=max_depth,
#              cut_point_rules=cut_rules,
#              terminal_rules=terminal_rules,
        )

        assert proof.status == proof_status
        assert leaf_number(kcfg) == expected_leaf_number
