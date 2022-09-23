import shutil
from argparse import ArgumentParser
from pathlib import Path
from typing import Any

from ..cli_utils import dir_path
from .config import KBUILD_DIR
from .package import RootPackage
from .project import Project


def main() -> None:
    args = vars(_argument_parser().parse_args())
    command = args['command']

    if command == 'clean':
        return do_clean(**args)

    if command == 'install':
        return do_install(**args)

    if command == 'kompile':
        return do_kompile(**args)

    raise AssertionError()


def _argument_parser() -> ArgumentParser:
    parser = ArgumentParser(description='Dependency management for the K Framework')
    parser.add_argument(
        '-d', '--dir', dest='start_dir', metavar='DIR', type=dir_path, default=Path('.'), help='run from DIR'
    )

    command_parser = parser.add_subparsers(dest='command', metavar='COMMAND', required=True)

    command_parser.add_parser('clean', help='clean build cache')

    command_parser.add_parser('install', help='install project')

    kompile_parser = command_parser.add_parser('kompile', help='kompile target')
    kompile_parser.add_argument('target_name', metavar='TARGET', help='target to build')

    return parser


def do_clean(**kwargs: Any) -> None:
    shutil.rmtree(KBUILD_DIR, ignore_errors=True)


def do_install(start_dir: Path, **kwargs: Any) -> None:
    project = Project.load_from_dir(start_dir)
    package = RootPackage(project)
    installed_files = package.install()
    for installed_file in installed_files:
        print(installed_file.relative_to(KBUILD_DIR))


def do_kompile(start_dir: Path, target_name: str, **kwargs: Any) -> None:
    project = Project.load_from_dir(start_dir)
    package = RootPackage(project)
    definition_dir = package.kompile(target_name)
    print(definition_dir)


if __name__ == '__main__':
    main()
