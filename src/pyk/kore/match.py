from typing import Callable, Optional, Tuple, TypeVar, overload

from ..utils import case, check_type
from .prelude import BOOL, INT, STRING
from .syntax import DV, App, LeftAssoc, Pattern, Sort

P = TypeVar('P')
R1 = TypeVar('R1')
R2 = TypeVar('R2')
R3 = TypeVar('R3')
R4 = TypeVar('R4')
K = TypeVar('K')
V = TypeVar('V')


def match_dv(pattern: Pattern, sort: Optional[Sort] = None) -> DV:
    dv = check_type(pattern, DV)
    if sort and dv.sort != sort:
        raise ValueError(f'Expected sort {sort.text}, found: {dv.sort.text}')
    return dv


def match_symbol(app: App, symbol: str) -> None:
    if app.symbol != symbol:
        raise ValueError(f'Expected symbol {symbol}, found: {app.symbol}')


def match_app(pattern: Pattern, symbol: Optional[str] = None) -> App:
    app = check_type(pattern, App)
    if symbol is not None:
        match_symbol(app, symbol)
    return app


def match_inj(pattern: Pattern) -> App:
    return match_app(pattern, 'inj')


def match_left_assoc(pattern: Pattern) -> LeftAssoc:
    return check_type(pattern, LeftAssoc)


def match_list(pattern: Pattern) -> Tuple[Pattern, ...]:
    if type(pattern) is App:
        match_app(pattern, "Lbl'Stop'List")
        return ()

    assoc = match_left_assoc(pattern)
    cons = match_app(assoc.app, "Lbl'Unds'List'Unds'")
    items = (match_app(arg, 'LblListItem') for arg in cons.args)
    elems = (item.args[0] for item in items)
    return tuple(elems)


def match_set(pattern: Pattern) -> Tuple[Pattern, ...]:
    if type(pattern) is App:
        match_app(pattern, "Lbl'Stop'Set")
        return ()

    assoc = match_left_assoc(pattern)
    cons = match_app(assoc.app, "Lbl'Unds'Set'Unds'")
    items = (match_app(arg, 'LblSetItem') for arg in cons.args)
    elems = (item.args[0] for item in items)
    return tuple(elems)


def match_map(pattern: Pattern, *, cell: Optional[str] = None) -> Tuple[Tuple[Pattern, Pattern], ...]:
    cell = cell or ''
    stop_symbol = f"Lbl'Stop'{cell}Map"
    cons_symbol = f"Lbl'Unds'{cell}Map'Unds'"
    item_symbol = "Lbl'UndsPipe'-'-GT-Unds'" if not cell else f'Lbl{cell}MapItem'

    if type(pattern) is App:
        match_app(pattern, stop_symbol)
        return ()

    assoc = match_left_assoc(pattern)
    cons = match_app(assoc.app, cons_symbol)
    items = (match_app(arg, item_symbol) for arg in cons.args)
    entries = ((item.args[0], item.args[1]) for item in items)
    return tuple(entries)


def kore_bool(pattern: Pattern) -> bool:
    dv = match_dv(pattern, BOOL)
    return bool(dv.value.value)


def kore_int(pattern: Pattern) -> int:
    dv = match_dv(pattern, INT)
    return int(dv.value.value)


def kore_str(pattern: Pattern) -> str:
    dv = match_dv(pattern, STRING)
    return dv.value.value


# Higher-order functions


def app(symbol: Optional[str] = None) -> Callable[[Pattern], App]:
    def res(pattern: Pattern) -> App:
        return match_app(pattern, symbol)

    return res


def arg(n: int) -> Callable[[App], Pattern]:
    def res(app: App) -> Pattern:
        return app.args[n]

    return res


@overload
def args(n1: int, n2: int, /) -> Callable[[App], Tuple[Pattern, Pattern]]:
    ...


@overload
def args(n1: int, n2: int, n3: int, /) -> Callable[[App], Tuple[Pattern, Pattern, Pattern]]:
    ...


@overload
def args(n1: int, n2: int, n3: int, n4: int, /) -> Callable[[App], Tuple[Pattern, Pattern, Pattern, Pattern]]:
    ...


def args(*ns: int) -> Callable[[App], Tuple]:
    def res(app: App) -> Tuple:
        return tuple(app.args[n] for n in ns)

    return res


def inj(pattern: Pattern) -> Pattern:
    return arg(0)(app('inj')(pattern))


def kore_list(item: Callable[[Pattern], P]) -> Callable[[Pattern], Tuple[P, ...]]:
    def res(pattern: Pattern) -> Tuple[P, ...]:
        return tuple(item(e) for e in match_list(pattern))

    return res


def kore_set(item: Callable[[Pattern], P]) -> Callable[[Pattern], Tuple[P, ...]]:
    def res(pattern: Pattern) -> Tuple[P, ...]:
        return tuple(item(e) for e in match_set(pattern))

    return res


def kore_map(
    key: Callable[[Pattern], K],
    value: Callable[[Pattern], V],
    *,
    cell: Optional[str] = None,
) -> Callable[[Pattern], Tuple[Tuple[K, V], ...]]:
    def res(pattern: Pattern) -> Tuple[Tuple[K, V], ...]:
        return tuple((key(k), value(v)) for k, v in match_map(pattern, cell=cell))

    return res


def case_symbol(
    *cases: Tuple[str, Callable[[App], P]],
    default: Optional[Callable[[App], P]] = None,
) -> Callable[[Pattern], P]:
    def cond(symbol: str) -> Callable[[App], bool]:
        return lambda app: app.symbol == symbol

    def res(pattern: Pattern) -> P:
        app = match_app(pattern)
        return case(
            cases=((cond(symbol), then) for symbol, then in cases),
            default=default,
        )(app)

    return res
