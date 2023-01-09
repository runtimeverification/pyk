from collections import defaultdict
from dataclasses import dataclass
from functools import cached_property, reduce
from pathlib import Path
from typing import Dict, Final, FrozenSet, Iterable, Optional, Set, Tuple, Union, final

from pyk.kast.inner import KApply, KInner, KSequence, KSort, KToken, KVariable
from pyk.kore.syntax import (
    DV,
    App,
    EVar,
    Exists,
    Forall,
    MLPattern,
    MLQuant,
    Pattern,
    SortApp,
    SortVar,
    String,
    Symbol,
    WithSort,
)
from pyk.prelude.bytes import BYTES
from pyk.prelude.string import STRING
from pyk.utils import Scope

from .cli_utils import check_dir_path, check_file_path
from .kore.parser import KoreParser
from .kore.syntax import Definition, Sort, SymbolDecl
from .utils import FrozenDict

ML_CONN_LABELS: Final = {
    '#Top': r'\top',
    '#Bottom': r'\bottom',
    '#Not': r'\not',
    '#And': r'\and',
    '#Or': r'\or',
    '#Implies': r'\implies',
    '#Iff': r'\iff',
}

ML_QUANT_LABELS: Final = {
    '#Exists': r'\exists',
    '#Forall': r'\forall',
}

ML_PRED_LABELS: Final = {
    '#Ceil': r'\ceil',
    '#Floor': r'\floor',
    '#Equals': r'\equals',
    '#In': r'\in',
}

ML_PATTERN_LABELS: Final = dict(
    **ML_CONN_LABELS,
    **ML_QUANT_LABELS,
    **ML_PRED_LABELS,
)


