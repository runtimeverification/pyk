import logging
from typing import Final

from pyk.ktool import KPrint

_LOGGER: Final = logging.getLogger(__name__)


class KCFGExplore:
    _kprint: KPrint

    def __init__(self, kprint: KPrint):
        self._kprint = kprint
