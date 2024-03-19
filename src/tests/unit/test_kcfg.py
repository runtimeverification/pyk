from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from pyk.cterm import CSubst, CTerm
from pyk.kast.inner import KApply, KSort, KVariable
from pyk.kcfg import KCFG, KCFGShow
from pyk.kcfg.show import NodePrinter
from pyk.prelude.kint import geInt, intToken, ltInt
from pyk.prelude.ml import mlEquals, mlEqualsTrue, mlTop
from pyk.prelude.utils import token

from .mock_kprint import MockKPrint

if TYPE_CHECKING:
    from collections.abc import Iterable
    from pathlib import Path
    from typing import Any

    from pyk.kast import KInner


# over 10 is variables
def term(i: int, with_cond: bool = False) -> CTerm:
    inside: KInner = token(i)
    if i > 10:
        inside = KVariable('V' + str(i))
    term: KInner = KApply('<top>', [inside])
    conds = (mlEquals(KVariable('x'), token(i)),) if with_cond else ()
    return CTerm(term, conds)


def node(i: int, with_cond: bool = False) -> KCFG.Node:
    return KCFG.Node(i, term(i, with_cond))


def edge(i: int, j: int) -> KCFG.Edge:
    return KCFG.Edge(node(i), node(j), 1, ())


def cover(i: int, j: int) -> KCFG.Cover:
    csubst = term(j).match_with_constraint(term(i))
    assert csubst is not None
    return KCFG.Cover(node(i), node(j), csubst)


def split(i: int, js: Iterable[int]) -> KCFG.Split:
    split_substs = []
    for j in js:
        csubst = term(i).match_with_constraint(term(j))
        assert csubst is not None
        split_substs.append(csubst)
    return KCFG.Split(node(i), zip((node(j) for j in js), split_substs, strict=True))


def ndbranch(i: int, js: Iterable[int]) -> KCFG.NDBranch:
    return KCFG.NDBranch(node(i), tuple(node(j) for j in js), ())


def node_dicts(n: int, start: int = 1) -> list[dict[str, Any]]:
    return [node(i).to_dict() for i in range(start, start + n)]


def predicate_node_dicts(n: int, start: int = 1) -> list[dict[str, Any]]:
    return [node(i, True).to_dict() for i in range(start, start + n)]


def edge_dicts(*edges: Iterable) -> list[dict[str, Any]]:
    def _make_edge_dict(i: int, j: int, depth: int = 1) -> dict[str, Any]:
        return {'source': i, 'target': j, 'depth': depth, 'rules': []}

    return [_make_edge_dict(*edge) for edge in edges]


def cover_dicts(*edges: tuple[int, int]) -> list[dict[str, Any]]:
    covers = []
    for i, j in edges:
        csubst = term(j).match_with_constraint(term(i))
        assert csubst is not None
        covers.append({'source': i, 'target': j, 'csubst': csubst.to_dict()})
    return covers


def split_dicts(*edges: tuple[int, Iterable[tuple[int, KInner]]]) -> list[dict[str, Any]]:
    def to_csubst(source_id: int, target_id: int, constraint: KInner) -> CSubst:
        csubst = term(source_id).match_with_constraint(term(target_id))
        assert csubst is not None
        csubst = csubst.add_constraint(constraint)
        return csubst

    return [
        {
            'source': source_id,
            'targets': [
                {
                    'target': target_id,
                    'csubst': to_csubst(source_id, target_id, constraint).to_dict(),
                }
                for target_id, constraint in targets
            ],
        }
        for source_id, targets in edges
    ]


def ndbranch_dicts(*edges: tuple[int, Iterable[tuple[int, bool]]]) -> list[dict[str, Any]]:
    return [
        {
            'source': source_id,
            'targets': [target_id for target_id, _ in target_ids],
            'rules': [],
        }
        for source_id, target_ids in edges
    ]


def test_from_dict_single_node() -> None:
    # Given
    d = {'next': 2, 'nodes': node_dicts(1)}

    # When
    cfg = KCFG.from_dict(d)

    # Then
    assert set(cfg.nodes) == {node(1)}
    assert cfg.to_dict() == d


def test_from_dict_two_nodes() -> None:
    # Given
    d = {'next': 3, 'nodes': node_dicts(2)}

    # When
    cfg = KCFG.from_dict(d)

    # Then
    assert set(cfg.nodes) == {node(1), node(2)}
    assert cfg.to_dict() == d


def test_from_dict_loop_edge() -> None:
    # Given
    d = {'next': 3, 'nodes': node_dicts(2), 'edges': edge_dicts((1, 2), (2, 1))}

    # When
    cfg = KCFG.from_dict(d)

    # Then
    assert set(cfg.nodes) == {node(1), node(2)}
    assert set(cfg.edges()) == {edge(1, 2), edge(2, 1)}
    assert cfg.edge(1, 2) == edge(1, 2)
    assert cfg.edge(2, 1) == edge(2, 1)
    assert cfg.to_dict() == d


