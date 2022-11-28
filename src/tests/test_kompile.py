from pathlib import Path

from pyk.ktool.kompile import KompileBackend, _build_arg_list


def test_all_args() -> None:
    # Given
    # fmt: off
    expected = [
        '--output-definition', 'path/to/kompiled',
        '--backend', 'haskell',
        '--main-module', 'MAIN-MODULE',
        '--syntax-module', 'SYNTAX-MODULE',
        '-I', '/',
        '-I', '/include/lib',
        '--md-selector', 'k & ! nobytes & ! node',
        '--hook-namespaces', 'JSON KRYPTO BLOCKCHAIN',
        '--emit-json',
        '--post-process', "'echo \"hello\"'",
        '--concrete-rules', 'foo,bar',
        '--new-fangled-option', 'buzz'
    ]
    # fmt: on

    # When
    actual = _build_arg_list(
        output_dir=Path('path/to/kompiled'),
        backend=KompileBackend.HASKELL,
        main_module='MAIN-MODULE',
        syntax_module='SYNTAX-MODULE',
        include_dirs=(Path(path) for path in ['/', '/include/lib']),
        md_selector='k & ! nobytes & ! node',
        hook_namespaces=['JSON', 'KRYPTO', 'BLOCKCHAIN'],
        emit_json=True,
        post_process='echo "hello"',
        concrete_rules=['foo', 'bar'],
        args=['--new-fangled-option', 'buzz'],
    )

    # Then
    assert actual == expected
