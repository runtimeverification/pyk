from __future__ import annotations

import fnmatch
import logging
from argparse import ArgumentParser
from typing import TYPE_CHECKING, Any

from pyk.cli.args import LoggingOptions
from pyk.cli.utils import loglevel

from ..kdist import kdist, target_ids

if TYPE_CHECKING:
    from argparse import Namespace, _SubParsersAction
    from typing import Final


_LOGGER: Final = logging.getLogger(__name__)
_LOG_FORMAT: Final = '%(levelname)s %(asctime)s %(name)s - %(message)s'


def main() -> None:
    args = _parse_arguments()

    logging.basicConfig(level=loglevel(args), format=_LOG_FORMAT)

    if args.command == 'build':
        _exec_build(**vars(args))

    elif args.command == 'clean':
        _exec_clean(args.target)

    elif args.command == 'which':
        _exec_which(args.target)

    elif args.command == 'list':
        _exec_list()

    else:
        raise AssertionError()


def _exec_build(
    command: str,
    targets: list[str],
    args: list[str],
    jobs: int,
    force: bool,
    verbose: bool,
    debug: bool,
) -> None:
    kdist.build(
        target_ids=_process_targets(targets),
        args=_process_args(args),
        jobs=jobs,
        force=force,
        verbose=verbose or debug,
    )


def _process_targets(targets: list[str]) -> list[str]:
    all_target_fqns = [target_id.full_name for target_id in target_ids()]
    res = []
    for pattern in targets:
        matches = fnmatch.filter(all_target_fqns, pattern)
        if not matches:
            raise ValueError(f'No target matches pattern: {pattern!r}')
        res += matches
    return res


def _process_args(args: list[str]) -> dict[str, str]:
    res: dict[str, str] = {}
    for arg in args:
        segments = arg.split('=')
        if len(segments) < 2:
            raise ValueError(f"Expected assignment of the form 'arg=value', got: {arg!r}")
        key, *values = segments
        res[key] = '='.join(values)
    return res


def _exec_clean(target: str | None) -> None:
    res = kdist.clean(target)
    print(res)


def _exec_which(target: str | None) -> None:
    res = kdist.which(target)
    print(res)


def _exec_list() -> None:
    targets_by_plugin: dict[str, list[str]] = {}
    for plugin_name, target_name in target_ids():
        targets = targets_by_plugin.get(plugin_name, [])
        targets.append(target_name)
        targets_by_plugin[plugin_name] = targets

    for plugin_name in targets_by_plugin:
        print(plugin_name)
        for target_name in targets_by_plugin[plugin_name]:
            print(f'* {target_name}')


class KDistBuildOptions(LoggingOptions):
    targets: list[str]
    force: bool
    jobs: int

    @staticmethod
    def defaults() -> dict[str, Any]:
        return {
            'force': False,
            'jobs': 1,
        }

    @staticmethod
    def parser(base: _SubParsersAction) -> _SubParsersAction:
        base.add_parser(
            'build',
            help='build targets',
            parents=[KDistBuildOptions.all_args()],
        )
        return base

    @staticmethod
    def update_args(parser: ArgumentParser) -> None:
        parser.add_argument('targets', metavar='TARGET', nargs='*', default='*', help='target to build')
        parser.add_argument(
            '-a',
            '--arg',
            dest='args',
            metavar='ARG',
            action='append',
            default=[],
            help='build with argument',
        )
        parser.add_argument('-f', '--force', action='store_true', default=None, help='force build')
        parser.add_argument('-j', '--jobs', metavar='N', type=int, default=None, help='maximal number of build jobs')


class KDistCleanOptions(LoggingOptions):
    target: str

    @staticmethod
    def parser(base: _SubParsersAction) -> _SubParsersAction:
        base.add_parser(
            'clean',
            help='clean targets',
            parents=[KDistCleanOptions.all_args()],
        )
        return base

    @staticmethod
    def update_args(parser: ArgumentParser) -> None:
        parser.add_argument(
            'target',
            metavar='TARGET',
            nargs='?',
            help='target to clean',
        )


class KDistWhichOptions(LoggingOptions):
    target: str

    @staticmethod
    def parser(base: _SubParsersAction) -> _SubParsersAction:
        base.add_parser(
            'which',
            help='print target location',
            parents=[KDistCleanOptions.all_args()],
        )
        return base

    @staticmethod
    def update_args(parser: ArgumentParser) -> None:
        parser.add_argument(
            'target',
            metavar='TARGET',
            nargs='?',
            help='target to print directory for',
        )


class KDistListOptions(LoggingOptions):
    @staticmethod
    def parser(base: _SubParsersAction) -> _SubParsersAction:
        base.add_parser(
            'list',
            help='print list of available targets',
            parents=[KDistCleanOptions.all_args()],
        )
        return base


def _parse_arguments() -> Namespace:
    def add_target_arg(parser: ArgumentParser, help_text: str) -> None:
        parser.add_argument(
            'target',
            metavar='TARGET',
            nargs='?',
            help=help_text,
        )

    parser = ArgumentParser(prog='kdist', parents=[LoggingOptions.all_args()])
    command_parser = parser.add_subparsers(dest='command', required=True)

    command_parser = KDistBuildOptions.parser(command_parser)
    command_parser = KDistCleanOptions.parser(command_parser)
    command_parser = KDistWhichOptions.parser(command_parser)
    command_parser = KDistListOptions.parser(command_parser)

    return parser.parse_args()


if __name__ == '__main__':
    main()
