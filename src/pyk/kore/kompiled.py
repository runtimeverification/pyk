from collections import defaultdict
from dataclasses import dataclass
from functools import cached_property, reduce
from itertools import chain
from pathlib import Path
from typing import Callable, Dict, FrozenSet, Iterable, Iterator, Mapping, Optional, Set, TypeVar, Union, final

from ..cli_utils import check_dir_path, check_file_path
from ..kore.parser import KoreParser
from ..kore.syntax import Definition, EVar, Exists, Forall, MLQuant, Sort
from ..utils import FrozenDict, unique
from .syntax import App, Pattern, SortApp


@final
@dataclass(frozen=True)
class KompiledKore:
    path: Path
    timestamp: int

    def __init__(self, definition_dir: Union[str, Path]):
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
        return KoreParser(self.path.read_text()).definition()

    @cached_property
    def _subsort_table(self) -> FrozenDict[Sort, FrozenSet[Sort]]:
        axioms = (axiom for module in self.definition for axiom in module.axioms)
        attrs = (attr for axiom in axioms for attr in axiom.attrs)
        subsort_attrs = (attr for attr in attrs if attr.symbol == 'subsort')
        subsort_attr_sorts = (attr.sorts for attr in subsort_attrs)

        direct_subsorts: Dict[Sort, Set[Sort]] = defaultdict(set)
        for subsort, supersort in subsort_attr_sorts:
            direct_subsorts[supersort].add(subsort)

        supersorts = direct_subsorts.keys()

        subsort_table = dict(direct_subsorts)
        for sort_k in supersorts:
            for sort_j in supersorts:
                if sort_k not in subsort_table[sort_j]:
                    continue

                for sort_i in subsort_table[sort_k]:
                    subsort_table[sort_j].add(sort_i)

        return FrozenDict((supersort, frozenset(subsorts)) for supersort, subsorts in subsort_table.items())

    def is_subsort(self, sort1: Sort, sort2: Sort) -> bool:
        if sort1 == sort2:
            return True

        if sort2 == SortApp('SortK'):
            return True

        if sort1 == SortApp('SortK'):
            return False

        return sort1 in self._subsort_table.get(sort2, frozenset())

    def meet_sorts(self, sort1: Sort, sort2: Sort) -> Sort:
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

    def meet_all_sorts(self, sorts: Iterable[Sort]) -> Sort:
        unit: Sort = SortApp('SortK')
        return reduce(self.meet_sorts, sorts, unit)

    def add_injections(self, pattern: Pattern, sort: Optional[Sort] = None) -> Pattern:
        if sort is None:
            sort = SortApp('SortK')
        patterns = pattern.patterns
        sorts = self.definition.pattern_sorts(pattern)
        pattern = pattern.let_patterns(self.add_injections(p, s) for p, s in zip(patterns, sorts))
        return self._inject(pattern, sort)

    def _inject(self, pattern: Pattern, sort: Sort) -> Pattern:
        actual_sort = self.definition.infer_sort(pattern)

        if actual_sort == sort:
            return pattern

        if self.is_subsort(actual_sort, sort):
            return App('inj', (actual_sort, sort), (pattern,))

        raise ValueError(f'Sort {actual_sort.name} is not a subsort of {sort.name}: {pattern}')

    def strengthen_sorts(self, pattern: Pattern, sort: Sort) -> Pattern:
        root: Scope[Set[Sort]] = Scope('.')

        def collect(scope: Scope[Set[Sort]], pattern: Pattern, sort: Sort) -> None:
            if isinstance(pattern, MLQuant):
                child = scope.push(str(id(pattern.var)))
                child.define(pattern.var.name, {pattern.var.sort})
                (sort,) = self.definition.pattern_sorts(pattern)
                collect(child, pattern.pattern, sort)

            elif isinstance(pattern, EVar):
                if pattern.name in scope:
                    scope[pattern.name].add(sort)
                    scope[pattern.name].add(pattern.sort)
                else:
                    root.define(pattern.name, {sort, pattern.sort})

            else:
                for subpattern, subsort in zip(pattern.patterns, self.definition.pattern_sorts(pattern)):
                    collect(scope, subpattern, subsort)

        def rewrite(scope: Scope[Sort], pattern: Pattern) -> Pattern:
            if type(pattern) is EVar:
                return pattern.let(sort=scope[pattern.name])

            if isinstance(pattern, MLQuant):
                child = scope.child(str(id(pattern.var)))
                sort = child[pattern.var.name]
                assert type(pattern) is Exists or type(pattern) is Forall  # This enables pattern.let
                return pattern.let(var=pattern.var.let(sort=sort), pattern=rewrite(child, pattern.pattern))

            return pattern.map_patterns(lambda p: rewrite(scope, p))

        collect(root, pattern, sort)
        scope = root.map(self.meet_all_sorts)
        return rewrite(scope, pattern)


S = TypeVar('S')
T = TypeVar('T')


class Scope(Mapping[str, T]):
    _name: str
    _symbols: Dict[str, T]
    _parent: Optional['Scope[T]']
    _children: Dict[str, 'Scope[T]']

    def __init__(self, name: str, parent: Optional['Scope[T]'] = None):
        self._name = name
        self._parent = parent
        self._symbols = {}
        self._children = {}

    def __getitem__(self, key: str) -> T:
        if key in self._symbols:
            return self._symbols[key]
        if self._parent is not None:
            return self._parent[key]
        raise KeyError(key)

    def __iter__(self) -> Iterator[str]:
        if self._parent is None:
            return iter(self._symbols)
        return unique(chain(iter(self._symbols), iter(self._parent)))

    def __len__(self) -> int:
        return len(set(self))

    def __str__(self) -> str:
        return f'Scope(symbols={self._symbols}, children={self._children})'

    def __repr__(self) -> str:
        return str(self)

    def define(self, symbol: str, value: T) -> None:
        self._symbols[symbol] = value

    def push(self, name: str) -> 'Scope[T]':
        if name in self._children:
            raise ValueError(f'Scope with name {name} already defined')
        child = Scope(name, self)
        self._children[name] = child
        return child

    def child(self, name: str) -> 'Scope[T]':
        return self._children[name]

    def map(self, f: Callable[[T], S]) -> 'Scope[S]':
        scope: Scope[S] = Scope(self._name)
        scope._symbols = {key: f(value) for key, value in self._symbols.items()}
        scope._children = {name: child.map(f) for name, child in self._children.items()}
        for child in scope._children.values():
            child._parent = scope
        return scope
