from pyk.kast.inner import KApply, KSequence, KToken
from pyk.kast.manip import flatten_label, get_cell
from pyk.kore.parser import KoreParser
from pyk.kore.syntax import DV, App, Pattern, SortApp, String
from pyk.ktool import KRun
from pyk.ktool.kprint import KAstInput, KAstOutput, _kast
from pyk.prelude.kint import intToken

from .utils import Kompiler, KRunTest


class TestImpRun(KRunTest):
    KOMPILE_MAIN_FILE = 'k-files/imp.k'
    KOMPILE_BACKEND = 'haskell'

    def test_run(self, krun: KRun) -> None:
        # Given
        init_pgm_token = KToken('int n , s ; n = 2 ; s = 0 ; while ( 0 <= n ) { s = s + n ; n = n + -1 ; }', 'Pgm')
        final_cterm = krun.run(init_pgm_token)

        expected_k = KSequence([])
        expected_map_items = [
            KApply('_|->_', [KToken('s', 'Id'), intToken(3)]),
            KApply('_|->_', [KToken('n', 'Id'), intToken(-1)]),
        ]

        # When
        actual_k = get_cell(final_cterm.config, 'K_CELL')
        actual_map_items = flatten_label('_Map_', get_cell(final_cterm.config, 'STATE_CELL'))

        assert actual_k == expected_k
        assert set(actual_map_items) == set(expected_map_items)

    def test_run_kore_term(self, krun: KRun) -> None:
        # Given
        x = '#token("x", "Id")'
        pattern = self._state(krun, k=f'int {x} ; {x} = 1 ;', state='.Map')
        expected = self._state(krun, k='.', state=f'{x} |-> 1')

        # When
        actual = krun.run_kore_term(pattern)

        # Then
        assert actual == expected

    def _state(self, krun: KRun, k: str, state: str) -> Pattern:
        pretty_text = f"""
            <generatedTop>
                <T>
                    <k> {k} </k>
                    <state> {state} </state>
                </T>
                <generatedCounter>
                    0
                </generatedCounter>
            </generatedTop>
        """
        proc_res = _kast(
            definition_dir=krun.definition_dir,
            input=KAstInput.RULE,
            output=KAstOutput.KORE,
            expression=pretty_text,
            sort='GeneratedTopCell',
        )
        kore_text = proc_res.stdout
        return KoreParser(kore_text).pattern()


def test_run_kore_config(kompile: Kompiler) -> None:
    # Given
    definition_dir = kompile('k-files/config.k')
    krun = KRun(definition_dir)

    fst = DV(SortApp('SortInt'), String('0'))
    snd = DV(SortApp('SortInt'), String('1'))
    expected = App(
        "Lbl'-LT-'generatedTop'-GT-'",
        (),
        (
            App(
                "Lbl'-LT-'T'-GT-'",
                (),
                (
                    App("Lbl'-LT-'first'-GT-'", (), (fst,)),
                    App("Lbl'-LT-'second'-GT-'", (), (snd,)),
                ),
            ),
            App(
                "Lbl'-LT-'generatedCounter'-GT-'",
                (),
                (DV(SortApp('SortInt'), String('0')),),
            ),
        ),
    )

    # When
    actual = krun.run_kore_config({'FST': fst, 'SND': snd}, depth=0)

    # Then
    assert actual == expected
