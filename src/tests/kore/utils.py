from pathlib import Path
from typing import Final

# JSON files for random generated patterns
_JSON_TEST_DIR: Final = Path(__file__).parent / 'json-data'
JSON_TEST_FILES: Final = tuple(_JSON_TEST_DIR.iterdir())

# Kore test files containing definitions
_KORE_TEST_DIR: Final = Path(__file__).parent / 'kore-data'
_KORE_PASS_DIR: Final = _KORE_TEST_DIR / 'pass'
_KORE_FAIL_DIR: Final = _KORE_TEST_DIR / 'fail'

KORE_PASS_TEST_FILES: Final = tuple(_KORE_PASS_DIR.iterdir())
KORE_FAIL_TEST_FILES: Final = tuple(test_file for test_file in _KORE_FAIL_DIR.iterdir() if test_file.suffix == '.kore')

assert KORE_PASS_TEST_FILES
assert KORE_FAIL_TEST_FILES
