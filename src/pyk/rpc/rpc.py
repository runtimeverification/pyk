from __future__ import annotations

import json
import logging
from functools import partial
from http.server import BaseHTTPRequestHandler, HTTPServer
from typing import TYPE_CHECKING, Any, Final
from collections.abc import Callable

from typing_extensions import Protocol

from ..cterm.cterm import Subst
from ..kast.inner import KApply, KSequence, KSort, KToken
from ..kast.manip import set_cell, split_config_from
from ..ktool.krun import KRun

if TYPE_CHECKING:
    from ..cli.pyk import ServeRpcOptions
    from ..kast import KInner

_LOGGER: Final = logging.getLogger(__name__)


class JsonRpcServer:
    JSONRPC_VERSION: str = '2.0'
    methods: dict[str, Callable[..., Any]]
    options: ServeRpcOptions
    http_server: HTTPServer

    def __init__(self, options: ServeRpcOptions) -> None:
        self.methods = {}
        self.options = options

    def register_method(self, name: str, function: Callable[..., Any]) -> None:
        _LOGGER.info(f'Registered method {name} using {function}')
        self.methods[name] = function

    def serve(self) -> None:
        handler = partial(JsonRpcRequestHandler, self.methods)
        _LOGGER.info(f'Starting JSON-RPC server at {self.options.addr}:{self.options.port}')
        self.http_server = HTTPServer((self.options.addr, self.options.port), handler)
        self.http_server.serve_forever()
        _LOGGER.info(f'JSON-RPC server at {self.options.addr}:{self.options.port} shut down.')

    def shutdown(self) -> None:
        self.http_server.shutdown()


class JsonRpcMethod(Protocol):
    def __call__(self, **kwargs: Any) -> Any: ...


class JsonRpcRequestHandler(BaseHTTPRequestHandler):
    methods: dict[str, JsonRpcMethod]

    def __init__(self, methods: dict[str, JsonRpcMethod], *args: Any, **kwargs: Any) -> None:
        self.methods = methods
        super().__init__(*args, **kwargs)

    def send_json_error(self, code: int, message: str, id: Any = None) -> None:
        error_dict = {
            'jsonrpc': JsonRpcServer.JSONRPC_VERSION,
            'error': {
                'code': code,
                'message': message,
            },
            'id': id,
        }
        error_bytes = json.dumps(error_dict).encode('ascii')
        self.set_response()
        self.wfile.write(error_bytes)

    def send_json_success(self, result: Any, id: Any) -> None:
        response_dict = {
            'jsonrpc': JsonRpcServer.JSONRPC_VERSION,
            'result': result,
            'id': id,
        }
        response_bytes = json.dumps(response_dict).encode('ascii')
        self.set_response()
        self.wfile.write(response_bytes)

    def set_response(self) -> None:
        self.send_response(200)
        self.send_header('Content-type', 'text/html')
        self.end_headers()

    def do_POST(self) -> None:  # noqa: N802
        content_len = self.headers.get('Content-Length')
        assert type(content_len) is str

        content = self.rfile.read(int(content_len))
        _LOGGER.debug(f'Received bytes: {content.decode()}')

        request: dict
        try:
            request = json.loads(content)
            _LOGGER.info(f'Received request: {request}')
        except json.JSONDecodeError:
            _LOGGER.warning(f'Invalid JSON: {content.decode()}')
            self.send_json_error(-32700, 'Invalid JSON')
            return

        required_fields = ['jsonrpc', 'method', 'id']
        for field in required_fields:
            if field not in request:
                _LOGGER.warning(f'Missing required field "{field}": {request}')
                self.send_json_error(-32600, f'Invalid request: missing field "{field}"', request.get('id', None))
                return

        jsonrpc_version = request['jsonrpc']
        if jsonrpc_version != JsonRpcServer.JSONRPC_VERSION:
            _LOGGER.warning(f'Bad JSON-RPC version: {jsonrpc_version}')
            self.send_json_error(-32600, f'Invalid request: bad version: "{jsonrpc_version}"', request['id'])
            return

        method_name = request['method']
        if method_name not in self.methods:
            _LOGGER.warning(f'Method not found: {method_name}')
            self.send_json_error(-32601, f'Method "{method_name}" not found.', request['id'])
            return

        method = self.methods[method_name]
        params = request.get('params', None)
        _LOGGER.info(f'Executing method {method_name}')
        if type(params) is dict:
            result = method(**params)
        elif type(params) is list:
            result = method(*params)
        elif params is None:
            result = method()
        else:
            self.send_json_error(-32602, 'Unrecognized method parameter format.')
        _LOGGER.debug(f'Got response {result}')
        self.send_json_success(result, request['id'])


class ExampleJsonRpcServer(JsonRpcServer):
    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self.register_method('print_hello', self.exec_print_hello)

    def exec_print_hello(self, obj: None) -> str:
        return 'hello.'


def get_cell(config: KInner, cell: str) -> KInner:
    _, subst = split_config_from(config)
    return Subst(subst)[cell]


class StatefulKJsonRpcServer(JsonRpcServer):
    krun: KRun
    config: KInner

    def __init__(self, options: ServeRpcOptions) -> None:
        super().__init__(options)

        self.register_method('get_x', self.exec_get_x)
        self.register_method('get_y', self.exec_get_y)
        self.register_method('set_x', self.exec_set_x)
        self.register_method('set_y', self.exec_set_y)
        self.register_method('add', self.exec_add)

        if not options.definition_dir:
            raise ValueError('Must specify a definition dir with --definition')
        self.krun = KRun(options.definition_dir)
        self.config = self.krun.definition.init_config(KSort('GeneratedTopCell'))

    def exec_get_x(self) -> int:
        x_cell = get_cell(self.config, 'X_CELL')
        assert type(x_cell) is KToken
        return int(x_cell.token)

    def exec_get_y(self) -> int:
        y_cell = get_cell(self.config, 'Y_CELL')
        assert type(y_cell) is KToken
        return int(y_cell.token)

    def exec_set_x(self, n: int) -> None:
        self.config = set_cell(self.config, 'X_CELL', KToken(token=str(n), sort=KSort(name='Int')))

    def exec_set_y(self, n: int) -> None:
        self.config = set_cell(self.config, 'Y_CELL', KToken(token=str(n), sort=KSort(name='Int')))

    def exec_add(self) -> int:
        x = get_cell(self.config, 'X_CELL')
        y = get_cell(self.config, 'Y_CELL')
        self.config = set_cell(self.config, 'K_CELL', KApply('_+Int_', [x, y]))

        pattern = self.krun.kast_to_kore(self.config, sort=KSort('GeneratedTopCell'))
        output_kore = self.krun.run_pattern(pattern)
        self.config = self.krun.kore_to_kast(output_kore)
        k_cell = get_cell(self.config, 'K_CELL')
        if type(k_cell) is KSequence:
            assert len(k_cell.items) == 1
            k_cell = k_cell.items[0]

        assert type(k_cell) is KToken
        return int(k_cell.token)
