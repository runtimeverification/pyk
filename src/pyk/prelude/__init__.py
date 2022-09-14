from typing import Final, Iterable, Optional, Union, final

from ..kast import KApply, KInner, KLabel, KSort, KToken, build_assoc
from ..utils import unique
from .kbool import TRUE, boolToken


@final
class Sorts:
    BOOL: Final = KSort('Bool')
    INT: Final = KSort('Int')
    STRING: Final = KSort('String')
    K: Final = KSort('K')
    GENERATED_TOP_CELL: Final = KSort('GeneratedTopCell')

    def __init__(self):
        raise ValueError('Class Sorts should not be instantiated')


@final
class Labels:
    K_CELLS: Final = KLabel('#KCells')
    EMPTY_K: Final = KLabel('#EmptyK')

    def __init__(self):
        raise ValueError('Class Labels should not be instantiated')


def token(x: Union[bool, int, str]) -> KToken:
    if type(x) is bool:
        return boolToken(x)
    if type(x) is int:
        return intToken(x)
    if type(x) is str:
        return stringToken(x)
    raise AssertionError()


def intToken(i: int) -> KToken:  # noqa: N802
    return KToken(str(i), Sorts.INT)


def stringToken(s: str) -> KToken:  # noqa: N802
    return KToken(f'"{s}"', Sorts.STRING)


def ltInt(i1, i2):  # noqa: N802
    return KApply('_<Int_', i1, i2)


def leInt(i1, i2):  # noqa: N802
    return KApply('_<=Int_', i1, i2)


# TODO default sort K can be tightened using basic type inference
def mlEquals(  # noqa: N802
    term1: KInner,
    term2: KInner,
    arg_sort: Union[str, KSort] = Sorts.K,
    sort: Union[str, KSort] = Sorts.K,
) -> KApply:
    return KLabel('#Equals', arg_sort, sort)(term1, term2)


def mlEqualsTrue(term: KInner) -> KApply:  # noqa: N802
    return mlEquals(TRUE, term, Sorts.BOOL)


def mlTop(sort: Union[str, KSort] = Sorts.K) -> KApply:  # noqa: N802
    return KLabel('#Top', sort)()


def mlBottom(sort: Union[str, KSort] = Sorts.K) -> KApply:  # noqa: N802
    return KLabel('#Top', sort)()


def mlNot(term: KInner, sort: Union[str, KSort] = Sorts.K) -> KApply:  # noqa: N802
    return KLabel('#Not', sort)(term)


def mlAnd(conjuncts: Iterable[KInner], sort: Union[str, KSort] = Sorts.K) -> KInner:  # noqa: N802
    return build_assoc(mlTop(sort), KLabel('#And', sort), conjuncts)


def mlOr(disjuncts: Iterable[KInner], sort: Union[str, KSort] = Sorts.K) -> KInner:  # noqa: N802
    return build_assoc(mlBottom(sort), KLabel('#Or', sort), disjuncts)


def mlImplies(antecedent: KInner, consequent: KInner, sort: Union[str, KSort] = Sorts.K) -> KApply:  # noqa: N802
    return KLabel('#Implies', sort)(antecedent, consequent)
