from __future__ import annotations

import json
import logging
import tempfile
from copy import deepcopy
from pathlib import Path
from typing import TYPE_CHECKING, cast

import igraph

from ..cli_utils import check_dir_path
from ..utils import hash_str
from .equality import EqualityProof, EqualityProver
from .proof import ProofStatus
from .reachability import APRBMCProof, APRProof, APRProver

if TYPE_CHECKING:
    from collections.abc import Iterable, Mapping
    from typing import Any, Final

    from ..kcfg import KCFGExplore
    from .proof import Proof

_LOGGER: Final = logging.getLogger(__name__)


def proof_status_color(status: ProofStatus) -> str:
    match status:
        case ProofStatus.FAILED:
            return 'red'
        case ProofStatus.PENDING:
            return 'yellow'
        case ProofStatus.PASSED:
            return 'green'


class ProofSchedule:
    """
    A ProofSchedule keeps a directed acyclic graph (DAG) of Proof objects, akin to a build-system.

    Attributes:
        if           string identifier
        proof_dir    directory on disk that keeps the JSON-serialised Proof objects
        _proofs      flat dictionary of proof ids and Proof objects
        _proof_dag   proof schedule DAG
    """

    id: str
    proof_dir: Path
    _proofs: dict[str, Proof]
    _proof_dag: igraph.Graph
    _proof_queue: list[str]

    def __init__(self, id: str, proof_dir: Path, proof_dag_edges: list[tuple[str, str]] | None = None):
        """
        The initializer walks the supplied proof_dag and populates the _proofs dictionary
        with the Proof objects retrieved from the proof_dir.

        A ValueError is raised if a proof is not found in the proof_dir.
        A ValueError is raised if the DAG contains a cycle.
        """

        proof_dag_edges = proof_dag_edges if proof_dag_edges else []
        self.id = id
        # intialize the internal igraph.Graph datastructure with the user-suppleid list of edges
        self._proof_dag = igraph.Graph.TupleList(edges=proof_dag_edges, directed=True)

        self.proof_dir = proof_dir
        self._proofs = {}

        # Compute the topological order on the proof schedule to make sure its actually a DAG
        try:
            _ = self._proof_dag.topological_sorting()
        except igraph.InternalError as err:
            first_loop = self._proof_dag.es[list(self._proof_dag.feedback_arc_set())[0]]
            loop_origin = self._proof_dag.vs[first_loop.source]['name']
            loop_target = self._proof_dag.vs[first_loop.target]['name']
            raise ValueError(f'Proof Schedule has a cycle from {loop_origin} to {loop_target}') from err
        # Load the actual proofs from disc
        for proof_id in self.proof_ids:
            self.load_proof(proof_id)

        # initialize vertex colors according to their proof statuses (for visialization only)
        for v in self._proof_dag.vs:
            v['color'] = proof_status_color(self._proofs[v['name']].status)
            v['label'] = v['name']

    def load_proof(self, proof_id: str) -> None:
        proof_file = self.proof_dir / f'{hash_str(proof_id)}.json'
        proof_dict = json.loads(proof_file.read_text())
        match proof_dict['type']:
            case 'APRProof':
                self._proofs[proof_id] = APRProof.from_dict(proof_dict)
            case 'APRBMCProof':
                self._proofs[proof_id] = APRBMCProof.from_dict(proof_dict)
            case 'EqualityProof':
                self._proofs[proof_id] = EqualityProof.from_dict(proof_dict)
            case other:
                raise ValueError(f'Unknown proof type {other} found in proof file {proof_file}')

    @property
    def topological_sorting(self) -> Iterable[Proof]:
        for v_id in self._proof_dag.topological_sorting():
            yield self._proofs[self._proof_dag.vs[v_id]['name']]

    @property
    def proof_ids(self) -> Iterable[str]:
        for v in self._proof_dag.vs:
            yield v['name']

    @property
    def proof_dag_edges(self) -> list[tuple[str, str]]:
        """
        Output the proof schedule dag as a list of edges
        """
        return [
            (self._proof_dag.vs[edge.source]['name'], self._proof_dag.vs[edge.target]['name'])
            for edge in self._proof_dag.es
        ]

    @classmethod
    def from_dict(cls: type[ProofSchedule], dct: Mapping[str, Any], proof_dir: Path | None = None) -> ProofSchedule:
        proof_dir = proof_dir if proof_dir else Path(dct['proof_dir'])
        check_dir_path(proof_dir)
        return ProofSchedule(id=dct['id'], proof_dir=proof_dir, proof_dag_edges=dct['proof_dag_edges'])

    @property
    def dict(self) -> dict[str, Any]:
        dct = {
            'type': 'ProofSchedule',
            'id': self.id,
            'proof_dag_edges': self.proof_dag_edges,
            'proof_dir': str(self.proof_dir),
        }
        return dct

    def write_proof_schedule(self) -> None:
        if not self.proof_dir:
            return
        proof_schedule_path = self.proof_dir / f'{hash_str(self.id)}.json'
        proof_schedule_path.write_text(json.dumps(self.dict))
        _LOGGER.info(f'Updated proof schedule file {self.id}: {proof_schedule_path}')

    @staticmethod
    def proof_schedule_exists(id: str, proof_dir: Path) -> bool:
        proof_schedule_path = proof_dir / f'{hash_str(id)}.json'
        return proof_schedule_path.exists() and proof_schedule_path.is_file()

    @staticmethod
    def read_proof_schedule(id: str, proof_dir: Path) -> ProofSchedule:
        proof_schedule_path = proof_dir / f'{hash_str(id)}.json'
        if ProofSchedule.proof_schedule_exists(id, proof_dir):
            proof_dict = json.loads(proof_schedule_path.read_text())
            _LOGGER.info(f'Reading ProofSchedule from file {id}: {proof_schedule_path}')
            return ProofSchedule.from_dict(proof_dict, proof_dir=proof_dir)
        raise ValueError(f'Could not load ProofSchedule from file {id}: {proof_schedule_path}')

    @property
    def dot(self) -> str:
        # make sure the vertex status coloring is up-to-date
        for v in self._proof_dag.vs:
            v['color'] = proof_status_color(self._proofs[v['name']].status)
        f = tempfile.TemporaryFile('r+')
        self._proof_dag.write_dot(f)
        f.seek(0)
        result = f.read()
        f.close()
        return result

    @property
    def leafs(self) -> Iterable[Proof]:
        """
        Enumerate leaf proofs in the schedule, i.e. the nodes in the DAG that have out-degree of zero
        """
        return self._proof_dag.vs.select(_outdegree=0)['name']

    @property
    def roots(self) -> Iterable[Proof]:
        return self._proof_dag.vs.select(_indegree=0)['name']

    def direct_dependencies(self, proof_id: str) -> Iterable[str]:
        """
        Direct dependenices of a proof, i.e. the predicessors of the proof's node in the DAG
        """
        return [self._proof_dag.vs[v_id]['name'] for v_id in self._proof_dag.predecessors(proof_id)]

    def _dependencies(self, proof_id: str) -> Iterable[str]:
        """
        ALL dependenices of a proof, i.e. the transitive predicessors of the proof's node in the DAG
        """
        reversed_dag = deepcopy(self._proof_dag)
        reversed_dag.reverse_edges()
        [deps_v_ids, _, _] = reversed_dag.bfs(self._proof_dag.vs.find(proof_id).index)
        return [self._proof_dag.vs[v_id]['name'] for v_id in deps_v_ids]

    def fire_proof(self, proof_id: str, kcfg_explore: KCFGExplore) -> None:
        """
        Trigger a proof in the schedule, also triggiring its dependencies
        """

        deps_set = set(self._dependencies(proof_id))
        # induce the subgraph generated by dependenices, including the target proof
        deps_dag = self._proof_dag.induced_subgraph(deps_set)
        proof_v = deps_dag.vs.find(proof_id)
        # execute the proof, but first execute it's dependencies
        deps_dag.reverse_edges()
        [vertices, _, _] = deps_dag.bfs(proof_v.index)
        for v in reversed(vertices):
            proof_name = deps_dag.vs[v]['name']
            _LOGGER.info(f'Processing proof {proof_name}')
            prover: APRProver | EqualityProver
            if type(self._proofs[proof_name]) == APRProof:
                prover = APRProver(proof=cast('APRProof', self._proofs[proof_name]))
            elif type(self._proofs[proof_name]) == EqualityProof:
                prover = EqualityProver(proof=cast('EqualityProof', self._proofs[proof_name]))
            else:
                raise ValueError(f'Proof type {type(self._proofs[proof_name])} is not yet supported')
            prover.advance_proof(kcfg_explore)
            # re-index the advanced proof into the schedule
            self._proofs[proof_name] = prover.proof
            _LOGGER.info(f'Proof {proof_name} {self._proofs[proof_name].status}')
