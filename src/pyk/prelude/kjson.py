from typing import Any, Dict, Final, List, Optional, Tuple, Union

from ..kast.inner import KApply, KInner, KLabel, KSort, KToken
from ..kast.manip import flatten_label
from .kint import INT
from .string import STRING

JSON: Final = KSort('JSON')
JSONs: Final = KSort('JSONs')

#     syntax JSONs   ::= List{JSON,","}      [klabel(JSONs)      , symbol]
#     syntax JSONKey ::= String
#     syntax JSON    ::= "null"              [klabel(JSONnull)   , symbol]
#                      | String | Int | Float | Bool
#                      | JSONKey ":" JSON    [klabel(JSONEntry)  , symbol]
#                      | "{" JSONs "}"       [klabel(JSONObject) , symbol]
#                      | "[" JSONs "]"       [klabel(JSONList)   , symbol]


def kjson_to_dict(kjson: KInner) -> Optional[Union[Dict[str, Any], List[Any], str, int]]:
    def _kjson_entry_to_dict(_kjson_entry: KInner) -> Tuple[str, Any]:
        if type(_kjson_entry) is KApply and _kjson_entry.label == KLabel('JSONEntry'):
            key = kjson_to_dict(_kjson_entry.args[0])
            if type(key) is str:
                value = kjson_to_dict(_kjson_entry.args[1])
                return (key, value)
        raise ValueError(f'Could not convert K JSON Entry to Python Dict: {kjson}')

    def _flatten_jsons(jsons: KInner) -> List[KInner]:
        return [k for k in flatten_label('JSONs', jsons) if k != KApply('.List{"JSONs"}_JSONs')]

    if type(kjson) is KToken:

        if kjson.sort == STRING:
            assert kjson.token[0] == '"'
            assert kjson.token[-1] == '"'
            return kjson.token[1:-1]

        if kjson.sort == INT:
            return int(kjson.token)

    if type(kjson) is KApply:

        if kjson.label == KLabel('JSONnull'):
            return None

        if kjson.label == KLabel('JSONList'):
            return [kjson_to_dict(k) for k in _flatten_jsons(kjson.args[0])]

            # .List{"JSONs"}_JSONs

        if kjson.label == KLabel('JSONObject'):
            dict_entries = [_kjson_entry_to_dict(k) for k in _flatten_jsons(kjson.args[0])]
            return {k: v for k, v in dict_entries}

    raise ValueError(f'Could not convert K JSON to Python Dict: {kjson}')
