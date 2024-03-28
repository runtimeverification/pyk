from __future__ import annotations

from multiprocessing import Process
from typing import TYPE_CHECKING

from pyk.cli.pyk import ServeRpcOptions
from pyk.kore.rpc import JsonRpcClient
from pyk.rpc.rpc import StatefulKJsonRpcServer
from pyk.testing import KRunTest
from threading import Thread
from pyk.kore.rpc import JsonRpcClient, TransportType

from .utils import K_FILES

if TYPE_CHECKING:
    from pyk.ktool.krun import KRun


class TestJsonRPCServer(KRunTest):
    KOMPILE_MAIN_FILE = K_FILES / 'json-rpc-example.k'
    KOMPILE_BACKEND = 'llvm'

    def test_json_rpc_server(self, krun: KRun) -> None:

        server = StatefulKJsonRpcServer(ServeRpcOptions({'definition_dir': krun.definition_dir, 'port': 56602}))
        def run_server() -> None:
            server.serve()

        process = Thread(target=run_server)
        process.start()

        rpc_client = JsonRpcClient('localhost', 56602, transport=TransportType.HTTP)

        def wait_until_ready() -> None:
            while True:
                try:
                    rpc_client.request('get_x')
                except ConnectionRefusedError:
                    sleep(1)
                    continue
                break

        wait_until_ready()

        rpc_client.request('set_x', n=123)
        res = rpc_client.request('get_x')
        assert res == 123

        rpc_client.request('set_y', n=456)
        res = rpc_client.request('get_y')
        assert res == 456

        res = rpc_client.request('add')
        assert res == (123 + 456)

        server.shutdown()
        process.join()