@final
@dataclass(frozen=True)
class KompiledDefn:
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
    def _symbol_table(self) -> FrozenDict[str, SymbolDecl]:
        S, T = (SortVar(name) for name in ('S', 'T'))  # noqa: N806
        ml_symbol_table = {
            r'\top': SymbolDecl(Symbol(r'\top', (S,)), (), S),
            r'\bottom': SymbolDecl(Symbol(r'\bottom', (S,)), (), S),
            r'\not': SymbolDecl(Symbol(r'\not', (S,)), (S,), S),
            r'\and': SymbolDecl(Symbol(r'\and', (S,)), (S, S), S),
            r'\or': SymbolDecl(Symbol(r'\or', (S,)), (S, S), S),
            r'\implies': SymbolDecl(Symbol(r'\implies', (S,)), (S, S), S),
            r'\iff': SymbolDecl(Symbol(r'\iff', (S,)), (S, S), S),
            r'\ceil': SymbolDecl(Symbol(r'\ceil', (S, T)), (S,), T),
            r'\floor': SymbolDecl(Symbol(r'\floor', (S, T)), (S,), T),
            r'\equals': SymbolDecl(Symbol(r'\equals', (S, T)), (S, S), T),
            r'\in': SymbolDecl(Symbol(r'\in', (S, T)), (S, S), T),
        }
        symbol_table = _symbol_table(self.definition)
        return FrozenDict({**ml_symbol_table, **symbol_table})

    def _resolve_symbol(self, symbol_id: str, sorts: Iterable[Sort] = ()) -> Tuple[Sort, Tuple[Sort, ...]]:
        symbol_decl = self._symbol_table.get(symbol_id)
        if not symbol_decl:
            raise ValueError(f'Undeclared symbol: {symbol_id}')

        symbol = symbol_decl.symbol
        sorts = tuple(sorts)

        nr_sort_vars = len(symbol.vars)
        nr_sorts = len(sorts)
        if nr_sort_vars != nr_sorts:
            raise ValueError(f'Expected {nr_sort_vars} sort parameters, got {nr_sorts} for: {symbol_id}')

        sort_table: Dict[Sort, Sort] = dict(zip(symbol.vars, sorts))

        def resolve(sort: Sort) -> Sort:
            if type(sort) is SortVar:
                return sort_table.get(sort, sort)
            return sort

        sort = resolve(symbol_decl.sort)
        param_sorts = tuple(resolve(sort) for sort in symbol_decl.param_sorts)

        return sort, param_sorts

    @cached_property
    def _subsort_table(self) -> FrozenDict[Sort, FrozenSet[Sort]]:
        subsort_table = _subsort_table(self.definition)
        return FrozenDict({supersort: frozenset(subsorts) for supersort, subsorts in subsort_table.items()})

    def subsorts(self, sort: Sort) -> Set[Sort]:
        subsorts = set(self._subsort_table.get(sort, frozenset()))
        subsorts.add(sort)
        return subsorts

    def meet_sorts(self, sort1: Sort, sort2: Sort) -> Sort:
        subsorts1 = self.subsorts(sort1)
        subsorts2 = self.subsorts(sort2)
        common_subsorts = subsorts1.intersection(subsorts2)
        if not common_subsorts:
            raise ValueError(f'Sorts have no common subsort: {sort1}, {sort2}')
        nr_subsorts = {sort: len(self._subsort_table.get(sort, {})) for sort in common_subsorts}
        max_subsort_nr = max(n for _, n in nr_subsorts.items())
        max_subsorts = {sort for sort, n in nr_subsorts.items() if n == max_subsort_nr}
        (subsort,) = max_subsorts
        return subsort

    def meet_all_sorts(self, sorts: Iterable[Sort]) -> Sort:
        unit: Sort = SortApp('SortKItem')
        return reduce(self.meet_sorts, sorts, unit)

    def infer_sort(self, pattern: Pattern) -> Sort:
        if isinstance(pattern, WithSort):
            return pattern.sort

        if type(pattern) is App:
            sort, _ = self._resolve_symbol(pattern.symbol, pattern.sorts)
            return sort

        raise ValueError(f'Cannot infer sort: {pattern}')

    def add_injections(self, pattern: Pattern, sort: Optional[Sort] = None) -> Pattern:
        # TODO
        return pattern

    def _inject(self, pattern: Pattern, sort: Sort) -> Pattern:
        actual_sort = self.infer_sort(pattern)
        expected_sort = sort or SortApp('SortKItem')

        if actual_sort == expected_sort:
            return pattern

        if actual_sort in self.subsorts(expected_sort):
            return App('inj', (actual_sort, expected_sort), (pattern,))

        raise ValueError(f'Sort {actual_sort.name} is not a subsort of {expected_sort.name}')

    def kast_to_kore(self, kast: KInner, sort: Optional[Sort] = None, *, with_inj: bool = True) -> Pattern:
        if not sort:
            sort = SortApp('SortKItem')

        pattern = self._kast_to_kore(kast, sort)
        pattern = self._meet_var_sorts(pattern)

        if with_inj:
            return self.add_injections(pattern, sort)

        return pattern

    def _kast_to_kore(self, kast: KInner, sort: Sort) -> Pattern:
        if type(kast) is KVariable:
            return _kvariable_to_kore(kast, sort)
        elif type(kast) is KToken:
            return _ktoken_to_kore(kast)
        elif type(kast) is KSequence:
            return self._ksequence_to_kore(kast)
        elif type(kast) is KApply:
            return self._kapply_to_kore(kast)

        raise ValueError(f'Unsupported KAst: {kast}')

    def _meet_var_sorts(self, pattern: Pattern) -> Pattern:
        def var_sorts(pattern: Pattern) -> Scope[Set[Sort]]:
            def collect(pattern: Pattern, scope: Scope[Set[Sort]]) -> None:
                if isinstance(pattern, MLQuant):
                    child = scope.push_scope(str(id(pattern.var)))
                    scope[pattern.var.name] = set()
                    collect(pattern.pattern, child)

                elif isinstance(pattern, EVar):
                    if pattern.name in scope:
                        scope[pattern.name].add(pattern.sort)
                    else:
                        root[pattern.name] = {pattern.sort}

                else:
                    for subpattern in pattern.patterns:
                        collect(subpattern, scope)

            root: Scope[Set[Sort]] = Scope('.')
            collect(pattern, root)
            return root

        def rewrite(pattern: Pattern, scope: Scope[Sort]) -> Pattern:
            if type(pattern) is EVar:
                return pattern.let(sort=scope[pattern.name])

            if isinstance(pattern, MLQuant):
                child = scope.child_scope(str(id(pattern.var)))
                sort = child[pattern.var.name]
                assert type(pattern) is Exists or type(pattern) is Forall  # This enables pattern.let
                return pattern.let(var=pattern.var.let(sort=sort), pattern=rewrite(pattern.pattern, child))

            return pattern.map_patterns(lambda p: rewrite(p, scope))

        vars_scope = var_sorts(pattern)
        sort_scope = vars_scope.map(self.meet_all_sorts)
        return rewrite(pattern, sort_scope)

    def _ksequence_to_kore(self, kseq: KSequence) -> App:
        patterns = tuple(self._kast_to_kore(item, SortApp('SortKItem')) for item in kseq)
        return reduce(lambda x, y: App('kseq', (), (y, x)), reversed(patterns), App('dotk'))

    def _kapply_to_kore(self, kapply: KApply) -> Pattern:
        if kapply.label.name in ML_QUANT_LABELS:
            return self._kapply_to_ml_quant(kapply)

        return self._kapply_to_pattern(kapply)

    def _kapply_to_ml_quant(self, kapply: KApply) -> MLQuant:
        label = kapply.label
        symbol = ML_QUANT_LABELS[label.name]
        sorts = tuple(_ksort_to_kore(ksort) for ksort in label.params)
        (sort,) = sorts

        kvar, kast = kapply.args
        var = self._kast_to_kore(kvar, SortApp('SortKItem'))
        pattern = self._kast_to_kore(kast, sort)
        patterns = (var, pattern)

        return MLQuant.of(symbol, sorts, patterns)

    def _kapply_to_pattern(self, kapply: KApply) -> Pattern:
        label = kapply.label
        symbol = _label_to_kore(label.name)
        sorts = tuple(_ksort_to_kore(ksort) for ksort in label.params)
        _, pattern_sorts = self._resolve_symbol(symbol, sorts)

        nr_pattern_sorts = len(pattern_sorts)
        if kapply.arity != nr_pattern_sorts:
            raise ValueError(f'Expected {nr_pattern_sorts} parameters, got {kapply.arity} in: {kapply}')

        patterns = (self._kast_to_kore(kast, sort) for kast, sort in zip(kapply.args, pattern_sorts))

        if label.name in ML_PATTERN_LABELS:
            return MLPattern.of(symbol, sorts, patterns)

        return App(symbol, sorts, patterns)


