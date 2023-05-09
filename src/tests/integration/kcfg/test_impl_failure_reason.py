from __future__ import annotations

from typing import TYPE_CHECKING

from pyk.kast.inner import KApply, KToken

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

        result = kcfg_explore.implication_failure_reason(lhs, rhs)
        
        for b,s in result:
            print(b)
            print(s)

        assert 1 == 2
