from __future__ import annotations

import graphlib
import sys
import json
import logging
import re
import time
from abc import ABC
from dataclasses import dataclass
from typing import TYPE_CHECKING

import pyk.proof.parallel as parallel
from pyk.kore.rpc import KoreClient, KoreExecLogFormat, LogEntry, kore_server

from ..kast.inner import KInner, Subst
from ..kast.manip import flatten_label, ml_pred_to_bool
from ..kast.outer import KFlatModule, KImport, KRule
from ..kcfg import KCFG, KCFGExplore
from ..kcfg.exploration import KCFGExploration
from ..konvert import kflatmodule_to_kore
from ..prelude.kbool import BOOL, TRUE
from ..prelude.ml import mlAnd, mlEquals, mlTop
from ..utils import FrozenDict, ensure_dir_path, hash_str, shorten_hashes, single
from .equality import ProofSummary, Prover, RefutationProof
from .proof import CompositeSummary, Proof, ProofStatus

if TYPE_CHECKING:
    from collections.abc import Iterable, Mapping
    from pathlib import Path
    from typing import Any, Final, TypeVar

    from pyk.kcfg.semantics import KCFGSemantics
    from pyk.kore.rpc import KoreServer
    from pyk.utils import BugReport

    from ..cterm import CSubst, CTerm
    from ..kast.outer import KClaim, KDefinition, KFlatModuleList
    from ..kcfg.explore import ExtendResult
    from ..kcfg.kcfg import NodeIdLike
    from ..ktool.kprint import KPrint

    T = TypeVar('T', bound='Proof')

_LOGGER: Final = logging.getLogger(__name__)


