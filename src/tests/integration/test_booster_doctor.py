from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from pyk.booster_doctor.__main__ import build_fallback_claim
from pyk.kast.inner import KApply, KSort, KToken
from pyk.kast.outer import KClaim
from pyk.konvert import _kast_to_kore
from pyk.kore.rpc import LogFallback
from pyk.testing import KPrintTest

from .utils import K_FILES

if TYPE_CHECKING:
    from pyk.booster_doctor.__main__ import KClaimWithComment
    from pyk.ktool.kprint import KPrint

FALLBACK_CLAIM_TEST_DATA = [
    (
        'empty-fallback-log',
        LogFallback.from_dict(
            {'origin': 'proxy', 'reason': 'UNKNOWN', 'fallback-rule-id': 'UNKNOWN', 'recovery-depth': 1}
        ),
        None,
    ),
    (
        'no-original-term-fallback-log',
        LogFallback.from_dict(
            {
                'origin': 'proxy',
                'reason': 'UNKNOWN',
                'fallback-rule-id': 'UNKNOWN',
                'recovery-depth': 1,
                'rewritten-term': {
                    'format': 'KORE',
                    'version': 1,
                    'term': _kast_to_kore(KApply('<generatedTopCell>', KToken('1', KSort('Int')))).dict,
                },
            }
        ),
        None,
    ),
    (
        'no-rewritten-term-fallback-log',
        LogFallback.from_dict(
            {
                'origin': 'proxy',
                'reason': 'UNKNOWN',
                'fallback-rule-id': 'UNKNOWN',
                'recovery-depth': 1,
                'original-term': {
                    'format': 'KORE',
                    'version': 1,
                    'term': _kast_to_kore(KApply('<generatedTopCell>', KToken('1', KSort('Int')))).dict,
                },
            }
        ),
        None,
    ),
    (
        'trivial-fallback-log',
        LogFallback.from_dict(
            {
                'origin': 'proxy',
                'reason': 'UNKNOWN',
                'fallback-rule-id': 'UNKNOWN',
                'recovery-depth': 1,
                'original-term': {
                    'format': 'KORE',
                    'version': 1,
                    'term': _kast_to_kore(KApply('<generatedTopCell>', KToken('1', KSort('Int')))).dict,
                },
                'rewritten-term': {
                    'format': 'KORE',
                    'version': 1,
                    'term': _kast_to_kore(KApply('<generatedTopCell>', KToken('1', KSort('Int')))).dict,
                },
            }
        ),
        KClaim.from_dict(
            {
                'node': 'KClaim',
                'body': {
                    'node': 'KApply',
                    'label': {'node': 'KLabel', 'name': '<generatedTopCell>', 'params': []},
                    'args': [{'node': 'KToken', 'token': '1', 'sort': {'node': 'KSort', 'name': 'Int'}}],
                    'arity': 1,
                    'variable': False,
                },
                'requires': {'node': 'KToken', 'token': 'true', 'sort': {'node': 'KSort', 'name': 'Bool'}},
                'ensures': {'node': 'KToken', 'token': 'true', 'sort': {'node': 'KSort', 'name': 'Bool'}},
                'att': {'node': 'KAtt', 'att': {'label': 'booster-fallback'}},
            }
        ),
    ),
]


class TestBuildFallbackClaim(KPrintTest):
    KOMPILE_MAIN_FILE = K_FILES / 'mini-kevm.k'

    @pytest.mark.parametrize(
        'test_id,log_entry,expected',
        FALLBACK_CLAIM_TEST_DATA,
        ids=[test_id for test_id, *_ in FALLBACK_CLAIM_TEST_DATA],
    )
    def test_build_fallback_claim(
        self, kprint: KPrint, test_id: str, log_entry: LogFallback, expected: KClaimWithComment | None
    ) -> None:
        assert build_fallback_claim(kprint, log_entry) == expected
