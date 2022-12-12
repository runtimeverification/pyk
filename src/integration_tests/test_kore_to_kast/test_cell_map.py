from typing import Final

import pytest

from pyk.kast.inner import KApply, KInner, KLabel, KSort, KVariable
from pyk.kore.syntax import DV, And, App, Equals, EVar, LeftAssoc, Pattern, SortApp, String
from pyk.ktool import KPrint
from pyk.prelude.kint import INT, intToken

from ..utils import KPrintTest

BIDIRECTIONAL_TEST_DATA: Final = (
    (
        'domain-value-int',
        INT,
        DV(SortApp('SortInt'), String('3')),
        intToken(3),
    ),
)

KAST_TO_KORE_TEST_DATA: Final = (
    (
        'cell-map',
        KSort('AccountCellMap'),
        And(
            SortApp('SortAccountCellMap'),
            App(
                "Lbl'Unds'AccountCellMap'Unds'",
                [],
                [
                    EVar("VarACCOUNTS'Unds'INIT", SortApp('AccountCellMap')),
                    App(
                        'AccountCellMapItem',
                        [],
                        [EVar('VarK', SortApp('SortIdCell')), EVar('VarV', SortApp('SortKItem'))],
                    ),
                ],
            ),
            Equals(
                SortApp('SortBool'),
                SortApp('SortAccountCellMap'),
                DV(SortApp('SortBool'), 'true'),
                App(
                    "Lbl'Unds'in'Unds'keys'LParUndsRParUnds'MAP'Unds'Bool'Unds'KItem'Unds'Map",
                    [],
                    [EVar('VarK', SortApp('SortIdCell')), EVar("VarACCOUNTS'Unds'INIT", SortApp('SortAccountCellMap'))],
                ),
            ),
        ),
        KApply(
            KLabel('#And', [KSort('AccountCellMap')]),
            [
                KApply(
                    '_AccountCellMap_',
                    [KVariable('ACCOUNTS_INIT'), KApply('AccountCellMapItem', [KVariable('K'), KVariable('V')])],
                ),
                KApply('_in_keys(_)_MAP_Bool_KItem_Map', [KVariable('K'), KVariable('ACCOUNTS_INIT')]),
            ],
        ),
    ),
)

KORE_TO_KAST_TEST_DATA: Final = (
    (
        'left-assoc',
        KSort('Map'),
        LeftAssoc(
            App(
                "Lbl'Unds'Map'Unds'",
                [],
                [
                    EVar('VarX', SortApp('SortMap')),
                    EVar('VarY', SortApp('SortMap')),
                    EVar('VarZ', SortApp('SortMap')),
                ],
            )
        ),
        KApply(
            '_Map_',
            [
                KApply('_Map_', [KVariable('X', sort=KSort('Map')), KVariable('Y', sort=KSort('Map'))]),
                KVariable('Z', sort=KSort('Map')),
            ],
        ),
    ),
)


class TestKoreToKastCellMap(KPrintTest):
    KOMPILE_MAIN_FILE = 'k-files/cell-map.k'

    @pytest.mark.parametrize(
        'test_id,sort,kore,kast', BIDIRECTIONAL_TEST_DATA, ids=[test_id for test_id, *_ in BIDIRECTIONAL_TEST_DATA]
    )
    def test_bidirectional(self, kprint: KPrint, test_id: str, sort: KSort, kore: Pattern, kast: KInner) -> None:
        # When
        actual_kore = kprint.kast_to_kore(kast, sort=sort)
        actual_kast = kprint.kore_to_kast(kore)

        # Then
        assert actual_kore == kore
        assert actual_kast == kast

    @pytest.mark.parametrize(
        'test_id,sort,kore,kast', KAST_TO_KORE_TEST_DATA, ids=[test_id for test_id, *_ in KAST_TO_KORE_TEST_DATA]
    )
    def test_kast_to_kore(self, kprint: KPrint, test_id: str, sort: KSort, kore: Pattern, kast: KInner) -> None:
        # When
        actual_kore = kprint.kast_to_kore(kast, sort=sort)

        # Then
        assert actual_kore == kore

    @pytest.mark.parametrize(
        'test_id,_sort,kore,kast', KORE_TO_KAST_TEST_DATA, ids=[test_id for test_id, *_ in KORE_TO_KAST_TEST_DATA]
    )
    def test_kore_to_kast(self, kprint: KPrint, test_id: str, _sort: KSort, kore: Pattern, kast: KInner) -> None:
        # When
        actual_kast = kprint.kore_to_kast(kore)

        # Then
        assert actual_kast == kast
