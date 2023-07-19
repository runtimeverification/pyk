from __future__ import annotations

from abc import ABC
from collections.abc import Sequence
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, final, overload

if TYPE_CHECKING:
    from collections.abc import Iterable
    from typing import Any, Final


class AST(ABC):
    ...


@final
@dataclass(frozen=True)
class Att(AST, Sequence[tuple[str, str]]):
    items: tuple[tuple[str, str], ...]

    def __init__(self, items: Iterable[tuple[str, str]] = ()):
        object.__setattr__(self, 'items', tuple(items))

    @overload
    def __getitem__(self, key: int) -> tuple[str, str]:
        ...

    @overload
    def __getitem__(self, key: slice) -> tuple[tuple[str, str], ...]:
        ...

    def __getitem__(self, key: Any) -> Any:
        return self.items[key]

    def __len__(self) -> int:
        return len(self.items)


EMPTY_ATT: Final = Att()


class StringSentence(AST, ABC):
    _prefix: str

    bubble: str
    label: str
    att: Att


@final
@dataclass(frozen=True)
class Rule(StringSentence):
    _prefix = 'rule'

    bubble: str
    label: str = field(default='')
    att: Att = field(default=EMPTY_ATT)


@final
@dataclass(frozen=True)
class Claim(StringSentence):
    _prefix = 'claim'

    bubble: str
    label: str = field(default='')
    att: Att = field(default=EMPTY_ATT)


@final
@dataclass(frozen=True)
class Config(StringSentence):
    _prefix = 'configuration'

    bubble: str
    label: str = field(default='')
    att: Att = field(default=EMPTY_ATT)


@final
@dataclass(frozen=True)
class Context(StringSentence):
    _prefix = 'context'

    bubble: str
    label: str = field(default='')
    att: Att = field(default=EMPTY_ATT)


@final
@dataclass(frozen=True)
class Alias(StringSentence):
    _prefix = 'context alias'

    bubble: str
    label: str = field(default='')
    att: Att = field(default=EMPTY_ATT)


@final
@dataclass(frozen=True)
class Import(AST):
    module_name: str
    public: bool = field(default=True, kw_only=True)
