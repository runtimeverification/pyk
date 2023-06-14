from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from ..kcfg.show import NodePrinter

if TYPE_CHECKING:
    from typing import Final

    from ..kcfg import KCFG
    from ..ktool.kprint import KPrint
    from .reachability import APRProof

_LOGGER: Final = logging.getLogger(__name__)


class APRProofNodePrinter(NodePrinter):
    proof: APRProof

    def __init__(self, proof: APRProof, kprint: KPrint):
        super().__init__(kprint)

    def node_attrs(self, kcfg: KCFG, node: KCFG.Node) -> list[str]:
        attrs = super().node_attrs(kcfg, node)
        if node.id in self.proof.pending:
            attrs.append('pending')
        if node.id in self.proof.terminal:
            attrs.append('terminal')
        return attrs