class APRProof(Proof, KCFGExploration, parallel.Proof):
    """APRProof and APRProver implement all-path reachability logic,
    as introduced by A. Stefanescu and others in their paper 'All-Path Reachability Logic':
    https://doi.org/10.23638/LMCS-15(2:5)2019
    Note that reachability logic formula `phi =>A psi` has *not* the same meaning
    as CTL/CTL*'s `phi -> AF psi`, since reachability logic ignores infinite traces.
    """

    node_refutations: dict[int, RefutationProof]  # TODO _node_refutatations
    init: int
    target: int
    logs: dict[int, tuple[LogEntry, ...]]
    circularity: bool
    failure_info: APRFailureInfo | None
    checked_for_subsumption: set[int]

    def __init__(
        self,
        id: str,
        kcfg: KCFG,
        terminal: Iterable[int],
        init: NodeIdLike,
        target: NodeIdLike,
        logs: dict[int, tuple[LogEntry, ...]],
        checked_for_subsumption: set[int] | None = None,
        proof_dir: Path | None = None,
        node_refutations: dict[int, str] | None = None,
        subproof_ids: Iterable[str] = (),
        circularity: bool = False,
        admitted: bool = False,
    ):
        Proof.__init__(self, id, proof_dir=proof_dir, subproof_ids=subproof_ids, admitted=admitted)
        KCFGExploration.__init__(self, kcfg, terminal)

        self.checked_for_subsumption = checked_for_subsumption if checked_for_subsumption is not None else set()
        self.failure_info = None
        self.init = kcfg._resolve(init)
        self.target = kcfg._resolve(target)
        self.logs = logs
        self.circularity = circularity
        self.node_refutations = {}
        self.kcfg.cfg_dir = self.proof_subdir / 'kcfg' if self.proof_subdir else None

        if self.proof_dir is not None and self.proof_subdir is not None:
            ensure_dir_path(self.proof_dir)
            ensure_dir_path(self.proof_subdir)

        if node_refutations is not None:
            refutations_not_in_subprroofs = set(node_refutations.values()).difference(
                set(subproof_ids if subproof_ids else [])
            )
            if refutations_not_in_subprroofs:
                raise ValueError(
                    f'All node refutations must be included in subproofs, violators are {refutations_not_in_subprroofs}'
                )
            for node_id, proof_id in node_refutations.items():
                subproof = self._subproofs[proof_id]
                assert type(subproof) is RefutationProof
                self.node_refutations[node_id] = subproof

    @property
    def pending(self) -> list[KCFG.Node]:
        return [node for node in self.explorable if self.is_pending(node.id)]

    @property
    def failing(self) -> list[KCFG.Node]:
        return [nd for nd in self.kcfg.leaves if self.is_failing(nd.id)]

    def is_refuted(self, node_id: NodeIdLike) -> bool:
        return self.kcfg._resolve(node_id) in self.node_refutations.keys()

    def is_pending(self, node_id: NodeIdLike) -> bool:
        return self.is_explorable(node_id) and not self.is_target(node_id) and not self.is_refuted(node_id)

    def is_init(self, node_id: NodeIdLike) -> bool:
        return self.kcfg._resolve(node_id) == self.kcfg._resolve(self.init)

    def is_target(self, node_id: NodeIdLike) -> bool:
        return self.kcfg._resolve(node_id) == self.kcfg._resolve(self.target)

    def is_failing(self, node_id: NodeIdLike) -> bool:
        return (
            self.kcfg.is_leaf(node_id)
            and ((node_id in self.checked_for_subsumption) or self.kcfg.is_stuck(node_id))
            and not self.is_target(node_id)
            and not self.is_refuted(node_id)
            and not self.kcfg.is_vacuous(node_id)
        )

    def shortest_path_to(self, node_id: NodeIdLike) -> tuple[KCFG.Successor, ...]:
        spb = self.kcfg.shortest_path_between(self.init, node_id)
        assert spb is not None
        return spb

    def prune(self, node_id: NodeIdLike, keep_nodes: Iterable[NodeIdLike] = ()) -> list[int]:
        pruned_nodes = super().prune(node_id, keep_nodes=list(keep_nodes) + [self.init, self.target])
        return pruned_nodes

    @staticmethod
    def read_proof(id: str, proof_dir: Path) -> APRProof:
        proof_path = proof_dir / f'{hash_str(id)}.json'
        if APRProof.proof_exists(id, proof_dir):
            proof_dict = json.loads(proof_path.read_text())
            _LOGGER.info(f'Reading APRProof from file {id}: {proof_path}')
            return APRProof.from_dict(proof_dict, proof_dir=proof_dir)
        raise ValueError(f'Could not load APRProof from file {id}: {proof_path}')

    @property
    def status(self) -> ProofStatus:
        if self.admitted:
            return ProofStatus.PASSED
        if len(self.failing) > 0 or self.subproofs_status == ProofStatus.FAILED:
            return ProofStatus.FAILED
        elif len(self.pending) > 0 or self.subproofs_status == ProofStatus.PENDING:
            return ProofStatus.PENDING
        else:
            return ProofStatus.PASSED

    @classmethod
    def from_dict(cls: type[APRProof], dct: Mapping[str, Any], proof_dir: Path | None = None) -> APRProof:
        kcfg = KCFG.from_dict(dct['kcfg'])
        terminal = dct['terminal']
        init_node = dct['init']
        target_node = dct['target']
        id = dct['id']
        circularity = dct.get('circularity', False)
        admitted = dct.get('admitted', False)
        subproof_ids = dct['subproof_ids'] if 'subproof_ids' in dct else []
        node_refutations: dict[int, str] = {}
        checked_for_subsumption = set(dct['checked_for_subsumption'])
        if 'node_refutation' in dct:
            node_refutations = {kcfg._resolve(node_id): proof_id for (node_id, proof_id) in dct['node_refutations']}
        if 'logs' in dct:
            logs = {int(k): tuple(LogEntry.from_dict(l) for l in ls) for k, ls in dct['logs'].items()}
        else:
            logs = {}

        return APRProof(
            id,
            kcfg,
            terminal,
            init_node,
            target_node,
            logs=logs,
            circularity=circularity,
            admitted=admitted,
            proof_dir=proof_dir,
            subproof_ids=subproof_ids,
            node_refutations=node_refutations,
            checked_for_subsumption=checked_for_subsumption,
        )

    @staticmethod
    def from_claim(
        defn: KDefinition,
        claim: KClaim,
        logs: dict[int, tuple[LogEntry, ...]],
        proof_dir: Path | None = None,
        **kwargs: Any,
    ) -> APRProof:
        kcfg_dir = proof_dir / claim.label / 'kcfg' if proof_dir is not None else None

        kcfg, init_node, target_node = KCFG.from_claim(defn, claim, cfg_dir=kcfg_dir)
        return APRProof(
            claim.label,
            kcfg,
            [],
            init=init_node,
            target=target_node,
            logs=logs,
            proof_dir=proof_dir,
            circularity=claim.is_circularity,
            admitted=claim.is_trusted,
            **kwargs,
        )

    def as_rule(self, priority: int = 20) -> KRule:
        _edge = KCFG.Edge(self.kcfg.node(self.init), self.kcfg.node(self.target), depth=0, rules=())
        _rule = _edge.to_rule('BASIC-BLOCK', priority=priority)
        assert type(_rule) is KRule
        return _rule

    @staticmethod
    def from_spec_modules(
        defn: KDefinition,
        spec_modules: KFlatModuleList,
        logs: dict[int, tuple[LogEntry, ...]],
        proof_dir: Path | None = None,
        spec_labels: Iterable[str] | None = None,
        **kwargs: Any,
    ) -> list[APRProof]:
        claims_by_label = {claim.label: claim for module in spec_modules.modules for claim in module.claims}
        if spec_labels is None:
            spec_labels = list(claims_by_label.keys())
        _spec_labels = []
        for spec_label in spec_labels:
            if spec_label in claims_by_label:
                _spec_labels.append(spec_label)
            elif f'{spec_modules.main_module}.{spec_label}' in claims_by_label:
                _spec_labels.append(f'{spec_modules.main_module}.{spec_label}')
            else:
                raise ValueError(
                    f'Could not find specification label: {spec_label} or {spec_modules.main_module}.{spec_label}'
                )
        spec_labels = _spec_labels

        claims_graph: dict[str, list[str]] = {}
        unfound_dependencies = []
        for module in spec_modules.modules:
            for claim in module.claims:
                claims_graph[claim.label] = []
                for dependency in claim.dependencies:
                    if dependency in claims_by_label:
                        claims_graph[claim.label].append(dependency)
                    elif f'{module.name}.{dependency}' in claims_by_label:
                        claims_graph[claim.label].append(f'{module.name}.{dependency}')
                    else:
                        unfound_dependencies.append((claim.label, module.name, dependency))
        if unfound_dependencies:
            unfound_dependency_list = [
                f'Could not find dependency for claim {label}: {dependency} or {module_name}.{dependency}'
                for label, module_name, dependency in unfound_dependencies
            ]
            unfound_dependency_message = '\n - ' + '\n - '.join(unfound_dependency_list)
            raise ValueError(f'Could not find dependencies:{unfound_dependency_message}')

        claims_subgraph: dict[str, list[str]] = {}
        remaining_claims = spec_labels
        while len(remaining_claims) > 0:
            claim_label = remaining_claims.pop()
            claims_subgraph[claim_label] = claims_graph[claim_label]
            remaining_claims.extend(claims_graph[claim_label])

        topological_sorter = graphlib.TopologicalSorter(claims_subgraph)
        topological_sorter.prepare()
        apr_proofs: list[APRProof] = []
        while topological_sorter.is_active():
            for claim_label in topological_sorter.get_ready():
                if proof_dir is not None and Proof.proof_data_exists(claim_label, proof_dir):
                    apr_proof = APRProof.read_proof_data(proof_dir, claim_label)
                else:
                    _LOGGER.info(f'Building APRProof for claim: {claim_label}')
                    claim = claims_by_label[claim_label]
                    apr_proof = APRProof.from_claim(
                        defn,
                        claim,
                        logs=logs,
                        proof_dir=proof_dir,
                        subproof_ids=claims_graph[claim_label],
                    )
                    apr_proof.write_proof_data()
                apr_proofs.append(apr_proof)
                topological_sorter.done(claim_label)

        return apr_proofs

    def path_constraints(self, final_node_id: NodeIdLike) -> KInner:
        path = self.shortest_path_to(final_node_id)
        curr_constraint: KInner = mlTop()
        for edge in reversed(path):
            if type(edge) is KCFG.Split:
                assert len(edge.targets) == 1
                csubst = edge.splits[edge.targets[0].id]
                curr_constraint = mlAnd([csubst.subst.ml_pred, csubst.constraint, curr_constraint])
            if type(edge) is KCFG.Cover:
                curr_constraint = mlAnd([edge.csubst.constraint, edge.csubst.subst.apply(curr_constraint)])
        return mlAnd(flatten_label('#And', curr_constraint))

    @property
    def dict(self) -> dict[str, Any]:
        # Note: We are relying on the order of inheritance to
        # access `dict` of `Proof`, since mypy is having issues
        # with the two correct solutions.
        dct = super().dict
        dct['type'] = 'APRProof'
        dct['kcfg'] = self.kcfg.to_dict()
        dct['terminal'] = sorted(self._terminal)
        dct['init'] = self.init
        dct['target'] = self.target
        dct['node_refutations'] = {node_id: proof.id for (node_id, proof) in self.node_refutations.items()}
        dct['circularity'] = self.circularity
        dct['checked_for_subsumption'] = list(self.checked_for_subsumption)
        logs = {int(k): [l.to_dict() for l in ls] for k, ls in self.logs.items()}
        dct['logs'] = logs
        return dct

    @property
    def summary(self) -> CompositeSummary:
        subproofs_summaries = [subproof.summary for subproof in self.subproofs]
        return CompositeSummary(
            [
                APRSummary(
                    self.id,
                    self.status,
                    self.admitted,
                    len(self.kcfg.nodes),
                    len(self.pending),
                    len(self.failing),
                    len(self.kcfg.vacuous),
                    len(self.kcfg.stuck),
                    len(self._terminal),
                    len(self.node_refutations),
                    len(self.subproof_ids),
                ),
                *subproofs_summaries,
            ]
        )

    def get_refutation_id(self, node_id: int) -> str:
        return f'{self.id}.node-infeasible-{node_id}'

    @staticmethod
    def read_proof_data(proof_dir: Path, id: str) -> APRProof:
        proof_subdir = proof_dir / id
        proof_json = proof_subdir / 'proof.json'
        proof_dict = json.loads(proof_json.read_text())
        cfg_dir = proof_subdir / 'kcfg'
        kcfg = KCFG.read_cfg_data(cfg_dir, id)
        init = int(proof_dict['init'])
        target = int(proof_dict['target'])
        circularity = bool(proof_dict['circularity'])
        admitted = bool(proof_dict['admitted'])
        terminal = proof_dict['terminal']
        logs = {int(k): tuple(LogEntry.from_dict(l) for l in ls) for k, ls in proof_dict['logs'].items()}
        subproof_ids = proof_dict['subproof_ids']
        checked_for_subsumption = proof_dict['checked_for_subsumption']
        node_refutations = {kcfg._resolve(node_id): proof_id for (node_id, proof_id) in proof_dict['node_refutations']}

        return APRProof(
            id=id,
            kcfg=kcfg,
            terminal=terminal,
            init=init,
            target=target,
            logs=logs,
            circularity=circularity,
            admitted=admitted,
            proof_dir=proof_dir,
            subproof_ids=subproof_ids,
            node_refutations=node_refutations,
            checked_for_subsumption=checked_for_subsumption,
        )

    def write_proof_data(self) -> None:
        if self.proof_dir is None or self.proof_subdir is None:
            _LOGGER.info(f'Skipped saving proof {self.id} since no save dir was specified.')
            return
        ensure_dir_path(self.proof_dir)
        ensure_dir_path(self.proof_subdir)
        proof_json = self.proof_subdir / 'proof.json'
        dct: dict[str, list[int] | list[str] | bool | str | int | dict[int, str] | dict[int, list[dict[str, Any]]]] = {}

        dct['id'] = self.id
        dct['subproof_ids'] = self.subproof_ids
        dct['admitted'] = self.admitted
        dct['type'] = 'APRProof'
        dct['init'] = self.kcfg._resolve(self.init)
        dct['target'] = self.kcfg._resolve(self.target)
        dct['terminal'] = sorted(self._terminal)
        dct['node_refutations'] = {
            self.kcfg._resolve(node_id): proof.id for (node_id, proof) in self.node_refutations.items()
        }
        dct['circularity'] = self.circularity
        dct['checked_for_subsumption'] = list(self.checked_for_subsumption)
        logs = {int(k): [l.to_dict() for l in ls] for k, ls in self.logs.items()}
        dct['logs'] = logs

        proof_json.write_text(json.dumps(dct))
        _LOGGER.info(f'Wrote proof data for {self.id}: {proof_json}')
        self.kcfg.write_cfg_data()


