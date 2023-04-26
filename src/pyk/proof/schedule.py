from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import TYPE_CHECKING

import igraph

from ..cli_utils import check_dir_path
from ..utils import hash_str
from .equality import EqualityProof
from .reachability import APRBMCProof, APRProof

if TYPE_CHECKING:
    from collections.abc import Iterable, Mapping
    from typing import Any, Final

    from .proof import Proof

_LOGGER: Final = logging.getLogger(__name__)


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
            proof_file = proof_dir / f'{hash_str(proof_id)}.json'
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

    def write_svg(self, svg_path: Path | None = None) -> None:
        svg_path = svg_path if svg_path else self.proof_dir / f'{hash_str(self.id)}.svg'
        self._proof_dag.write_svg(fname=str(svg_path), labels='name')

    def advance_schedule(self) -> None:
        pass
