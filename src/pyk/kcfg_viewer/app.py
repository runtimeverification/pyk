import json
from pathlib import Path
from typing import Union

from textual.app import App, ComposeResult
from textual.containers import Horizontal, Vertical
from textual.widgets import Header, Static

from pyk.kast.manip import minimize_term
from pyk.ktool import KPrint

from ..cli_utils import check_file_path
from ..kcfg import KCFG


class KCFGViewer(App):
    CSS_PATH = 'style.css'

    _kcfg_file: Path
    _cfg: KCFG
    _kprint: KPrint
    _curr_node: str
    _minimize: bool

    BINDINGS = [
        ('p', 'select_node("prev")', 'Select previous node'),
        ('n', 'select_node("next")', 'Select next node'),
        ('P', 'select_node("Prev")', 'Select prev branch'),
        ('N', 'select_node("Next")', 'Select next branch'),
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
            Vertical(Static(self._behavior_text(), id='behavior'), id='behavior-view'),
            Vertical(Static(self._node_text(), id='node'), id='node-view'),
        )

    def action_select_node(self, nid: str) -> None:
        if nid == 'next':
            edges = self._cfg.edges(source_id=self._curr_node)
            if len(edges) == 1:
                self._curr_node = edges[0].target.id
        elif nid == 'prev':
            edges = self._cfg.edges(target_id=self._curr_node)
            if len(edges) == 1:
                self._curr_node = edges[0].source.id
        self.query_one('#node', Static).update(self._node_text())