class APRBMCProof(APRProof):
    """APRBMCProof and APRBMCProver perform bounded model-checking of an all-path reachability logic claim."""

    bmc_depth: int
    _bounded: set[int]

    def __init__(
        self,
        id: str,
        kcfg: KCFG,
        terminal: Iterable[int],
        init: NodeIdLike,
        target: NodeIdLike,
        logs: dict[int, tuple[LogEntry, ...]],
        bmc_depth: int,
        bounded: Iterable[int] | None = None,
        proof_dir: Path | None = None,
        subproof_ids: Iterable[str] = (),
        checked_for_subsumption: set[int] | None = None,
        node_refutations: dict[int, str] | None = None,
        circularity: bool = False,
        admitted: bool = False,
    ):
        super().__init__(
            id,
            kcfg,
            terminal,
            init,
            target,
            logs,
            proof_dir=proof_dir,
            subproof_ids=subproof_ids,
            node_refutations=node_refutations,
            circularity=circularity,
            admitted=admitted,
            checked_for_subsumption=checked_for_subsumption,
        )
        self.bmc_depth = bmc_depth
        self._bounded = set(bounded) if bounded is not None else set()

    @staticmethod
    def read_proof_data(proof_dir: Path, id: str) -> APRBMCProof:
        proof_subdir = proof_dir / id
        proof_json = proof_subdir / 'proof.json'
        proof_dict = json.loads(proof_json.read_text())
        cfg_dir = proof_subdir / 'kcfg'
        kcfg = KCFG.read_cfg_data(cfg_dir, id)
        init = int(proof_dict['init'])
        target = int(proof_dict['target'])
        circularity = bool(proof_dict['circularity'])
        terminal = proof_dict['terminal']
        admitted = bool(proof_dict['admitted'])
        logs = {int(k): tuple(LogEntry.from_dict(l) for l in ls) for k, ls in proof_dict['logs'].items()}
        subproof_ids = proof_dict['subproof_ids']
        node_refutations = {kcfg._resolve(node_id): proof_id for (node_id, proof_id) in proof_dict['node_refutations']}
        bounded = proof_dict['bounded']
        bmc_depth = int(proof_dict['bmc_depth'])
        checked_for_subsumption = {kcfg._resolve(node_id) for node_id in proof_dict['checked_for_subsumption']}

        return APRBMCProof(
            id=id,
            kcfg=kcfg,
            terminal=terminal,
            init=init,
            target=target,
            logs=logs,
            circularity=circularity,
            admitted=admitted,
            bounded=bounded,
            bmc_depth=bmc_depth,
            proof_dir=proof_dir,
            subproof_ids=subproof_ids,
            node_refutations=node_refutations,
            checked_for_subsumption=checked_for_subsumption,
        )

    def write_proof_data(self) -> None:
        if self.proof_dir is None or self.proof_subdir is None:
            _LOGGER.info(f'Skipped saving proof {self.id} since no save dir was specified.')
            return
        ensure_dir_path(self.proof_dir)
        ensure_dir_path(self.proof_subdir)
        proof_json = self.proof_subdir / 'proof.json'
        dct: dict[str, list[int] | list[str] | bool | str | int | dict[int, str] | dict[int, list[dict[str, Any]]]] = {}

        dct['id'] = self.id
        dct['subproof_ids'] = self.subproof_ids
        dct['admitted'] = self.admitted
        dct['type'] = 'APRBMCProof'
        dct['init'] = self.kcfg._resolve(self.init)
        dct['target'] = self.kcfg._resolve(self.target)
        dct['node_refutations'] = {
            self.kcfg._resolve(node_id): proof.id for (node_id, proof) in self.node_refutations.items()
        }
        dct['circularity'] = self.circularity
        logs = {int(k): [l.to_dict() for l in ls] for k, ls in self.logs.items()}
        dct['logs'] = logs
        dct['terminal'] = sorted(self._terminal)
        dct['bounded'] = sorted(self._bounded)
        dct['bmc_depth'] = self.bmc_depth
        dct['checked_for_subsumption'] = list(self.checked_for_subsumption)

        proof_json.write_text(json.dumps(dct))
        _LOGGER.info(f'Wrote proof data for {self.id}: {proof_json}')
        self.kcfg.write_cfg_data()

    @property
    def bounded(self) -> list[KCFG.Node]:
        return [nd for nd in self.kcfg.leaves if self.is_bounded(nd.id)]

    def is_bounded(self, node_id: NodeIdLike) -> bool:
        return self.kcfg._resolve(node_id) in self._bounded

    def is_pending(self, node_id: NodeIdLike) -> bool:
        return super().is_pending(node_id) and not self.is_bounded(node_id)

    def is_failing(self, node_id: NodeIdLike) -> bool:
        return super().is_failing(node_id) and not self.is_bounded(node_id)

    def prune(self, node_id: NodeIdLike, keep_nodes: Iterable[NodeIdLike] = ()) -> list[int]:
        pruned_nodes = super().prune(node_id, keep_nodes=keep_nodes)
        for nid in pruned_nodes:
            self.remove_bounded(nid)
        return pruned_nodes

    @classmethod
    def from_dict(cls: type[APRBMCProof], dct: Mapping[str, Any], proof_dir: Path | None = None) -> APRBMCProof:
        kcfg = KCFG.from_dict(dct['kcfg'])
        terminal = dct['terminal']
        init = dct['init']
        target = dct['target']
        bounded = dct['bounded']

        admitted = dct.get('admitted', False)
        circularity = dct.get('circularity', False)
        bmc_depth = dct['bmc_depth']
        subproof_ids = dct['subproof_ids'] if 'subproof_ids' in dct else []
        node_refutations: dict[int, str] = {}
        if 'node_refutation' in dct:
            node_refutations = {kcfg._resolve(node_id): proof_id for (node_id, proof_id) in dct['node_refutations']}
        id = dct['id']
        if 'logs' in dct:
            logs = {int(k): tuple(LogEntry.from_dict(l) for l in ls) for k, ls in dct['logs'].items()}
        else:
            logs = {}
        checked_for_subsumption = {kcfg._resolve(node_id) for node_id in dct['checked_for_subsumption']}

        return APRBMCProof(
            id,
            kcfg,
            terminal,
            init,
            target,
            logs,
            bmc_depth,
            bounded=bounded,
            proof_dir=proof_dir,
            circularity=circularity,
            subproof_ids=subproof_ids,
            node_refutations=node_refutations,
            admitted=admitted,
            checked_for_subsumption=checked_for_subsumption,
        )

    @property
    def dict(self) -> dict[str, Any]:
        dct = super().dict
        dct['type'] = 'APRBMCProof'
        dct['bmc_depth'] = self.bmc_depth
        dct['bounded'] = list(self._bounded)
        logs = {int(k): [l.to_dict() for l in ls] for k, ls in self.logs.items()}
        dct['logs'] = logs
        dct['circularity'] = self.circularity
        return dct

    @staticmethod
    def from_claim_with_bmc_depth(
        defn: KDefinition, claim: KClaim, bmc_depth: int, proof_dir: Path | None = None
    ) -> APRBMCProof:
        kcfg_dir = proof_dir / claim.label / 'kcfg' if proof_dir is not None else None

        kcfg, init_node, target_node = KCFG.from_claim(defn, claim, cfg_dir=kcfg_dir)

        return APRBMCProof(
            claim.label,
            kcfg,
            [],
            bmc_depth=bmc_depth,
            init=init_node,
            target=target_node,
            logs={},
            proof_dir=proof_dir,
            circularity=claim.is_circularity,
            admitted=claim.is_trusted,
        )

    def add_bounded(self, nid: NodeIdLike) -> None:
        self._bounded.add(self.kcfg._resolve(nid))

    def remove_bounded(self, node_id: int) -> None:
        self._bounded.discard(node_id)

    @property
    def summary(self) -> CompositeSummary:
        subproofs_summaries = [subproof.summary for subproof in self.subproofs]
        return CompositeSummary(
            [
                APRBMCSummary(
                    self.id,
                    self.bmc_depth,
                    self.status,
                    len(self.kcfg.nodes),
                    len(self.pending),
                    len(self.failing),
                    len(self.kcfg.vacuous),
                    len(self.kcfg.stuck),
                    len(self._terminal),
                    len(self.node_refutations),
                    len(self._bounded),
                    len(self.subproof_ids),
                ),
                *subproofs_summaries,
            ]
        )


