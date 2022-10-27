from pyk.kast import KApply, KSequence, KSort
from pyk.kore.syntax import DV, App, SortApp, String
from pyk.ktool import KompileBackend
from pyk.ktool.kprint import SymbolTable
from pyk.prelude.kint import intToken

from .kprove_test import KProveTest


class KoreToKastTest(KProveTest):
    KOMPILE_MAIN_FILE = 'k-files/simple-proofs.k'
    KOMPILE_BACKEND = KompileBackend.HASKELL
    KOMPILE_EMIT_JSON = True

    @staticmethod
    def _update_symbol_table(symbol_table: SymbolTable) -> None:
        pass

    def test_kast_to_kore(self) -> None:
        kore_kast_pairs = (
            (
                'domain-value',
                KSort('Int'),
                DV(SortApp('SortInt'), String('3')),
                intToken(3),
            ),
            (
                'issue:k/2762',
                KSort('Bool'),
                App('Lblpred1', [], [DV(SortApp('SortInt'), String('3'))]),
                KApply('pred1', [intToken(3)]),
            ),
            (
                'cells-conversion',
                KSort('KCell'),
                App("Lbl'-LT-'k'-GT-'", [], [App('dotk', [], [])]),
                KApply('<k>', [KSequence()]),
            ),
            (
                'simple-injection',
                KSort('Foo'),
                App('Lblfoo', [], [App('inj', [SortApp('SortBaz'), SortApp('SortBar')], [App('Lblbaz', [], [])])]),
                KApply('foo', [KApply('baz')]),
            ),
            (
                'cells-conversion',
                KSort('KItem'),
                App(
                    'inj',
                    [SortApp('SortKCell'), SortApp('SortKItem')],
                    [App("Lbl'-LT-'k'-GT-'", [], [App('dotk', [], [])])],
                ),
                KApply('<k>', [KSequence()]),
            ),
        )
        for name, sort, kore, kast in kore_kast_pairs:
            with self.subTest(name):
                kore_actual = self.kprove.kast_to_kore(kast, sort=sort)
                kast_actual = self.kprove.kore_to_kast(kore)
                self.assertEqual(kore_actual, kore)
                self.assertEqual(kast_actual, kast)
