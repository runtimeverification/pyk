from ..kast import KToken
from .sorts import STRING


def stringToken(s: str) -> KToken:  # noqa: N802
    return KToken(f'"{s}"', STRING)
