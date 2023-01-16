import logging
from pathlib import Path

import pytest

from pyk.kcfg import KCFG, KCFGExplore
from pyk.ktool import KProve
from pyk.ktool.kprint import SymbolTable

from ..utils import KProveTest

IMP_SIMPLE_TEST_DATA = (('imp-simple-addition-1', 'k-files/imp-simple-spec.k', 'IMP-SIMPLE-SPEC', 'addition-1', 1),)


class TestImpSimpleKCFGExplore(KProveTest):
    KOMPILE_MAIN_FILE = 'k-files/imp-verification.k'
    KOMPILE_MAIN_MODULE = 'IMP-VERIFICATION'

    @staticmethod
    def _update_symbol_table(symbol_table: SymbolTable) -> None:
        symbol_table['.List{"_,_"}_Ids'] = lambda: '.Ids'

    @pytest.mark.parametrize(
        'test_id,spec_file,spec_module,claim_id,max_depth',
        IMP_SIMPLE_TEST_DATA,
        ids=[test_id for test_id, *_ in IMP_SIMPLE_TEST_DATA],
    )
    def test_imp_simple_kcfg_explore(
        self,
        kprove: KProve,
        test_id: str,
        spec_file: str,
        spec_module: str,
        claim_id: str,
        max_depth: int,
    ) -> None:

        claims = kprove.get_claims(
            Path(spec_file), spec_module_name=spec_module, claim_labels=[f'{spec_module}.{claim_id}']
        )
        assert len(claims) == 1

        kcfg_explore = KCFGExplore(kprove)
        kcfg = KCFG.from_claim(kprove.definition, claims[0])
        kcfg = kcfg_explore.all_path_reachability(f'{spec_module}.{claim_id}', kcfg, execute_depth=max_depth)

        failed_nodes = len(kcfg.frontier) + len(kcfg.stuck)
        assert failed_nodes == 0
