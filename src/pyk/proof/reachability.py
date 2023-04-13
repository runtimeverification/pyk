from __future__ import annotations

import json
import logging
from typing import TYPE_CHECKING

from ..kcfg import KCFG
from ..prelude.ml import mlAnd
from ..utils import hash_str, shorten_hashes
from .proof import Proof, ProofStatus

if TYPE_CHECKING:
    from collections.abc import Callable, Iterable, Mapping
    from pathlib import Path
    from typing import Any, Final, TypeVar

    from ..cterm import CTerm
    from ..kast.inner import KInner
    from ..kcfg import KCFGExplore
    from ..ktool.kprint import KPrint

    T = TypeVar('T', bound='Proof')

_LOGGER: Final = logging.getLogger(__name__)


class AGProof(Proof):
    kcfg: KCFG

    def __init__(self, id: str, kcfg: KCFG, proof_dir: Path | None = None):
        super().__init__(id, proof_dir=proof_dir)
        self.kcfg = kcfg

    @staticmethod
    def read_proof(id: str, proof_dir: Path) -> Proof:
        proof_path = proof_dir / f'{hash_str(id)}.json'
        if AGProof.proof_exists(id, proof_dir):
            proof_dict = json.loads(proof_path.read_text())
            _LOGGER.info(f'Reading AGProof from file {id}: {proof_path}')
            return AGProof.from_dict(proof_dict, proof_dir=proof_dir)
        raise ValueError(f'Could not load AGProof from file {id}: {proof_path}')

    @property
    def status(self) -> ProofStatus:
        if len(self.kcfg.stuck) > 0:
            return ProofStatus.FAILED
        elif len(self.kcfg.frontier) > 0:
            return ProofStatus.PENDING
        else:
            return ProofStatus.PASSED

    @classmethod
    def from_dict(cls: type[AGProof], dct: Mapping[str, Any], proof_dir: Path | None = None) -> AGProof:
        cfg = KCFG.from_dict(dct['cfg'])
        id = dct['id']
        return AGProof(id, cfg, proof_dir=proof_dir)

    @property
    def dict(self) -> dict[str, Any]:
        return {'type': 'AGProof', 'id': self.id, 'cfg': self.kcfg.to_dict()}

    def summary(self) -> Iterable[str]:
        return [
            f'AGProof: {self.id}',
            f'    nodes: {len(self.kcfg.nodes)}',
            f'    frontier: {len(self.kcfg.frontier)}',
            f'    stuck: {len(self.kcfg.stuck)}',
        ]

    def pretty(
        self,
        kprint: KPrint,
        minimize: bool = True,
        node_printer: Callable[[CTerm], Iterable[str]] | None = None,
        omit_node_hash: bool = False,
        **kwargs: Any,
    ) -> Iterable[str]:
        return self.kcfg.pretty(kprint, minimize=minimize, node_printer=node_printer, omit_node_hash=omit_node_hash)


