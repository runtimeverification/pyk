from __future__ import annotations

from abc import ABC, abstractmethod, abstractproperty
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Iterable

    from ..cterm import CTerm
    from ..kast.inner import KInner
    from ..kast.outer import KDefinition


class KCFGSemantics(ABC):
    _definition: KDefinition | None

    def __init__(self, definition: KDefinition | None = None):
        self._definition = definition

    def set_definition(self, definition: KDefinition) -> None:
        self._definition = definition

    @staticmethod
    @abstractmethod
    def is_terminal(c: CTerm) -> bool:
        ...

    @abstractmethod
    def extract_branches(self, c: CTerm) -> Iterable[KInner]:
        ...

    @staticmethod
    @abstractmethod
    def abstract_node(c: CTerm) -> CTerm:
        ...

    @staticmethod
    @abstractmethod
    def same_loop(c1: CTerm, c2: CTerm) -> bool:
        ...

    @abstractproperty
    def cut_point_rules(self) -> Iterable[str]:
        ...

    @abstractproperty
    def terminal_rules(self) -> Iterable[str]:
        ...


class DefaultSemantics(KCFGSemantics):
    def __init__(self, definition: KDefinition | None = None):
        super().__init__(definition)

    @staticmethod
    def is_terminal(c: CTerm) -> bool:
        return False

    def extract_branches(self, c: CTerm) -> Iterable[KInner]:
        return []

    @staticmethod
    def abstract_node(c: CTerm) -> CTerm:
        return c

    @staticmethod
    def same_loop(c1: CTerm, c2: CTerm) -> bool:
        return False

    @property
    def cut_point_rules(self) -> Iterable[str]:
        return []

    @property
    def terminal_rules(self) -> Iterable[str]:
        return []
