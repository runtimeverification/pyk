from __future__ import annotations

import logging
from abc import abstractmethod
from enum import Enum
from typing import TYPE_CHECKING, Any, Callable, Dict, Final, Iterable, Optional, Type, TypeVar

from ..prelude.ml import mlAnd
from ..utils import shorten_hashes
from .explore import KCFGExplore
from .kcfg import KCFG

if TYPE_CHECKING:
    from pathlib import Path

    from ..cterm import CTerm
    from ..kast.inner import KInner

T = TypeVar('T', bound='Proof')

_LOGGER: Final = logging.getLogger(__name__)


class ProofStatus(Enum):
    PASSED = 'passed'
    FAILED = 'failed'
    PENDING = 'pending'


class Proof:
    _PROOF_TYPES: Final = {'AllPathReachabilityProof'}

    @classmethod
    def _check_proof_type(cls: Type[T], dct: Dict[str, Any], expected: Optional[str] = None) -> None:
        expected = expected if expected is not None else cls.__name__
        actual = dct['type']
        if actual != expected:
            raise ValueError(f'Expected "type" value: {expected}, got: {actual}')

    @classmethod
    @abstractmethod
    def from_dict(cls: Type[Proof], dct: Dict[str, Any]) -> Proof:
        proof_type = dct['type']
        if proof_type in Proof._PROOF_TYPES:
            return globals()[proof_type].from_dict(dct)
        raise ValueError(f'Expected "type" value in: {Proof._PROOF_TYPES}, got {proof_type}')

    @property
    @abstractmethod
    def status(self) -> ProofStatus:
        ...

    @abstractmethod
    def to_dict(self) -> Dict[str, Any]:
        ...


class AllPathReachabilityProof(Proof):
    cfg: KCFG

    def __init__(self, cfg: KCFG):
        self.cfg = cfg

    @property
    def status(self) -> ProofStatus:
        if len(self.cfg.stuck) > 0:
            return ProofStatus.FAILED
        elif len(self.cfg.frontier) > 0:
            return ProofStatus.PENDING
        else:
            return ProofStatus.PASSED

    @classmethod
    def from_dict(cls: Type[AllPathReachabilityProof], dct: Dict[str, Any]) -> AllPathReachabilityProof:
        cls._check_proof_type(dct)
        cfg = KCFG.from_dict(dct['cfg'])
        return AllPathReachabilityProof(cfg)

    def to_dict(self) -> Dict[str, Any]:
        return {'type': 'AllPathReachabilityProof', 'cfg': self.cfg.to_dict()}

    def advance_proof(
        self,
        cfgid: str,
        kcfg_explore: KCFGExplore,
        cfg_dir: Optional[Path] = None,
        is_terminal: Optional[Callable[[CTerm], bool]] = None,
        extract_branches: Optional[Callable[[CTerm], Iterable[KInner]]] = None,
        max_iterations: Optional[int] = None,
        execute_depth: Optional[int] = None,
        cut_point_rules: Iterable[str] = (),
        terminal_rules: Iterable[str] = (),
        simplify_init: bool = True,
        implication_every_block: bool = True,
    ) -> KCFG:
        def _write_cfg(_cfg: KCFG) -> None:
            if cfg_dir is not None:
                KCFGExplore.write_cfg(cfgid, cfg_dir, _cfg)

        target_node = self.cfg.get_unique_target()
        iterations = 0

        while self.cfg.frontier:
            _write_cfg(self.cfg)

            if max_iterations is not None and max_iterations <= iterations:
                _LOGGER.warning(f'Reached iteration bound {cfgid}: {max_iterations}')
                break
            iterations += 1
            curr_node = self.cfg.frontier[0]

            if implication_every_block or (is_terminal is not None and is_terminal(curr_node.cterm)):
                _LOGGER.info(
                    f'Checking subsumption into target state {cfgid}: {shorten_hashes((curr_node.id, target_node.id))}'
                )
                csubst = kcfg_explore.cterm_implies(curr_node.cterm, target_node.cterm)
                if csubst is not None:
                    self.cfg.create_cover(curr_node.id, target_node.id, csubst=csubst)
                    _LOGGER.info(f'Subsumed into target node {cfgid}: {shorten_hashes((curr_node.id, target_node.id))}')
                    continue

            if is_terminal is not None:
                _LOGGER.info(f'Checking terminal {cfgid}: {shorten_hashes(curr_node.id)}')
                if is_terminal(curr_node.cterm):
                    _LOGGER.info(f'Terminal node {cfgid}: {shorten_hashes(curr_node.id)}.')
                    self.cfg.add_expanded(curr_node.id)
                    continue

            self.cfg.add_expanded(curr_node.id)

            _LOGGER.info(f'Advancing proof from node {cfgid}: {shorten_hashes(curr_node.id)}')
            depth, cterm, next_cterms = kcfg_explore.cterm_execute(
                curr_node.cterm, depth=execute_depth, cut_point_rules=cut_point_rules, terminal_rules=terminal_rules
            )

            # Nonsense case.
            if len(next_cterms) == 1:
                raise ValueError(f'Found a single successor cterm {cfgid}: {(depth, cterm, next_cterms)}')

            if depth > 0:
                next_node = self.cfg.get_or_create_node(cterm)
                self.cfg.create_edge(curr_node.id, next_node.id, depth)
                _LOGGER.info(
                    f'Found basic block at depth {depth} for {cfgid}: {shorten_hashes((curr_node.id, next_node.id))}.'
                )
                curr_node = next_node

            if len(next_cterms) == 0:
                _LOGGER.info(f'Found stuck node {cfgid}: {shorten_hashes(curr_node.id)}')

            else:
                branches = list(extract_branches(cterm)) if extract_branches is not None else []
                if len(branches) != len(next_cterms):
                    _LOGGER.warning(f'Falling back to manual branch extraction {cfgid}: {shorten_hashes(curr_node.id)}')
                    branches = [mlAnd(c for c in s.constraints if c not in cterm.constraints) for s in next_cterms]
                _LOGGER.info(
                    f'Found {len(branches)} branches for node {cfgid}: {shorten_hashes(curr_node.id)}: {[kcfg_explore.kprint.pretty_print(bc) for bc in branches]}'
                )
                self.cfg.split_on_constraints(curr_node.id, branches)

        _write_cfg(self.cfg)
        return self.cfg
