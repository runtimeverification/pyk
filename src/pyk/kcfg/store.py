from __future__ import annotations

import threading
from abc import abstractmethod
from collections.abc import MutableMapping
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Generic, TypeVar, final

from ..cterm import CTerm
from ..kast.inner import KApply, KSequence, KToken, KVariable, bottom_up_with_summary
from .kcfg import KCFG

if TYPE_CHECKING:
    from collections.abc import Iterator

    from ..kast.inner import KInner, KLabel


A = TypeVar('A')


@dataclass
class CachedValues(Generic[A]):
    value_to_id: dict[A, int] = field(default_factory=dict)
    values: list[A] = field(default_factory=list)

    def cache(self, value: A) -> int:
        id = self.value_to_id.get(value)
        if id is not None:
            return id
        id = len(self.values)
        self.value_to_id[value] = id
        self.values.append(value)
        return id


@dataclass(eq=True, frozen=True)
class OptimizedKInner:
    @abstractmethod
    def build(self, klabels: list[KLabel], terms: list[KInner]) -> KInner:
        ...


@final
@dataclass(eq=True, frozen=True)
class SimpleOptimizedKInner(OptimizedKInner):
    term: KInner

    def build(self, klabels: list[KLabel], terms: list[KInner]) -> KInner:
        return self.term


@final
@dataclass(eq=True, frozen=True)
class OptimizedKApply(OptimizedKInner):
    label: int
    children: tuple[int, ...]

    def build(self, klabels: list[KLabel], terms: list[KInner]) -> KInner:
        return KApply(klabels[self.label], tuple(terms[child] for child in self.children))


@final
@dataclass(eq=True, frozen=True)
class OptimizedKSequence(OptimizedKInner):
    children: tuple[int, ...]

    def build(self, klabels: list[KLabel], terms: list[KInner]) -> KInner:
        return KSequence(tuple(terms[child] for child in self.children))


class OptimizedNodeStore(MutableMapping[int, KCFG.Node]):
    __nodes: dict[int, KCFG.Node]
    __optimized_terms: CachedValues[OptimizedKInner]
    __klabels: CachedValues[KLabel]
    __terms: list[KInner]

    __lock: threading.Lock

    def __init__(self) -> None:
        super().__init__()
        self.__nodes = {}
        self.__optimized_terms = CachedValues()
        self.__klabels = CachedValues()
        self.__terms = []

        self.__lock = threading.Lock()

    def __getitem__(self, key: int) -> KCFG.Node:
        return self.__nodes[key]

    def __setitem__(self, key: int, node: KCFG.Node) -> None:
        old_cterm = node.cterm
        new_config = self.__optimize(old_cterm.config)
        new_constraints = tuple(self.__optimize(c) for c in old_cterm.constraints)
        new_node = KCFG.Node(node.id, CTerm(new_config, new_constraints))
        self.__nodes[key] = new_node

    def __delitem__(self, key: int) -> None:
        del self.__nodes[key]

    def __iter__(self) -> Iterator[int]:
        return self.__nodes.__iter__()

    def __len__(self) -> int:
        return len(self.__nodes)

    def __optimize(self, term: KInner) -> KInner:
        def optimizer(to_optimize: KInner, children: list[int]) -> tuple[KInner, int]:
            if isinstance(to_optimize, KToken) or isinstance(to_optimize, KVariable):
                optimized_id = self.__cache(SimpleOptimizedKInner(to_optimize))
            elif isinstance(to_optimize, KApply):
                klabel_id = self.__cache_klabel(to_optimize.label)
                optimized_id = self.__cache(OptimizedKApply(klabel_id, tuple(children)))
            elif isinstance(to_optimize, KSequence):
                optimized_id = self.__cache(OptimizedKSequence(tuple(children)))
            else:
                raise ValueError('Unknown term type: ' + str(type(to_optimize)))
            return (self.__terms[optimized_id], optimized_id)

        with self.__lock:
            optimized, _ = bottom_up_with_summary(optimizer, term)
        return optimized

    def __cache(self, term: OptimizedKInner) -> int:
        id = self.__optimized_terms.cache(term)
        assert id <= len(self.__terms)
        if id == len(self.__terms):
            self.__terms.append(term.build(self.__klabels.values, self.__terms))
        return id

    def __cache_klabel(self, label: KLabel) -> int:
        return self.__klabels.cache(label)
