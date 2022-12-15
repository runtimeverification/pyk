import json
from pathlib import Path
from typing import Dict, List, Tuple, Union

from textual.app import App, ComposeResult
from textual.containers import Horizontal, Vertical
from textual.widgets import Header, Static

from pyk.kast.manip import minimize_term
from pyk.ktool import KPrint

from ..cli_utils import check_file_path
from ..kcfg import KCFG
from ..utils import shorten_hashes


class KCFGViewer(App):
    CSS_PATH = 'style.css'

    _kcfg_file: Path
    _cfg: KCFG
    _kprint: KPrint
    _curr_node: str
    _minimize: bool

    BINDINGS = [
        ('p', 'select_node("p")', 'Select previous node'),
        ('n', 'select_node("n")', 'Select next node'),
        ('0', 'select_node("0")', 'Select node 0'),
        ('1', 'select_node("1")', 'Select node 1'),
        ('2', 'select_node("2")', 'Select node 2'),
        ('3', 'select_node("3")', 'Select node 3'),
        ('4', 'select_node("4")', 'Select node 4'),
        ('5', 'select_node("5")', 'Select node 5'),
        ('6', 'select_node("6")', 'Select node 6'),
        ('7', 'select_node("7")', 'Select node 7'),
        ('8', 'select_node("8")', 'Select node 8'),
        ('9', 'select_node("9")', 'Select node 9'),
    ]

    def __init__(self, kcfg_file: Union[str, Path], kprint: KPrint) -> None:
        kcfg_file = Path(kcfg_file)
        check_file_path(kcfg_file)
        super().__init__()
        self._kcfg_file = kcfg_file
        self._cfg = KCFG.from_dict(json.loads(kcfg_file.read_text()))
        self._kprint = kprint
        self._curr_node = self._cfg.get_unique_init().id
        self._minimize = True

    def _navigation_options(self) -> Dict[str, Tuple[str, str]]:
        nav_opts = {}
        in_edges: List[KCFG.EdgeLike] = []
        out_edges: List[KCFG.EdgeLike] = []
        for e in self._cfg.edges(target_id=self._curr_node):
            in_edges.append(e)
        for c in self._cfg.covers(target_id=self._curr_node):
            in_edges.append(c)
        for e in self._cfg.edges(source_id=self._curr_node):
            out_edges.append(e)
        for c in self._cfg.covers(source_id=self._curr_node):
            out_edges.append(c)
        counter = 0
        if len(in_edges) == 1:
            nav_opts['p'] = ('prev', in_edges[0].source.id)
        else:
            for ie in in_edges:
                if counter > 9:
                    break
                nav_opts[str(counter)] = ('prev', ie.source.id)
                counter += 1
        if len(out_edges) == 1:
            nav_opts['n'] = ('next', out_edges[0].target.id)
        else:
            for oe in out_edges:
                if counter > 9:
                    break
                nav_opts[str(counter)] = ('next', oe.target.id)
                counter += 1
        return nav_opts

    def _navigation_text(self) -> str:
        text_lines = [f'current node: {shorten_hashes(self._curr_node)}']
        for k, (d, n) in self._navigation_options().items():
            text_lines.append(f'    {k}: {d} {shorten_hashes(n)}')
        return '\n'.join(text_lines)

    def _behavior_text(self) -> str:
        text_lines = self._cfg.pretty(self._kprint, minimize=self._minimize)
        return '\n'.join(text_lines)

    def _node_text(self) -> str:
        kast = self._cfg.node(self._curr_node).cterm.kast
        if self._minimize:
            kast = minimize_term(kast)
        return self._kprint.pretty_print(kast)

    def compose(self) -> ComposeResult:
        yield Header()
        yield Horizontal(
            Vertical(
                Horizontal(Static(self._navigation_text(), id='navigation'), id='navigation-view'),
                Horizontal(Static(self._behavior_text(), id='behavior'), id='behavior-view'),
                id='left-pane-view',
            ),
            Vertical(Static(self._node_text(), id='node'), id='right-pane-view'),
        )

    def update(self) -> None:
        self.query_one('#navigation', Static).update(self._navigation_text())
        # self.query_one('#behavior', Static).update(self._behavior_text())
        self.query_one('#node', Static).update(self._node_text())

    def action_select_node(self, nid: str) -> None:
        nav_opts = self._navigation_options()
        if nid in nav_opts:
            _, next_node = nav_opts[nid]
            self._curr_node = next_node
            self.update()