class APRProver(Prover):
    proof: APRProof

    main_module_name: str
    dependencies_module_name: str
    circularities_module_name: str
    counterexample_info: bool
    always_check_subsumption: bool
    fast_check_subsumption: bool

    _checked_for_terminal: set[int]
    _checked_for_subsumption: set[int]

    def __init__(
        self,
        proof: APRProof,
        kcfg_explore: KCFGExplore,
        counterexample_info: bool = False,
        always_check_subsumption: bool = True,
        fast_check_subsumption: bool = False,
    ) -> None:
        def _inject_module(module_name: str, import_name: str, sentences: list[KRule]) -> None:
            _module = KFlatModule(module_name, sentences, [KImport(import_name)])
            _kore_module = kflatmodule_to_kore(
                self.kcfg_explore.kprint.definition, self.kcfg_explore.kprint.kompiled_kore, _module
            )
            self.kcfg_explore._kore_client.add_module(_kore_module, name_as_id=True)

        super().__init__(kcfg_explore)
        self.proof = proof
        self.main_module_name = self.kcfg_explore.kprint.definition.main_module_name
        self.counterexample_info = counterexample_info
        self.always_check_subsumption = always_check_subsumption
        self.fast_check_subsumption = fast_check_subsumption

        subproofs: list[Proof] = (
            [Proof.read_proof_data(proof.proof_dir, i) for i in proof.subproof_ids]
            if proof.proof_dir is not None
            else []
        )

        apr_subproofs: list[APRProof] = [pf for pf in subproofs if isinstance(pf, APRProof)]

        dependencies_as_rules: list[KRule] = [d.as_rule(priority=20) for d in apr_subproofs]
        circularity_rule = proof.as_rule(priority=20)

        module_name = re.sub(r'[%().:,_]+', '-', self.proof.id.upper())
        self.dependencies_module_name = module_name + '-DEPENDS-MODULE'
        self.circularities_module_name = module_name + '-CIRCULARITIES-MODULE'
        _inject_module(self.dependencies_module_name, self.main_module_name, dependencies_as_rules)
        _inject_module(self.circularities_module_name, self.dependencies_module_name, [circularity_rule])

        self._checked_for_terminal = set()
        self._checked_for_subsumption = set()
        self._check_all_terminals()

    def nonzero_depth(self, node: KCFG.Node) -> bool:
        return not self.proof.kcfg.zero_depth_between(self.proof.init, node.id)

    def _check_terminal(self, node: KCFG.Node) -> None:
        if node.id not in self._checked_for_terminal:
            _LOGGER.info(f'Checking terminal: {node.id}')
            self._checked_for_terminal.add(node.id)
            if self.kcfg_explore.kcfg_semantics.is_terminal(node.cterm):
                _LOGGER.info(f'Terminal node: {node.id}.')
                self.proof._terminal.add(node.id)
            elif self.fast_check_subsumption and self._may_subsume(node):
                _LOGGER.info(f'Marking node as terminal because of fast may subsume check {self.proof.id}: {node.id}')
                self.proof._terminal.add(node.id)

    def _check_all_terminals(self) -> None:
        for node in self.proof.kcfg.nodes:
            self._check_terminal(node)

    def _may_subsume(self, node: KCFG.Node) -> bool:
        node_k_cell = node.cterm.try_cell('K_CELL')
        target_k_cell = self.proof.kcfg.node(self.proof.target).cterm.try_cell('K_CELL')
        if node_k_cell and target_k_cell and not target_k_cell.match(node_k_cell):
            return False
        return True

    def _check_subsume(self, node: KCFG.Node) -> bool:
        _LOGGER.info(
            f'Checking subsumption into target state {self.proof.id}: {shorten_hashes((node.id, self.proof.target))}'
        )
        if self.fast_check_subsumption and not self._may_subsume(node):
            _LOGGER.info(
                f'Skipping full subsumption check because of fast may subsume check {self.proof.id}: {node.id}'
            )
            return False
        csubst = self.kcfg_explore.cterm_implies(node.cterm, self.proof.kcfg.node(self.proof.target).cterm)
        self.proof.checked_for_subsumption.add(node.id)
        if csubst is not None:
            self.proof.kcfg.create_cover(node.id, self.proof.target, csubst=csubst)
            _LOGGER.info(f'Subsumed into target node {self.proof.id}: {shorten_hashes((node.id, self.proof.target))}')
            return True
        else:
            return False

    def advance_pending_node(
        self,
        node: KCFG.Node,
        execute_depth: int | None = None,
        cut_point_rules: Iterable[str] = (),
        terminal_rules: Iterable[str] = (),
    ) -> None:
        if self.proof.target not in self.proof._terminal:
            if self.always_check_subsumption and self._check_subsume(node):
                return

        module_name = self.circularities_module_name if self.nonzero_depth(node) else self.dependencies_module_name
        self.kcfg_explore.extend(
            self.proof,
            node,
            self.proof.logs,
            execute_depth=execute_depth,
            cut_point_rules=cut_point_rules,
            terminal_rules=terminal_rules,
            module_name=module_name,
        )

    def advance_proof(
        self,
        max_iterations: int | None = None,
        execute_depth: int | None = None,
        cut_point_rules: Iterable[str] = (),
        terminal_rules: Iterable[str] = (),
        fail_fast: bool = False,
    ) -> None:
        iterations = 0

        self._check_all_terminals()

        while self.proof.pending:
            self.proof.write_proof_data()
            if fail_fast and self.proof.failed:
                _LOGGER.warning(
                    f'Terminating proof early because fail_fast is set {self.proof.id}, failing nodes: {[nd.id for nd in self.proof.failing]}'
                )
                break

            if max_iterations is not None and max_iterations <= iterations:
                _LOGGER.warning(f'Reached iteration bound {self.proof.id}: {max_iterations}')
                break
            iterations += 1
            curr_node = self.proof.pending[0]

            self.advance_pending_node(
                node=curr_node,
                execute_depth=execute_depth,
                cut_point_rules=cut_point_rules,
                terminal_rules=terminal_rules,
            )

            self._check_all_terminals()

            for node in self.proof.terminal:
                if (
                    not node.id in self._checked_for_subsumption
                    and self.proof.kcfg.is_leaf(node.id)
                    and not self.proof.is_target(node.id)
                ):
                    self._checked_for_subsumption.add(node.id)
                    self._check_subsume(node)

        if self.proof.failed:
            self.save_failure_info()

        self.proof.write_proof_data()

    def refute_node(self, node: KCFG.Node) -> RefutationProof | None:
        _LOGGER.info(f'Attempting to refute node {node.id}')
        refutation = self.construct_node_refutation(node)
        if refutation is None:
            _LOGGER.error(f'Failed to refute node {node.id}')
            return None
        refutation.write_proof_data()

        self.proof.node_refutations[node.id] = refutation

        self.proof.write_proof_data()

        return refutation

    def unrefute_node(self, node: KCFG.Node) -> None:
        self.proof.remove_subproof(self.proof.get_refutation_id(node.id))
        del self.proof.node_refutations[node.id]
        self.proof.write_proof_data()
        _LOGGER.info(f'Disabled refutation of node {node.id}.')

    def construct_node_refutation(self, node: KCFG.Node) -> RefutationProof | None:  # TODO put into prover class
        path = single(self.proof.kcfg.paths_between(source_id=self.proof.init, target_id=node.id))
        branches_on_path = list(filter(lambda x: type(x) is KCFG.Split or type(x) is KCFG.NDBranch, reversed(path)))
        if len(branches_on_path) == 0:
            _LOGGER.error(f'Cannot refute node {node.id} in linear KCFG')
            return None
        closest_branch = branches_on_path[0]
        if type(closest_branch) is KCFG.NDBranch:
            _LOGGER.error(f'Cannot refute node {node.id} following a non-deterministic branch: not yet implemented')
            return None

        assert type(closest_branch) is KCFG.Split
        refuted_branch_root = closest_branch.targets[0]
        csubst = closest_branch.splits[refuted_branch_root.id]
        if len(csubst.subst) > 0:
            _LOGGER.error(
                f'Cannot refute node {node.id}: unexpected non-empty substitution {csubst.subst} in Split from {closest_branch.source.id}'
            )
            return None
        if len(csubst.constraints) > 1:
            _LOGGER.error(
                f'Cannot refute node {node.id}: unexpected non-singleton constraints {csubst.constraints} in Split from {closest_branch.source.id}'
            )
            return None

        # extract the path condition prior to the Split that leads to the node-to-refute
        pre_split_constraints = [
            mlEquals(TRUE, ml_pred_to_bool(c), arg_sort=BOOL) for c in closest_branch.source.cterm.constraints
        ]

        # extract the constriant added by the Split that leads to the node-to-refute
        last_constraint = mlEquals(TRUE, ml_pred_to_bool(csubst.constraints[0]), arg_sort=BOOL)

        refutation_id = self.proof.get_refutation_id(node.id)
        _LOGGER.info(f'Adding refutation proof {refutation_id} as subproof of {self.proof.id}')
        refutation = RefutationProof(
            id=refutation_id,
            sort=BOOL,
            pre_constraints=pre_split_constraints,
            last_constraint=last_constraint,
            proof_dir=self.proof.proof_dir,
        )

        self.proof.add_subproof(refutation)
        return refutation

    def save_failure_info(self) -> None:
        self.proof.failure_info = self.failure_info()

    def failure_info(self) -> APRFailureInfo:
        return APRFailureInfo.from_proof(self.proof, self.kcfg_explore, counterexample_info=self.counterexample_info)


