from __future__ import annotations

from itertools import count
from typing import TYPE_CHECKING

import pytest

from pyk.kast.inner import KSequence
from pyk.kast.optimizer import CachedValues, KInnerOptimizer
from pyk.prelude.utils import token

from ..utils import a, b, c, f

if TYPE_CHECKING:
    from typing import Final

    from pyk.kast import KInner


EQUAL_TEST_DATA: Final[tuple[tuple[KInner, KInner], ...]] = (
    (token(1), token(1)),
    (token('a'), token('a')),
    (a, a),
    (f(a), f(a)),
    (KSequence([a, b]), KSequence([a, b])),
)


@pytest.mark.parametrize('term1,term2', EQUAL_TEST_DATA, ids=count())
def test_use_cached(term1: KInner, term2: KInner) -> None:
    # When

    cached_values: CachedValues[KInner] = CachedValues()

    id1 = cached_values.cache(term1)
    id2 = cached_values.cache(term2)

    # Then
    assert id1 == id2


NOT_EQUAL_TEST_DATA: Final[tuple[tuple[KInner, KInner], ...]] = (
    (token(1), token(2)),
    (token(1), token('1')),
    (a, b),
    (f(a), f(b)),
    (KSequence([a, b]), KSequence([a, c])),
)


@pytest.mark.parametrize('term1,term2', NOT_EQUAL_TEST_DATA, ids=count())
def test_not_use_cached(term1: KInner, term2: KInner) -> None:
    # When

    cached_values: CachedValues[KInner] = CachedValues()

    id1 = cached_values.cache(term1)
    id2 = cached_values.cache(term2)

    # Then
    assert term1 != term2
    assert id1 != id2


OPTIMIZE_TEST_DATA: Final[tuple[KInner, ...]] = (
    token(1),
    token('a'),
    a,
    f(a),
    KSequence([a, token(3)]),
)


def test_optimize() -> None:
    kinner_optimizer = KInnerOptimizer()

    for item in OPTIMIZE_TEST_DATA:
        optimized = kinner_optimizer.optimize(item)
        assert item == optimized
