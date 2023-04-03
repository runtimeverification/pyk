from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any, Callable, Dict, Final, Iterable, Optional, Type, TypeVar

from ..kcfg import KCFG
from ..prelude.ml import mlAnd
from ..utils import shorten_hashes
from .proof import Proof, ProofStatus

if TYPE_CHECKING:
    pass

    from ..cterm import CTerm
    from ..kast.inner import KInner
    from ..kcfg import KCFGExplore

T = TypeVar('T', bound='Proof')

_LOGGER: Final = logging.getLogger(__name__)


class AGProof(Proof):
    kcfg: KCFG

    def __init__(self, id: str, kcfg: KCFG):
        super().__init__(id)
        self.kcfg = kcfg

    @property
    def status(self) -> ProofStatus:
        if len(self.kcfg.stuck) > 0:
            return ProofStatus.FAILED
        elif len(self.kcfg.frontier) > 0:
            return ProofStatus.PENDING
        else:
            return ProofStatus.PASSED

    @classmethod
    def from_dict(cls: Type[AGProof], dct: Dict[str, Any]) -> AGProof:
        cfg = KCFG.from_dict(dct['cfg'])
        id = dct['id']
        return AGProof(id, cfg)

    @property
    def dict(self) -> Dict[str, Any]:
        return {'type': 'AGProof', 'id': self.id, 'cfg': self.kcfg.to_dict()}


class AGProver:
    proof: AGProof

    def __init__(self, proof: AGProof) -> None:
        self.proof = proof

    def advance_proof(
        self,
        kcfg_explore: KCFGExplore,
        is_terminal: Optional[Callable[[CTerm], bool]] = None,
        extract_branches: Optional[Callable[[CTerm], Iterable[KInner]]] = None,
        max_iterations: Optional[int] = None,
        execute_depth: Optional[int] = None,
        cut_point_rules: Iterable[str] = (),
        terminal_rules: Iterable[str] = (),
        simplify_init: bool = True,
        implication_every_block: bool = True,
    ) -> KCFG:
        target_node = self.proof.kcfg.get_unique_target()
        iterations = 0

        while self.proof.kcfg.frontier:
            self.proof.write_proof()

            if max_iterations is not None and max_iterations <= iterations:
                _LOGGER.warning(f'Reached iteration bound {self.proof.id}: {max_iterations}')
                break
            iterations += 1
            curr_node = self.proof.kcfg.frontier[0]

            if implication_every_block or (is_terminal is not None and is_terminal(curr_node.cterm)):
                _LOGGER.info(
                    f'Checking subsumption into target state {self.proof.id}: {shorten_hashes((curr_node.id, target_node.id))}'
                )
                csubst = kcfg_explore.cterm_implies(curr_node.cterm, target_node.cterm)
                if csubst is not None:
                    self.proof.kcfg.create_cover(curr_node.id, target_node.id, csubst=csubst)
                    _LOGGER.info(
                        f'Subsumed into target node {self.proof.id}: {shorten_hashes((curr_node.id, target_node.id))}'
                    )
                    continue

            if is_terminal is not None:
                _LOGGER.info(f'Checking terminal {self.proof.id}: {shorten_hashes(curr_node.id)}')
                if is_terminal(curr_node.cterm):
                    _LOGGER.info(f'Terminal node {self.proof.id}: {shorten_hashes(curr_node.id)}.')
                    self.proof.kcfg.add_expanded(curr_node.id)
                    continue

            self.proof.kcfg.add_expanded(curr_node.id)

            _LOGGER.info(f'Advancing proof from node {self.proof.id}: {shorten_hashes(curr_node.id)}')
            depth, cterm, next_cterms = kcfg_explore.cterm_execute(
                curr_node.cterm, depth=execute_depth, cut_point_rules=cut_point_rules, terminal_rules=terminal_rules
            )

            # Nonsense case.
            if len(next_cterms) == 1:
                raise ValueError(f'Found a single successor cterm {self.proof.id}: {(depth, cterm, next_cterms)}')

            if depth > 0:
                next_node = self.proof.kcfg.get_or_create_node(cterm)
                self.proof.kcfg.create_edge(curr_node.id, next_node.id, depth)
                _LOGGER.info(
                    f'Found basic block at depth {depth} for {self.proof.id}: {shorten_hashes((curr_node.id, next_node.id))}.'
                )
                curr_node = next_node

            if len(next_cterms) == 0:
                _LOGGER.info(f'Found stuck node {self.proof.id}: {shorten_hashes(curr_node.id)}')

            else:
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
