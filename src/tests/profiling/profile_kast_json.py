from __future__ import annotations

import json
from typing import TYPE_CHECKING

import pytest

from pyk.kast import kast_term

from .utils import TEST_DATA_DIR

if TYPE_CHECKING:
    from pyk.kast import KAst
    from pyk.testing import Profiler


KAST_JSON_TEST_DATA: list[tuple[str, str]] = [
    ('kast-term', 'kast.json'),
    ('compiled-defn', 'compiled.json'),
]


@pytest.mark.parametrize('test_id,file_name', KAST_JSON_TEST_DATA, ids=[test_id for test_id, *_ in KAST_JSON_TEST_DATA])
def test_kast_json(profile: Profiler, test_id: str, file_name: str) -> None:
    json_file = TEST_DATA_DIR / file_name
    with profile('json-load.prof', sort_keys=('cumtime',), limit=20):
        with json_file.open() as f:
            json_data = json.load(f)

    with profile('json-to-kast.prof', sort_keys=('cumtime',), limit=20):
        kast: KAst = kast_term(json_data)

    with profile('kast-to-json.prof', sort_keys=('cumtime',), limit=20):
        kast.to_dict()
