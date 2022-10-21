from contextlib import closing
from socket import AF_INET, SO_REUSEADDR, SOCK_STREAM, SOL_SOCKET, socket


# Based on: https://stackoverflow.com/a/45690594
# Note: has an obvious race condition, use only for testing
def free_port_on_host(host: str = 'localhost') -> int:
    with closing(socket(AF_INET, SOCK_STREAM)) as sock:
        sock.bind((host, 0))
        sock.setsockopt(SOL_SOCKET, SO_REUSEADDR, 1)
        _, port = sock.getsockname()
    return port
