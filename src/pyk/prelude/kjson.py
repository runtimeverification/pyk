from typing import Any, Dict, Final, List, Union

from ..kast.inner import KInner, KSort, KToken
from .string import STRING

JSON: Final = KSort('JSON')
JSONs: Final = KSort('JSONs')


def kjson_to_dict(kjson: KInner) -> Union[Dict[str, Any], List[Any], str]:
    if type(kjson) is KToken and kjson.sort == STRING:
        return kjson.token
    raise ValueError(f'Could not convert K JSON to Python Dict: {kjson}')
