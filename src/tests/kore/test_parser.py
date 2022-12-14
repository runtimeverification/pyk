import json
from pathlib import Path
from typing import Any, Final, Mapping

import pytest

from pyk.kore.parser import KoreParser
from pyk.kore.syntax import Kore, Pattern, kore_term

TEST_DATA_DIR: Final = Path(__file__).parent / 'test-data'

DEFINITION_PASS_KORE_FILES: Final = tuple((TEST_DATA_DIR / 'definitions/pass').iterdir())
DEFINITION_FAIL_KORE_FILES: Final = tuple(
    test_file for test_file in (TEST_DATA_DIR / 'definitions/fail').iterdir() if test_file.suffix == '.kore'
)

PATTERN_FILES: Final = tuple((TEST_DATA_DIR / 'patterns').iterdir())

JSON_FILES: Final = tuple((TEST_DATA_DIR / 'json').iterdir())
JSON_TEST_DATA: Final = tuple(
    (json_file, i, dct) for json_file in JSON_FILES for i, dct in enumerate(json.loads(json_file.read_text()))
)


@pytest.mark.parametrize(
    'kore_file', DEFINITION_PASS_KORE_FILES, ids=lambda path: path.name
)  # mypy complains on Path.name.fget
def test_parse_definition_pass(kore_file: Path) -> None:
    # Given
    text = kore_file.read_text()

    # When
    parser1 = KoreParser(text)
    definition1 = parser1.definition()
    parser2 = KoreParser(definition1.text)
    definition2 = parser2.definition()

    # Then
    assert parser1.eof
    assert parser2.eof
    assert definition1 == definition2


@pytest.mark.parametrize('kore_file', DEFINITION_FAIL_KORE_FILES, ids=lambda path: path.name)
def test_parse_definition_fail(kore_file: Path) -> None:
    # Given
    text = kore_file.read_text()
    parser = KoreParser(text)

    # Then
    with pytest.raises(ValueError):
        # When
        parser.definition()


@pytest.mark.parametrize('kore_file', PATTERN_FILES, ids=lambda path: path.name)
def test_parse_pattern(kore_file: Path) -> None:
    # Given
    text = kore_file.read_text()

    # When
    parser1 = KoreParser(text)
    pattern1 = parser1.pattern()
    parser2 = KoreParser(pattern1.text)
    pattern2 = parser2.pattern()
    pattern3 = Pattern.from_dict(pattern1.dict)

    # Then
    assert parser1.eof
    assert parser2.eof
    assert pattern1 == pattern2
    assert pattern1 == pattern3


@pytest.mark.parametrize(
    'json_file,i,dct', JSON_TEST_DATA, ids=[f'{json_file.name}-{i}' for json_file, i, _ in JSON_TEST_DATA]
)
def test_parse_json(json_file: Path, i: int, dct: Mapping[str, Any]) -> None:
    # When
    kore1: Kore = kore_term(dct)  # TODO type hint should be unnecessary
    parser = KoreParser(kore1.text)
    kore2 = parser.pattern()
    kore3 = Kore.from_json(kore1.json)

    # Then
    assert parser.eof
    assert kore1 == kore2
    assert kore1 == kore3
