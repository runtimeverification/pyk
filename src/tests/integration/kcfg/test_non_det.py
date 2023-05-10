from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

import pytest

from pyk.kcfg import KCFG
from pyk.proof import APRProof, APRProver, ProofStatus

from ..utils import K_FILES, KCFGExploreTest

if TYPE_CHECKING:
    from collections.abc import Iterable

    from pyk.kcfg import KCFGExplore
    from pyk.ktool.kprove import KProve


APR_PROVE_TEST_DATA: Iterable[tuple[str, Path, str, str, int | None, int | None, Iterable[str]]] = (
    ('test-nondet', K_FILES / 'non-det-spec.k', 'NON-DET-SPEC', 'non-det', 8, 1, []),
)


class TestImpProof(KCFGExploreTest):
    KOMPILE_MAIN_FILE = K_FILES / 'non-det.k'

    @pytest.mark.parametrize(
        'test_id,spec_file,spec_module,claim_id,max_iterations,max_depth,terminal_rules',
        APR_PROVE_TEST_DATA,
        ids=[test_id for test_id, *_ in APR_PROVE_TEST_DATA],
    )
    def test_all_path_reachability_prove(
        self,
        kprove: KProve,
        kcfg_explore: KCFGExplore,
        test_id: str,
        spec_file: str,
        spec_module: str,
        claim_id: str,
        max_iterations: int,
        max_depth: int,
        terminal_rules: Iterable[str],
    ) -> None:
        claims = kprove.get_claims(
            Path(spec_file), spec_module_name=spec_module, claim_labels=[f'{spec_module}.{claim_id}']
        )
        assert len(claims) == 1

        kcfg = KCFG.from_claim(kprove.definition, claims[0])
        proof = APRProof(f'{spec_module}.{claim_id}', kcfg, logs={})
        prover = APRProver(proof, kcfg_explore=kcfg_explore)
        kcfg = prover.advance_proof(
            max_iterations=max_iterations,
            execute_depth=max_depth,
            terminal_rules=terminal_rules,
        )

        # We expect this graph, in which all splits are non-deterministic:
        #
        #      id1a - final1 - success
        #     /
        #    /      id1b1 - final2 - success
        # id1      /
        #    \id1b
        #          \
        #           id1b2 - final3 - success

        id1 = kcfg.get_unique_init().id

        def assert_nd_branch(id: str) -> tuple[str, str]:
            assert len(kcfg.successors(source_id=id)) == 1
            ndbranches = kcfg.ndbranches(source_id=id)
            assert len(ndbranches) == 1
            assert len(ndbranches[0].target_ids) == 2
            ida, idb = ndbranches[0].target_ids
            return ida, idb

        def assert_edge(id: str) -> str:
            assert len(kcfg.successors(source_id=id)) == 1
            edges = kcfg.edges(source_id=id)
            assert len(edges) == 1
            return edges[0].target.id

        id1a, id1b = assert_nd_branch(id1)
        if len(kcfg.ndbranches(source_id=id1a)) > len(kcfg.ndbranches(source_id=id1b)):
            (tmp, id1a) = (id1a, id1b)
            id1b = tmp
        id1b1, id1b2 = assert_nd_branch(id1b)

        assert_edge(id1a)
        assert_edge(id1b1)
        assert_edge(id1b2)

        assert proof.status == ProofStatus.PASSED
