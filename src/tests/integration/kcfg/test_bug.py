from __future__ import annotations

from typing import TYPE_CHECKING

from pyk.kast.inner import KApply, KLabel, KSort
from pyk.kast.manip import split_config_and_constraints

from ..utils import JSON_DATA

if TYPE_CHECKING:
    from typing import Union

    STATE = Union[tuple[str, str], tuple[str, str, str]]


BUG_FILE = JSON_DATA / 'test-split-crash.json'

def test_split_conf() -> None:
    kast = KApply(
        label=KLabel(name='#And', params=(KSort(name='GeneratedTopCell'),)),
        args=(
            KApply(label=KLabel(name='#Bottom', params=(KSort(name='GeneratedTopCell'),)), args=()),
            KApply(label=KLabel(name='#Bottom', params=(KSort(name='GeneratedTopCell'),)), args=()),
        ),
    )
    config, constraints = split_config_and_constraints(kast)