def test_from_dict_simple_edge() -> None:
    # Given
    d = {'nodes': node_dicts(2), 'edges': edge_dicts((1, 2))}

    # When
    cfg = KCFG.from_dict(d)

    # Then
    assert set(cfg.nodes) == {node(1), node(2)}
    assert set(cfg.edges()) == {edge(1, 2)}
    assert cfg.edge(1, 2) == edge(1, 2)


def test_to_dict() -> None:
    # Given
    d = {'nodes': node_dicts(2), 'edges': edge_dicts((1, 2)), 'next': 3}

    # When
    cfg = KCFG.from_dict(d)
    cfg_dict = cfg.to_dict()

    # Then
    assert cfg_dict == d


def test_to_dict_repeated() -> None:
    # Given
    d = {'nodes': node_dicts(2), 'edges': edge_dicts((1, 2)), 'next': 3}

    # When
    cfg = KCFG.from_dict(d)
    cfg_dict1 = cfg.to_dict()
    cfg_dict2 = cfg.to_dict()

    # Then
    assert cfg_dict1 == cfg_dict2


def test_create_node() -> None:
    # Given
    cfg = KCFG()

    # When
    new_node = cfg.create_node(term(1))

    # Then
    assert new_node == node(1)
    assert set(cfg.nodes) == {node(1)}
    assert not cfg.is_stuck(new_node.id)


def test_remove_unknown_node() -> None:
    # Given
    cfg = KCFG()

    # Then
    with pytest.raises(ValueError):
        # When
        cfg.remove_node(0)


def test_remove_node() -> None:
    # Given
    d = {'nodes': node_dicts(3), 'edges': edge_dicts((1, 2), (2, 3))}
    cfg = KCFG.from_dict(d)

    # When
    cfg.remove_node(2)

    # Then
    assert set(cfg.nodes) == {node(1), node(3)}
    assert set(cfg.edges()) == set()
    assert not cfg.is_stuck(1)
    with pytest.raises(ValueError):
        cfg.node(2)
    with pytest.raises(ValueError):
        cfg.edge(1, 2)
    with pytest.raises(ValueError):
        cfg.edge(2, 3)


def test_cover_then_remove() -> None:
    # Given
    cfg = KCFG()

    # When
    node1 = cfg.create_node(CTerm(KApply('<top>', token(1))))
    node2 = cfg.create_node(CTerm(KApply('<top>', KVariable('X'))))
    cover = cfg.create_cover(node1.id, node2.id)

    # Then
    assert cfg.is_covered(node1.id)
    assert not cfg.is_covered(node2.id)
    assert dict(cover.csubst.subst) == {'X': token(1)}
    assert cfg.covers() == [cover]

    # When
    cfg.remove_cover(node1.id, node2.id)

    # Then
    assert not cfg.is_covered(node1.id)
    assert not cfg.is_covered(node2.id)
    assert cfg.covers() == []


def test_insert_simple_edge() -> None:
    # Given
    d = {'nodes': node_dicts(2)}
    cfg = KCFG.from_dict(d)

    # When
    new_edge = cfg.create_edge(1, 2, 1)

    # Then
    assert new_edge == edge(1, 2)
    assert set(cfg.nodes) == {node(1), node(2)}
    assert set(cfg.edges()) == {edge(1, 2)}


def test_get_successors() -> None:
    d = {
        'next': 19,
        'nodes': node_dicts(18),
        'edges': edge_dicts((11, 12)),
        'splits': split_dicts((12, [(13, mlTop()), (14, mlTop())])),
        'covers': cover_dicts((14, 11)),
        'ndbranches': ndbranch_dicts((13, [(16, False), (17, False)])),
    }
    cfg = KCFG.from_dict(d)

    # When
    edges = set(cfg.edges(source_id=11))
    covers = set(cfg.covers(source_id=14))
    splits = sorted(cfg.splits(source_id=12))
    ndbranches = set(cfg.ndbranches(source_id=13))

    # Then
    assert edges == {edge(11, 12)}
    assert covers == {cover(14, 11)}
    assert splits == [split(12, [13, 14])]
    assert ndbranches == {ndbranch(13, [16, 17])}
    assert cfg.to_dict() == d


def test_get_predecessors() -> None:
    d = {'nodes': node_dicts(3), 'edges': edge_dicts((1, 3), (2, 3))}
    cfg = KCFG.from_dict(d)

    # When
    preds = set(cfg.edges(target_id=3))

    # Then
    assert preds == {edge(1, 3), edge(2, 3)}


def test_reachable_nodes() -> None:
    # Given
    d = {
        'nodes': node_dicts(20),
        'edges': edge_dicts((13, 15), (14, 15), (15, 12)),
        'covers': cover_dicts((12, 13)),
        'splits': split_dicts(
            (16, [(12, mlTop()), (13, mlTop()), (17, mlTop())]), (17, [(12, mlTop()), (18, mlTop())])
        ),
        'ndbranches': ndbranch_dicts((18, [(19, False), (20, False)])),
    }
    cfg = KCFG.from_dict(d)

    # When
    nodes_2 = cfg.reachable_nodes(12)
    nodes_3 = cfg.reachable_nodes(16)
    nodes_4 = cfg.reachable_nodes(13, reverse=True)
    nodes_5 = cfg.reachable_nodes(19, reverse=True)

    # Then
    assert nodes_2 == {node(12), node(13), node(15)}
    assert nodes_3 == {node(16), node(12), node(13), node(17), node(18), node(15), node(19), node(20)}
    assert nodes_4 == {node(13), node(16), node(12), node(15), node(17), node(14)}
    assert nodes_5 == {node(19), node(18), node(17), node(16)}


