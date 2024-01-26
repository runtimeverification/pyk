from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from pyk.testing import KProveTest

from ..utils import K_FILES

if TYPE_CHECKING:
    from typing import Iterable

    from pyk.ktool.kprove import KProve


GET_CLAIMS_SPEC_DATA: Iterable[tuple[str, list[str], dict[str, list[str]] | None]] = (
    (
        'simple-dep-in-submodule-fail',
        ['dep-1.1'],
        None,
    ),
    (
        'simple-dep-in-submodule-pass',
        ['MULTI-CLAIM-SPEC-DEPENDENCY-1.dep-1.1'],
        {'MULTI-CLAIM-SPEC-DEPENDENCY-1.dep-1.1': []},
    ),
    (
        'simple-dep-in-submodule-fail-dep',
        ['MULTI-CLAIM-SPEC-DEPENDENCY-2.dep-2.2'],
        None,
    ),
    (
        'no-dep-name-unqualified',
        ['dep'],
        {'MULTI-CLAIM-SPEC.dep': []},
    ),
    (
        'no-dep-name-qualified',
        ['MULTI-CLAIM-SPEC.dep'],
        {'MULTI-CLAIM-SPEC.dep': []},
    ),
    (
        'two-deps-one-nested',
        ['MULTI-CLAIM-SPEC.main.1'],
        {
            'MULTI-CLAIM-SPEC.main.1': ['MULTI-CLAIM-SPEC.dep', 'MULTI-CLAIM-DEPENDENCY-1.dep-1.1'],
            'MULTI-CLAIM-SPEC.dep': [],
            'MULTI-CLAIM-DEPENDENCY-1.dep-1.1': [],
        },
    ),
    (
        'bad-unqualified-main-dep',
        ['MULTI-CLAIM-SPEC.main.4'],
        None,
    ),
)


class TestGetClaims(KProveTest):
    KOMPILE_MAIN_FILE = K_FILES / 'multi-claim-spec.k'
    KOMPILE_ARGS = {'main_module': 'MULTI-CLAIM'}
    SPEC_MODULE_NAME = 'MULTI-CLAIM-SPEC'

    @pytest.mark.parametrize(
        'test_id,include_labels,expected_graph',
        GET_CLAIMS_SPEC_DATA,
        ids=[test_id for test_id, *_ in GET_CLAIMS_SPEC_DATA],
    )
    def test_get_claims(
        self, kprove: KProve, test_id: str, include_labels: list[str], expected_graph: dict[str, list[str]] | None
    ) -> None:
        if expected_graph is None:
            with pytest.raises(ValueError):
                all_claims = kprove.get_claims(
                    self.KOMPILE_MAIN_FILE, self.SPEC_MODULE_NAME, claim_labels=include_labels
                )

        else:
            all_claims = kprove.get_claims(self.KOMPILE_MAIN_FILE, self.SPEC_MODULE_NAME, claim_labels=include_labels)
            actual_graph: dict[str, list[str]] = {claim.label: claim.dependencies for claim in all_claims}

            assert set(expected_graph.keys()) == set(actual_graph.keys())
            for claim_label, deps in expected_graph.items():
                assert set(deps) == set(actual_graph[claim_label])
