from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from pyk.kast.markdown import CodeBlock, code_blocks

from ..utils import TEST_DATA_DIR

if TYPE_CHECKING:
    from collections.abc import Iterator
    from pathlib import Path
    from typing import Final


CODE_BLOCKS_TEST_DIR: Final = TEST_DATA_DIR / 'markdown-code-blocks'
CODE_BLOCKS_TEST_FILES: Final = tuple(CODE_BLOCKS_TEST_DIR.glob('*.test'))
assert CODE_BLOCKS_TEST_FILES


@pytest.mark.parametrize(
    'test_file',
    CODE_BLOCKS_TEST_FILES,
    ids=[test_file.stem for test_file in CODE_BLOCKS_TEST_FILES],
)
def test_code_blocks(test_file: Path) -> None:
    # Given
    text, expected = _parse_code_blocks_test_data(test_file)

    # When
    actual = list(code_blocks(text))

    # Then
    assert actual == expected


def _parse_code_blocks_test_data(test_file: Path) -> tuple[str, list[CodeBlock]]:
    def _text(lines: Iterator[str]) -> str:
        text_lines: list[str] = []

        while True:
            line = next(lines)
            if line == '===':
                break
            text_lines.append(line)

        return '\n'.join(text_lines)

    def _blocks(lines: Iterator[str]) -> list[CodeBlock]:
        blocks: list[CodeBlock] = []

        la = next(lines, None)

        while la is not None:
            info = la
            code_lines: list[str] = []

            la = next(lines, None)
            while la is not None and la != '---':
                code_lines.append(la)
                la = next(lines, None)

            code = '\n'.join(code_lines)
            blocks.append(CodeBlock(info, code))

            if la:  # i.e. la == '---'
                la = next(lines, None)

        return blocks

    lines = test_file.read_text().splitlines()
    it = iter(lines)
    text = _text(it)
    blocks = _blocks(it)
    return text, blocks