def test_paths_between() -> None:
    # Given
    d = {
        'nodes': node_dicts(20),
        'edges': edge_dicts((13, 15), (14, 15), (15, 12)),
        'covers': cover_dicts((12, 13)),
        'splits': split_dicts(
            (16, [(12, mlTop()), (13, mlTop()), (17, mlTop())]), (17, [(12, mlTop()), (18, mlTop())])
        ),
        'ndbranches': ndbranch_dicts((18, [(19, False), (20, False)])),
    }
    cfg = KCFG.from_dict(d)

    # When
    paths = sorted(cfg.paths_between(16, 15))

    # Then
    assert paths == [
        (split(16, [12]), cover(12, 13), edge(13, 15)),
        (split(16, [13]), edge(13, 15)),
        (split(16, [17]), split(17, [12]), cover(12, 13), edge(13, 15)),
    ]

    # When
    paths = sorted(cfg.paths_between(17, 20))

    # Then
    assert paths == [
        (split(17, [18]), ndbranch(18, [20])),
    ]


def test_resolve() -> None:
    # Given
    d = {
        'nodes': node_dicts(4),
    }
    cfg = KCFG.from_dict(d)

    assert node(1) == cfg.node(1)


def test_vacuous() -> None:
    # Given
    d = {
        'nodes': node_dicts(4),
        'edges': edge_dicts((1, 2), (2, 3)),
        'aliases': {'foo': 2},
    }

    cfg = KCFG.from_dict(d)
    cfg.add_vacuous(3)
    assert cfg.vacuous, node(3)


def test_replace_node() -> None:
    # Given
    d = {
        'nodes': node_dicts(4),
        'edges': edge_dicts((1, 2), (2, 3)),
    }

    cfg = KCFG.from_dict(d)
    cfg.replace_node(2, term(5))

    node = cfg.node(2)
    assert node is not None
    assert node.cterm == term(5)

    first_edge = cfg.edge(1, 2)
    assert first_edge is not None
    assert first_edge.target.cterm == term(5)

    second_edge = cfg.edge(2, 3)
    assert second_edge is not None
    assert second_edge.source.cterm == term(5)


def test_aliases() -> None:
    # Given
    d = {
        'nodes': node_dicts(4),
        'edges': edge_dicts((1, 2), (2, 3)),
        'aliases': {'foo': 2},
    }

    cfg = KCFG.from_dict(d)
    assert cfg.node('@foo'), node(2)

    cfg.add_alias('bar', 1)
    cfg.add_alias('bar2', 1)
    assert cfg.node('@bar'), node(1)
    assert cfg.node('@bar2'), node(1)
    cfg.remove_alias('bar')
    with pytest.raises(ValueError, match='Unknown alias: @bar'):
        cfg.node('@bar')

    with pytest.raises(ValueError, match='Duplicate alias: bar2'):
        cfg.add_alias('bar2', 2)
    with pytest.raises(ValueError, match='Alias may not contain "@"'):
        cfg.add_alias('@buzz', 2)
    with pytest.raises(ValueError, match='Unknown node: 10'):
        cfg.add_alias('buzz', 10)


