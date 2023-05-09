from __future__ import annotations

from typing import TYPE_CHECKING

from pyk.cterm import CTerm
from pyk.kast.inner import KApply, KToken, KVariable
from pyk.prelude.ml import mlEqualsTrue

from ..utils import KCFGExploreTest

if TYPE_CHECKING:
    from pyk.kcfg import KCFGExplore
    from pyk.ktool.kprove import KProve


class TestImpProof(KCFGExploreTest):
    KOMPILE_MAIN_FILE = 'k-files/imp.k'

    def test_implication_failure_reason(
        self,
        kcfg_explore: KCFGExplore,
        kprove: KProve,
    ) -> None:
        lhs_config = KApply('<T>', [KApply('<k>', [KToken('1', 'Int')]), KApply('<state>', [KToken('.Map', 'Map')])])
        rhs_config = KApply('<T>', [KApply('<k>', [KToken('2', 'Int')]), KApply('<state>', [KToken('.Map', 'Map')])])

        lhs = CTerm(lhs_config, ())
        rhs = CTerm(rhs_config, ())

        (b, s) = kcfg_explore.implication_failure_reason(lhs, rhs)

        assert b == False
        assert (
            s
            == 'Structural matching failed, the following cells failed individually (abstract => concrete):\nK_CELL: ( 1 => 2 )'
        )

        lhs_config = KApply(
            '<T>',
            [
                KApply('<k>', [KVariable('VAR', 'Int')]),
                KApply('<state>', [KApply('_|->_', [KToken('1', 'Int'), KVariable('A', 'Int')])]),
            ],
        )
        rhs_config = KApply(
            '<T>',
            [
                KApply('<k>', [KVariable('VAR', 'Int')]),
                KApply('<state>', [KApply('_|->_', [KToken('1', 'Int'), KVariable('A', 'Int')])]),
            ],
        )

        lhs_constraint = [
            mlEqualsTrue(KApply('_<Int_', [KVariable('VAR', 'Int'), KToken('1', 'Int')])),
            mlEqualsTrue(KApply('_<Int_', [KVariable('A', 'Int'), KToken('1', 'Int')])),
        ]

        rhs_constraint = [
            mlEqualsTrue(KApply('_<Int_', [KVariable('VAR', 'Int'), KToken('1', 'Int')])),
            mlEqualsTrue(KApply('_<Int_', [KVariable('A', 'Int'), KToken('2', 'Int')])),
        ]

        lhs = CTerm(lhs_config, lhs_constraint)
        rhs = CTerm(rhs_config, rhs_constraint)

        (b, s) = kcfg_explore.implication_failure_reason(lhs, rhs)

        assert b == False
        assert (
            s
            == 'Implication check failed, the following is the remaining implication:\n{ true #Equals A:Int <Int 1 }\n#And { true #Equals VAR:Int <Int 1 } #Implies { true #Equals A:Int <Int 2 }'
        )