@dataclass(frozen=True)
class APRSummary(ProofSummary):
    id: str
    status: ProofStatus
    admitted: bool
    nodes: int
    pending: int
    failing: int
    vacuous: int
    stuck: int
    terminal: int
    refuted: int
    subproofs: int

    @property
    def lines(self) -> list[str]:
        return [
            f'APRProof: {self.id}',
            f'    status: {self.status}',
            f'    admitted: {self.admitted}',
            f'    nodes: {self.nodes}',
            f'    pending: {self.pending}',
            f'    failing: {self.failing}',
            f'    vacuous: {self.vacuous}',
            f'    stuck: {self.stuck}',
            f'    terminal: {self.terminal}',
            f'    refuted: {self.refuted}',
            f'Subproofs: {self.subproofs}',
        ]


@dataclass(frozen=True)
class APRFailureInfo:
    pending_nodes: frozenset[int]
    failing_nodes: frozenset[int]
    path_conditions: FrozenDict[int, str]
    failure_reasons: FrozenDict[int, str]
    models: FrozenDict[int, frozenset[tuple[str, str]]]

    def __init__(
        self,
        failing_nodes: Iterable[int],
        pending_nodes: Iterable[int],
        path_conditions: Mapping[int, str],
        failure_reasons: Mapping[int, str],
        models: Mapping[int, Iterable[tuple[str, str]]],
    ):
        object.__setattr__(self, 'failing_nodes', frozenset(failing_nodes))
        object.__setattr__(self, 'pending_nodes', frozenset(pending_nodes))
        object.__setattr__(self, 'path_conditions', FrozenDict(path_conditions))
        object.__setattr__(self, 'failure_reasons', FrozenDict(failure_reasons))
        object.__setattr__(
            self, 'models', FrozenDict({node_id: frozenset(model) for (node_id, model) in models.items()})
        )

    @staticmethod
    def from_proof(proof: APRProof, kcfg_explore: KCFGExplore, counterexample_info: bool = False) -> APRFailureInfo:
        target = proof.kcfg.node(proof.target)
        pending_nodes = {node.id for node in proof.pending}
        failing_nodes = {node.id for node in proof.failing}
        path_conditions = {}
        failure_reasons = {}
        models = {}
        for node in proof.failing:
            node_cterm, _ = kcfg_explore.cterm_simplify(node.cterm)
            target_cterm, _ = kcfg_explore.cterm_simplify(target.cterm)
            _, reason = kcfg_explore.implication_failure_reason(node_cterm, target_cterm)
            path_condition = kcfg_explore.kprint.pretty_print(proof.path_constraints(node.id))
            failure_reasons[node.id] = reason
            path_conditions[node.id] = path_condition
            if counterexample_info:
                model_subst = kcfg_explore.cterm_get_model(node.cterm)
                if type(model_subst) is Subst:
                    model: list[tuple[str, str]] = []
                    for var, term in model_subst.to_dict().items():
                        term_kast = KInner.from_dict(term)
                        term_pretty = kcfg_explore.kprint.pretty_print(term_kast)
                        model.append((var, term_pretty))
                    models[node.id] = model
        return APRFailureInfo(
            failing_nodes=failing_nodes,
            pending_nodes=pending_nodes,
            path_conditions=path_conditions,
            failure_reasons=failure_reasons,
            models=models,
        )

    def print(self) -> list[str]:
        res_lines: list[str] = []

        num_pending = len(self.pending_nodes)
        num_failing = len(self.failing_nodes)
        res_lines.append(
            f'{num_pending + num_failing} Failure nodes. ({num_pending} pending and {num_failing} failing)'
        )

        if num_pending > 0:
            res_lines.append('')
            res_lines.append(f'Pending nodes: {sorted(self.pending_nodes)}')

        if num_failing > 0:
            res_lines.append('')
            res_lines.append('Failing nodes:')
            for node_id in self.failing_nodes:
                reason = self.failure_reasons[node_id]
                path_condition = self.path_conditions[node_id]
                res_lines.append('')
                res_lines.append(f'  Node id: {str(node_id)}')

                res_lines.append('  Failure reason:')
                res_lines += [f'    {line}' for line in reason.split('\n')]

                res_lines.append('  Path condition:')
                res_lines += [f'    {path_condition}']

                if node_id in self.models:
                    res_lines.append('  Model:')
                    for var, term in self.models[node_id]:
                        res_lines.append(f'    {var} = {term}')
                else:
                    res_lines.append('  Failed to generate a model.')

            res_lines.append('')
            res_lines.append('Join the Runtime Verification Discord server for support: https://discord.gg/CurfmXNtbN')
        return res_lines