def test_lifting_functions_manual() -> None:
    #                                                                      /-- Y >=Int 0 -- 8
    #                                   /-- X >=Int 0 --> 4 --10 steps--> 6
    #  1 --25 steps--> 2 --30 steps--> 3                                   \-- Y  <Int 0 -- 9
    #                                   \
    #                                    \-- X <Int 0 --> 5 --20 steps--> 7 --15 steps--> 10

    # Given
    config = KApply('<top>', [KVariable('X', sort=KSort('Int'))])

    x_ge_0 = mlEqualsTrue(geInt(KVariable('X'), intToken(0)))
    x_lt_0 = mlEqualsTrue(ltInt(KVariable('X'), intToken(0)))
    y_ge_0 = mlEqualsTrue(geInt(KVariable('Y'), intToken(0)))
    y_lt_0 = mlEqualsTrue(ltInt(KVariable('Y'), intToken(0)))

    node_1 = KCFG.Node(1, CTerm(config, [mlTop()]))
    node_3 = KCFG.Node(3, CTerm(config, [mlTop()]))
    node_4 = KCFG.Node(4, CTerm(config, [x_ge_0]))
    node_5 = KCFG.Node(5, CTerm(config, [x_lt_0]))
    node_10 = KCFG.Node(10, CTerm(config, [x_lt_0]))

    cfg = KCFG()

    cfg.create_node(CTerm(config, [mlTop()]))
    cfg.create_node(CTerm(config, [mlTop()]))
    cfg.create_node(CTerm(config, [mlTop()]))
    cfg.create_node(CTerm(config, [x_ge_0]))
    cfg.create_node(CTerm(config, [x_lt_0]))
    cfg.create_node(CTerm(config, [x_ge_0]))
    cfg.create_node(CTerm(config, [x_lt_0]))
    cfg.create_node(CTerm(config, [x_ge_0, y_ge_0]))
    cfg.create_node(CTerm(config, [x_ge_0, y_lt_0]))
    cfg.create_node(CTerm(config, [x_lt_0]))

    cfg.create_edge(1, 2, 25, ['rule_1', 'rule_2'])
    cfg.create_edge(2, 3, 30, ['rule_3', 'rule_4'])
    cfg.create_split(3, [(4, CSubst(constraints=[x_ge_0])), (5, CSubst(constraints=[x_lt_0]))])
    cfg.create_edge(4, 6, 10, ['rule 5'])
    cfg.create_edge(5, 7, 20, ['rule_6', 'rule_7', 'rule_8'])
    cfg.create_split(6, [(8, CSubst(constraints=[y_ge_0])), (9, CSubst(constraints=[y_lt_0]))])
    cfg.create_edge(7, 10, 15, ['rule_9'])

    # Impossible edge lifts
    for id in [1, 3, 4, 5, 6, 8, 9, 10]:
        with pytest.raises(ValueError, match='Expected a single element, found none'):
            cfg.lift_edge(id)

    # Impossible split lifts
    for id in [1, 2, 4, 5, 7, 8, 9, 10]:
        with pytest.raises(ValueError, match='Expected a single element, found none'):
            cfg.lift_split(id)
    with pytest.raises(
        AssertionError, match='Cannot lift split at node 6 due to branching on freshly introduced variables'
    ):
        cfg.lift_split(6)

    # Lift edge `1 -> 2 -> 3` and check correctness
    cfg.lift_edge(2)
    assert not cfg.get_node(2)
    assert cfg.contains_edge(KCFG.Edge(node_1, node_3, 55, ('rule_1', 'rule_2', 'rule_3', 'rule_4')))
    assert cfg.contains_edge(KCFG.Edge(node_1, node_3, 55, ('rule_1', 'rule_2', 'rule_3', 'rule_4')))

    # Lift edge `5 -> 7 -> 10` and check correctness
    cfg.lift_edge(7)
    assert not cfg.get_node(7)
    assert cfg.contains_edge(KCFG.Edge(node_5, node_10, 35, ('rule_6', 'rule_7', 'rule_8', 'rule_9')))
    assert cfg.contains_edge(KCFG.Edge(node_5, node_10, 35, ('rule_6', 'rule_7', 'rule_8', 'rule_9')))

    # Lift split `1 -> 3 -> [4, 5]` and check correctness
    cfg.lift_split(3)
    assert not cfg.get_node(3)

    node_11 = KCFG.Node(11, CTerm(config, [x_ge_0]))
    node_12 = KCFG.Node(12, CTerm(config, [x_lt_0]))

    assert cfg.node(11) == node_11
    assert cfg.node(12) == node_12
    assert cfg._node_id == 13

    assert cfg.contains_edge(KCFG.Edge(node_11, node_4, 55, ('rule_1', 'rule_2', 'rule_3', 'rule_4')))
    assert cfg.contains_edge(KCFG.Edge(node_12, node_5, 55, ('rule_1', 'rule_2', 'rule_3', 'rule_4')))
    assert cfg.contains_split(
        KCFG.Split(node_1, [(node_11, CSubst(constraints=[x_ge_0])), (node_12, CSubst(constraints=[x_lt_0]))])
    )


