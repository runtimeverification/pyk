from pathlib import Path
from typing import ClassVar, Iterator

import pytest

from pyk.kore.rpc import KoreClient, KoreServer

from ..utils import KompiledTest, free_port_on_host


class KoreClientTest(KompiledTest):
    KOMPILE_BACKEND = 'haskell'

    KORE_MODULE_NAME: ClassVar[str]
    KORE_CLIENT_TIMEOUT: ClassVar = 1000

    @pytest.fixture
    def kore_client(self, definition_dir: Path) -> Iterator[KoreClient]:
        port = free_port_on_host()
        server = KoreServer(definition_dir, self.KORE_MODULE_NAME, port)
        client = KoreClient('localhost', port, timeout=self.KORE_CLIENT_TIMEOUT)
        yield client
        client.close()
        server.close()
