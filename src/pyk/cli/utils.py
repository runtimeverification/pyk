from __future__ import annotations

import logging
from pathlib import Path
from typing import TYPE_CHECKING

from ..utils import check_dir_path, check_file_path, check_relative_path

if TYPE_CHECKING:
    from collections.abc import Callable
    from typing import TypeVar

    from ..kcfg.kcfg import NodeIdLike

    T1 = TypeVar('T1')
    T2 = TypeVar('T2')


def loglevel(level: str) -> int:
    res = getattr(logging, level.upper(), None)

    if isinstance(res, int):
        return res

    try:
        return int(level)
    except ValueError:
        raise ValueError('Invalid log level: {level}') from None


def dir_path(s: str | Path) -> Path:
    path = Path(s)
    check_dir_path(path)
    return path


def file_path(s: str) -> Path:
    path = Path(s)
    check_file_path(path)
    return path


def relative_path(path: str | Path) -> Path:
    path = Path(path)
    check_relative_path(path)
    return path


def list_of(elem_type: Callable[[str], T1], delim: str = ';') -> Callable[[str], list[T1]]:
    def parse(s: str) -> list[T1]:
        return [elem_type(elem) for elem in s.split(delim)]

    return parse


def node_id_like(s: str) -> NodeIdLike:
    try:
        return int(s)
    except ValueError:
        return s


def arg_pair_of(
    fst_type: Callable[[str], T1], snd_type: Callable[[str], T2], delim: str = ','
) -> Callable[[str], tuple[T1, T2]]:
    def parse(s: str) -> tuple[T1, T2]:
        elems = s.split(delim)
        length = len(elems)
        if length != 2:
            raise ValueError(f'Expected 2 elements, found {length}')

        return fst_type(elems[0]), snd_type(elems[1])

    return parse
