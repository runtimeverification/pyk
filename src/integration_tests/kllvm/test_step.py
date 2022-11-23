from pyk.kllvm.ast import Pattern
from pyk.kllvm.parser import Parser

from .utils import RuntimeTest


class StepTest(RuntimeTest):
    KOMPILE_MAIN_FILE = 'k-files/steps.k'

    def test_steps_1(self) -> None:
        term = self.runtime.Term(start_pattern())
        term.step(0)
        self.assertEqual(str(term), foo_output(0))
        term.step()
        term.step()
        self.assertEqual(str(term), foo_output(2))
        term.step(200)
        self.assertEqual(str(term), bar_output())

    def test_steps_2(self) -> None:
        term = self.runtime.Term(start_pattern())
        self.assertEqual(str(term), foo_output(0))
        term.step(50)
        self.assertEqual(str(term), foo_output(50))
        term.step(-1)
        self.assertEqual(str(term), bar_output())

    def test_steps_3(self) -> None:
        term = self.runtime.Term(start_pattern())
        term.run()
        self.assertEqual(str(term), bar_output())


def start_pattern() -> Pattern:
    """
    <k> foo(100) </k>
    """
    text = r"""
        LblinitGeneratedTopCell{}(
            Lbl'Unds'Map'Unds'{}(
                Lbl'Stop'Map{}(),
                Lbl'UndsPipe'-'-GT-Unds'{}(
                    inj{SortKConfigVar{}, SortKItem{}}(\dv{SortKConfigVar{}}("$PGM")),
                    inj{SortFoo{}, SortKItem{}}(
                        inj{SortFoo{}, SortKItem{}}(
                            Lblfoo'LParUndsRParUnds'STEPS'Unds'Foo'Unds'Int{}(\dv{SortInt{}}("100"))
                        )
                    )
                )
            )
        )
    """
    return Parser.from_string(text).pattern()


def foo_output(n: int) -> str:
    """
    <k> foo(100 - n) </k>
    """
    return fr"""Lbl'-LT-'generatedTop'-GT-'{{}}(Lbl'-LT-'k'-GT-'{{}}(kseq{{}}(inj{{SortFoo{{}}, SortKItem{{}}}}(Lblfoo'LParUndsRParUnds'STEPS'Unds'Foo'Unds'Int{{}}(\dv{{SortInt{{}}}}("{100-n}"))),dotk{{}}())),Lbl'-LT-'generatedCounter'-GT-'{{}}(\dv{{SortInt{{}}}}("0")))"""


def bar_output() -> str:
    """
    <k> bar() </k>
    """
    return r"""Lbl'-LT-'generatedTop'-GT-'{}(Lbl'-LT-'k'-GT-'{}(kseq{}(inj{SortFoo{}, SortKItem{}}(Lblbar'LParRParUnds'STEPS'Unds'Foo{}()),dotk{}())),Lbl'-LT-'generatedCounter'-GT-'{}(\dv{SortInt{}}("0")))"""
