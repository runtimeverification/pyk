import json
from pathlib import Path
from typing import Final
from unittest import TestCase

from pyk.kore.parser import KoreParser
from pyk.kore.syntax import Kore, kore_term

TEST_DATA_DIR: Final = Path(__file__).parent / 'test-data'


class ParserTest(TestCase):
    def test_parse_definition_pass(self) -> None:
        test_dir = TEST_DATA_DIR / 'definitions/pass'
        test_files = tuple(test_dir.iterdir())
        assert test_files

        for test_file in test_files:
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

    def test_parse_definition_fail(self) -> None:
        test_dir = TEST_DATA_DIR / 'definitions/fail'
        test_files = tuple(test_file for test_file in test_dir.iterdir() if test_file.suffix == '.kore')
        assert test_files

        for test_file in test_files:
            with self.subTest(test_file.name):
                # Given
                with open(test_file, 'r') as f:
                    parser = KoreParser(f.read())

                # Then
                with self.assertRaises(ValueError):
                    # When
                    parser.definition()

    def test_parse_json(self) -> None:
        test_dir = TEST_DATA_DIR / 'json'
        test_files = tuple(test_dir.iterdir())
        assert test_files

        for test_file in test_files:
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
