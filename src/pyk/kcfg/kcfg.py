from __future__ import annotations

import json
from abc import ABC, abstractmethod
from collections.abc import Container
from dataclasses import dataclass
from threading import RLock
from typing import TYPE_CHECKING, List, Union, cast, final

from ..cterm import CSubst, CTerm
from ..kast.manip import (
    bool_to_ml_pred,
    extract_lhs,
    extract_rhs,
    flatten_label,
    remove_source_attributes,
    rename_generated_vars,
)
from ..prelude.ml import mlAnd, mlTop
from ..utils import compare_short_hashes, shorten_hash

if TYPE_CHECKING:
    from collections.abc import Callable, Iterable, Mapping
    from types import TracebackType
    from typing import Any

    from ..kast.inner import KInner
    from ..kast.outer import KClaim, KDefinition


class KCFG(Container[Union['KCFG.Node', 'KCFG.Successor']]):
    @final
    @dataclass(frozen=True, order=True)
    class Node:
        cterm: CTerm

        @property
        def id(self) -> str:
            return self.cterm.hash

        def to_dict(self) -> dict[str, Any]:
            return {'id': self.id, 'cterm': self.cterm.to_dict()}

    class Successor(ABC):
        source: KCFG.Node

        def __lt__(self, other: Any) -> bool:
            if not isinstance(other, KCFG.Successor):
                return NotImplemented
            return self.source < other.source

        @property
        @abstractmethod
        def targets(self) -> tuple[KCFG.Node, ...]:
            ...

        @property
        def target_ids(self) -> list[str]:
            return sorted([target.id for target in self.targets])

    class EdgeLike(Successor):
        source: KCFG.Node
        target: KCFG.Node

        @property
        def targets(self) -> tuple[KCFG.Node, ...]:
            return (self.target,)

    @final
    @dataclass(frozen=True)
    class Edge(EdgeLike):
        source: KCFG.Node
        target: KCFG.Node
        depth: int

        def to_dict(self) -> dict[str, Any]:
            return {
                'source': self.source.id,
                'target': self.target.id,
                'depth': self.depth,
            }

    @final
    @dataclass(frozen=True)
    class Cover(EdgeLike):
        source: KCFG.Node
        target: KCFG.Node
        csubst: CSubst

        def to_dict(self) -> dict[str, Any]:
            return {
                'source': self.source.id,
                'target': self.target.id,
                'csubst': self.csubst.to_dict(),
            }

    @dataclass(frozen=True)
    class MultiEdge(Successor):
        source: KCFG.Node

        def __lt__(self, other: Any) -> bool:
            if not type(other) is type(self):
                return NotImplemented
            return (self.source, self.target_ids) < (other.source, other.target_ids)

        @abstractmethod
        def with_single_target(self, target: KCFG.Node) -> KCFG.MultiEdge:
            ...

    @final
    @dataclass(frozen=True)
    class Split(MultiEdge):
        source: KCFG.Node
        _targets: tuple[tuple[KCFG.Node, CSubst], ...]

        def __init__(self, source: KCFG.Node, _targets: Iterable[tuple[KCFG.Node, CSubst]]) -> None:
            object.__setattr__(self, 'source', source)
            object.__setattr__(self, '_targets', tuple(_targets))

        def to_dict(self) -> dict[str, Any]:
            return {
                'source': self.source.id,
                'targets': {target.id: self.splits[target.id].to_dict() for target in self.targets},
            }

        @property
        def targets(self) -> tuple[KCFG.Node, ...]:
            return tuple(target for target, _ in self._targets)

        @property
        def splits(self) -> dict[str, CSubst]:
            return {target.id: csubst for target, csubst in self._targets}

        def with_single_target(self, target: KCFG.Node) -> KCFG.Split:
            return KCFG.Split(self.source, ((target, self.splits[target.id]),))

    @final
    @dataclass(frozen=True)
    class NDBranch(MultiEdge):
        source: KCFG.Node
        _targets: tuple[KCFG.Node, ...]

        def __init__(self, source: KCFG.Node, _targets: Iterable[KCFG.Node]) -> None:
            object.__setattr__(self, 'source', source)
            object.__setattr__(self, '_targets', tuple(_targets))

        @property
        def targets(self) -> tuple[KCFG.Node, ...]:
            return self._targets

        def to_dict(self) -> dict[str, Any]:
            return {
                'source': self.source.id,
                'targets': [target.id for target in self.targets],
            }

        def with_single_target(self, target: KCFG.Node) -> KCFG.NDBranch:
            return KCFG.NDBranch(self.source, (target,))

    _nodes: dict[str, Node]
    _edges: dict[str, dict[str, Edge]]
    _covers: dict[str, dict[str, Cover]]
    _splits: dict[str, Split]
    _ndbranches: dict[str, NDBranch]
    _init: set[str]
    _target: set[str]
    _expanded: set[str]
    _aliases: dict[str, str]
    _lock: RLock

    def __init__(self) -> None:  # TODO should be unnecessary
        self._nodes = {}
        self._edges = {}
        self._covers = {}
        self._splits = {}
        self._ndbranches = {}
        self._init = set()
        self._target = set()
        self._expanded = set()
        self._aliases = {}
        self._lock = RLock()

    def __contains__(self, item: object) -> bool:
        if type(item) is KCFG.Node:
            return self.contains_node(item)
        if type(item) is KCFG.Edge:
            return self.contains_edge(item)
        if type(item) is KCFG.Cover:
            return self.contains_cover(item)
        if type(item) is KCFG.Split:
            return self.contains_split(item)
        return False

    def __enter__(self) -> KCFG:
        self._lock.acquire()
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: TracebackType | None,
    ) -> bool:
        self._lock.release()
        if exc_type is None:
            return True
        return False

    @property
    def nodes(self) -> list[Node]:
        return list(self._nodes.values())

    @property
    def init(self) -> list[Node]:
        return [node for node in self.nodes if self.is_init(node.id)]

    @property
    def target(self) -> list[Node]:
        return [node for node in self.nodes if self.is_target(node.id)]

    @property
    def expanded(self) -> list[Node]:
        return [node for node in self.nodes if self.is_expanded(node.id)]

    @property
    def leaves(self) -> list[Node]:
        return [node for node in self.nodes if self.is_leaf(node.id)]

    @property
    def covered(self) -> list[Node]:
        return [node for node in self.nodes if self.is_covered(node.id)]

    @property
    def uncovered(self) -> list[Node]:
        return [node for node in self.nodes if not self.is_covered(node.id)]

    @property
    def frontier(self) -> list[Node]:
        return [node for node in self.nodes if self.is_frontier(node.id)]

    @property
    def stuck(self) -> list[Node]:
        return [node for node in self.nodes if self.is_stuck(node.id)]

    @staticmethod
    def from_claim(defn: KDefinition, claim: KClaim) -> KCFG:
        cfg = KCFG()
        claim_body = claim.body
        claim_body = defn.instantiate_cell_vars(claim_body)
        claim_body = rename_generated_vars(claim_body)

        claim_lhs = CTerm.from_kast(extract_lhs(claim_body)).add_constraint(bool_to_ml_pred(claim.requires))
        init_state = cfg.create_node(claim_lhs)
        cfg.add_init(init_state.id)

        claim_rhs = CTerm.from_kast(extract_rhs(claim_body)).add_constraint(bool_to_ml_pred(claim.ensures))
        target_state = cfg.create_node(claim_rhs)
        cfg.add_target(target_state.id)

        return cfg

    def to_dict(self) -> dict[str, Any]:
        nodes = [node.to_dict() for node in self.nodes]
        edges = [edge.to_dict() for edge in self.edges()]
        covers = [cover.to_dict() for cover in self.covers()]
        splits = dict(sorted((k, s.to_dict()) for k, s in self._splits.items()))
        ndbranches = dict(sorted((k, b.to_dict()) for k, b in self._ndbranches.items()))

        init = sorted(self._init)
        target = sorted(self._target)
        expanded = sorted(self._expanded)
        aliases = dict(sorted(self._aliases.items()))

        res = {
            'nodes': nodes,
            'edges': edges,
            'covers': covers,
            'splits': splits,
            'ndbranches': ndbranches,
            'init': init,
            'target': target,
            'expanded': expanded,
            'aliases': aliases,
        }
        return {k: v for k, v in res.items() if v}

    @staticmethod
    def from_dict(dct: Mapping[str, Any]) -> KCFG:
        cfg = KCFG()

        nodes: dict[str, str] = {}

        def resolve(node_id: str) -> str:
            if node_id not in nodes:
                raise ValueError(f'Undeclared node: {node_id}')
            return nodes[node_id]

        for node_dict in dct.get('nodes') or []:
            cterm = CTerm.from_dict(node_dict['cterm'])
            node = cfg.create_node(cterm)

            node_key = node_dict['id']
            if node_key in nodes:
                raise ValueError(f'Multiple declarations of node: {node_key}')
            nodes[node_key] = node.id

        for edge_dict in dct.get('edges') or []:
            source_id = resolve(edge_dict['source'])
            target_id = resolve(edge_dict['target'])
            depth = edge_dict['depth']
            cfg.create_edge(source_id, target_id, depth)

        for cover_dict in dct.get('covers') or []:
            source_id = resolve(cover_dict['source'])
            target_id = resolve(cover_dict['target'])
            csubst = CSubst.from_dict(cover_dict['csubst'])
            cfg.create_cover(source_id, target_id, csubst=csubst)

        for init_id in dct.get('init') or []:
            cfg.add_init(resolve(init_id))

        for target_id in dct.get('target') or []:
            cfg.add_target(resolve(target_id))

        for expanded_id in dct.get('expanded') or []:
            cfg.add_expanded(resolve(expanded_id))

        for alias, id in dct.get('aliases', {}).items():
            cfg.add_alias(alias=alias, node_id=resolve(id))

        for split_dict in dct.get('splits', {}).values():
            source_id = resolve(split_dict['source'])
            targets = [
                (resolve(target_id), CSubst.from_dict(csubst)) for target_id, csubst in split_dict['targets'].items()
            ]
            cfg.create_split(source_id, targets)

        for ndbranch_dict in dct.get('ndbranches', {}).values():
            source_id = resolve(ndbranch_dict['source'])
            nd_targets = [resolve(target_id) for target_id in ndbranch_dict['targets']]
            cfg.create_ndbranch(source_id, nd_targets)

        return cfg

    def aliases(self, node_id: str) -> list[str]:
        node_id = self._resolve(node_id)
        return [alias for alias, value in self._aliases.items() if node_id == value]

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), sort_keys=True)

    @staticmethod
    def from_json(s: str) -> KCFG:
        return KCFG.from_dict(json.loads(s))

    def node_short_info(
        self, node: Node, node_printer: Callable[[CTerm], Iterable[str]] | None = None, omit_node_hash: bool = False
    ) -> list[str]:
        attrs = self.node_attrs(node.id) + ['@' + alias for alias in sorted(self.aliases(node.id))]
        attr_string = ' (' + ', '.join(attrs) + ')' if attrs else ''
        if omit_node_hash:
            node_hash = 'OMITTED HASH'
        else:
            node_hash = shorten_hash(node.id)
        node_header = node_hash + attr_string
        node_strs = [node_header]
        if node_printer:
            node_strs.extend(f' {nl}' for nl in node_printer(node.cterm))
        return node_strs

    def _resolve_hash(self, id_like: str) -> list[str]:
        return [node_id for node_id in self._nodes if compare_short_hashes(id_like, node_id)]

    def get_unique_init(self) -> Node:
        if len(self.init) > 1:
            raise ValueError(f'Multiple init nodes found: {[shorten_hash(n.id) for n in self.init]}')
        return self.init[0]

    def get_unique_target(self) -> Node:
        if len(self.target) > 1:
            raise ValueError(f'Multiple target nodes found: {[shorten_hash(n.id) for n in self.target]}')
        return self.target[0]

    def get_first_frontier(self) -> Node:
        if len(self.frontier) == 0:
            raise ValueError('No frontiers remaining!')
        return self.frontier[0]

    def _resolve_or_none(self, id_like: str) -> str | None:
        if id_like == '#init':
            return self.get_unique_init().id
        if id_like == '#target':
            return self.get_unique_target().id
        if id_like == '#frontier':
            return self.get_first_frontier().id

        if id_like.startswith('@'):
            if id_like[1:] in self._aliases:
                return self._aliases[id_like[1:]]
            raise ValueError(f'Unknown alias: {id_like}')
        matches = self._resolve_hash(id_like)
        if not matches:
            return None
        if len(matches) > 1:
            raise ValueError(f'Multiple nodes for pattern: {id_like} (matches e.g. {matches[0]} and {matches[1]})')
        return matches[0]

    def _resolve(self, id_like: str) -> str:
        match = self._resolve_or_none(id_like)
        if not match:
            raise ValueError(f'Unknown node: {id_like}')
        return match

    def node(self, node_id: str) -> Node:
        node_id = self._resolve(node_id)
        return self._nodes[node_id]

    def get_node(self, id: str) -> Node | None:
        return self._nodes.get(id)

    def get_node_by_cterm(self, cterm: CTerm) -> Node | None:
        node = KCFG.Node(cterm)
        return self.get_node(node.id)

    def contains_node(self, node: Node) -> bool:
        return bool(self.get_node(node.id))

    def create_node(self, cterm: CTerm) -> Node:
        term = cterm.kast
        term = remove_source_attributes(term)
        cterm = CTerm.from_kast(term)
        node = KCFG.Node(cterm)

        if node.id in self._nodes:
            raise ValueError(f'Node already exists: {node.id}')

        self._nodes[node.id] = node
        return node

    def get_or_create_node(self, cterm: CTerm) -> Node:
        return self.get_node_by_cterm(cterm) or self.create_node(cterm)

    def remove_node(self, node_id: str) -> None:
        node_id = self._resolve(node_id)

        for edge_in in [edge.source for edge in self.edges(target_id=node_id)]:
            self.discard_expanded(edge_in.id)

        self._nodes.pop(node_id)

        self._edges.pop(node_id, None)
        for source_id in list(self._edges):
            self._edges[source_id].pop(node_id, None)
            if not self._edges[source_id]:
                self._edges.pop(source_id)

        self._covers.pop(node_id, None)
        for source_id in list(self._covers):
            self._covers[source_id].pop(node_id, None)
            if not self._covers[source_id]:
                self._covers.pop(source_id)

        self._init.discard(node_id)
        self._target.discard(node_id)
        self._expanded.discard(node_id)

        self._splits = {k: s for k, s in self._splits.items() if k != node_id and node_id not in s.target_ids}
        self._ndbranches = {k: b for k, b in self._ndbranches.items() if k != node_id and node_id not in b.target_ids}

        for alias in [alias for alias, id in self._aliases.items() if id == node_id]:
            self.remove_alias(alias)

    def replace_node(self, node_id: str, new_cterm: CTerm) -> str:
        # Remove old node, record data
        node = self.node(node_id)
        in_edges = self.edges(target_id=node.id)
        out_edges = self.edges(source_id=node.id)
        in_covers = self.covers(target_id=node.id)
        out_covers = self.covers(source_id=node.id)
        init = self.is_init(node.id)
        target = self.is_target(node.id)
        expanded = self.is_expanded(node.id)
        in_expanded = {edge.source.id: self.is_expanded(edge.source.id) for edge in in_edges}
        self.remove_node(node.id)

        # Add the new, update data
        new_node = self.get_or_create_node(new_cterm)
        for in_edge in in_edges:
            self.create_edge(in_edge.source.id, new_node.id, in_edge.depth)
        for out_edge in out_edges:
            self.create_edge(new_node.id, out_edge.target.id, out_edge.depth)
        for in_cover in in_covers:
            self.create_cover(in_cover.source.id, new_node.id, csubst=in_cover.csubst)
        for out_cover in out_covers:
            self.create_cover(new_node.id, out_cover.target.id, csubst=out_cover.csubst)
        if init:
            self.add_init(new_node.id)
        if target:
            self.add_target(new_node.id)
        if expanded:
            self.add_expanded(new_node.id)
        for nid in in_expanded:
            if in_expanded[nid]:
                self.add_expanded(nid)

        return new_node.id

    def successors(
        self, source_id: str, edges: bool = True, covers: bool = True, splits: bool = True, ndbranches: bool = True
    ) -> list[Successor]:
        out_edges: Iterable[KCFG.Successor] = self.edges(source_id=source_id) if edges else []
        out_covers: Iterable[KCFG.Successor] = self.covers(source_id=source_id) if covers else []
        out_splits: Iterable[KCFG.Successor] = self.splits(source_id=source_id) if splits else []
        out_ndbranches: Iterable[KCFG.Successor] = self.ndbranches(source_id=source_id) if ndbranches else []
        return list(out_edges) + list(out_covers) + list(out_splits) + list(out_ndbranches)

    def predecessors(
        self, target_id: str, edges: bool = True, covers: bool = True, splits: bool = True, ndbranches: bool = True
    ) -> list[Successor]:
        in_edges: Iterable[KCFG.Successor] = self.edges(target_id=target_id) if edges else []
        in_covers: Iterable[KCFG.Successor] = self.covers(target_id=target_id) if covers else []
        in_splits: Iterable[KCFG.Successor] = self.splits(target_id=target_id) if splits else []
        in_ndbranches: Iterable[KCFG.Successor] = self.ndbranches(target_id=target_id) if ndbranches else []
        return list(in_edges) + list(in_covers) + list(in_splits) + list(in_ndbranches)

    def _check_no_successors(self, source_id: str) -> None:
        if len(list(self.successors(source_id))) > 0:
            raise ValueError(f'Node already has successors: {source_id} -> {self.successors(source_id)}')

    def edge(self, source_id: str, target_id: str) -> Edge | None:
        source_id = self._resolve(source_id)
        target_id = self._resolve(target_id)
        return self._edges.get(source_id, {}).get(target_id)

    def edges(self, *, source_id: str | None = None, target_id: str | None = None) -> list[Edge]:
        source_id = self._resolve(source_id) if source_id is not None else None
        target_id = self._resolve(target_id) if target_id is not None else None

        res: Iterable[KCFG.Edge]
        if source_id:
            res = self._edges.get(source_id, {}).values()
        else:
            res = (edge for _, targets in self._edges.items() for _, edge in targets.items())

        return [edge for edge in res if not target_id or target_id == edge.target.id]

    def contains_edge(self, edge: Edge) -> bool:
        if other := self.edge(source_id=edge.source.id, target_id=edge.target.id):
            return edge == other
        return False

    def create_edge(self, source_id: str, target_id: str, depth: int) -> Edge:
        self._check_no_successors(source_id)

        if depth <= 0:
            raise ValueError(f'Cannot build KCFG Edge with non-positive depth: {depth}')

        source = self.node(source_id)
        target = self.node(target_id)

        if source.id not in self._edges:
            self._edges[source.id] = {}

        edge = KCFG.Edge(source, target, depth)
        self._edges[source.id][target.id] = edge
        return edge

    def remove_edge(self, source_id: str, target_id: str) -> None:
        source_id = self._resolve(source_id)
        target_id = self._resolve(target_id)
        edge = self.edge(source_id, target_id)

        if not edge:
            raise ValueError(f'Edge does not exist: {source_id} -> {target_id}')

        self._edges[source_id].pop(target_id)
        if not self._edges[source_id]:
            self._edges.pop(source_id)

    def cover(self, source_id: str, target_id: str) -> Cover | None:
        source_id = self._resolve(source_id)
        target_id = self._resolve(target_id)
        return self._covers.get(source_id, {}).get(target_id)

    def covers(self, *, source_id: str | None = None, target_id: str | None = None) -> list[Cover]:
        source_id = self._resolve(source_id) if source_id is not None else None
        target_id = self._resolve(target_id) if target_id is not None else None

        res: Iterable[KCFG.Cover]
        if source_id:
            res = self._covers.get(source_id, {}).values()
        else:
            res = (cover for _, targets in self._covers.items() for _, cover in targets.items())

        return [cover for cover in res if not target_id or target_id == cover.target.id]

    def contains_cover(self, cover: Cover) -> bool:
        if other := self.cover(source_id=cover.source.id, target_id=cover.target.id):
            return cover == other
        return False

    def create_cover(self, source_id: str, target_id: str, csubst: CSubst | None = None) -> Cover:
        self._check_no_successors(source_id)

        source = self.node(source_id)
        target = self.node(target_id)

        if csubst is None:
            csubst = target.cterm.match_with_constraint(source.cterm)
            if csubst is None:
                raise ValueError(f'No matching between: {source.id} and {target.id}')

        if source.id not in self._covers:
            self._covers[source.id] = {}

        cover = KCFG.Cover(source, target, csubst=csubst)
        self._covers[source.id][target.id] = cover
        return cover

    def remove_cover(self, source_id: str, target_id: str) -> None:
        source_id = self._resolve(source_id)
        target_id = self._resolve(target_id)
        cover = self.cover(source_id, target_id)

        if not cover:
            raise ValueError(f'Cover does not exist: {source_id} -> {target_id}')

        self._covers[source_id].pop(target_id)
        if not self._covers[source_id]:
            self._covers.pop(source_id)

    def edge_likes(self, *, source_id: str | None = None, target_id: str | None = None) -> list[EdgeLike]:
        return cast('List[KCFG.EdgeLike]', self.edges(source_id=source_id, target_id=target_id)) + cast(
            'List[KCFG.EdgeLike]', self.covers(source_id=source_id, target_id=target_id)
        )

    def add_init(self, node_id: str) -> None:
        node_id = self._resolve(node_id)
        self._init.add(node_id)

    def add_target(self, node_id: str) -> None:
        node_id = self._resolve(node_id)
        self._target.add(node_id)

    def add_expanded(self, node_id: str) -> None:
        node_id = self._resolve(node_id)
        self._expanded.add(node_id)

    def splits(self, *, source_id: str | None = None, target_id: str | None = None) -> list[Split]:
        return [
            s
            for s in self._splits.values()
            if (source_id is None or source_id == s.source.id) and (target_id is None or target_id in s.target_ids)
        ]

    def contains_split(self, split: Split) -> bool:
        return split in self._splits

    def create_split(self, source_id: str, splits: Iterable[tuple[str, CSubst]]) -> None:
        self._check_no_successors(source_id)

        splits = list(splits)

        if len(splits) <= 1:
            raise ValueError(f'Cannot create split node with less than 2 targets: {source_id} -> {splits}')

        source_id = self._resolve(source_id)
        split = KCFG.Split(self.node(source_id), tuple((self.node(nid), csubst) for nid, csubst in splits))
        self._splits[source_id] = split

    def ndbranches(self, *, source_id: str | None = None, target_id: str | None = None) -> list[NDBranch]:
        return [
            b
            for b in self._ndbranches.values()
            if (source_id is None or source_id == b.source.id) and (target_id is None or target_id in b.target_ids)
        ]

    def create_ndbranch(self, source_id: str, ndbranches: Iterable[str]) -> None:
        self._check_no_successors(source_id)

        ndbranches = list(ndbranches)

        if len(ndbranches) <= 1:
            raise ValueError(
                f'Cannot create non-deterministic branches node with less than 2 targets: {source_id} -> {ndbranches}'
            )

        source_id = self._resolve(source_id)
        ndbranch = KCFG.NDBranch(self.node(source_id), tuple(self.node(nid) for nid in ndbranches))
        self._ndbranches[source_id] = ndbranch

    def split_on_constraints(self, source_id: str, constraints: Iterable[KInner]) -> list[str]:
        source = self.node(source_id)
        branch_node_ids = [self.get_or_create_node(source.cterm.add_constraint(c)).id for c in constraints]
        csubsts = [CSubst(constraints=flatten_label('#And', constraint)) for constraint in constraints]
        self.create_split(source.id, zip(branch_node_ids, csubsts, strict=True))
        return branch_node_ids

    def add_alias(self, alias: str, node_id: str) -> None:
        if '@' in alias:
            raise ValueError('Alias may not contain "@"')
        if alias in self._aliases:
            raise ValueError(f'Duplicate alias: {alias}')
        node_id = self._resolve(node_id)
        self._aliases[alias] = node_id

    def remove_init(self, node_id: str) -> None:
        node_id = self._resolve(node_id)
        if node_id not in self._init:
            raise ValueError(f'Node is not init: {node_id}')
        self._init.remove(node_id)

    def remove_target(self, node_id: str) -> None:
        node_id = self._resolve(node_id)
        if node_id not in self._target:
            raise ValueError(f'Node is not target: {node_id}')
        self._target.remove(node_id)

    def remove_expanded(self, node_id: str) -> None:
        node_id = self._resolve(node_id)
        if node_id not in self._expanded:
            raise ValueError(f'Node is not expanded: {node_id}')
        self._expanded.remove(node_id)

    def remove_alias(self, alias: str) -> None:
        if alias not in self._aliases:
            raise ValueError(f'Alias does not exist: {alias}')
        self._aliases.pop(alias)

    def discard_init(self, node_id: str) -> None:
        node_id = self._resolve(node_id)
        self._init.discard(node_id)

    def discard_target(self, node_id: str) -> None:
        node_id = self._resolve(node_id)
        self._target.discard(node_id)

    def discard_expanded(self, node_id: str) -> None:
        node_id = self._resolve(node_id)
        self._expanded.discard(node_id)

    def is_init(self, node_id: str) -> bool:
        node_id = self._resolve(node_id)
        return node_id in self._init

    def is_target(self, node_id: str) -> bool:
        node_id = self._resolve(node_id)
        return node_id in self._target

    def is_expanded(self, node_id: str) -> bool:
        node_id = self._resolve(node_id)
        return node_id in self._expanded

    def is_split(self, node_id: str) -> bool:
        node_id = self._resolve(node_id)
        return node_id in self._splits

    def is_ndbranch(self, node_id: str) -> bool:
        node_id = self._resolve(node_id)
        return node_id in self._ndbranches

    def is_leaf(self, node_id: str) -> bool:
        node_id = self._resolve(node_id)
        return node_id not in self._edges and node_id not in self._splits and node_id not in self._ndbranches

    def is_covered(self, node_id: str) -> bool:
        node_id = self._resolve(node_id)
        return node_id in self._covers

    def is_frontier(self, node_id: str) -> bool:
        node_id = self._resolve(node_id)
        return not any(
            [
                self.is_target(node_id),
                self.is_expanded(node_id),
                self.is_covered(node_id),
                self.is_split(node_id),
            ]
        )

    def is_stuck(self, node_id: str) -> bool:
        node_id = self._resolve(node_id)
        return self.is_expanded(node_id) and self.is_leaf(node_id)

    def node_attrs(self, node_id: str) -> list[str]:
        attrs = []
        if self.is_init(node_id):
            attrs.append('init')
        if self.is_target(node_id):
            attrs.append('target')
        if self.is_expanded(node_id):
            attrs.append('expanded')
        if self.is_stuck(node_id):
            attrs.append('stuck')
        if self.is_frontier(node_id):
            attrs.append('frontier')
        if self.is_leaf(node_id):
            attrs.append('leaf')
        if self.is_split(node_id):
            attrs.append('split')
        return attrs

    def prune(self, node_id: str) -> list[str]:
        nodes = self.reachable_nodes(node_id, traverse_covers=True)
        for node in nodes:
            self.remove_node(node.id)
        return [node.id for node in nodes]

    def shortest_path_between(self, source_node_id: str, target_node_id: str) -> tuple[Successor, ...] | None:
        paths = self.paths_between(source_node_id, target_node_id)
        return sorted(paths, key=(lambda path: len(path)))[0]

    def path_constraints(self, final_node_id: str) -> KInner:
        path = self.shortest_path_between(self.get_unique_init().id, final_node_id)
        if path is None:
            raise ValueError(f'No path found to specified node: {final_node_id}')
        curr_constraint: KInner = mlTop()
        for edge in reversed(path):
            if type(edge) is KCFG.Split:
                assert len(edge.targets) == 1
                csubst = edge.splits[edge.targets[0].id]
                curr_constraint = mlAnd([csubst.subst.ml_pred, csubst.constraint, curr_constraint])
            if type(edge) is KCFG.Cover:
                curr_constraint = mlAnd([edge.csubst.constraint, edge.csubst.subst.apply(curr_constraint)])
        return mlAnd(flatten_label('#And', curr_constraint))

    def paths_between(
        self, source_id: str, target_id: str, *, traverse_covers: bool = False
    ) -> list[tuple[Successor, ...]]:
        source_id = self._resolve(source_id)
        target_id = self._resolve(target_id)

        source_successors = list(self.successors(source_id))
        assert len(source_successors) <= 1
        if len(source_successors) == 0:
            return []

        paths: list[tuple[KCFG.Successor, ...]] = []
        worklist: list[list[KCFG.Successor]] = [[source_successors[0]]]

        def _in_path(_nid: str, _path: list[KCFG.Successor]) -> bool:
            for succ in _path:
                if _nid == succ.source.id:
                    return True
            if len(_path) > 0:
                if isinstance(_path[-1], KCFG.EdgeLike) and _path[-1].target.id == _nid:
                    return True
                elif isinstance(_path[-1], KCFG.MultiEdge) and _nid in _path[-1].target_ids:
                    return True
            return False

        while worklist:
            curr_path = worklist.pop()
            curr_successor = curr_path[-1]
            successors: list[KCFG.Successor] = []

            if isinstance(curr_successor, KCFG.EdgeLike):
                if curr_successor.target.id == target_id:
                    paths.append(tuple(curr_path))
                    continue
                else:
                    successors = list(self.successors(curr_successor.target.id))

            elif isinstance(curr_successor, KCFG.MultiEdge):
                if len(list(curr_successor.targets)) == 1:
                    target = list(curr_successor.targets)[0]
                    if target.id == target_id:
                        paths.append(tuple(curr_path))
                        continue
                    else:
                        successors = list(self.successors(target.id))
                if len(list(curr_successor.targets)) > 1:
                    curr_path = curr_path[0:-1]
                    successors = [curr_successor.with_single_target(target) for target in curr_successor.targets]

            for successor in successors:
                if isinstance(successor, KCFG.EdgeLike) and not _in_path(successor.target.id, curr_path):
                    worklist.append(curr_path + [successor])
                elif isinstance(successor, KCFG.MultiEdge):
                    if len(list(successor.targets)) == 1:
                        target = list(successor.targets)[0]
                        if not _in_path(target.id, curr_path):
                            worklist.append(curr_path + [successor])
                    elif len(list(successor.targets)) > 1:
                        worklist.append(curr_path + [successor])

        return paths

    def reachable_nodes(self, source_id: str, *, reverse: bool = False, traverse_covers: bool = False) -> set[Node]:
        visited: set[KCFG.Node] = set()
        worklist: list[KCFG.Node] = [self.node(source_id)]

        while worklist:
            node = worklist.pop()

            if node in visited:
                continue

            visited.add(node)

            if not reverse:
                worklist.extend(
                    target
                    for succ in self.successors(source_id=node.id, covers=traverse_covers)
                    for target in succ.targets
                )
            else:
                worklist.extend(succ.source for succ in self.predecessors(target_id=node.id, covers=traverse_covers))

        return visited
