from __future__ import annotations

from itertools import count
from typing import TYPE_CHECKING
from unittest.mock import patch

import pytest

from pyk.kore.prelude import INT, int_dv
from pyk.kore.rpc import (
    ImpliesResult,
    JsonRpcClient,
    KoreClient,
    KoreClientError,
    SatResult,
    SingleSocketTransport,
    State,
    StuckResult,
    TransportType,
    UnknownResult,
    UnsatResult,
)
from pyk.kore.syntax import And, App, Bottom, Module, Top

if TYPE_CHECKING:
    from collections.abc import Iterator
    from typing import Any, Final
    from unittest.mock import Mock

    from pyk.kore.rpc import ExecuteResult
    from pyk.kore.syntax import Pattern

int_top = Top(INT)
int_bottom = Bottom(INT)


def kore(pattern: Pattern) -> dict[str, Any]:
    return {
        'format': 'KORE',
        'version': 1,
        'term': pattern.dict,
    }


class MockClient:
    mock: Mock

    def __init__(self, mock: Mock):
        self.mock = mock

    def assume_response(self, response: Any) -> None:
        self.mock.request.return_value = response

    def assert_request(self, method: str, **params: Any) -> None:
        self.mock.request.assert_called_with(method, **params)


@pytest.fixture
def rpc_mock_class() -> Iterator[Mock]:
    patcher = patch('pyk.kore.rpc.JsonRpcClient', spec=True)
    yield patcher.start()
    patcher.stop()


@pytest.fixture
def mock(rpc_mock_class: Mock) -> Mock:
    mock = rpc_mock_class.return_value
    assert isinstance(mock, JsonRpcClient)
    return mock  # type: ignore


@pytest.fixture
def rpc_client(mock: Mock) -> MockClient:
    return MockClient(mock)


@pytest.fixture
def kore_client(mock: Mock, rpc_mock_class: Mock) -> Iterator[KoreClient]:  # noqa: N803
    client = KoreClient('localhost', 3000)
    rpc_mock_class.assert_called_with(
        'localhost', 3000, timeout=None, bug_report=None, transport=TransportType.SINGLE_SOCKET
    )
    assert client._client == mock
    yield client
    client.close()
    mock.close.assert_called()


EXECUTE_TEST_DATA: Final = (
    (
        App('IntAdd', (), (int_dv(1), int_dv(1))),
        {'state': kore(App('IntAdd', [], [int_dv(1), int_dv(1)]))},
        {
            'state': {'term': kore(int_dv(2)), 'substitution': kore(int_top), 'predicate': kore(int_top)},
            'depth': 1,
            'reason': 'stuck',
        },
        StuckResult(State(int_dv(2), int_top, int_top), 1, logs=()),
    ),
)


@pytest.mark.parametrize('pattern,params,response,expected', EXECUTE_TEST_DATA, ids=count())
def test_execute(
    kore_client: KoreClient,
    rpc_client: MockClient,
    pattern: Pattern,
    params: dict[str, Any],
    response: dict[str, Any],
    expected: ExecuteResult,
) -> None:
    # Given
    rpc_client.assume_response(response)

    # When
    actual = kore_client.execute(pattern)

    # Then
    rpc_client.assert_request('execute', **params)
    assert actual == expected


IMPLIES_TEST_DATA: Final = (
    (
        int_bottom,
        int_top,
        {'antecedent': kore(int_bottom), 'consequent': kore(int_top)},
        {'satisfiable': True, 'implication': kore(int_top)},
        ImpliesResult(True, int_top, None, None, ()),
    ),
)


@pytest.mark.parametrize('antecedent,consequent,params,response,expected', IMPLIES_TEST_DATA, ids=count())
def test_implies(
    kore_client: KoreClient,
    rpc_client: MockClient,
    antecedent: Pattern,
    consequent: Pattern,
    params: dict[str, Any],
    response: dict[str, Any],
    expected: ImpliesResult,
) -> None:
    # Given
    rpc_client.assume_response(response)

    # When
    actual = kore_client.implies(antecedent, consequent)

    # Then
    rpc_client.assert_request('implies', **params)
    assert actual == expected


SIMPLIFY_TEST_DATA: Final = (
    (
        And(INT, int_top, int_top),
        {'state': kore(And(INT, int_top, int_top))},
        {'state': kore(int_top)},
        int_top,
    ),
)


