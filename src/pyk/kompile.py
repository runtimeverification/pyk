from dataclasses import dataclass
from functools import cached_property
from pathlib import Path
from typing import Union, final

from .cli_utils import check_dir_path, check_file_path
from .kore.parser import KoreParser
from .kore.syntax import Definition


@final
@dataclass(frozen=True)
class KompiledDefn:
    path: Path
    timestamp: int

    def __init__(self, definition_dir: Union[str, Path]):
        definition_dir = Path(definition_dir)
        check_dir_path(definition_dir)

        path = (definition_dir / 'definition.kore').resolve()
        check_file_path(path)

        timestamp_file = definition_dir / 'timestamp'
        check_file_path(timestamp_file)
        timestamp = timestamp_file.stat().st_mtime_ns

        object.__setattr__(self, 'path', path)
        object.__setattr__(self, 'timestamp', timestamp)

    @cached_property
    def definition(self) -> Definition:
        return KoreParser(self.path.read_text()).definition()
