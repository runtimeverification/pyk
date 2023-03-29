from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Callable, Final, Iterable, Optional

from pyk.utils import shorten_hashes

from ..prelude.ml import mlAnd
from .explore import KCFGExplore

if TYPE_CHECKING:
    from pathlib import Path

    from pyk.cterm import CTerm
    from pyk.kast.inner import KInner

    from .kcfg import KCFG

_LOGGER: Final = logging.getLogger(__name__)


class AllPathReachabilityProver:
    cfg: KCFG
    explore: KCFGExplore

    def __init__(self, cfg: KCFG, explore: KCFGExplore):
        self.cfg = cfg
        self.explore = explore

    def advance_proof(
        self,
        cfgid: str,
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
                csubst = self.explore.cterm_implies(curr_node.cterm, target_node.cterm)
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
            depth, cterm, next_cterms = self.explore.cterm_execute(
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
                    f'Found {len(branches)} branches for node {cfgid}: {shorten_hashes(curr_node.id)}: {[self.explore.kprint.pretty_print(bc) for bc in branches]}'
                )
                self.cfg.split_on_constraints(curr_node.id, branches)

        _write_cfg(self.cfg)
        return self.cfg
