import logging
from pathlib import Path
from typing import Callable, Final, Iterable, Optional

from pyk.cterm import CTerm
from pyk.kast.inner import KInner
from pyk.kcfg import KCFG
from pyk.ktool import KProve
from pyk.prelude.ml import mlAnd, mlTop
from pyk.utils import shorten_hashes

_LOGGER: Final = logging.getLogger(__name__)


class KCFGExplore:
    _kprove: KProve

    def __init__(self, kprove: KProve):
        self._kprove = kprove

    def rpc_prove(
        self,
        cfgid: str,
        cfg: KCFG,
        cfg_path: Optional[Path] = None,
        rpc_port: Optional[int] = None,
        is_terminal: Optional[Callable[[CTerm], bool]] = None,
        extract_branches: Optional[Callable[[CTerm], Iterable[KInner]]] = None,
        max_iterations: Optional[int] = None,
        execute_depth: Optional[int] = None,
        cut_point_rules: Iterable[str] = (),
        terminal_rules: Iterable[str] = (),
        simplify_init: bool = True,
        implication_every_block: bool = False,
    ) -> KCFG:
        def _write_cfg(_cfg: KCFG) -> None:
            if cfg_path is not None:
                cfg_path.write_text(_cfg.to_json())
                _LOGGER.info(f'Updated CFG file: {cfg_path}')

        if rpc_port is not None:
            self._kprove.set_kore_rpc_port(rpc_port)

        target_node = cfg.get_unique_target()
        iterations = 0

        while cfg.frontier:
            _write_cfg(cfg)

            if max_iterations is not None and max_iterations <= iterations:
                _LOGGER.warning(f'Reached iteration bound: {max_iterations}')
                break
            iterations += 1
            curr_node = cfg.frontier[0]

            if implication_every_block or (is_terminal is not None and is_terminal(curr_node.cterm)):
                _LOGGER.info(
                    f'Checking subsumption into target state {cfgid}: {shorten_hashes((curr_node.id, target_node.id))}'
                )
                impl = self._kprove.implies(curr_node.cterm, target_node.cterm)
                if impl is not None:
                    subst, pred = impl
                    cfg.create_cover(curr_node.id, target_node.id, subst=subst, constraint=pred)
                    _LOGGER.info(f'Subsumed into target node: {shorten_hashes((curr_node.id, target_node.id))}')
                    continue

            if is_terminal is not None:
                _LOGGER.info(f'Checking terminal {cfgid}: {shorten_hashes(curr_node.id)}')
                if is_terminal(curr_node.cterm):
                    _LOGGER.info(f'Terminal node {cfgid}: {shorten_hashes(curr_node.id)}.')
                    cfg.add_expanded(curr_node.id)
                    continue

            cfg.add_expanded(curr_node.id)

            _LOGGER.info(f'Advancing proof from node {cfgid}: {shorten_hashes(curr_node.id)}')
            depth, cterm, next_cterms = self._kprove.execute(
                curr_node.cterm, depth=execute_depth, cut_point_rules=cut_point_rules, terminal_rules=terminal_rules
            )

            # Nonsense case.
            if len(next_cterms) == 1:
                raise ValueError(f'Found a single successor cterm: {(depth, cterm, next_cterms)}')

            if len(next_cterms) == 0 and depth == 0:
                _LOGGER.info(f'Found stuck node {cfgid}: {shorten_hashes(curr_node.id)}')
                continue

            if depth > 0:
                next_node = cfg.get_or_create_node(cterm)
                cfg.create_edge(curr_node.id, next_node.id, mlTop(), depth)
                _LOGGER.info(
                    f'Found basic block at depth {depth} for {cfgid}: {shorten_hashes((curr_node.id, next_node.id))}.'
                )

                branches = extract_branches(cterm) if extract_branches is not None else []
                if len(list(branches)) > 0:
                    cfg.add_expanded(next_node.id)
                    _LOGGER.info(
                        f'Found {len(list(branches))} branches {cfgid}: {[self._kprove.pretty_print(b) for b in branches]}'
                    )
                    splits = cfg.split_node(next_node.id, branches)
                    _LOGGER.info(f'Made split for {cfgid}: {shorten_hashes((next_node.id, splits))}')
                    continue

            else:
                _LOGGER.warning(f'Falling back to manual branch extraction {cfgid}: {shorten_hashes(curr_node.id)}')
                branch_constraints = [[c for c in s.constraints if c not in cterm.constraints] for s in next_cterms]
                _LOGGER.info(
                    f'Found {len(list(next_cterms))} branches manually at depth 1 for {cfgid}: {[self._kprove.pretty_print(mlAnd(bc)) for bc in branch_constraints]}'
                )
                for bs, bc in zip(next_cterms, branch_constraints, strict=True):
                    branch_node = cfg.get_or_create_node(bs)
                    cfg.create_edge(curr_node.id, branch_node.id, mlAnd(bc), 1)

        _write_cfg(cfg)
        return cfg
