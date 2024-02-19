from __future__ import annotations

from dataclasses import dataclass, field
from typing import Generic, TypeVar

A = TypeVar('A')


@dataclass
class CachedValues(Generic[A]):
    value_to_id: dict[A, int] = field(default_factory=dict)
    values: list[A] = field(default_factory=list)

    def cache(self, value: A) -> int:
        id = self.value_to_id.get(value)
        if id is not None:
            return id
        id = len(self.values)
        self.value_to_id[value] = id
        self.values.append(value)
        return id
