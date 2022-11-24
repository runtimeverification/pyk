from typing import Final, Tuple
from unittest import TestCase

from pyk.kast.inner import KApply, KAst, KAtt, KLabel, KSort, KVariable
from pyk.kast.outer import KNonTerminal, KProduction, KRule, KTerminal
from pyk.ktool.kprint import SymbolTable, pretty_print_kast, unparser_for_production
from pyk.prelude.kbool import TRUE

success_production = KProduction(
    KSort('EndStatusCode'), [KTerminal('EVMC_SUCCESS')], klabel=KLabel('EVMC_SUCCESS_NETWORK_EndStatusCode')
)


class PrettyPrintKastTest(TestCase):
    TEST_DATA: Final[Tuple[Tuple[str, KAst, str], ...]] = (
        ('var', KVariable('V'), 'V'),
        ('var-sorted', KVariable('V', sort=KSort('Int')), 'V:Int'),
        ('rule', KRule(TRUE), 'rule  true\n  '),
        ('rule-empty-req', KRule(TRUE, ensures=TRUE), 'rule  true\n  '),
        (
            'rule-req-andbool',
            KRule(TRUE, ensures=KApply('_andBool_', [TRUE, TRUE])),
            'rule  true\n   ensures ( true\n   andBool ( true\n           ))\n  ',
        ),
        ('sort-decl', KProduction(KSort('Test')), 'syntax Test'),
        ('token-decl', KProduction(KSort('Test'), att=KAtt({'token': ''})), 'syntax Test [token()]'),
        (
            'function-decl',
            KProduction(KSort('Test'), [KTerminal('foo'), KNonTerminal(KSort('Int'))], att=KAtt({'function': ''})),
            'syntax Test ::= "foo" Int [function()]',
        ),
    )

    SYMBOL_TABLE: Final[SymbolTable] = {}

    def test_pretty_print(self) -> None:
        for name, kast, expected in self.TEST_DATA:
            with self.subTest(name):
                actual = pretty_print_kast(kast, self.SYMBOL_TABLE)
                actual_tokens = actual.split('\n')
                expected_tokens = expected.split('\n')
                self.assertListEqual(actual_tokens, expected_tokens)

    def test_unparser_underbars(self) -> None:
        unparser = unparser_for_production(success_production)
        expected = 'EVMC_SUCCESS'
        actual = unparser(KApply('EVMC_SUCCESS_NETWORK_EndStatusCode'))
        self.assertEqual(actual, expected)
