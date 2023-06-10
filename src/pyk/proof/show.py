from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from ..kcfg import KCFGShow
from ..utils import ensure_dir_path

if TYPE_CHECKING:
    from collections.abc import Callable, Iterable
    from pathlib import Path
    from typing import Final

    from graphviz import Digraph

    from ..cterm import CTerm
    from ..kcfg.kcfg import NodeIdLike
    from ..ktool.kprint import KPrint
    from .reachability import APRProof

_LOGGER: Final = logging.getLogger(__name__)


class APRProofShow:
    kcfg_show: KCFGShow

    def __init__(
        self,
        kprint: KPrint,
    ):
        self.kcfg_show = KCFGShow(kprint)

    def pretty(
        self,
        proof: APRProof,
        minimize: bool = True,
        node_printer: Callable[[CTerm], Iterable[str]] | None = None,
    ) -> Iterable[str]:
        return (
            line
            for _, seg_lines in self.kcfg_show.pretty_segments(
                proof.kcfg,
                minimize=minimize,
                node_printer=node_printer,
            )
            for line in seg_lines
        )

    def show(
        self,
        proof: APRProof,
        nodes: Iterable[NodeIdLike] = (),
        node_deltas: Iterable[tuple[NodeIdLike, NodeIdLike]] = (),
        to_module: bool = False,
        minimize: bool = True,
        sort_collections: bool = False,
        node_printer: Callable[[CTerm], Iterable[str]] | None = None,
        omit_cells: Iterable[str] = (),
    ) -> list[str]:
        nodes = list(nodes) + [nd.id for nd in proof.pending]
        node_descriptors: dict[NodeIdLike, list[str]] = {}
        for pending in proof.pending:
            if pending.id not in node_descriptors:
                node_descriptors[pending.id] = []
            node_descriptors[pending.id].append('pending')
        for terminal in proof.terminal:
            if terminal.id not in node_descriptors:
                node_descriptors[terminal.id] = []
            node_descriptors[terminal.id].append('terminal')

        res_lines = self.kcfg_show.show(
            proof.id,
            proof.kcfg,
            nodes=nodes,
            node_deltas=node_deltas,
            to_module=to_module,
            minimize=minimize,
            sort_collections=sort_collections,
            node_printer=node_printer,
            node_descriptors=node_descriptors,
            omit_cells=omit_cells,
        )

        return res_lines

    def dot(self, proof: APRProof, node_printer: Callable[[CTerm], Iterable[str]] | None = None) -> Digraph:
        graph = self.kcfg_show.dot(proof.kcfg, node_printer=node_printer)
        return graph

    def dump(
        self,
        proof: APRProof,
        dump_dir: Path,
        dot: bool = False,
        node_printer: Callable[[CTerm], Iterable[str]] | None = None,
    ) -> None:
        ensure_dir_path(dump_dir)

        proof_file = dump_dir / f'{proof.id}.json'
        proof_file.write_text(proof.json)
        _LOGGER.info(f'Wrote APRProof file {proof.id}: {proof_file}')

        if dot:
            cfg_dot = self.dot(proof, node_printer=node_printer).source
            dot_file = dump_dir / f'{proof.id}.dot'
            dot_file.write_text(cfg_dot)
            _LOGGER.info(f'Wrote DOT file {proof.id}: {dot_file}')

        self.kcfg_show.dump(proof.id, proof.kcfg, dump_dir, dot=False, node_printer=node_printer)