def _label_to_kore(label: str) -> str:
    if label in ML_PATTERN_LABELS:
        return ML_PATTERN_LABELS[label]

    return 'Lbl' + unmunge(label)


def _ksort_to_kore(ksort: KSort) -> SortApp:
    return SortApp('Sort' + ksort.name)


def _kvariable_to_kore(kvar: KVariable, sort: Sort) -> EVar:
    return EVar('Var' + munge(kvar.name), sort)


def _ktoken_to_kore(ktoken: KToken) -> DV:
    token = ktoken.token
    sort = ktoken.sort

    if sort == STRING:
        assert token.startswith('"')
        assert token.endswith('"')
        return DV(_ksort_to_kore(sort), String(token[1:-1]))

    if sort == BYTES:
        assert token.startswith('b"')
        assert token.endswith('"')
        return DV(_ksort_to_kore(sort), String(token[2:-1]))

    return DV(_ksort_to_kore(sort), String(token))


def _subsort_table(definition: Definition) -> Dict[Sort, Set[Sort]]:
    axioms = (axiom for module in definition for axiom in module.axioms)
    attrs = (attr for axiom in axioms for attr in axiom.attrs)
    subsort_attrs = (attr for attr in attrs if attr.symbol == 'subsort')
    subsort_attr_sorts = (attr.sorts for attr in subsort_attrs)

    res: Dict[Sort, Set[Sort]] = defaultdict(set)
    for subsort, supersort in subsort_attr_sorts:
        res[supersort].add(subsort)

    return res


def _symbol_table(definition: Definition) -> Dict[str, SymbolDecl]:
    symbol_decls = (symbol_decl for module in definition for symbol_decl in module.symbol_decls)
    return {symbol_decl.symbol.name: symbol_decl for symbol_decl in symbol_decls}


UNMUNGE_TABLE: Final[FrozenDict[str, str]] = FrozenDict(
    {
        'Spce': ' ',
        'Bang': '!',
        'Quot': '"',
        'Hash': '#',
        'Dolr': '$',
        'Perc': '%',
        'And-': '&',
        'Apos': "'",
        'LPar': '(',
        'RPar': ')',
        'Star': '*',
        'Plus': '+',
        'Comm': ',',
        'Stop': '.',
        'Slsh': '/',
        'Coln': ':',
        'SCln': ';',
        '-LT-': '<',
        'Eqls': '=',
        '-GT-': '>',
        'Ques': '?',
        '-AT-': '@',
        'LSqB': '[',
        'RSqB': ']',
        'Bash': '\\',
        'Xor-': '^',
        'Unds': '_',
        'BQuo': '`',
        'LBra': '{',
        'Pipe': '|',
        'RBra': '}',
        'Tild': '~',
    }
)

MUNGE_TABLE: Final[FrozenDict[str, str]] = FrozenDict({v: k for k, v in UNMUNGE_TABLE.items()})


def munge(label: str) -> str:
    symbol = ''
    quot = False
    for c in label:
        if c in MUNGE_TABLE:
            symbol += "'" if not quot else ''
            symbol += MUNGE_TABLE[c]
            quot = True
        else:
            symbol += "'" if quot else ''
            symbol += c
            quot = False
    symbol += "'" if quot else ''
    return symbol


class Unmunger:
    _rest: str

    def __init__(self, symbol: str):
        self._rest = symbol

    def label(self) -> str:
        res = ''
        while self._la():
            if self._la() == "'":
                self._consume()
                res += self._unmunged()
                while self._la() != "'":
                    res += self._unmunged()
                self._consume()
                if self._la() == "'":
                    raise ValueError('Quoted sections next to each other')
            else:
                res += self._consume()
        return res

    def _la(self) -> Optional[str]:
        if self._rest:
            return self._rest[0]
        return None

    def _consume(self, n: int = 1) -> str:
        if len(self._rest) < n:
            raise ValueError('Unexpected end of symbol')
        consumed = self._rest[:n]
        self._rest = self._rest[n:]
        return consumed

    def _unmunged(self) -> str:
        munged = self._consume(4)
        if munged not in UNMUNGE_TABLE:
            raise ValueError(f'Unknown encoding "{munged}"')
        return UNMUNGE_TABLE[munged]


def unmunge(symbol: str) -> str:
    return Unmunger(symbol).label()