def test_lifting_functions_automatic() -> None:
    #                                                    /-- Y >=Int 0 --> 10
    #                           /-- X >=Int 0 --> 6 --> 8
    #  1 --> 2 --> 3 --> 4 --> 5                         \-- Y  <Int 0 --> 11
    #                           \
    #                            \-- X <Int 0 --> 7 --> 9 --> 12 --> 13

    # Given
    config = KApply('<top>', [KApply('_+Int_', [KVariable('X', sort=KSort('Int')), KVariable('Y', sort=KSort('Int'))])])

    x_ge_0 = mlEqualsTrue(geInt(KVariable('X'), intToken(0)))
    x_lt_0 = mlEqualsTrue(ltInt(KVariable('X'), intToken(0)))
    y_ge_0 = mlEqualsTrue(geInt(KVariable('Y'), intToken(0)))
    y_lt_0 = mlEqualsTrue(ltInt(KVariable('Y'), intToken(0)))

    node_1 = KCFG.Node(1, CTerm(config, [mlTop()]))
    node_5 = KCFG.Node(5, CTerm(config, [mlTop()]))
    node_7 = KCFG.Node(7, CTerm(config, [x_lt_0]))
    node_10 = KCFG.Node(10, CTerm(config, [x_ge_0, y_ge_0]))
    node_11 = KCFG.Node(11, CTerm(config, [x_ge_0, y_lt_0]))
    node_13 = KCFG.Node(13, CTerm(config, [x_lt_0]))

    cfg = KCFG()

    cfg.create_node(CTerm(config, [mlTop()]))
    cfg.create_node(CTerm(config, [mlTop()]))
    cfg.create_node(CTerm(config, [mlTop()]))
    cfg.create_node(CTerm(config, [mlTop()]))
    cfg.create_node(CTerm(config, [mlTop()]))
    cfg.create_node(CTerm(config, [x_ge_0]))
    cfg.create_node(CTerm(config, [x_lt_0]))
    cfg.create_node(CTerm(config, [x_ge_0]))
    cfg.create_node(CTerm(config, [x_lt_0]))
    cfg.create_node(CTerm(config, [x_ge_0, y_ge_0]))
    cfg.create_node(CTerm(config, [x_ge_0, y_lt_0]))
    cfg.create_node(CTerm(config, [x_lt_0]))
    cfg.create_node(CTerm(config, [x_lt_0]))

    cfg.create_edge(1, 2, 5, ['rule_1'])
    cfg.create_edge(2, 3, 10, ['rule_2'])
    cfg.create_edge(3, 4, 15, ['rule_3'])
    cfg.create_edge(4, 5, 20, ['rule_4'])
    cfg.create_split(5, [(6, CSubst(constraints=[x_ge_0])), (7, CSubst(constraints=[x_lt_0]))])
    cfg.create_edge(6, 8, 25, ['rule_5'])
    cfg.create_edge(7, 9, 30, ['rule_6'])
    cfg.create_split(8, [(10, CSubst(constraints=[y_ge_0])), (11, CSubst(constraints=[y_lt_0]))])
    cfg.create_edge(9, 12, 35, ['rule_7'])
    cfg.create_edge(12, 13, 40, ['rule_8'])

    # Apply edge lifting and check correctness
    cfg.lift_edges()

    #                                 /-- Y >=Int 0 --> 10
    #         /-- X >=Int 0 --> 6 --> 8
    #  1 --> 5                         \-- Y  <Int 0 --> 11
    #         \
    #          \-- X <Int 0 --> 7 --> 13

    # Nodes removed
    assert cfg._deleted_nodes == {2, 3, 4, 9, 12}

    # Structure
    assert cfg.contains_edge(KCFG.Edge(node_1, node_5, 50, ('rule_1', 'rule_2', 'rule_3', 'rule_4')))
    assert cfg.contains_edge(KCFG.Edge(node_7, node_13, 105, ('rule_6', 'rule_7', 'rule_8')))

    # Apply split lifting and check correctness
    cfg.lift_splits()

    #                       /-- Y >=Int 0 --> 18 -> 16 --> 10
    #   /-- X >=Int 0 --> 14
    #  1                    \-- Y  <Int 0 --> 19 -> 17 --> 11
    #   \
    #    \-- X <Int 0 --> 15 --> 7 --> 13

    # Nodes removed
    assert cfg._deleted_nodes == {2, 3, 4, 5, 6, 8, 9, 12}

    # Nodes added
    node_14 = KCFG.Node(14, CTerm(config, [x_ge_0]))
    node_15 = KCFG.Node(15, CTerm(config, [x_lt_0]))
    node_16 = KCFG.Node(16, CTerm(config, [x_ge_0, y_ge_0]))
    node_17 = KCFG.Node(17, CTerm(config, [x_ge_0, y_lt_0]))
    node_18 = KCFG.Node(18, CTerm(config, [x_ge_0, y_ge_0]))
    node_19 = KCFG.Node(19, CTerm(config, [x_ge_0, y_lt_0]))
    assert cfg.node(14) == node_14
    assert cfg.node(15) == node_15
    assert cfg.node(16) == node_16
    assert cfg.node(17) == node_17
    assert cfg.node(18) == node_18
    assert cfg.node(19) == node_19
    assert cfg._node_id == 20

    # Structure
    assert cfg.contains_split(
        KCFG.Split(node_1, [(node_14, CSubst(constraints=[x_ge_0])), (node_15, CSubst(constraints=[x_lt_0]))])
    )
    assert cfg.contains_split(
        KCFG.Split(node_14, [(node_18, CSubst(constraints=[y_ge_0])), (node_19, CSubst(constraints=[y_lt_0]))])
    )
    assert cfg.contains_edge(KCFG.Edge(node_18, node_16, 50, ('rule_1', 'rule_2', 'rule_3', 'rule_4')))
    assert cfg.contains_edge(KCFG.Edge(node_16, node_10, 25, ('rule_5',)))
    assert cfg.contains_edge(KCFG.Edge(node_19, node_17, 50, ('rule_1', 'rule_2', 'rule_3', 'rule_4')))
    assert cfg.contains_edge(KCFG.Edge(node_17, node_11, 25, ('rule_5',)))
    assert cfg.contains_edge(KCFG.Edge(node_15, node_7, 50, ('rule_1', 'rule_2', 'rule_3', 'rule_4')))


