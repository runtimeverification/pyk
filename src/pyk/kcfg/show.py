import logging
from pathlib import Path
from typing import Callable, Final, Iterable, List, Optional, Tuple

from pyk.cli_utils import ensure_dir_path
from pyk.cterm import CTerm, build_claim, build_rule
from pyk.kast.inner import KApply, KRewrite
from pyk.kast.manip import flatten_label, minimize_term, push_down_rewrites
from pyk.kast.outer import KFlatModule, KRuleLike
from pyk.ktool.kprint import KPrint
from pyk.prelude.ml import mlAnd, mlTop

from .kcfg import KCFG

_LOGGER: Final = logging.getLogger(__name__)


class KCFGShow:
    kprint: KPrint

    def __init__(
        self,
        kprint: KPrint,
    ):
        self.kprint = kprint

    def show(
        self,
        cfgid: str,
        cfg: KCFG,
        nodes: Iterable[str] = (),
        node_deltas: Iterable[Tuple[str, str]] = (),
        to_module: bool = False,
        minimize: bool = True,
        node_printer: Optional[Callable[[CTerm], Iterable[str]]] = None,
    ) -> List[str]:
        res_lines: List[str] = []
        res_lines += cfg.pretty(self.kprint, minimize=minimize, node_printer=node_printer)

        for node_id in nodes:
            kast = cfg.node(node_id).cterm.kast
            if minimize:
                kast = minimize_term(kast)
            res_lines.append('')
            res_lines.append('')
            res_lines.append(f'Node {node_id}:')
            res_lines.append('')
            res_lines.append(self.kprint.pretty_print(kast))
            res_lines.append('')

        for node_id_1, node_id_2 in node_deltas:
            config_1 = cfg.node(node_id_1).cterm.config
            config_2 = cfg.node(node_id_2).cterm.config
            config_delta = push_down_rewrites(KRewrite(config_1, config_2))
            if minimize:
                config_delta = minimize_term(config_delta)
            res_lines.append('')
            res_lines.append('')
            res_lines.append(f'State Delta {node_id_1} => {node_id_2}:')
            res_lines.append('')
            res_lines.append(self.kprint.pretty_print(config_delta))
            res_lines.append('')

        if to_module:

            def to_rule(edge: KCFG.Edge, *, claim: bool = False) -> KRuleLike:
                sentence_id = f'BASIC-BLOCK-{edge.source.id}-TO-{edge.target.id}'
                init_cterm = CTerm(edge.source.cterm.config)
                for c in edge.source.cterm.constraints:
                    assert type(c) is KApply
                    if c.label.name == '#Ceil':
                        _LOGGER.warning(f'Ignoring Ceil condition: {c}')
                    else:
                        init_cterm.add_constraint(c)
                target_cterm = CTerm(edge.target.cterm.config)
                for c in edge.source.cterm.constraints:
                    assert type(c) is KApply
                    if c.label.name == '#Ceil':
                        _LOGGER.warning(f'Ignoring Ceil condition: {c}')
                    else:
                        target_cterm.add_constraint(c)
                rule: KRuleLike
                if claim:
                    rule, _ = build_claim(sentence_id, init_cterm.add_constraint(edge.condition), target_cterm)
                else:
                    rule, _ = build_rule(
                        sentence_id, init_cterm.add_constraint(edge.condition), target_cterm, priority=35
                    )
                return rule

            rules = [to_rule(e) for e in cfg.edges() if e.depth > 0]
            claims = [to_rule(KCFG.Edge(nd, cfg.get_unique_target(), mlTop(), -1), claim=True) for nd in cfg.frontier]
            cfg_module_name = cfgid.upper().replace('.', '-').replace('_', '-')
            new_module = KFlatModule(f'SUMMARY-{cfg_module_name}', rules + claims)
            res_lines.append(self.kprint.pretty_print(new_module))
            res_lines.append('')

        return res_lines

    def dot(self, cfgid: str, cfg: KCFG, dump_dir: Optional[Path] = None) -> List[str]:
        dot_lines = cfg.to_dot(self.kprint).split('\n')

        if dump_dir is not None:
            ensure_dir_path(dump_dir)

            dot_file = dump_dir / f'{cfgid}.dot'
            dot_file.write_text('\n'.join(dot_lines))
            _LOGGER.info(f'Wrote DOT file {cfgid}: {dot_file}')

            for node in cfg.nodes:
                node_file = dump_dir / f'node_config_{node.id}.txt'
                node_minimized_file = dump_dir / f'node_config_minimized_{node.id}.txt'
                node_constraint_file = dump_dir / f'node_constraint_{node.id}.txt'

                config = node.cterm.config
                if not node_file.exists():
                    node_file.write_text(self.kprint.pretty_print(config))
                    _LOGGER.info(f'Wrote node file {cfgid}: {node_file}')
                config = minimize_term(config)
                if not node_minimized_file.exists():
                    node_minimized_file.write_text(self.kprint.pretty_print(config))
                    _LOGGER.info(f'Wrote node file {cfgid}: {node_minimized_file}')
                if not node_constraint_file.exists():
                    constraint = mlAnd(node.cterm.constraints)
                    node_constraint_file.write_text(self.kprint.pretty_print(constraint))
                    _LOGGER.info(f'Wrote node file {cfgid}: {node_constraint_file}')

            for edge in cfg.edges():
                edge_file = dump_dir / f'edge_config_{edge.source.id}_{edge.target.id}.txt'
                edge_minimized_file = dump_dir / f'edge_config_minimized_{edge.source.id}_{edge.target.id}.txt'
                edge_constraint_file = dump_dir / f'edge_constraint_{edge.source.id}_{edge.target.id}.txt'

                config = push_down_rewrites(KRewrite(edge.source.cterm.config, edge.target.cterm.config))
                if not edge_file.exists():
                    edge_file.write_text(self.kprint.pretty_print(config))
                    _LOGGER.info(f'Wrote edge file {cfgid}: {edge_file}')
                config = minimize_term(config)
                if not edge_minimized_file.exists():
                    edge_minimized_file.write_text(self.kprint.pretty_print(config))
                    _LOGGER.info(f'Wrote edge file {cfgid}: {edge_minimized_file}')
                if not edge_constraint_file.exists():
                    edge_constraint_file.write_text(self.kprint.pretty_print(edge.condition))
                    _LOGGER.info(f'Wrote edge file {cfgid}: {edge_constraint_file}')

            for cover in cfg.covers():
                cover_file = dump_dir / f'cover_config_{cover.source.id}_{cover.target.id}.txt'
                cover_constraint_file = dump_dir / f'cover_constraint_{cover.source.id}_{cover.target.id}.txt'

                subst_equalities = flatten_label('#And', cover.subst.ml_pred)

                if not cover_file.exists():
                    cover_file.write_text('\n'.join(self.kprint.pretty_print(se) for se in subst_equalities))
                    _LOGGER.info(f'Wrote cover file {cfgid}: {cover_file}')
                if not cover_constraint_file.exists():
                    cover_constraint_file.write_text(self.kprint.pretty_print(cover.constraint))
                    _LOGGER.info(f'Wrote cover file {cfgid}: {cover_constraint_file}')

        return dot_lines
