from typing import List
from unittest import TestCase, defaultTestLoader

from pyk.utils import flatten


def test_cases() -> List[TestCase]:
    test_suite = defaultTestLoader.discover(__name__)
    return list(flatten(test_suite))


def test_fqns() -> List[str]:
    return [f'{tc.__module__}.{type(tc).__name__}.{tc._testMethodName}' for tc in test_cases()]
