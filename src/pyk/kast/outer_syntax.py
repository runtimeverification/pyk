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


class Sentence(AST, ABC):
    ...


class StringSentence(Sentence, ABC):
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


@final
@dataclass(frozen=True)
class Module(AST):
    name: str
    sentences: tuple[Sentence, ...]
    imports: tuple[Import, ...]
    att: Att

    def __init__(
        self,
        name: str,
        sentences: Iterable[Sentence] = (),
        imports: Iterable[Import] = (),
        att: Att = EMPTY_ATT,
    ):
        object.__setattr__(self, 'name', name)
        object.__setattr__(self, 'sentences', tuple(sentences))
        object.__setattr__(self, 'imports', tuple(imports))
        object.__setattr__(self, 'att', att)


@final
@dataclass(frozen=True)
class Require(AST):
    path: str


@final
@dataclass(frozen=True)
class Definition(AST):
    modules: tuple[Module, ...]
    requires: tuple[Require, ...]

    def __init__(self, modules: Iterable[Module] = (), requires: Iterable[Require] = ()):
        object.__setattr__(self, 'modules', tuple(modules))
        object.__setattr__(self, 'requires', tuple(requires))