def test_minimize() -> None:
    #                                                    /-- Y >=Int 0 --> 10
    #                           /-- X >=Int 0 --> 6 --> 8
    #  1 --> 2 --> 3 --> 4 --> 5                         \-- Y  <Int 0 --> 11
    #                           \
    #                            \-- X <Int 0 --> 7 --> 9 --> 12 --> 13

    # Given
    config = KApply('<top>', [KApply('_+Int_', [KVariable('X', sort=KSort('Int')), KVariable('Y', sort=KSort('Int'))])])

    x_ge_0 = mlEqualsTrue(geInt(KVariable('X'), intToken(0)))
    x_lt_0 = mlEqualsTrue(ltInt(KVariable('X'), intToken(0)))
    y_ge_0 = mlEqualsTrue(geInt(KVariable('Y'), intToken(0)))
    y_lt_0 = mlEqualsTrue(ltInt(KVariable('Y'), intToken(0)))

    node_1 = KCFG.Node(1, CTerm(config, [mlTop()]))
    node_10 = KCFG.Node(10, CTerm(config, [x_ge_0, y_ge_0]))
    node_11 = KCFG.Node(11, CTerm(config, [x_ge_0, y_lt_0]))
    node_13 = KCFG.Node(13, CTerm(config, [x_lt_0]))

    cfg = KCFG()

    cfg.create_node(CTerm(config, [mlTop()]))
    cfg.create_node(CTerm(config, [mlTop()]))
    cfg.create_node(CTerm(config, [mlTop()]))
    cfg.create_node(CTerm(config, [mlTop()]))
    cfg.create_node(CTerm(config, [mlTop()]))
    cfg.create_node(CTerm(config, [x_ge_0]))
    cfg.create_node(CTerm(config, [x_lt_0]))
    cfg.create_node(CTerm(config, [x_ge_0]))
    cfg.create_node(CTerm(config, [x_lt_0]))
    cfg.create_node(CTerm(config, [x_ge_0, y_ge_0]))
    cfg.create_node(CTerm(config, [x_ge_0, y_lt_0]))
    cfg.create_node(CTerm(config, [x_lt_0]))
    cfg.create_node(CTerm(config, [x_lt_0]))

    cfg.create_edge(1, 2, 5, ['rule_1'])
    cfg.create_edge(2, 3, 10, ['rule_2'])
    cfg.create_edge(3, 4, 15, ['rule_3'])
    cfg.create_edge(4, 5, 20, ['rule_4'])
    cfg.create_split(5, [(6, CSubst(constraints=[x_ge_0])), (7, CSubst(constraints=[x_lt_0]))])
    cfg.create_edge(6, 8, 25, ['rule_5'])
    cfg.create_edge(7, 9, 30, ['rule_6'])
    cfg.create_split(8, [(10, CSubst(constraints=[y_ge_0])), (11, CSubst(constraints=[y_lt_0]))])
    cfg.create_edge(9, 12, 35, ['rule_7'])
    cfg.create_edge(12, 13, 40, ['rule_8'])

    # Apply kcfg minimization and check correctness
    cfg.minimize()

    #                       /-- Y >=Int 0 --> 18 --> 10
    #   /-- X >=Int 0 --> 14
    #  1                    \-- Y  <Int 0 --> 19 --> 11
    #   \
    #    \-- X <Int 0 --> 15 --> 13

    # Nodes still present
    assert cfg.node(1) == node_1
    assert cfg.node(10) == node_10
    assert cfg.node(11) == node_11
    assert cfg.node(13) == node_13

    # Nodes removed
    assert cfg._deleted_nodes == {2, 3, 4, 5, 6, 7, 8, 9, 12, 16, 17}

    # Nodes added and still present
    node_14 = KCFG.Node(14, CTerm(config, [x_ge_0]))
    node_15 = KCFG.Node(15, CTerm(config, [x_lt_0]))
    node_18 = KCFG.Node(18, CTerm(config, [x_ge_0, y_ge_0]))
    node_19 = KCFG.Node(19, CTerm(config, [x_ge_0, y_lt_0]))
    assert cfg.node(14) == node_14
    assert cfg.node(15) == node_15
    assert cfg.node(18) == node_18
    assert cfg.node(19) == node_19
    assert cfg._node_id == 20

    # Structure
    assert cfg.contains_split(
        KCFG.Split(node_1, [(node_14, CSubst(constraints=[x_ge_0])), (node_15, CSubst(constraints=[x_lt_0]))])
    )
    assert cfg.contains_split(
        KCFG.Split(node_14, [(node_18, CSubst(constraints=[y_ge_0])), (node_19, CSubst(constraints=[y_lt_0]))])
    )
    assert cfg.contains_edge(KCFG.Edge(node_18, node_10, 75, ('rule_1', 'rule_2', 'rule_3', 'rule_4', 'rule_5')))
    assert cfg.contains_edge(KCFG.Edge(node_19, node_11, 75, ('rule_1', 'rule_2', 'rule_3', 'rule_4', 'rule_5')))
    assert cfg.contains_edge(
        KCFG.Edge(node_15, node_13, 155, ('rule_1', 'rule_2', 'rule_3', 'rule_4', 'rule_6', 'rule_7', 'rule_8'))
    )