@pytest.mark.parametrize('pattern,params,response,expected', SIMPLIFY_TEST_DATA, ids=count())
def test_simplify(
    kore_client: KoreClient,
    rpc_client: MockClient,
    pattern: Pattern,
    params: dict[str, Any],
    response: dict[str, Any],
    expected: Pattern,
) -> None:
    # Given
    rpc_client.assume_response(response)

    # When
    actual, _logs = kore_client.simplify(pattern)

    # Then
    rpc_client.assert_request('simplify', **params)
    assert actual == expected


GET_MODEL_TEST_DATA: Final = (
    (
        int_dv(0),
        None,
        {'state': kore(int_dv(0))},
        {'satisfiable': 'Unknown'},
        UnknownResult(),
    ),
    (
        int_dv(1),
        'TEST-MODULE',
        {'state': kore(int_dv(1)), 'module': 'TEST-MODULE'},
        {'satisfiable': 'Unknown'},
        UnknownResult(),
    ),
    (
        int_dv(2),
        None,
        {'state': kore(int_dv(2))},
        {'satisfiable': 'Unsat'},
        UnsatResult(),
    ),
    (
        int_dv(3),
        None,
        {'state': kore(int_dv(3))},
        {'satisfiable': 'Sat', 'substitution': kore(int_dv(0))},
        SatResult(int_dv(0)),
    ),
)


@pytest.mark.parametrize('pattern,module_name,params,response,expected', GET_MODEL_TEST_DATA, ids=count())
def test_get_model(
    kore_client: KoreClient,
    rpc_client: MockClient,
    pattern: Pattern,
    module_name: str | None,
    params: dict[str, Any],
    response: dict[str, Any],
    expected: Pattern,
) -> None:
    # Given
    rpc_client.assume_response(response)

    # When
    actual = kore_client.get_model(pattern, module_name)

    # Then
    rpc_client.assert_request('get-model', **params)
    assert actual == expected


ADD_MODULE_TEST_DATA: Final = (
    (
        Module('HELLO'),
        {'module': 'module HELLO\nendmodule []'},
    ),
)


@pytest.mark.parametrize('module,params', ADD_MODULE_TEST_DATA, ids=count())
def test_add_module(
    kore_client: KoreClient,
    rpc_client: MockClient,
    module: Module,
    params: dict[str, Any],
) -> None:
    # Given
    rpc_client.assume_response([])

    # When
    kore_client.add_module(module)

    # Then
    rpc_client.assert_request('add-module', **params)


class MockTransport:
    mock: Mock

    def __init__(self, mock: Mock):
        self.mock = mock

    def assume_response(self, response: str) -> None:
        self.mock.request.return_value = response


@pytest.fixture
def transport_mock_class() -> Iterator[Mock]:
    patcher = patch('pyk.kore.rpc.SingleSocketTransport', spec=True)
    yield patcher.start()
    patcher.stop()


@pytest.fixture
def transport_mock(transport_mock_class: Mock) -> Mock:
    transport_mock = transport_mock_class.return_value
    assert isinstance(transport_mock, SingleSocketTransport)
    return transport_mock  # type: ignore


@pytest.fixture
def transport(transport_mock: Mock) -> MockTransport:
    return MockTransport(transport_mock)


@pytest.fixture
def transport_kore_client(transport_mock: Mock, transport_mock_class: Mock) -> Iterator[KoreClient]:  # noqa: N803
    client = KoreClient('localhost', 3000)
    transport_mock_class.assert_called_with('localhost', 3000, timeout=None)
    assert client._client._transport == transport_mock
    yield client
    client.close()
    transport_mock.close.assert_called()


EXCEPTION_TEST_DATA: Final = (
    (App('IntAdd', (), (int_dv(1), int_dv(1))), '', KoreClientError('Parse error: Empty response received', -32700)),
)


@pytest.mark.parametrize('pattern,response,expected', EXCEPTION_TEST_DATA, ids=count())
def test_exceptions(
    transport_kore_client: KoreClient,
    transport: MockTransport,
    pattern: Pattern,
    response: str,
    expected: Exception,
) -> None:
    # Given
    transport.assume_response(response)

    with pytest.raises(Exception) as client_err:
        # When
        transport_kore_client.execute(pattern)

    # Then
    assert client_err.value == expected
