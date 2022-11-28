from pathlib import Path
from typing import Final

import pytest

from pyk.kast.inner import KApply, KInner, KSequence, KToken, KVariable
from pyk.kast.manip import remove_attrs
from pyk.ktool import KPrint
from pyk.prelude.kint import intToken

from .utils import Kompiler


@pytest.fixture(scope='module')
def imp_definition_dir(kompile: Kompiler) -> Path:
    return kompile('k-files/imp.k')


TEST_DATA: Final = (
    ('int-token', False, KToken('3', 'Int'), intToken(3)),
    ('id-token', False, KToken('abc', 'Id'), KToken('abc', 'Id')),
    ('add-aexp', False, KToken('3 + 4', 'AExp'), KApply('_+_', [intToken(3), intToken(4)])),
    ('add-int', True, KToken('3 +Int V', 'Int'), KApply('_+Int_', [intToken(3), KVariable('V')])),
    ('k-cell', True, KToken('<k> . </k>', 'KCell'), KApply('<k>', KSequence())),
)


@pytest.mark.parametrize('test_id,as_rule,token,expected', TEST_DATA, ids=[test_id for test_id, _, _, _ in TEST_DATA])
def test_parse_token(
    imp_definition_dir: Path,
    test_id: str,
    as_rule: bool,
    token: KToken,
    expected: KInner,
) -> None:
    # Given
    kprint = KPrint(imp_definition_dir)

    # When
    actual = kprint.parse_token(token, as_rule=as_rule)

    # Then
    assert remove_attrs(actual) == expected