def test_write_cfg_data(tmp_path: Path) -> None:
    def _written_nodes() -> set[str]:
        return {nd_path.name for nd_path in (tmp_path / 'nodes').iterdir()}

    kcfg = KCFG(cfg_dir=tmp_path)

    kcfg.add_node(node(1))
    kcfg.add_node(node(2))
    kcfg.add_node(node(3))

    assert _written_nodes() == set()

    kcfg.write_cfg_data()

    assert _written_nodes() == {'1.json', '2.json', '3.json'}

    kcfg.add_node(node(4))
    kcfg.remove_node(1)
    kcfg.remove_node(2)
    kcfg.replace_node(3, node(3).cterm)
    kcfg.add_node(node(2))

    assert _written_nodes() == {'1.json', '2.json', '3.json'}

    kcfg.write_cfg_data()

    assert _written_nodes() == {'2.json', '3.json', '4.json'}


def test_pretty_print() -> None:
    def _x_equals(i: int) -> KInner:
        return mlEquals(KVariable('x'), token(i))

    d = {
        'nodes': node_dicts(15, start=10) + predicate_node_dicts(1, start=25),
        'aliases': {'foo': 14, 'bar': 14},
        'edges': edge_dicts((21, 12), (12, 13, 5), (13, 14), (15, 16), (16, 13), (18, 17), (22, 19)),
        'covers': cover_dicts((19, 22)),
        'splits': split_dicts(
            (
                14,
                [
                    (15, _x_equals(15)),
                    (16, _x_equals(16)),
                    (17, _x_equals(17)),
                    (18, _x_equals(18)),
                    (20, _x_equals(20)),
                    (23, _x_equals(23)),
                    (22, _x_equals(22)),
                ],
            )
        ),
        'ndbranches': ndbranch_dicts((20, [(24, False), (25, True)])),
        'stuck': [23],
        'vacuous': [17],
    }
    cfg = KCFG.from_dict(d)

    expected = (
        '\n'
        '┌─ 21 (root)\n'
        '│\n'
        '│  (1 step)\n'
        '├─ 12\n'
        '│\n'
        '│  (5 steps)\n'
        '├─ 13\n'
        '│\n'
        '│  (1 step)\n'
        '├─ 14 (split, @bar, @foo)\n'
        '┃\n'
        '┃ (branch)\n'
        '┣━━┓ constraint: _==K_ ( x , 15 )\n'
        '┃  ┃ subst: V14 <- V15\n'
        '┃  │\n'
        '┃  ├─ 15\n'
        '┃  │\n'
        '┃  │  (1 step)\n'
        '┃  ├─ 16\n'
        '┃  │\n'
        '┃  │  (1 step)\n'
        '┃  └─ 13\n'
        '┃     (looped back)\n'
        '┃\n'
        '┣━━┓ constraint: _==K_ ( x , 16 )\n'
        '┃  ┃ subst: V14 <- V16\n'
        '┃  │\n'
        '┃  └─ 16\n'
        '┃     (continues as previously)\n'
        '┃\n'
        '┣━━┓ constraint: _==K_ ( x , 17 )\n'
        '┃  ┃ subst: V14 <- V17\n'
        '┃  │\n'
        '┃  └─ 17 (vacuous, leaf)\n'
        '┃\n'
        '┣━━┓ constraint: _==K_ ( x , 18 )\n'
        '┃  ┃ subst: V14 <- V18\n'
        '┃  │\n'
        '┃  ├─ 18\n'
        '┃  │\n'
        '┃  │  (1 step)\n'
        '┃  └─ 17 (vacuous, leaf)\n'
        '┃\n'
        '┣━━┓ constraint: _==K_ ( x , 20 )\n'
        '┃  ┃ subst: V14 <- V20\n'
        '┃  │\n'
        '┃  ├─ 20\n'
        '┃  ┃\n'
        '┃  ┃ (1 step)\n'
        '┃  ┣━━┓\n'
        '┃  ┃  │\n'
        '┃  ┃  └─ 24 (leaf)\n'
        '┃  ┃\n'
        '┃  ┗━━┓\n'
        '┃     │\n'
        '┃     └─ 25 (leaf)\n'
        '┃\n'
        '┣━━┓ constraint: _==K_ ( x , 23 )\n'
        '┃  ┃ subst: V14 <- V23\n'
        '┃  │\n'
        '┃  └─ 23 (stuck, leaf)\n'
        '┃\n'
        '┗━━┓ constraint: _==K_ ( x , 22 )\n'
        '   ┃ subst: V14 <- V22\n'
        '   │\n'
        '   ├─ 22\n'
        '   │\n'
        '   │  (1 step)\n'
        '   ├─ 19\n'
        '   │\n'
        '   ┊  constraint: true\n'
        '   ┊  subst: V22 <- V19\n'
        '   └─ 22\n'
        '      (looped back)\n'
        '\n'
        '\n'
        '┌─ 10 (root, leaf)\n'
        '\n'
        '┌─ 11 (root, leaf)\n'
    )

    expected_full_printer = (
        '\n'
        '┌─ 21 (root)\n'
        '│     <top>\n'
        '│       V21\n'
        '│     </top>\n'
        '│\n'
        '│  (1 step)\n'
        '├─ 12\n'
        '│     <top>\n'
        '│       V12\n'
        '│     </top>\n'
        '│\n'
        '│  (5 steps)\n'
        '├─ 13\n'
        '│     <top>\n'
        '│       V13\n'
        '│     </top>\n'
        '│\n'
        '│  (1 step)\n'
        '├─ 14 (split, @bar, @foo)\n'
        '│     <top>\n'
        '│       V14\n'
        '│     </top>\n'
        '┃\n'
        '┃ (branch)\n'
        '┣━━┓ constraint: _==K_ ( x , 15 )\n'
        '┃  ┃ subst: V14 <- V15\n'
        '┃  │\n'
        '┃  ├─ 15\n'
        '┃  │     <top>\n'
        '┃  │       V15\n'
        '┃  │     </top>\n'
        '┃  │\n'
        '┃  │  (1 step)\n'
        '┃  ├─ 16\n'
        '┃  │     <top>\n'
        '┃  │       V16\n'
        '┃  │     </top>\n'
        '┃  │\n'
        '┃  │  (1 step)\n'
        '┃  └─ 13\n'
        '┃        <top>\n'
        '┃          V13\n'
        '┃        </top>\n'
        '┃     (looped back)\n'
        '┃\n'
        '┣━━┓ constraint: _==K_ ( x , 16 )\n'
        '┃  ┃ subst: V14 <- V16\n'
        '┃  │\n'
        '┃  └─ 16\n'
        '┃        <top>\n'
        '┃          V16\n'
        '┃        </top>\n'
        '┃     (continues as previously)\n'
        '┃\n'
        '┣━━┓ constraint: _==K_ ( x , 17 )\n'
        '┃  ┃ subst: V14 <- V17\n'
        '┃  │\n'
        '┃  └─ 17 (vacuous, leaf)\n'
        '┃        <top>\n'
        '┃          V17\n'
        '┃        </top>\n'
        '┃\n'
        '┣━━┓ constraint: _==K_ ( x , 18 )\n'
        '┃  ┃ subst: V14 <- V18\n'
        '┃  │\n'
        '┃  ├─ 18\n'
        '┃  │     <top>\n'
        '┃  │       V18\n'
        '┃  │     </top>\n'
        '┃  │\n'
        '┃  │  (1 step)\n'
        '┃  └─ 17 (vacuous, leaf)\n'
        '┃        <top>\n'
        '┃          V17\n'
        '┃        </top>\n'
        '┃\n'
        '┣━━┓ constraint: _==K_ ( x , 20 )\n'
        '┃  ┃ subst: V14 <- V20\n'
        '┃  │\n'
        '┃  ├─ 20\n'
        '┃  │     <top>\n'
        '┃  │       V20\n'
        '┃  │     </top>\n'
        '┃  ┃\n'
        '┃  ┃ (1 step)\n'
        '┃  ┣━━┓\n'
        '┃  ┃  │\n'
        '┃  ┃  └─ 24 (leaf)\n'
        '┃  ┃        <top>\n'
        '┃  ┃          V24\n'
        '┃  ┃        </top>\n'
        '┃  ┃\n'
        '┃  ┗━━┓\n'
        '┃     │\n'
        '┃     └─ 25 (leaf)\n'
        '┃           <top>\n'
        '┃             V25\n'
        '┃           </top>\n'
        '┃           #And #Equals ( x , 25 )\n'
        '┃\n'
        '┣━━┓ constraint: _==K_ ( x , 23 )\n'
        '┃  ┃ subst: V14 <- V23\n'
        '┃  │\n'
        '┃  └─ 23 (stuck, leaf)\n'
        '┃        <top>\n'
        '┃          V23\n'
        '┃        </top>\n'
        '┃\n'
        '┗━━┓ constraint: _==K_ ( x , 22 )\n'
        '   ┃ subst: V14 <- V22\n'
        '   │\n'
        '   ├─ 22\n'
        '   │     <top>\n'
        '   │       V22\n'
        '   │     </top>\n'
        '   │\n'
        '   │  (1 step)\n'
        '   ├─ 19\n'
        '   │     <top>\n'
        '   │       V19\n'
        '   │     </top>\n'
        '   │\n'
        '   ┊  constraint: true\n'
        '   ┊  subst: V22 <- V19\n'
        '   └─ 22\n'
        '         <top>\n'
        '           V22\n'
        '         </top>\n'
        '      (looped back)\n'
        '\n'
        '\n'
        '┌─ 10 (root, leaf)\n'
        '│     <top>\n'
        '│       10\n'
        '│     </top>\n'
        '\n'
        '┌─ 11 (root, leaf)\n'
        '│     <top>\n'
        '│       V11\n'
        '│     </top>\n'
    )

    # When
    kcfg_show = KCFGShow(MockKPrint(), node_printer=NodePrinter(MockKPrint()))
    kcfg_show_full_printer = KCFGShow(MockKPrint(), node_printer=NodePrinter(MockKPrint(), full_printer=True))
    actual = '\n'.join(kcfg_show.pretty(cfg)) + '\n'
    actual_full_printer = '\n'.join(kcfg_show_full_printer.pretty(cfg)) + '\n'

    # Then
    assert actual == expected
    assert actual_full_printer == expected_full_printer
