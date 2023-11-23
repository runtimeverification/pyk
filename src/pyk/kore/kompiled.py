from __future__ import annotations

import logging
from dataclasses import dataclass
from functools import cached_property
from itertools import chain
from pathlib import Path
from typing import TYPE_CHECKING, Final, final

from ..cli.utils import check_dir_path, check_file_path
from .parser import KoreParser
from .syntax import DV, ML_SYMBOL_DECLS, App, MLPattern, MLQuant, SortApp, SortVar, WithSort

if TYPE_CHECKING:
    from collections.abc import Iterable

    from .syntax import Definition, Pattern, Sort, SymbolDecl

_LOGGER: Final = logging.getLogger(__name__)


@final
@dataclass(frozen=True)
class KompiledKore:
    path: Path
    timestamp: int

    def __init__(self, definition_dir: str | Path):
        definition_dir = Path(definition_dir)
        check_dir_path(definition_dir)

        path = (definition_dir / 'definition.kore').resolve()
        check_file_path(path)

        timestamp_file = definition_dir / 'timestamp'
        check_file_path(timestamp_file)
        timestamp = timestamp_file.stat().st_mtime_ns

        object.__setattr__(self, 'path', path)
        object.__setattr__(self, 'timestamp', timestamp)

    @cached_property
    def definition(self) -> Definition:
        _LOGGER.info(f'Loading kore definition: {self.path}')
        kore_text = self.path.read_text()
        _LOGGER.info(f'Parsing kore definition: {self.path}')
        return KoreParser(kore_text).definition()

    @cached_property
    def sort_table(self) -> KoreSortTable:
        return KoreSortTable.for_definition(self.definition)

    @cached_property
    def symbol_table(self) -> KoreSymbolTable:
        return KoreSymbolTable.for_definition(self.definition)

    def add_injections(self, pattern: Pattern, sort: Sort | None = None) -> Pattern:
        if sort is None:
            sort = SortApp('SortK')
        patterns = pattern.patterns
        sorts = self.symbol_table.pattern_sorts(pattern)
        pattern = pattern.let_patterns(self.add_injections(p, s) for p, s in zip(patterns, sorts, strict=True))
        return self._inject(pattern, sort)

    def _inject(self, pattern: Pattern, sort: Sort) -> Pattern:
        actual_sort = self.symbol_table.infer_sort(pattern)

        if actual_sort == sort:
            return pattern

        if self.sort_table.is_subsort(actual_sort, sort):
            return App('inj', (actual_sort, sort), (pattern,))

        raise ValueError(f'Sort {actual_sort.name} is not a subsort of {sort.name}: {pattern}')


