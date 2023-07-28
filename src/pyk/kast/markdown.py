from __future__ import annotations

import re
from typing import TYPE_CHECKING, NamedTuple

if TYPE_CHECKING:
    from collections.abc import Iterator
    from typing import Final


_CODE_BLOCK_PATTERN: Final = re.compile(
    r'(^|(?<=\n)) {0,3}(?P<fence>```+)(?!`)(?P<info>.*)\n(?P<code>(.*\n)*?) {0,3}(?P=fence)`*'
)


class CodeBlock(NamedTuple):
    info: str
    code: str


def code_blocks(text: str) -> Iterator[CodeBlock]:
    return (CodeBlock(match['info'], match['code'].rstrip()) for match in _CODE_BLOCK_PATTERN.finditer(text))


def filter_md_tags(text: str) -> str:
    return '\n'.join(code_block.code for code_block in code_blocks(text))
