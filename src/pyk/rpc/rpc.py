from __future__ import annotations

import json
import logging
from functools import partial
from http.server import BaseHTTPRequestHandler, HTTPServer
from typing import TYPE_CHECKING, Any, Callable, Final

if TYPE_CHECKING:
    from ..cli.pyk import ServeRpcOptions

_LOGGER: Final = logging.getLogger(__name__)


class JsonRpcServer:
    JSONRPC_VERSION: str = '2.0'
    methods: dict[str, Callable[[Any], Any]]
    options: ServeRpcOptions

    def __init__(self, options: ServeRpcOptions) -> None:
        self.methods = {}
        self.options = options

    def register_method(self, name: str, function: Callable[[Any], Any]) -> None:
        _LOGGER.info(f'Registered method {name} using {function}')
        self.methods[name] = function

    def serve(self) -> None:
        handler = partial(JsonRpcRequestHandler, self.methods)
        _LOGGER.info(f'Starting JSON-RPC server at {self.options.addr}:{self.options.port}')
        HTTPServer((self.options.addr, self.options.port), handler).serve_forever()


class JsonRpcRequestHandler(BaseHTTPRequestHandler):
    methods: dict[str, Callable[[Any], Any]]

    def __init__(self, methods: dict[str, Callable[[Any], Any]], *args: Any, **kwargs: Any) -> None:
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
        result = method(params)
        _LOGGER.debug(f'Got response {result}')
        self.send_json_success(result, request['id'])


class ExampleJsonRpcServer(JsonRpcServer):
    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self.register_method('print_hello', self.exec_print_hello)

    def exec_print_hello(self, obj: None) -> str:
        return 'hello.'
