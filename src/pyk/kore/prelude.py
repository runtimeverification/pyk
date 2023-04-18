from __future__ import annotations

from itertools import chain
from typing import TYPE_CHECKING

from .syntax import DV, App, LeftAssoc, RightAssoc, SortApp, String, SymbolId

if TYPE_CHECKING:
    from collections.abc import Iterable
    from typing import Any, Final

    from .syntax import EVar, Pattern, Sort


# ----------
# Base types
# ----------

BOOL: Final = SortApp('SortBool')
INT: Final = SortApp('SortInt')
BYTES: Final = SortApp('SortBytes')
STRING: Final = SortApp('SortString')

TRUE: Final = DV(BOOL, String('true'))
FALSE: Final = DV(BOOL, String('false'))


def dv(val: bool | int | str) -> DV:
    if type(val) is bool:
        return bool_dv(val)
    if type(val) is int:
        return int_dv(val)
    if type(val) is str:
        return string_dv(val)
    raise TypeError(f'Illegal type: {type(val)}')


def bool_dv(val: bool) -> DV:
    return TRUE if val else FALSE


def int_dv(val: int) -> DV:
    return DV(INT, String(str(val)))


def string_dv(val: str) -> DV:
    return DV(STRING, String(val))


# ------------
# K constructs
# ------------

SORT_K: Final = SortApp('SortK')
SORT_K_ITEM: Final = SortApp('SortKItem')
SORT_K_CONFIG_VAR: Final = SortApp('SortKConfigVar')


LBL_GENERATED_TOP: Final = SymbolId("Lbl'-LT-'generatedTop'-GT-'")
LBL_GENERATED_COUNTER: Final = SymbolId("Lbl'-LT-'generatedCounter'-GT-'")
LBL_K: Final = SymbolId("Lbl'-LT-'k'-GT-'")
INJ: Final = SymbolId('inj')
KSEQ: Final = SymbolId('kseq')

DOTK: Final = App('dotk', (), ())


def generated_top(patterns: Iterable[Pattern]) -> App:
    return App(LBL_GENERATED_TOP, (), patterns)


def generated_counter(pattern: Pattern) -> App:
    return App(LBL_GENERATED_COUNTER, (), (pattern,))


def k(pattern: Pattern) -> App:
    return App(LBL_K, (), (pattern,))


def inj(sort1: Sort, sort2: Sort, pattern: Pattern) -> App:
    return App(INJ, (sort1, sort2), (pattern,))


# TODO auto injections
def kseq(kitems: Iterable[Pattern], *, dotvar: EVar | None = None) -> RightAssoc:
    if dotvar and dotvar.sort != SORT_K:
        raise ValueError(f'Expected {SORT_K.text} as dotvar sort, got: {dotvar.sort.text}')
    tail = dotvar or DOTK
    return RightAssoc(App(KSEQ, (), chain(kitems, (tail,))))


# -----------
# Collections
# -----------

STOP_LIST: Final = App("Lbl'Stop'List")
LBL_LIST: Final = SymbolId("Lbl'Unds'List'Unds'")
LBL_LIST_ITEM: Final = SymbolId('LblListItem')


def kore_list(*args: Pattern) -> Pattern:
    if not args:
        return STOP_LIST
    return LeftAssoc(App(LBL_LIST, args=(App(LBL_LIST_ITEM, args=(arg,)) for arg in args)))


STOP_SET: Final = App("Lbl'Stop'Set")
LBL_SET: Final = SymbolId("Lbl'Unds'Set'Unds'")
LBL_SET_ITEM: Final = SymbolId('LblSetItem')


def kore_set(*args: Pattern) -> Pattern:
    if not args:
        return STOP_SET
    return LeftAssoc(App(LBL_SET, args=(App(LBL_SET_ITEM, args=(arg,)) for arg in args)))


STOP_MAP: Final = App("Lbl'Stop'Map")
LBL_MAP: Final = SymbolId("Lbl'Unds'Map'Unds'")
LBL_MAP_ITEM: Final = SymbolId("Lbl'UndsPipe'-'-GT-Unds'")


def kore_map(*args: tuple[Pattern, Pattern], cell: str | None = None) -> Pattern:
    if not args:
        return App(f"Lbl'Stop'{cell}Map") if cell else STOP_MAP

    cons_symbol = SymbolId(f"Lbl'Unds'{cell}Map'Unds'") if cell else LBL_MAP
    item_symbol = SymbolId(f'Lbl{cell}MapItem') if cell else LBL_MAP_ITEM
    return LeftAssoc(App(cons_symbol, args=(App(item_symbol, args=arg) for arg in args)))


# ----
# JSON
# ----

SORT_JSON: Final = SortApp('SortJSON')
SORT_JSON_KEY: Final = SortApp('SortJSONKey')

LBL_JSONS: Final = SymbolId('LblJSONs')
LBL_JSON_LIST: Final = SymbolId('LblJSONList')
LBL_JSON_OBJECT: Final = SymbolId('LblJSONObject')
LBL_JSON_ENTRY: Final = SymbolId('LblJSONEntry')

STOP_JSONS: Final = App("Lbl'Stop'List'LBraQuot'JSONs'QuotRBraUnds'JSONs")

LBL_STRING2JSON: Final = SymbolId("LblString2JSON'LParUndsRParUnds'JSON'Unds'JSON'Unds'String")
LBL_JSON2STRING: Final = SymbolId("LblJSON2String'LParUndsRParUnds'JSON'Unds'String'Unds'JSON")


def string2json(pattern: Pattern) -> App:
    return App(LBL_STRING2JSON, (), (pattern,))


def json2string(pattern: Pattern) -> App:
    return App(LBL_JSON2STRING, (), (pattern,))


def json_to_kore(data: Any) -> Pattern:
    return App(LBL_JSON_OBJECT, (), (STOP_JSONS,))


def kore_to_json(pattern: Pattern) -> dict[str, Any]:
    return {}