class KoreSortTable:
    _subsort_table: dict[Sort, set[Sort]]

    def __init__(self, definition: Definition):
        self._subsort_table = self.__subsort_table(self._subsorts_for_definition(definition))

    @staticmethod
    def for_definition(definition: Definition) -> KoreSortTable:
        return KoreSortTable(definition)

    @staticmethod
    def __subsort_table(subsorts: Iterable[tuple[Sort, Sort]]) -> dict[Sort, set[Sort]]:
        res: dict[Sort, set[Sort]] = {}
        for subsort, supersort in subsorts:
            if supersort not in res:
                res[supersort] = set()
            res[supersort].add(subsort)

        supersorts = res.keys()
        for sort_k in supersorts:
            for sort_j in supersorts:
                if sort_k not in res[sort_j]:
                    continue

                for sort_i in res[sort_k]:
                    res[sort_j].add(sort_i)

        return res

    @staticmethod
    def _subsorts_for_definition(definition: Definition) -> list[tuple[Sort, Sort]]:
        axioms = (axiom for module in definition for axiom in module.axioms)
        attrs = (attr for axiom in axioms for attr in axiom.attrs)
        subsort_attrs = (attr for attr in attrs if attr.symbol == 'subsort')
        subsort_attr_sorts = (attr.sorts for attr in subsort_attrs)
        return [(subsort, supersort) for subsort, supersort in subsort_attr_sorts]

    def is_subsort(self, sort1: Sort, sort2: Sort) -> bool:
        if sort1 == sort2:
            return True

        if sort2 == SortApp('SortK'):
            return True

        if sort1 == SortApp('SortK'):
            return False

        return sort1 in self._subsort_table.get(sort2, ())

    def meet(self, sort1: Sort, sort2: Sort) -> Sort:
        if self.is_subsort(sort1, sort2):
            return sort1

        if self.is_subsort(sort2, sort1):
            return sort2

        subsorts1 = set(self._subsort_table.get(sort1, set())).union({sort1})
        subsorts2 = set(self._subsort_table.get(sort2, set())).union({sort2})
        common_subsorts = subsorts1.intersection(subsorts2)
        if not common_subsorts:
            raise ValueError(f'Sorts have no common subsort: {sort1}, {sort2}')
        nr_subsorts = {sort: len(self._subsort_table.get(sort, {})) for sort in common_subsorts}
        max_subsort_nr = max(n for _, n in nr_subsorts.items())
        max_subsorts = {sort for sort, n in nr_subsorts.items() if n == max_subsort_nr}
        (subsort,) = max_subsorts
        return subsort


class KoreSymbolTable:
    _symbol_table: dict[str, SymbolDecl]

    def __init__(self, symbol_decls: Iterable[SymbolDecl] = ()):
        self._symbol_table = {symbol_decl.symbol.name: symbol_decl for symbol_decl in symbol_decls}

    @staticmethod
    def for_definition(definition: Definition, *, with_ml_symbols: bool = True) -> KoreSymbolTable:
        return KoreSymbolTable(
            chain(
                (symbol_decl for module in definition for symbol_decl in module.symbol_decls),
                ML_SYMBOL_DECLS if with_ml_symbols else (),
            )
        )

    def resolve(self, symbol_id: str, sorts: Iterable[Sort] = ()) -> tuple[Sort, tuple[Sort, ...]]:
        symbol_decl = self._symbol_table.get(symbol_id)
        if not symbol_decl:
            raise ValueError(f'Undeclared symbol: {symbol_id}')

        symbol = symbol_decl.symbol
        sorts = tuple(sorts)

        nr_sort_vars = len(symbol.vars)
        nr_sorts = len(sorts)
        if nr_sort_vars != nr_sorts:
            raise ValueError(f'Expected {nr_sort_vars} sort parameters, got {nr_sorts} for: {symbol_id}')

        sort_table: dict[Sort, Sort] = dict(zip(symbol.vars, sorts, strict=True))

        def resolve_sort(sort: Sort) -> Sort:
            if type(sort) is SortVar:
                return sort_table.get(sort, sort)
            return sort

        sort = resolve_sort(symbol_decl.sort)
        param_sorts = tuple(resolve_sort(sort) for sort in symbol_decl.param_sorts)

        return sort, param_sorts

    def infer_sort(self, pattern: Pattern) -> Sort:
        if isinstance(pattern, WithSort):
            return pattern.sort

        if type(pattern) is App:
            sort, _ = self.resolve(pattern.symbol, pattern.sorts)
            return sort

        raise ValueError(f'Cannot infer sort: {pattern}')

    def pattern_sorts(self, pattern: Pattern) -> tuple[Sort, ...]:
        sorts: tuple[Sort, ...]
        if isinstance(pattern, DV):
            sorts = ()

        elif isinstance(pattern, MLQuant):
            sorts = (pattern.sort,)

        elif isinstance(pattern, MLPattern):
            _, sorts = self.resolve(pattern.symbol(), pattern.sorts)

        elif isinstance(pattern, App):
            _, sorts = self.resolve(pattern.symbol, pattern.sorts)

        else:
            sorts = ()

        assert len(sorts) == len(pattern.patterns)
        return sorts
