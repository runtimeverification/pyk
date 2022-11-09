import json
from pathlib import Path
from typing import Final
from unittest import TestCase

from pyk.kore.parser import KoreParser
from pyk.kore.syntax import Kore, kore_term

TEST_DIR: Final = Path(__file__).parent

# JSON files for random generated patterns
JSON_TEST_DIR: Final = TEST_DIR / 'json-data'
JSON_TEST_FILES: Final = tuple(JSON_TEST_DIR.iterdir())

# Kore test files containing definitions
KORE_TEST_DIR: Final = TEST_DIR / 'kore-data'
KORE_PASS_DIR: Final = KORE_TEST_DIR / 'pass'
KORE_PASS_TEST_FILES: Final = tuple(KORE_PASS_DIR.iterdir())
KORE_FAIL_DIR: Final = KORE_TEST_DIR / 'fail'
KORE_FAIL_TEST_FILES: Final = tuple(test_file for test_file in KORE_FAIL_DIR.iterdir() if test_file.suffix == '.kore')

assert KORE_PASS_TEST_FILES
assert KORE_FAIL_TEST_FILES


class ParserTest(TestCase):
    def test_parse_kore_pass(self) -> None:
        for test_file in KORE_PASS_TEST_FILES:
            with self.subTest(test_file.name):
                # Given
                with open(test_file, 'r') as f:
                    parser1 = KoreParser(f.read())

                # When
                definition1 = parser1.definition()
                parser2 = KoreParser(definition1.text)
                definition2 = parser2.definition()

                # Then
                self.assertTrue(parser1.eof)
                self.assertTrue(parser2.eof)
                self.assertEqual(definition1, definition2)

    def test_parse_kore_fail(self) -> None:
        for test_file in KORE_FAIL_TEST_FILES:
            with self.subTest(test_file.name):
                # Given
                with open(test_file, 'r') as f:
                    parser = KoreParser(f.read())

                # Then
                with self.assertRaises(ValueError):
                    # When
                    parser.definition()

    def test_parse_json(self) -> None:
        for test_file in JSON_TEST_FILES:
            with open(test_file, 'r') as f:
                # Given
                terms = json.load(f)

                for i, term in enumerate(terms):
                    with self.subTest(test_file.name, i=i):
                        # When
                        kore1: Kore = kore_term(term)  # TODO type hint should be unnecessary
                        parser = KoreParser(kore1.text)
                        kore2 = parser.pattern()
                        kore3 = Kore.from_json(kore1.json)

                        # Then
                        self.assertTrue(parser.eof)
                        self.assertEqual(kore1, kore2)
                        self.assertEqual(kore1, kore3)
