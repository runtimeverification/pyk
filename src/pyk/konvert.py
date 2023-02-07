from collections import defaultdict
from dataclasses import dataclass
from functools import cached_property, reduce
from pathlib import Path
from typing import Dict, Final, FrozenSet, Iterable, Optional, Set, Tuple, Union, final

from pyk.kast.inner import KApply, KInner, KSequence, KSort, KToken, KVariable
from pyk.kast.outer import KDefinition
from pyk.kore.syntax import DV, App, EVar, MLPattern, MLQuant, Pattern, SortApp, String
from pyk.prelude.bytes import BYTES
from pyk.prelude.k import K
from pyk.prelude.string import STRING

from .cli_utils import check_dir_path, check_file_path
from .kore.parser import KoreParser
from .kore.syntax import Definition, Sort
from .utils import FrozenDict


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

        subsort_table: Dict[Sort, Set[Sort]] = defaultdict(set)
        for subsort, supersort in subsort_attr_sorts:
            subsort_table[supersort].add(subsort)

        return FrozenDict({supersort: frozenset(subsorts) for supersort, subsorts in subsort_table.items()})

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

    def pattern_sorts(self, pattern: Pattern) -> Tuple[Sort, ...]:
        sorts: Tuple[Sort, ...]
        if isinstance(pattern, DV):
            sorts = ()

        elif isinstance(pattern, MLQuant):
            sorts = (pattern.sort,)

        elif isinstance(pattern, MLPattern):
            _, sorts = self.definition.resolve(pattern.symbol(), pattern.sorts)

        elif isinstance(pattern, App):
            _, sorts = self.definition.resolve(pattern.symbol, pattern.sorts)

        else:
            sorts = ()

        assert len(sorts) == len(pattern.patterns)
        return sorts

    def add_injections(self, pattern: Pattern, sort: Optional[Sort] = None) -> Pattern:
        if sort is None:
            sort = SortApp('SortK')
        patterns = pattern.patterns
        sorts = self.pattern_sorts(pattern)
        pattern = pattern.let_patterns(self.add_injections(p, s) for p, s in zip(patterns, sorts))
        return self._inject(pattern, sort)

    def _inject(self, pattern: Pattern, sort: Sort) -> Pattern:
        actual_sort = self.definition.infer_sort(pattern)

        if actual_sort == sort:
            return pattern

        if self.is_subsort(actual_sort, sort):
            return App('inj', (actual_sort, sort), (pattern,))

        raise ValueError(f'Sort {actual_sort.name} is not a subsort of {sort.name}')


# ------------
# KAST-to-KORE
# ------------

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


def kast_to_kore(
    kast_defn: KDefinition,
    kompiled_kore: KompiledKore,
    kast: KInner,
    sort: Optional[KSort] = None,
) -> Pattern:
    if sort is None:
        sort = K
    kast = kast_defn.sort_vars(kast, sort)
    kore = _kast_to_kore(kast)
    return kompiled_kore.add_injections(kore, _ksort_to_kore(sort))


def _kast_to_kore(kast: KInner) -> Pattern:
    if type(kast) is KToken:
        return _ktoken_to_kore(kast)
    elif type(kast) is KVariable:
        return _kvariable_to_kore(kast)
    elif type(kast) is KSequence:
        return _ksequence_to_kore(kast)
    elif type(kast) is KApply:
        return _kapply_to_kore(kast)

    raise ValueError(f'Unsupported KInner: {kast}')


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


def _ksort_to_kore(ksort: KSort) -> SortApp:
    return SortApp('Sort' + ksort.name)


def _kvariable_to_kore(kvar: KVariable) -> EVar:
    sort: Sort
    if kvar.sort:
        sort = _ksort_to_kore(kvar.sort)
    else:
        sort = SortApp('SortK')
    return EVar('Var' + munge(kvar.name), sort)


def _ksequence_to_kore(kseq: KSequence) -> Pattern:
    if not kseq:
        return App('dotk')

    unit: Pattern
    items: Tuple[KInner, ...]

    last = kseq[-1]
    if type(last) is KVariable and (not last.sort or last.sort == KSort('K')):
        unit = _kvariable_to_kore(last)
        items = kseq[:-1]
    else:
        unit = App('dotk')
        items = kseq.items

    patterns = tuple(_kast_to_kore(item) for item in items)
    return reduce(lambda x, y: App('kseq', (), (y, x)), reversed(patterns), unit)


def _kapply_to_kore(kapply: KApply) -> Pattern:
    if kapply.label.name in ML_QUANT_LABELS:
        return _kapply_to_ml_quant(kapply)

    return _kapply_to_pattern(kapply)


def _kapply_to_ml_quant(kapply: KApply) -> MLQuant:
    label = kapply.label
    symbol = ML_QUANT_LABELS[label.name]
    sorts = tuple(_ksort_to_kore(ksort) for ksort in label.params)
    (_,) = sorts

    kvar, kast = kapply.args
    var = _kast_to_kore(kvar)
    pattern = _kast_to_kore(kast)
    patterns = (var, pattern)

    return MLQuant.of(symbol, sorts, patterns)


def _kapply_to_pattern(kapply: KApply) -> Pattern:
    label = kapply.label
    symbol = _label_to_kore(label.name)
    sorts = tuple(_ksort_to_kore(ksort) for ksort in label.params)
    patterns = tuple(_kast_to_kore(kast) for kast in kapply.args)

    if label.name in ML_PATTERN_LABELS:
        return MLPattern.of(symbol, sorts, patterns)

    return App(symbol, sorts, patterns)


def _label_to_kore(label: str) -> str:
    if label in ML_PATTERN_LABELS:
        return ML_PATTERN_LABELS[label]

    return 'Lbl' + munge(label)


# --------------
# Symbol munging
# --------------

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
