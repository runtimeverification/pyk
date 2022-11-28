from pathlib import Path

import pytest
from pytest import TempPathFactory

from pyk.kast.outer import KDefinition, read_kast_definition

from .utils import Kompiler


@pytest.fixture(scope='session')
def kompile(tmp_path_factory: TempPathFactory) -> Kompiler:
    return Kompiler(tmp_path_factory)


@pytest.fixture(scope='session')
def imp_definition_dir(kompile: Kompiler) -> Path:
    return kompile('k-files/imp.k')


@pytest.fixture(scope='session')
def imp_definition(imp_definition_dir: Path) -> KDefinition:
    return read_kast_definition(imp_definition_dir / 'compiled.json')
