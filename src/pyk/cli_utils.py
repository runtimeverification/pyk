import logging
import subprocess
import sys
import tarfile
import time
from datetime import datetime
from logging import Logger
from pathlib import Path
from subprocess import CalledProcessError, CompletedProcess
from tempfile import NamedTemporaryFile
from typing import Dict, Final, Iterable, Mapping, Optional, Union

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
        raise ValueError(f'Path does not exist: {path}')
    elif not path.is_dir():
        raise ValueError(f'Path is not a directory: {path}')


def dir_path(s: Union[str, Path]) -> Path:
    path = Path(s)
    check_dir_path(path)
    return path


def ensure_dir_path(path: Union[str, Path]) -> Path:
    path = Path(path)
    if not path.exists():
        _LOGGER.info(f'Making directory: {path}')
        path.mkdir(parents=True)
    else:
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


def relative_path(path: Union[str, Path]) -> Path:
    path = Path(path)
    check_relative_path(path)
    return path


def abs_or_rel_to(path: Path, base: Path) -> Path:
    if path.is_absolute():
        return path
    return base / path


# Implementation because of outdated Python versions: https://github.com/python/cpython/blob/1de4395f62bb140563761ef5cbdf46accef3c550/Lib/pathlib.py#L554
def is_relative_to(_self: Path, other: Path) -> bool:
    return _self == other or other in _self.parents


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


class BugReport:
    _bug_report: Path
    _command_id: int
    _defn_id: int
    _file_remap: Dict[str, str]

    def __init__(self, bug_report: Path) -> None:
        self._bug_report = bug_report.with_suffix('.tar')
        self._command_id = 0
        self._defn_id = 0
        self._file_remap = {}
        if self._bug_report.exists():
            _LOGGER.warning(f'Bug report exists, removing: {self._bug_report}')
            self._bug_report.unlink()

    def add_file(self, finput: Path, arcname: Path) -> None:
        if str(finput) not in self._file_remap:
            self._file_remap[str(finput)] = str(arcname)
            with tarfile.open(self._bug_report, 'a') as tar:
                tar.add(finput, arcname=arcname)
                _LOGGER.info(f'Added file to bug report {self._bug_report}:{arcname}: {finput}')

    def add_file_contents(self, input: str, arcname: Path) -> None:
        with NamedTemporaryFile('w') as ntf:
            ntf.write(input)
            ntf.flush()
            self.add_file(Path(ntf.name), arcname)

    def add_command(self, args: Iterable[str]) -> None:
        def _remap_arg(_a: str) -> str:
            if _a in self._file_remap:
                return self._file_remap[_a]
            _a_path = Path(_a)
            for _f in self._file_remap:
                _f_path = Path(_f)
                if is_relative_to(_a_path, _f_path):
                    return str(Path(self._file_remap[_f]) / _a_path.relative_to(_f_path))
            return _a

        remapped_args = [_remap_arg(a) for a in args]
        arcname = Path(f'commands/{self._command_id:03}.sh')
        shebang = '#!/usr/bin/env bash\nset -euxo pipefail\n'
        self.add_file_contents(shebang + ' '.join(remapped_args) + '\n', arcname)
        self._command_id += 1

    def add_definition(self, defn_path: Path) -> None:
        if str(defn_path) not in self._file_remap:
            arcname = Path('kompiled') / f'{self._defn_id:03}_defn'
            self.add_file(defn_path, arcname)
            self._defn_id += 1
