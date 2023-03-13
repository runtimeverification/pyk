from pathlib import Path

from pyk.ktool.krun import KRunOutput, _build_arg_list


def test_all_args() -> None:
    # Given
    # fmt: off
    expected = [
        'kevm-krun',
        'input/path',
        '--definition', 'def/dir',
        '--output', 'json',
        '--parser', 'cat',
        '--depth', '12355',
        '-pFOO=bar', '-pBUZZ=kill',
        '-cCOO=car', '-cFUZZ=bill',
        '--term',
        '--no-expand-macros',
        '--search-final',
        '--no-pattern',
    ]
    # fmt: on

    # When
    actual = _build_arg_list(
        command='kevm-krun',
        input_file=Path('input/path'),
        definition_dir=Path('def/dir'),
        output=KRunOutput.JSON,
        parser='cat',
        pmap={'FOO': 'bar', 'BUZZ': 'kill'},
        cmap={'COO': 'car', 'FUZZ': 'bill'},
        depth=12355,
        term=True,
        no_expand_macros=True,
        search_final=True,
        no_pattern=True,
    )

    # Then
    assert actual == expected
