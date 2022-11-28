from contextlib import closing
from pathlib import Path
from socket import AF_INET, SO_REUSEADDR, SOCK_STREAM, SOL_SOCKET, socket
from time import sleep
from typing import ClassVar, Iterable, Optional, Union

import pytest
from pytest import TempPathFactory

from pyk.kast.outer import KDefinition, read_kast_definition
from pyk.ktool import KompileBackend, kompile


class Kompiler:
    _tmp_path_factory: TempPathFactory

    def __init__(self, tmp_path_factory: TempPathFactory):
        self._tmp_path_factory = tmp_path_factory

    def __call__(
        self,
        main_file: Union[str, Path],
        *,
        backend: Optional[KompileBackend] = None,
        main_module: Optional[str] = None,
        syntax_module: Optional[str] = None,
        include_dirs: Iterable[Union[str, Path]] = (),
    ) -> Path:
        return kompile(
            main_file=main_file,
            output_dir=self._tmp_path_factory.mktemp('kompiled'),
            backend=backend,
            main_module=main_module,
            syntax_module=syntax_module,
            include_dirs=include_dirs,
        )


class KompiledTest:
    KOMPILE_MAIN_FILE: ClassVar[str]
    KOMPILE_BACKEND: ClassVar[Optional[str]] = None
    KOMPILE_MAIN_MODULE: ClassVar[Optional[str]] = None
    KOMPILE_SYNTAX_MODULE: ClassVar[Optional[str]] = None
    KOMPILE_INCLUDE_DIRS: ClassVar[Iterable[str]] = []

    @pytest.fixture(scope='class')
    def definition_dir(self, kompile: Kompiler) -> Path:
        return kompile(
            main_file=self.KOMPILE_MAIN_FILE,
            backend=KompileBackend(self.KOMPILE_BACKEND) if self.KOMPILE_BACKEND else None,
            main_module=self.KOMPILE_MAIN_MODULE,
            syntax_module=self.KOMPILE_SYNTAX_MODULE,
            include_dirs=self.KOMPILE_INCLUDE_DIRS,
        )

    @pytest.fixture(scope='class')
    def definition(self, definition_dir: Path) -> KDefinition:
        return read_kast_definition(definition_dir / 'compiled.json')


# Based on: https://stackoverflow.com/a/45690594
# Note: has an obvious race condition, use only for testing
def free_port_on_host(host: str = 'localhost') -> int:
    with closing(socket(AF_INET, SOCK_STREAM)) as sock:
        sock.bind((host, 0))
        sock.setsockopt(SOL_SOCKET, SO_REUSEADDR, 1)
        _, port = sock.getsockname()
    return port


def port_is_open(port: int) -> bool:
    sock = socket(AF_INET, SOCK_STREAM)
    try:
        sock.connect(('localhost', port))
    except BaseException:
        return False
    else:
        return True
    finally:
        sock.close()


def wait_for_port(port: int) -> None:
    while not port_is_open(port):
        sleep(0.1)
