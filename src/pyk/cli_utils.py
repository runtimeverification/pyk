import logging
import subprocess
import sys
import time
from datetime import datetime
from logging import Logger
from pathlib import Path
from subprocess import CalledProcessError, CompletedProcess
from typing import Final, Iterable, Mapping, Optional, Union

_LOGGER: Final = logging.getLogger(__name__)


def loglevel(level: str) -> int:
    res = getattr(logging, level.upper(), None)

    if isinstance(res, int):
        return res

    try:
        return int(level)
    except ValueError:
        raise ValueError('Invalid log level: {level}') from None


def check_dir_path(path: Path) -> None:
    path = path.resolve()
    if not path.exists():
        raise ValueError(f'Directory does not exist: {path}')
    if not path.is_dir():
        raise ValueError(f'Path is not a directory: {path}')


def dir_path(s: str) -> Path:
    path = Path(s)
    check_dir_path(path)
    return path


def check_file_path(path: Path) -> None:
    path = path.resolve()
    if not path.exists():
        raise ValueError(f'File does not exist: {path}')
    if not path.is_file():
        raise ValueError(f'Path is not a file: {path}')


def file_path(s: str) -> Path:
    path = Path(s)
    check_file_path(path)
    return path


def check_absolute_path(path: Path) -> None:
    if not path.is_absolute():
        raise ValueError(f'Path is not absolute: {path}')


def check_relative_path(path: Path) -> None:
    if path.is_absolute():
        raise ValueError(f'Path is not relative: {path}')


def abs_or_rel_to(path: Path, base: Path) -> Path:
    if path.is_absolute():
        return path
    return base / path


def run_process(
    args: Union[str, Iterable[str]],
    *,
    check: bool = True,
    input: Optional[str] = None,
    pipe_stdout: bool = True,
    pipe_stderr: bool = False,
    cwd: Optional[Union[str, Path]] = None,
    env: Optional[Mapping[str, str]] = None,
    logger: Optional[Logger] = None,
    profile: bool = False,
) -> CompletedProcess:
    if cwd is not None:
        cwd = Path(cwd)
        check_dir_path(cwd)

    if type(args) is str:
        command = args
    else:
        args = tuple(args)
        command = ' '.join(args)

    if not logger:
        logger = _LOGGER

    stdout = subprocess.PIPE if pipe_stdout else None
    stderr = subprocess.PIPE if pipe_stderr else None

    logger.info(f'Running: {command}')
    try:
        if profile:
            start_time = time.time()
        res = subprocess.run(args, input=input, cwd=cwd, env=env, stdout=stdout, stderr=stderr, check=check, text=True)
    except CalledProcessError as err:
        logger.info(f'Completed with status {err.returncode}: {command}')
        raise

    if profile:
        stop_time = time.time()
        delta_time = stop_time - start_time
        logger.info(f'Timing [{delta_time:.3f}]: {command}')

    logger.info(f'Completed: {command}')
    return res


def gen_file_timestamp(comment: str = '//') -> str:
    return comment + ' This file generated by: ' + sys.argv[0] + '\n' + comment + ' ' + str(datetime.now()) + '\n'
