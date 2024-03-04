from __future__ import annotations

import logging
import sys
from typing import TYPE_CHECKING

from .cli.args import (
    KEVMCLI,
    CoverageOptions,
    GraphImportsOptions,
    JsonToKoreOptions,
    KoreToJsonOptions,
    PrintOptions,
    ProveOptions,
    RPCKastOptions,
    RPCPrintOptions,
)
from .cli.utils import LOG_FORMAT, loglevel

if TYPE_CHECKING:
    from typing import Final


_LOGGER: Final = logging.getLogger(__name__)


def main() -> None:
    # KAST terms can end up nested quite deeply, because of the various assoc operators (eg. _Map_, _Set_, ...).
    # Most pyk operations are defined recursively, meaning you get a callstack the same depth as the term.
    # This change makes it so that in most cases, by default, pyk doesn't run out of stack space.
    sys.setrecursionlimit(10**7)

    cli = KEVMCLI(
        [
            CoverageOptions,
            GraphImportsOptions,
            JsonToKoreOptions,
            KoreToJsonOptions,
            PrintOptions,
            ProveOptions,
            RPCKastOptions,
            RPCPrintOptions,
        ]
    )

    cli_parser = cli.create_argument_parser()
    args = cli_parser.parse_args()

    command = cli.generate_command({key: val for (key, val) in vars(args).items() if val is not None})
    command.exec()

    logging.basicConfig(level=loglevel(command), format=LOG_FORMAT)


if __name__ == '__main__':
    main()