class APRBMCProver(APRProver):
    proof: APRBMCProof
    _checked_nodes: list[int]

    def __init__(
        self,
        proof: APRBMCProof,
        kcfg_explore: KCFGExplore,
        counterexample_info: bool = False,
        always_check_subsumption: bool = True,
        fast_check_subsumption: bool = False,
    ) -> None:
        super().__init__(
            proof,
            kcfg_explore=kcfg_explore,
            counterexample_info=counterexample_info,
            always_check_subsumption=always_check_subsumption,
            fast_check_subsumption=fast_check_subsumption,
        )
        self._checked_nodes = []

    def advance_pending_node(
        self,
        node: KCFG.Node,
        execute_depth: int | None = None,
        cut_point_rules: Iterable[str] = (),
        terminal_rules: Iterable[str] = (),
    ) -> None:
        if node.id not in self._checked_nodes:
            _LOGGER.info(f'Checking bmc depth for node {self.proof.id}: {node.id}')
            self._checked_nodes.append(node.id)
            _prior_loops = [
                succ.source.id
                for succ in self.proof.shortest_path_to(node.id)
                if self.kcfg_explore.kcfg_semantics.same_loop(succ.source.cterm, node.cterm)
            ]
            prior_loops: list[NodeIdLike] = []
            for _pl in _prior_loops:
                if not (
                    self.proof.kcfg.zero_depth_between(_pl, node.id)
                    or any(self.proof.kcfg.zero_depth_between(_pl, pl) for pl in prior_loops)
                ):
                    prior_loops.append(_pl)
            _LOGGER.info(f'Prior loop heads for node {self.proof.id}: {(node.id, prior_loops)}')
            if len(prior_loops) > self.proof.bmc_depth:
                self.proof.add_bounded(node.id)
                return
        super().advance_pending_node(
            node=node,
            execute_depth=execute_depth,
            cut_point_rules=cut_point_rules,
            terminal_rules=terminal_rules,
        )


@dataclass(frozen=True)
class APRBMCSummary(ProofSummary):
    id: str
    bmc_depth: int
    status: ProofStatus
    nodes: int
    pending: int
    failing: int
    vacuous: int
    stuck: int
    terminal: int
    refuted: int
    bounded: int
    subproofs: int

    @property
    def lines(self) -> list[str]:
        return [
            f'APRBMCProof(depth={self.bmc_depth}): {self.id}',
            f'    status: {self.status}',
            f'    nodes: {self.nodes}',
            f'    pending: {self.pending}',
            f'    failing: {self.failing}',
            f'    vacuous: {self.vacuous}',
            f'    stuck: {self.stuck}',
            f'    terminal: {self.terminal}',
            f'    refuted: {self.refuted}',
            f'    bounded: {self.bounded}',
            f'Subproofs: {self.subproofs}',
        ]


@dataclass(frozen=True)
class APRProofResult(ABC):
    cterm_implies_time: int
    extend_cterm_time: int


@dataclass(frozen=True)
class APRProofExtendResult(APRProofResult):
    extend_result: ExtendResult
    node_id: int


@dataclass(frozen=True)
class APRProofSubsumeResult(APRProofResult):
    node_id: int
    subsume_node_id: int
    csubst: CSubst | None


