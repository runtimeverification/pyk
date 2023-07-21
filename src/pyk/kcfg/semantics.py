from __future__ import annotations

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Iterable

    from ..cterm import CTerm
    from ..kast.inner import KInner
    from ..kast.outer import KDefinition


class KCFGSemantics(ABC):
    definition: KDefinition | None

    cut_point_rules: Iterable[str]
    terminal_rules: Iterable[str]

    def __init__(self, definition: KDefinition | None = None):
        self.definition = definition
        self.cut_point_rules = []
        self.terminal_rules = []

    @abstractmethod
    def is_terminal(self, c: CTerm) -> bool:
        ...

    @abstractmethod
    def extract_branches(self, c: CTerm) -> Iterable[KInner]:
        ...

    @abstractmethod
    def abstract_node(self, c: CTerm) -> CTerm:
        ...

    @abstractmethod
    def same_loop(self, c1: CTerm, c2: CTerm) -> bool:
        ...


class DefaultSemantics(KCFGSemantics):
    def __init__(self, definition: KDefinition | None = None):
        super().__init__(definition)

    def is_terminal(self, c: CTerm) -> bool:
        return False

    def extract_branches(self, c: CTerm) -> Iterable[KInner]:
        return []

    def abstract_node(self, c: CTerm) -> CTerm:
        return c

    def same_loop(self, c1: CTerm, c2: CTerm) -> bool:
        return False
