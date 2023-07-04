from __future__ import annotations

from typing import TYPE_CHECKING

from textual.containers import Horizontal, ScrollableContainer
from textual.widget import Widget
from textual.widgets import Footer
from textual.message import Message

from ..kcfg.tui import GraphChunk, KCFGViewer, NodeView, Window
from .show import APRProofShow

if TYPE_CHECKING:
    from collections.abc import Callable, Iterable

    from textual.app import ComposeResult
    from textual.events import Click

    from ..kcfg.show import NodePrinter
    from ..kcfg.tui import KCFGElem
    from ..ktool.kprint import KPrint
    from .reachability import APRProof


class APRProofBehaviorView(ScrollableContainer, can_focus=True):
    _proof: APRProof
    _kprint: KPrint
    _minimize: bool
    _node_printer: NodePrinter | None
    _proof_nodes: Iterable[GraphChunk]

    class Selected(Message):
        def __init__(self) -> None:
            super().__init__()

    def __init__(
        self,
        proof: APRProof,
        kprint: KPrint,
        minimize: bool = True,
        node_printer: NodePrinter | None = None,
        id: str = '',
    ):
        super().__init__(id=id)
        self._proof = proof
        self._kprint = kprint
        self._minimize = minimize
        self._node_printer = node_printer
        self._proof_nodes = []
        proof_show = APRProofShow(kprint, node_printer=node_printer)
        for lseg_id, node_lines in proof_show.pretty_segments(self._proof, minimize=self._minimize):
            self._proof_nodes.append(GraphChunk(lseg_id, node_lines))

    def on_click(self, click: Click) -> None:
        self.post_message(APRProofBehaviorView.Selected())
        click.stop()

    def compose(self) -> ComposeResult:
        return self._proof_nodes


class APRProofViewer(KCFGViewer):
    CSS_PATH = '../kcfg/style.css'

    _proof: APRProof

    def __init__(
        self,
        proof: APRProof,
        kprint: KPrint,
        node_printer: NodePrinter | None = None,
        custom_view: Callable[[KCFGElem], Iterable[str]] | None = None,
        minimize: bool = True,
    ) -> None:
        super().__init__(proof.kcfg, kprint, node_printer=node_printer, custom_view=custom_view, minimize=minimize)
        self._proof = proof

    def on_apr_proof_behavior_view_selected(self, message: APRProofBehaviorView.Selected) -> None:
        self.focus_window(Window.BEHAVIOR)

    def compose(self) -> ComposeResult:
        yield Horizontal(
            ScrollableContainer(
                APRProofBehaviorView(self._proof, self._kprint, node_printer=self._node_printer, id='behavior'),
                id='navigation',
            ),
            NodeView(self._kprint, custom_view=self._custom_view, id='node-view'),
            id='display',
        )
        yield Footer()