class APRProofProcessData(parallel.ProcessData):
    kprint: KPrint
    kcfg_semantics: KCFGSemantics | None

    definition_dir: str | Path
    llvm_definition_dir: Path | None
    module_name: str
    command: str | Iterable[str] | None
    smt_timeout: int | None
    smt_retry_limit: int | None
    smt_tactic: str | None
    haskell_log_format: KoreExecLogFormat
    haskell_log_entries: Iterable[str]
    log_axioms_file: Path | None

    #      kore_servers: dict[str, KoreServer]

    def __init__(
        self,
        kprint: KPrint,
        kcfg_semantics: KCFGSemantics,
        definition_dir: str | Path,
        module_name: str,
        llvm_definition_dir: Path | None = None,
        command: str | Iterable[str] | None = None,
        smt_timeout: int | None = None,
        smt_retry_limit: int | None = None,
        smt_tactic: str | None = None,
        haskell_log_format: KoreExecLogFormat = KoreExecLogFormat.ONELINE,
        haskell_log_entries: Iterable[str] = (),
        log_axioms_file: Path | None = None,
    ) -> None:
        self.kprint = kprint
        self.kcfg_semantics = kcfg_semantics
        #          self.kore_servers = {}
        self.definition_dir = definition_dir
        self.llvm_definition_dir = llvm_definition_dir
        self.module_name = module_name
        self.command = command
        self.smt_timeout = smt_timeout
        self.smt_retry_limit = smt_retry_limit
        self.smt_tactic = smt_tactic
        self.haskell_log_format = haskell_log_format
        self.haskell_log_entries = haskell_log_entries
        self.log_axioms_file = log_axioms_file


#      def cleanup(self) -> None:
#          for server in self.kore_servers.values():
#              server.close()


class ParallelAPRProver(parallel.Prover[APRProof, APRProofResult, APRProofProcessData]):
    prover: APRProver
    kcfg_explore: KCFGExplore
    port: int
    client: KoreClient

    execute_depth: int | None
    cut_point_rules: Iterable[str]
    terminal_rules: Iterable[str]

    kprint: KPrint
    kcfg_semantics: KCFGSemantics | None
    id: str | None
    trace_rewrites: bool

    bug_report: BugReport | None
    bug_report_id: str | None

    total_cterm_implies_time: int
    total_cterm_extend_time: int

    def __init__(
        self,
        proof: APRProof,
        module_name: str,
        definition_dir: str | Path,
        execute_depth: int | None,
        kprint: KPrint,
        kcfg_semantics: KCFGSemantics | None,
        port: int,
        id: str | None,
        trace_rewrites: bool,
        cut_point_rules: Iterable[str],
        terminal_rules: Iterable[str],
        bug_report_id: str | None,
        llvm_definition_dir: Path | None = None,
        command: str | Iterable[str] | None = None,
        bug_report: BugReport | None = None,
        smt_timeout: int | None = None,
        smt_retry_limit: int | None = None,
        smt_tactic: str | None = None,
        haskell_log_format: KoreExecLogFormat = KoreExecLogFormat.ONELINE,
        haskell_log_entries: Iterable[str] = (),
        log_axioms_file: Path | None = None,
    ) -> None:
        self.execute_depth = execute_depth
        self.cut_point_rules = cut_point_rules
        self.terminal_rules = terminal_rules
        self.kprint = kprint
        self.kcfg_semantics = kcfg_semantics
        self.id = id
        self.trace_rewrites = trace_rewrites
        self.port = port
        self.bug_report = bug_report
        self.bug_report_id = bug_report_id
        self.total_cterm_extend_time = 0
        self.total_cterm_implies_time = 0
        self.client = KoreClient(
            host='localhost',
            port=self.port,
            bug_report=self.bug_report,
            bug_report_id=self.bug_report_id,
        )
        self.kcfg_explore = KCFGExplore(
            kprint=self.kprint,
            kore_client=self.client,
            kcfg_semantics=self.kcfg_semantics,
            id=self.id,
            trace_rewrites=self.trace_rewrites,
        )
        self.prover = APRProver(proof=proof, kcfg_explore=self.kcfg_explore)
        self.prover._check_all_terminals()

    def __del__(self) -> None:
        self.client.close()

    def steps(self, proof: APRProof) -> Iterable[APRProofStep]:
        """
        Return a list of `ProofStep[U]` which represents all the computation jobs as defined by `ProofStep`, which have not yet been computed and committed, and are available given the current state of `proof`. Note that this is a requirement which is not enforced by the type system.
        If `steps()` or `commit()` has been called on a proof `proof`, `steps()` may never again be called on `proof`.
        Must not modify `self` or `proof`.
        The output of this function must only change with calls to `self.commit()`.
        """
        steps: list[APRProofStep] = []
        target_node = proof.kcfg.node(proof.target)
        for pending_node in proof.pending:
            module_name = (
                self.prover.circularities_module_name
                if self.prover.nonzero_depth(pending_node)
                else self.prover.dependencies_module_name
            )

            subproofs: list[Proof] = (
                [Proof.read_proof_data(proof.proof_dir, i) for i in proof.subproof_ids]
                if proof.proof_dir is not None
                else []
            )

            apr_subproofs: list[APRProof] = [pf for pf in subproofs if isinstance(pf, APRProof)]

            steps.append(
                APRProofStep(
                    proof_id=proof.id,
                    cterm=pending_node.cterm,
                    node_id=pending_node.id,
                    dependencies_module_name=self.prover.dependencies_module_name,
                    circularities_module_name=self.prover.circularities_module_name,
                    target_cterm=target_node.cterm,
                    target_node_id=target_node.id,
                    use_module_name=module_name,
                    port=self.port,
                    execute_depth=self.execute_depth,
                    terminal_rules=self.terminal_rules,
                    cut_point_rules=self.cut_point_rules,
                    id=self.id,
                    trace_rewrites=self.trace_rewrites,
                    bug_report=self.bug_report,
                    bug_report_id=self.bug_report_id,
                    is_terminal=(self.kcfg_explore.kcfg_semantics.is_terminal(pending_node.cterm)),
                    target_is_terminal=(proof.target not in proof._terminal),
                    main_module_name=self.prover.main_module_name,
                    dependencies_as_rules=[d.as_rule() for d in apr_subproofs],
                    self_proof_as_rule=proof.as_rule(),
                    circularity=proof.circularity,
                    depth_is_nonzero=self.prover.nonzero_depth(pending_node),
                )
            )
        return steps

    def commit(self, proof: APRProof, update: APRProofResult) -> None:
        """
        Should update `proof` according to `update`.
        If `steps()` or `commit()` has been called on a proof `proof`, `commit()` may never again be called on `proof`.
        Must only be called with an `update` that was returned by `step.execute()` where `step` was returned by `self.steps(proof)`.
        Steps for a proof `proof` can have their results submitted any time after they are made available by `self.steps(proof)`, including in any order and multiple times, and the Prover must be able to handle this.
        """

        self.prover._check_all_terminals()

        self.total_cterm_extend_time += update.extend_cterm_time
        self.total_cterm_implies_time += update.cterm_implies_time

        # Extend proof as per `update`
        if type(update) is APRProofExtendResult:
            node = proof.kcfg.node(update.node_id)
            self.kcfg_explore.extend_kcfg(
                extend_result=update.extend_result, kcfg=proof.kcfg, node=node, logs=proof.logs
            )
        elif type(update) is APRProofSubsumeResult:
            proof.checked_for_subsumption.add(update.node_id)
            if update.csubst is None:
                proof._terminal.add(update.node_id)
            else:
                proof.kcfg.create_cover(update.node_id, proof.target, csubst=update.csubst)

        if proof.failed:
            self.prover.save_failure_info()

        proof.write_proof_data()


