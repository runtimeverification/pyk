from __future__ import annotations

import json
import logging
from abc import ABC, abstractmethod
from collections.abc import Mapping
from dataclasses import dataclass, fields
from functools import cached_property
from itertools import chain
from typing import TYPE_CHECKING, Any, final

from ..utils import FrozenDict, hash_str

if TYPE_CHECKING:
    from collections.abc import Callable, Iterable, Iterator
    from typing import Final, TypeVar

    T = TypeVar('T', bound='KAst')
    W = TypeVar('W', bound='WithKAtt')

_LOGGER: Final = logging.getLogger(__name__)


class KAst(ABC):
    @staticmethod
    def version() -> int:
        return 3

    @abstractmethod
    def to_dict(self) -> dict[str, Any]:
        ...

    @final
    def to_json(self) -> str:
        return json.dumps(self.to_dict(), sort_keys=True)

    @final
    @cached_property
    def hash(self) -> str:
        return hash_str(self.to_json())

    def __lt__(self, other: Any) -> bool:
        if not isinstance(other, KAst):
            return NotImplemented
        if type(self) == type(other):
            return self._as_shallow_tuple() < other._as_shallow_tuple()
        return type(self).__name__ < type(other).__name__

    def _as_shallow_tuple(self) -> tuple[Any, ...]:
        # shallow copy version of dataclass.astuple.
        return tuple(self.__dict__[field.name] for field in fields(type(self)))  # type: ignore


@final
@dataclass(frozen=True)
class AttKey:
    name: str

    def __call__(self, value: Any) -> AttEntry:
        return AttEntry(self, value)


@final
@dataclass(frozen=True)
class AttEntry:
    key: AttKey
    value: Any


class Atts:
    ALIAS: Final = AttKey('alias')
    ALIAS_REC: Final = AttKey('alias-rec')
    ANYWHERE: Final = AttKey('anywhere')
    ASSOC: Final = AttKey('assoc')
    CIRCULARITY: Final = AttKey('circularity')
    CELL: Final = AttKey('cell')
    CELL_COLLECTION: Final = AttKey('cellCollection')
    COLORS: Final = AttKey('colors')
    COMM: Final = AttKey('comm')
    CONCAT: Final = AttKey('concat')
    CONSTRUCTOR: Final = AttKey('constructor')
    DEPENDS: Final = AttKey('depends')
    DIGEST: Final = AttKey('digest')
    ELEMENT: Final = AttKey('element')
    FORMAT: Final = AttKey('format')
    FUNCTION: Final = AttKey('function')
    FUNCTIONAL: Final = AttKey('functional')
    HAS_DOMAIN_VALUES: Final = AttKey('hasDomainValues')
    HOOK: Final = AttKey('hook')
    IDEM: Final = AttKey('idem')
    INITIALIZER: Final = AttKey('initializer')
    INJECTIVE: Final = AttKey('injective')
    KLABEL: Final = AttKey('klabel')
    LABEL: Final = AttKey('label')
    LEFT: Final = AttKey('left')
    LOCATION: Final = AttKey('org.kframework.attributes.Location')
    MACRO: Final = AttKey('macro')
    MACRO_REC: Final = AttKey('macro-rec')
    OWISE: Final = AttKey('owise')
    PRIORITY: Final = AttKey('priority')
    PRODUCTION: Final = AttKey('org.kframework.definition.Production')
    PROJECTION: Final = AttKey('projection')
    RIGHT: Final = AttKey('right')
    SIMPLIFICATION: Final = AttKey('simplification')
    SYMBOL: Final = AttKey('symbol')
    SORT: Final = AttKey('org.kframework.kore.Sort')
    SOURCE: Final = AttKey('org.kframework.attributes.Source')
    TOKEN: Final = AttKey('token')
    TOTAL: Final = AttKey('total')
    TRUSTED: Final = AttKey('trusted')
    UNIT: Final = AttKey('unit')
    UNIQUE_ID: Final = AttKey('UNIQUE_ID')
    UNPARSE_AVOID: Final = AttKey('unparseAvoid')
    WRAP_ELEMENT: Final = AttKey('wrapElement')


@final
@dataclass(frozen=True)
class KAtt(KAst, Mapping[AttKey, Any]):
    atts: FrozenDict[AttKey, Any]

    def __init__(self, entries: Iterable[AttEntry] = ()):
        atts: FrozenDict[AttKey, Any] = FrozenDict((e.key, self._freeze(e.value)) for e in entries)
        object.__setattr__(self, 'atts', atts)

    def __iter__(self) -> Iterator[AttKey]:
        return iter(self.atts)

    def __len__(self) -> int:
        return len(self.atts)

    def __getitem__(self, key: AttKey) -> Any:
        return self.atts[key]

    def entries(self) -> Iterator[AttEntry]:
        return (key(value) for key, value in self.atts.items())

    @classmethod
    def from_dict(cls: type[KAtt], d: Mapping[str, Any]) -> KAtt:
        return KAtt(entries=(AttEntry(AttKey(key), value) for key, value in d['att'].items()))

    def to_dict(self) -> dict[str, Any]:
        return {'node': 'KAtt', 'att': KAtt._unfreeze({key.name: value for key, value in self.atts.items()})}

    @staticmethod
    def _freeze(m: Any) -> Any:
        if isinstance(m, (int, str, tuple, FrozenDict, frozenset)):
            return m
        elif isinstance(m, list):
            return tuple(KAtt._freeze(v) for v in m)
        elif isinstance(m, dict):
            return FrozenDict((k, KAtt._freeze(v)) for (k, v) in m.items())
        raise ValueError(f"Don't know how to freeze attribute value {m} of type {type(m)}.")

    @staticmethod
    def _unfreeze(x: Any) -> Any:
        if isinstance(x, FrozenDict):
            return {k: KAtt._unfreeze(v) for (k, v) in x.items()}
        return x

    def update(self, entries: Iterable[AttEntry]) -> KAtt:
        entries = chain((AttEntry(key, value) for key, value in self.atts.items()), entries)
        return KAtt(entries=entries)

    def remove(self, keys: Iterable[AttKey]) -> KAtt:
        entries = (AttEntry(key, value) for key, value in self.atts.items() if key not in keys)
        return KAtt(entries=entries)

    def drop_source(self) -> KAtt:
        return self.remove([Atts.SOURCE, Atts.LOCATION])

    @property
    def pretty(self) -> str:
        if len(self) == 0:
            return ''
        att_strs = []
        for k, v in self.items():
            if k == Atts.LOCATION:
                loc_ids = str(v).replace(' ', '')
                att_strs.append(f'{k.name}{loc_ids}')
            elif k == Atts.SOURCE:
                att_strs.append(k.name + '("' + v + '")')
            else:
                att_strs.append(f'{k.name}({v})')
        return f'[{", ".join(att_strs)}]'


EMPTY_ATT: Final = KAtt()


class WithKAtt(ABC):
    att: KAtt

    @abstractmethod
    def let_att(self: W, att: KAtt) -> W:
        ...

    def map_att(self: W, f: Callable[[KAtt], KAtt]) -> W:
        return self.let_att(att=f(self.att))

    def update_atts(self: W, entries: Iterable[AttEntry]) -> W:
        return self.let_att(att=self.att.update(entries))


def kast_term(dct: Mapping[str, Any]) -> Mapping[str, Any]:
    if dct['format'] != 'KAST':
        raise ValueError(f"Invalid format: {dct['format']}")

    if dct['version'] != KAst.version():
        raise ValueError(f"Invalid version: {dct['version']}")

    return dct['term']
