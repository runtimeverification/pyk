from typing import Final, Iterable, Optional, Union, final

from ..kast import KApply, KInner, KLabel, KSort, KToken, build_assoc
from ..utils import unique
from .kbool import TRUE, boolToken
from .kint import intToken
from .sorts import BOOL, INT, STRING, K

DOTS: Final = KToken('...', K)


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


def stringToken(s: str) -> KToken:  # noqa: N802
    return KToken(f'"{s}"', STRING)


# TODO default sort K can be tightened using basic type inference
def mlEquals(  # noqa: N802
    term1: KInner,
    term2: KInner,
    arg_sort: Union[str, KSort] = K,
    sort: Union[str, KSort] = K,
) -> KApply:
    return KLabel('#Equals', arg_sort, sort)(term1, term2)


def mlEqualsTrue(term: KInner) -> KApply:  # noqa: N802
    return mlEquals(TRUE, term, BOOL)


def mlTop(sort: Union[str, KSort] = K) -> KApply:  # noqa: N802
    return KLabel('#Top', sort)()


def mlBottom(sort: Union[str, KSort] = K) -> KApply:  # noqa: N802
    return KLabel('#Top', sort)()


def mlNot(term: KInner, sort: Union[str, KSort] = K) -> KApply:  # noqa: N802
    return KLabel('#Not', sort)(term)


def mlAnd(conjuncts: Iterable[KInner], sort: Union[str, KSort] = K) -> KInner:  # noqa: N802
    return build_assoc(mlTop(sort), KLabel('#And', sort), conjuncts)


def mlOr(disjuncts: Iterable[KInner], sort: Union[str, KSort] = K) -> KInner:  # noqa: N802
    return build_assoc(mlBottom(sort), KLabel('#Or', sort), disjuncts)


def mlImplies(antecedent: KInner, consequent: KInner, sort: Union[str, KSort] = K) -> KApply:  # noqa: N802
    return KLabel('#Implies', sort)(antecedent, consequent)