class ParallelAPRBMCProver(ParallelAPRProver):
    def __init__(
        self,
        proof: APRBMCProof,
        module_name: str,
        definition_dir: str | Path,
        execute_depth: int | None,
        kprint: KPrint,
        kcfg_semantics: KCFGSemantics | None,
        port: int,
        id: str | None,
        trace_rewrites: bool,
        cut_point_rules: Iterable[str],
        terminal_rules: Iterable[str],
        bug_report_id: str | None,
        llvm_definition_dir: Path | None = None,
        command: str | Iterable[str] | None = None,
        bug_report: BugReport | None = None,
        smt_timeout: int | None = None,
        smt_retry_limit: int | None = None,
        smt_tactic: str | None = None,
        haskell_log_format: KoreExecLogFormat = KoreExecLogFormat.ONELINE,
        haskell_log_entries: Iterable[str] = (),
        log_axioms_file: Path | None = None,
    ) -> None:
        self.execute_depth = execute_depth
        self.cut_point_rules = cut_point_rules
        self.terminal_rules = terminal_rules
        self.kprint = kprint
        self.kcfg_semantics = kcfg_semantics
        self.id = id
        self.trace_rewrites = trace_rewrites
        self.bug_report = bug_report
        self.bug_report_id = bug_report_id
        self.client = KoreClient(
            host='localhost',
            port=self.port,
            bug_report=self.bug_report,
            bug_report_id=self.bug_report_id,
        )
        self.kcfg_explore = KCFGExplore(
            kprint=self.kprint,
            kore_client=self.client,
            kcfg_semantics=self.kcfg_semantics,
            id=self.id,
            trace_rewrites=self.trace_rewrites,
        )
        self.prover = APRBMCProver(proof=proof, kcfg_explore=self.kcfg_explore)


@dataclass(frozen=True, eq=True)
class APRProofStep(parallel.ProofStep[APRProofResult, APRProofProcessData]):
    proof_id: str
    cterm: CTerm
    node_id: int
    dependencies_module_name: str
    circularities_module_name: str
    use_module_name: str
    target_cterm: CTerm
    target_node_id: int
    port: int
    execute_depth: int | None
    cut_point_rules: Iterable[str]
    terminal_rules: Iterable[str]
    is_terminal: bool
    target_is_terminal: bool

    main_module_name: str

    bug_report: BugReport | None
    bug_report_id: str | None

    id: str | None
    trace_rewrites: bool

    dependencies_as_rules: list[KRule]
    self_proof_as_rule: KRule
    circularity: bool
    depth_is_nonzero: bool

    #      @property
    #      def circularities_module_name(self) -> str:
    #          return self.circularities_module_name
    #
    #      @property
    #      def dependencies_module_name(self) -> str:
    #          return self.dependencies_module_name

    def __hash__(self) -> int:
        return hash((self.cterm, self.node_id))

    def exec(self, data: APRProofProcessData) -> APRProofResult:
        """
        Should perform some nontrivial computation given by `self`, which can be done independently of other calls to `exec()`.
        Allowed to be nondeterministic.
        Able to be called on any `ProofStep` returned by `prover.steps(proof)`.
        """

        print('ba', file=sys.stderr)

        init_kcfg_explore = False

        #          if data.kore_servers.get(self.proof_id) is None:
        #              init_kcfg_explore = True
        #              data.kore_servers[self.proof_id] = kore_server(
        #                  definition_dir=data.definition_dir,
        #                  llvm_definition_dir=data.llvm_definition_dir,
        #                  module_name=data.module_name,
        #                  command=data.command,
        #                  bug_report=self.bug_report,
        #                  smt_timeout=data.smt_timeout,
        #                  smt_retry_limit=data.smt_retry_limit,
        #                  smt_tactic=data.smt_tactic,
        #                  haskell_log_format=data.haskell_log_format,
        #                  haskell_log_entries=data.haskell_log_entries,
        #                  log_axioms_file=data.log_axioms_file,
        #                  fallback_on=None,
        #                  interim_simplification=None,
        #                  no_post_exec_simplify=None,
        #              )
        #          server = data.kore_servers[self.proof_id]

        print('bb', file=sys.stderr)

        with KoreClient(
            host='localhost',
            port=self.port,
            bug_report=self.bug_report,
            bug_report_id=self.bug_report_id,
        ) as client:
            kcfg_explore = KCFGExplore(
                kprint=data.kprint,
                kore_client=client,
                kcfg_semantics=data.kcfg_semantics,
                id=self.id,
                trace_rewrites=self.trace_rewrites,
            )

            #              if init_kcfg_explore:
            #                  kcfg_explore.add_dependencies_module(
            #                      self.main_module_name,
            #                      self.dependencies_module_name,
            #                      self.dependencies_as_claims,
            #                      priority=1,
            #                  )
            #                  kcfg_explore.add_dependencies_module(
            #                      self.main_module_name,
            #                      self.circularities_module_name,
            #                      self.dependencies_as_claims + ([self.self_proof_as_claim] if self.circularity else []),
            #                      priority=1,
            #                  )
            def _inject_module(module_name: str, import_name: str, sentences: list[KRule]) -> None:
                _module = KFlatModule(module_name, sentences, [KImport(import_name)])
                _kore_module = kflatmodule_to_kore(
                    kcfg_explore.kprint.definition, kcfg_explore.kprint.kompiled_kore, _module
                )
                kcfg_explore._kore_client.add_module(_kore_module, name_as_id=True)
            print('bc', file=sys.stderr)

            if init_kcfg_explore:
                _inject_module(self.dependencies_module_name, self.main_module_name, self.dependencies_as_rules)
                _inject_module(self.circularities_module_name, self.main_module_name, [self.self_proof_as_rule])
            print('bd', file=sys.stderr)

            cterm_implies_time = 0
            extend_cterm_time = 0

            if self.is_terminal or self.target_is_terminal:
                init_cterm_implies_time = time.time_ns()
                csubst = kcfg_explore.cterm_implies(self.cterm, self.target_cterm)
                cterm_implies_time = time.time_ns() - init_cterm_implies_time
                if csubst is not None or self.is_terminal:
                    return APRProofSubsumeResult(
                        node_id=self.node_id,
                        subsume_node_id=self.target_node_id,
                        csubst=csubst,
                        cterm_implies_time=cterm_implies_time,
                        extend_cterm_time=extend_cterm_time,
                    )

            print('be', file=sys.stderr)

            self.circularities_module_name if self.depth_is_nonzero else self.dependencies_module_name
            init_extend_cterm_time = time.time_ns()
            result = kcfg_explore.extend_cterm(
                self.cterm,
                module_name=self.use_module_name,
                execute_depth=self.execute_depth,
                terminal_rules=self.terminal_rules,
                cut_point_rules=self.cut_point_rules,
            )
            print('bf', file=sys.stderr)
            extend_cterm_time = time.time_ns() - init_extend_cterm_time
            return APRProofExtendResult(
                extend_result=result,
                node_id=self.node_id,
                cterm_implies_time=cterm_implies_time,
                extend_cterm_time=extend_cterm_time,
            )
