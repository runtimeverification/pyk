from pyk.kast import KApply, KSequence, KSort, KVariable
from pyk.kore.syntax import DV, App, EVar, SortApp, String
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
                'variable-with-sort',
                KSort('Int'),
                EVar('VarX', SortApp('SortInt')),
                KVariable('X', sort=KSort('Int')),
            ),
            (
                'variable-with-super-sort',
                KSort('Bar'),
                App('inj', [SortApp('SortBaz'), SortApp('SortBar')], [EVar('VarX', SortApp('SortBaz'))]),
                KVariable('X', sort=KSort('Baz')),
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
            (
                'munging-problem',
                KSort('Baz'),
                App("Lblfoo-bar'Unds'SIMPLE-PROOFS'Unds'Baz", [], []),
                KApply('foo-bar_SIMPLE-PROOFS_Baz', []),
            ),
            (
                'kseq-empty',
                KSort('K'),
                App('dotk', [], []),
                KSequence([]),
            ),
            (
                'kseq-singleton',
                KSort('K'),
                App(
                    'kseq',
                    [],
                    [
                        App(
                            'inj',
                            [SortApp('SortBaz'), SortApp('SortKItem')],
                            [App("Lblfoo-bar'Unds'SIMPLE-PROOFS'Unds'Baz", [], [])],
                        ),
                        App('dotk', (), ()),
                    ],
                ),
                KSequence([KApply('foo-bar_SIMPLE-PROOFS_Baz')]),
            ),
            (
                'kseq-two-element',
                KSort('K'),
                App(
                    'kseq',
                    [],
                    [
                        App("Lblfoo'Unds'SIMPLE-PROOFS'Unds'KItem", [], []),
                        App(
                            'kseq',
                            [],
                            [
                                App(
                                    'inj',
                                    [SortApp('SortBaz'), SortApp('SortKItem')],
                                    [App("Lblfoo-bar'Unds'SIMPLE-PROOFS'Unds'Baz", [], [])],
                                ),
                                App('dotk', (), ()),
                            ],
                        ),
                    ],
                ),
                KSequence([KApply('foo_SIMPLE-PROOFS_KItem'), KApply('foo-bar_SIMPLE-PROOFS_Baz')]),
            ),
        )
        for name, sort, kore, kast in kore_kast_pairs:
            with self.subTest(name):
                kore_actual = self.kprove.kast_to_kore(kast, sort=sort)
                kast_actual = self.kprove.kore_to_kast(kore)
                self.assertEqual(kore_actual, kore)
                self.assertEqual(kast_actual, kast)
