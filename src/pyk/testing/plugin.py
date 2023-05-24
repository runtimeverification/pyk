from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from .ktool import Kompiler
from .profiler import Profiler

if TYPE_CHECKING:
    from pathlib import Path

    from pytest import TempPathFactory


@pytest.fixture
def profile(tmp_path: Path) -> Profiler:
    return Profiler(tmp_path)


@pytest.fixture(scope='session')
def kompile(tmp_path_factory: TempPathFactory) -> Kompiler:
    return Kompiler(tmp_path_factory)
