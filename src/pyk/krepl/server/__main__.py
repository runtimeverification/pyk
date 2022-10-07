import logging
from argparse import ArgumentParser
from typing import Final

from pyk.cli_utils import loglevel

_LOG_FORMAT: Final = '%(levelname)s %(asctime)s %(name)s - %(message)s'
_LOGGER: Final = logging.getLogger(__name__)


def main() -> None:
    args = argument_parser().parse_args()
    logging.basicConfig(level=args.loglevel, format=_LOG_FORMAT)
    _LOGGER.info('Server started')


def argument_parser() -> ArgumentParser:
    parser = ArgumentParser(description='K-REPL Server')
    parser.add_argument('-l', '--loglevel', type=loglevel, default=logging.INFO, metavar='LEVEL', help='log level')
    return parser


if __name__ == '__main__':
    main()