class AGProver:
    proof: AGProof

    def __init__(self, proof: AGProof) -> None:
        self.proof = proof

    def _check_subsumption(
        self,
        kcfg_explore: KCFGExplore,
        curr_node: KCFG.Node,
        is_terminal: Callable[[CTerm], bool] | None = None,
        implication_every_block: bool = True,
    ) -> bool:
        if implication_every_block or (is_terminal is not None and is_terminal(curr_node.cterm)):
            target_node = self.proof.kcfg.get_unique_target()
            _LOGGER.info(
                f'Checking subsumption into target state {self.proof.id}: {shorten_hashes((curr_node.id, target_node.id))}'
            )
            csubst = kcfg_explore.cterm_implies(curr_node.cterm, target_node.cterm)
            if csubst is not None:
                self.proof.kcfg.create_cover(curr_node.id, target_node.id, csubst=csubst)
                _LOGGER.info(
                    f'Subsumed into target node {self.proof.id}: {shorten_hashes((curr_node.id, target_node.id))}'
                )
                return True
        return False

    def _check_terminal(self, curr_node: KCFG.Node, is_terminal: Callable[[CTerm], bool] | None = None) -> bool:
        if is_terminal is not None:
            _LOGGER.info(f'Checking terminal {self.proof.id}: {shorten_hashes(curr_node.id)}')
            if is_terminal(curr_node.cterm):
                _LOGGER.info(f'Terminal node {self.proof.id}: {shorten_hashes(curr_node.id)}.')
                self.proof.kcfg.add_expanded(curr_node.id)
                return True
        return False

    def advance_proof(
        self,
        kcfg_explore: KCFGExplore,
        is_terminal: Callable[[CTerm], bool] | None = None,
        extract_branches: Callable[[CTerm], Iterable[KInner]] | None = None,
        max_iterations: int | None = None,
        execute_depth: int | None = None,
        cut_point_rules: Iterable[str] = (),
        terminal_rules: Iterable[str] = (),
        implication_every_block: bool = True,
    ) -> KCFG:
        iterations = 0

        while self.proof.kcfg.frontier:
            self.proof.write_proof()

            if max_iterations is not None and max_iterations <= iterations:
                _LOGGER.warning(f'Reached iteration bound {self.proof.id}: {max_iterations}')
                break
            iterations += 1
            curr_node = self.proof.kcfg.frontier[0]

            if self._check_subsumption(
                kcfg_explore, curr_node, is_terminal=is_terminal, implication_every_block=implication_every_block
            ):
                continue

            if self._check_terminal(curr_node, is_terminal=is_terminal):
                continue

            self.proof.kcfg.add_expanded(curr_node.id)

            _LOGGER.info(f'Advancing proof from node {self.proof.id}: {shorten_hashes(curr_node.id)}')
            depth, cterm, next_cterms = kcfg_explore.cterm_execute(
                curr_node.cterm, depth=execute_depth, cut_point_rules=cut_point_rules, terminal_rules=terminal_rules
            )

            # Cut Rule
            if depth == 0 and len(next_cterms) == 1:
                new_execute_depth = execute_depth - 1 if execute_depth is not None else None
                depth, cterm, next_cterms = kcfg_explore.cterm_execute(
                    next_cterms[0],
                    depth=new_execute_depth,
                    cut_point_rules=cut_point_rules,
                    terminal_rules=terminal_rules,
                )
                depth = depth + 1

            if depth > 0:
                next_node = self.proof.kcfg.get_or_create_node(cterm)
                self.proof.kcfg.create_edge(curr_node.id, next_node.id, depth)
                _LOGGER.info(
                    f'Found basic block at depth {depth} for {self.proof.id}: {shorten_hashes((curr_node.id, next_node.id))}.'
                )
                curr_node = next_node

                if self._check_subsumption(
                    kcfg_explore, curr_node, is_terminal=is_terminal, implication_every_block=implication_every_block
                ):
                    continue

            if len(next_cterms) == 0:
                _LOGGER.info(f'Found stuck node {self.proof.id}: {shorten_hashes(curr_node.id)}')

            elif len(next_cterms) > 1:
                branches = list(extract_branches(cterm)) if extract_branches is not None else []
                if len(branches) != len(next_cterms):
                    _LOGGER.warning(
                        f'Falling back to manual branch extraction {self.proof.id}: {shorten_hashes(curr_node.id)}'
                    )
                    branches = [mlAnd(c for c in s.constraints if c not in cterm.constraints) for s in next_cterms]
                _LOGGER.info(
                    f'Found {len(branches)} branches for node {self.proof.id}: {shorten_hashes(curr_node.id)}: {[kcfg_explore.kprint.pretty_print(bc) for bc in branches]}'
                )
                self.proof.kcfg.split_on_constraints(curr_node.id, branches)

        self.proof.write_proof()
        return self.proof.kcfg
