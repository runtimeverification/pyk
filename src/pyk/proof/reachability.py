from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from typing import TYPE_CHECKING

from pyk.kore.rpc import LogEntry

from ..cterm import CTerm
from ..kast.inner import KRewrite, KSort
from ..kast.manip import flatten_label, ml_pred_to_bool
from ..kast.outer import KClaim
from ..kcfg import KCFG
from ..kcfg.exploration import KCFGExploration
from ..prelude.kbool import BOOL, TRUE
from ..prelude.ml import mlAnd, mlEquals, mlTop
from ..utils import FrozenDict, ensure_dir_path, hash_str, shorten_hashes, single
from .equality import ProofSummary, Prover, RefutationProof
from .proof import CompositeSummary, Proof, ProofStatus

if TYPE_CHECKING:
    from collections.abc import Iterable, Mapping
    from pathlib import Path
    from typing import Any, Final, TypeVar

    from ..kast.inner import KInner
    from ..kast.outer import KDefinition
    from ..kcfg import KCFGExplore
    from ..kcfg.kcfg import NodeIdLike
    from ..ktool.kprint import KPrint

    T = TypeVar('T', bound='Proof')

_LOGGER: Final = logging.getLogger(__name__)


class APRProof(Proof):
    """APRProof and APRProver implement all-path reachability logic,
    as introduced by A. Stefanescu and others in their paper 'All-Path Reachability Logic':
    https://doi.org/10.23638/LMCS-15(2:5)2019
    Note that reachability logic formula `phi =>A psi` has *not* the same meaning
    as CTL/CTL*'s `phi -> AF psi`, since reachability logic ignores infinite traces.
    """

    kcfg_exploration: KCFGExploration
    node_refutations: dict[NodeIdLike, RefutationProof]  # TODO _node_refutatations
    init: NodeIdLike
    target: NodeIdLike
    logs: dict[int, tuple[LogEntry, ...]]
    circularity: bool

    def __init__(
        self,
        id: str,
        kcfg_exploration: KCFGExploration,
        init: NodeIdLike,
        target: NodeIdLike,
        logs: dict[int, tuple[LogEntry, ...]],
        proof_dir: Path | None = None,
        node_refutations: dict[int, str] | None = None,
        subproof_ids: Iterable[str] = (),
        circularity: bool = False,
        admitted: bool = False,
    ):
        super().__init__(id, proof_dir=proof_dir, subproof_ids=subproof_ids, admitted=admitted)
        self.kcfg_exploration = kcfg_exploration
        self.init = init
        self.target = target
        self.logs = logs
        self.circularity = circularity
        self.node_refutations = {}
        self.kcfg_exploration.kcfg.cfg_dir = self.proof_subdir / 'kcfg' if self.proof_subdir else None

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
    def terminals(self) -> list[KCFG.Node]:
        return self.kcfg_exploration.terminals

    @property
    def pending(self) -> list[KCFG.Node]:
        return [node for node in self.kcfg_exploration.explorables if self.is_pending(node.id)]

    @property
    def failing(self) -> list[KCFG.Node]:
        return [nd for nd in self.kcfg_exploration.kcfg.leaves if self.is_failing(nd.id)]

    def is_refuted(self, node_id: NodeIdLike) -> bool:
        return self.kcfg_exploration.kcfg._resolve(node_id) in self.node_refutations.keys()

    def is_terminal(self, node_id: NodeIdLike) -> bool:
        return self.kcfg_exploration.is_terminal(node_id)

    def is_pending(self, node_id: NodeIdLike) -> bool:
        return (
            self.kcfg_exploration.is_explorable(node_id)
            and not self.is_target(node_id)
            and not self.is_refuted(node_id)
        )

    def is_init(self, node_id: NodeIdLike) -> bool:
        return self.kcfg_exploration.kcfg._resolve(node_id) == self.kcfg_exploration.kcfg._resolve(self.init)

    def is_target(self, node_id: NodeIdLike) -> bool:
        return self.kcfg_exploration.kcfg._resolve(node_id) == self.kcfg_exploration.kcfg._resolve(self.target)

    def is_failing(self, node_id: NodeIdLike) -> bool:
        return (
            self.kcfg_exploration.kcfg.is_leaf(node_id)
            and not self.kcfg_exploration.is_explorable(node_id)
            and not self.is_target(node_id)
            and not self.is_refuted(node_id)
        )

    def shortest_path_to(self, node_id: NodeIdLike) -> tuple[KCFG.Successor, ...]:
        spb = self.kcfg_exploration.kcfg.shortest_path_between(self.init, node_id)
        assert spb is not None
        return spb

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
        kcfg_exploration = KCFGExploration.from_dict(dct['kcfg_exploration'])
        init_node = dct['init']
        target_node = dct['target']
        id = dct['id']
        circularity = dct.get('circularity', False)
        admitted = dct.get('admitted', False)
        subproof_ids = dct['subproof_ids'] if 'subproof_ids' in dct else []
        node_refutations: dict[int, str] = {}
        if 'node_refutation' in dct:
            node_refutations = {
                kcfg_exploration.kcfg._resolve(node_id): proof_id for (node_id, proof_id) in dct['node_refutations']
            }
        if 'logs' in dct:
            logs = {int(k): tuple(LogEntry.from_dict(l) for l in ls) for k, ls in dct['logs'].items()}
        else:
            logs = {}

        return APRProof(
            id,
            kcfg_exploration,
            init_node,
            target_node,
            logs=logs,
            circularity=circularity,
            admitted=admitted,
            proof_dir=proof_dir,
            subproof_ids=subproof_ids,
            node_refutations=node_refutations,
        )

    @staticmethod
    def from_claim(
        defn: KDefinition,
        claim: KClaim,
        logs: dict[int, tuple[LogEntry, ...]],
        *args: Any,
        **kwargs: Any,
    ) -> APRProof:
        apr_proof = APRProof(claim.label, KCFGExploration(KCFG()), init=0, target=0, logs=logs, **kwargs)

        kcfg_dir = apr_proof.proof_subdir / 'kcfg' if apr_proof.proof_subdir else None

        kcfg, init_node, target_node = KCFG.from_claim(defn, claim, cfg_dir=kcfg_dir)
        apr_proof.kcfg_exploration.kcfg = kcfg
        apr_proof.init = init_node
        apr_proof.target = target_node

        return apr_proof

    def as_claim(self, kprint: KPrint) -> KClaim:
        fr: CTerm = self.kcfg_exploration.kcfg.node(self.init).cterm
        to: CTerm = self.kcfg_exploration.kcfg.node(self.target).cterm
        fr_config_sorted = kprint.definition.sort_vars(fr.config, sort=KSort('GeneratedTopCell'))
        to_config_sorted = kprint.definition.sort_vars(to.config, sort=KSort('GeneratedTopCell'))
        kc = KClaim(
            body=KRewrite(fr_config_sorted, to_config_sorted),
            requires=ml_pred_to_bool(mlAnd(fr.constraints)),
            ensures=ml_pred_to_bool(mlAnd(to.constraints)),
        )
        return kc

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
        dct = super().dict
        dct['type'] = 'APRProof'
        dct['kcfg_exploration'] = self.kcfg_exploration.to_dict()
        dct['init'] = self.init
        dct['target'] = self.target
        dct['node_refutations'] = {node_id: proof.id for (node_id, proof) in self.node_refutations.items()}
        dct['circularity'] = self.circularity
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
                    len(self.kcfg_exploration.kcfg.nodes),
                    len(self.pending),
                    len(self.failing),
                    len(self.kcfg_exploration.kcfg.stuck),
                    len(self.kcfg_exploration._terminals),
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
        terminals = proof_dict['terminals']
        logs = {int(k): tuple(LogEntry.from_dict(l) for l in ls) for k, ls in proof_dict['logs'].items()}
        subproof_ids = proof_dict['subproof_ids']
        node_refutations = {kcfg._resolve(node_id): proof_id for (node_id, proof_id) in proof_dict['node_refutations']}

        return APRProof(
            id=id,
            kcfg_exploration=KCFGExploration(kcfg, terminals),
            init=init,
            target=target,
            logs=logs,
            circularity=circularity,
            admitted=admitted,
            proof_dir=proof_dir,
            subproof_ids=subproof_ids,
            node_refutations=node_refutations,
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
        dct['init'] = self.kcfg_exploration.kcfg._resolve(self.init)
        dct['target'] = self.kcfg_exploration.kcfg._resolve(self.target)
        dct['terminals'] = sorted(self.kcfg_exploration._terminals)
        dct['node_refutations'] = {
            self.kcfg_exploration.kcfg._resolve(node_id): proof.id for (node_id, proof) in self.node_refutations.items()
        }
        dct['circularity'] = self.circularity
        logs = {int(k): [l.to_dict() for l in ls] for k, ls in self.logs.items()}
        dct['logs'] = logs

        proof_json.write_text(json.dumps(dct))

        self.kcfg_exploration.kcfg.write_cfg_data()


class APRBMCProof(APRProof):
    """APRBMCProof and APRBMCProver perform bounded model-checking of an all-path reachability logic claim."""

    bmc_depth: int
    _bounded: set[int]

    def __init__(
        self,
        id: str,
        kcfg_exploration: KCFGExploration,
        init: NodeIdLike,
        target: NodeIdLike,
        logs: dict[int, tuple[LogEntry, ...]],
        bmc_depth: int,
        bounded: Iterable[int] | None = None,
        proof_dir: Path | None = None,
        subproof_ids: Iterable[str] = (),
        node_refutations: dict[int, str] | None = None,
        circularity: bool = False,
        admitted: bool = False,
    ):
        super().__init__(
            id,
            kcfg_exploration,
            init,
            target,
            logs,
            proof_dir=proof_dir,
            subproof_ids=subproof_ids,
            node_refutations=node_refutations,
            circularity=circularity,
            admitted=admitted,
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
        terminals = proof_dict['terminals']
        admitted = bool(proof_dict['admitted'])
        logs = {int(k): tuple(LogEntry.from_dict(l) for l in ls) for k, ls in proof_dict['logs'].items()}
        subproof_ids = proof_dict['subproof_ids']
        node_refutations = {kcfg._resolve(node_id): proof_id for (node_id, proof_id) in proof_dict['node_refutations']}
        bounded = proof_dict['bounded']
        bmc_depth = int(proof_dict['bmc_depth'])

        return APRBMCProof(
            id=id,
            kcfg_exploration=KCFGExploration(kcfg, terminals),
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
        dct['init'] = self.kcfg_exploration.kcfg._resolve(self.init)
        dct['target'] = self.kcfg_exploration.kcfg._resolve(self.target)
        dct['node_refutations'] = {
            self.kcfg_exploration.kcfg._resolve(node_id): proof.id for (node_id, proof) in self.node_refutations.items()
        }
        dct['circularity'] = self.circularity
        logs = {int(k): [l.to_dict() for l in ls] for k, ls in self.logs.items()}
        dct['logs'] = logs
        dct['terminals'] = sorted(self.kcfg_exploration._terminals)
        dct['bounded'] = sorted(self._bounded)
        dct['bmc_depth'] = self.bmc_depth

        proof_json.write_text(json.dumps(dct))

        self.kcfg_exploration.kcfg.write_cfg_data()

    @property
    def bounded(self) -> list[KCFG.Node]:
        return [nd for nd in self.kcfg_exploration.kcfg.leaves if self.is_bounded(nd.id)]

    def is_bounded(self, node_id: NodeIdLike) -> bool:
        return self.kcfg_exploration.kcfg._resolve(node_id) in self._bounded

    def is_pending(self, node_id: NodeIdLike) -> bool:
        return super().is_pending(node_id) and not self.is_bounded(node_id)

    def is_failing(self, node_id: NodeIdLike) -> bool:
        return super().is_failing(node_id) and not self.is_bounded(node_id)

    def prune(self, node_id: NodeIdLike, keep_nodes: Iterable[NodeIdLike] = ()) -> list[int]:
        pruned_nodes = self.kcfg_exploration.prune(node_id, keep_nodes=keep_nodes)
        for nid in pruned_nodes:
            self.remove_bounded(nid)
        return pruned_nodes

    @classmethod
    def from_dict(cls: type[APRBMCProof], dct: Mapping[str, Any], proof_dir: Path | None = None) -> APRBMCProof:
        kcfg_exploration = KCFGExploration.from_dict(dct['kcfg_exploration'])
        init = dct['init']
        target = dct['target']
        bounded = dct['bounded']

        admitted = dct.get('admitted', False)
        circularity = dct.get('circularity', False)
        bmc_depth = dct['bmc_depth']
        subproof_ids = dct['subproof_ids'] if 'subproof_ids' in dct else []
        node_refutations: dict[int, str] = {}
        if 'node_refutation' in dct:
            node_refutations = {
                kcfg_exploration.kcfg._resolve(node_id): proof_id for (node_id, proof_id) in dct['node_refutations']
            }
        id = dct['id']
        if 'logs' in dct:
            logs = {int(k): tuple(LogEntry.from_dict(l) for l in ls) for k, ls in dct['logs'].items()}
        else:
            logs = {}

        return APRBMCProof(
            id,
            kcfg_exploration,
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
        aprbmc_proof = APRBMCProof(
            claim.label, KCFGExploration(KCFG()), bmc_depth=bmc_depth, init=0, target=0, logs={}, proof_dir=proof_dir
        )

        kcfg_dir = aprbmc_proof.proof_subdir / 'kcfg' if aprbmc_proof.proof_subdir else None

        kcfg, init_node, target_node = KCFG.from_claim(defn, claim, cfg_dir=kcfg_dir)
        aprbmc_proof.kcfg_exploration.kcfg = kcfg
        aprbmc_proof.init = init_node
        aprbmc_proof.target = target_node

        return aprbmc_proof

    def add_bounded(self, nid: NodeIdLike) -> None:
        self._bounded.add(self.kcfg_exploration.kcfg._resolve(nid))

    def remove_bounded(self, node_id: NodeIdLike) -> None:
        self._bounded.discard(self.kcfg_exploration.kcfg._resolve(node_id))

    @property
    def summary(self) -> CompositeSummary:
        subproofs_summaries = [subproof.summary for subproof in self.subproofs]
        return CompositeSummary(
            [
                APRBMCSummary(
                    self.id,
                    self.bmc_depth,
                    self.status,
                    len(self.kcfg_exploration.kcfg.nodes),
                    len(self.pending),
                    len(self.failing),
                    len(self.kcfg_exploration.kcfg.stuck),
                    len(self.kcfg_exploration._terminals),
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

    _target: KCFG.Node
    _target_is_terminal: bool

    _subsumption_checks: dict[int, bool]

    def __init__(
        self,
        proof: APRProof,
        kcfg_explore: KCFGExplore,
    ) -> None:
        super().__init__(kcfg_explore)
        self.proof = proof
        self.main_module_name = self.kcfg_explore.kprint.definition.main_module_name

        subproofs: list[Proof] = (
            [Proof.read_proof_data(proof.proof_dir, i) for i in proof.subproof_ids]
            if proof.proof_dir is not None
            else []
        )

        apr_subproofs: list[APRProof] = [pf for pf in subproofs if isinstance(pf, APRProof)]

        dependencies_as_claims: list[KClaim] = [d.as_claim(self.kcfg_explore.kprint) for d in apr_subproofs]

        self.dependencies_module_name = self.main_module_name + '-DEPENDS-MODULE'
        self.kcfg_explore.add_dependencies_module(
            self.main_module_name,
            self.dependencies_module_name,
            dependencies_as_claims,
            priority=1,
        )
        self.circularities_module_name = self.main_module_name + '-CIRCULARITIES-MODULE'
        self.kcfg_explore.add_dependencies_module(
            self.main_module_name,
            self.circularities_module_name,
            dependencies_as_claims + ([proof.as_claim(self.kcfg_explore.kprint)] if proof.circularity else []),
            priority=1,
        )

        self._target = self.proof.kcfg_exploration.kcfg.node(self.proof.target)
        self._target_is_terminal = kcfg_explore._check_terminal(self._target)

        # All nodes marked as terminal are semantically terminal
        for node in self.proof.terminals:
            assert kcfg_explore._check_terminal(node)

        # Target node is not marked as terminal
        assert self._target.id not in self.proof.kcfg_exploration._terminals

        # All non-target leaves not marked as terminal are checked for terminalness
        for node in [
            node
            for node in self.proof.kcfg_exploration.kcfg.nodes
            if not self.proof.is_terminal(node.id) and not self.proof.is_target(node.id)
        ]:
            if kcfg_explore._check_terminal(node):
                self.proof.kcfg_exploration.add_terminal(node.id)

        # Subsumption checks
        self._subsumption_checks = { }

        for node in self.proof.terminals:
            self._check_subsume(node)

    def nonzero_depth(self, node: KCFG.Node) -> bool:
        return not self.proof.kcfg_exploration.kcfg.zero_depth_between(self.proof.init, node.id)

    def _check_subsume(self, node: KCFG.Node) -> bool:
        if node.id not in self._subsumption_checks:
            _LOGGER.info(
                f'Checking subsumption into target state {self.proof.id}: {shorten_hashes((node.id, self._target.id))}'
            )
            csubst = self.kcfg_explore.cterm_implies(node.cterm, self._target.cterm)
            if csubst is not None:
                self.proof.kcfg_exploration.kcfg.create_cover(node.id, self._target.id, csubst=csubst)
                _LOGGER.info(f'Subsumed into target node {self.proof.id}: {shorten_hashes((node.id, self._target.id))}')
                self._subsumption_checks[node.id] = True
            else:
                self._subsumption_checks[node.id] = False

        return self._subsumption_checks[node.id]

    def advance_pending_node(
        self,
        node: KCFG.Node,
        execute_depth: int | None = None,
        cut_point_rules: Iterable[str] = (),
        terminal_rules: Iterable[str] = (),
    ) -> None:
        if not self._target_is_terminal:
            if self._check_subsume(node):
                return

        module_name = self.circularities_module_name if self.nonzero_depth(node) else self.dependencies_module_name
        self.kcfg_explore.extend(
            self.proof.kcfg_exploration,
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

            for node in self.proof.terminals:
                self._check_subsume(node)

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
        path = single(self.proof.kcfg_exploration.kcfg.paths_between(source_id=self.proof.init, target_id=node.id))
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

    def failure_info(self) -> APRFailureInfo:
        return APRFailureInfo.from_proof(self.proof, self.kcfg_explore)


@dataclass(frozen=True)
class APRSummary(ProofSummary):
    id: str
    status: ProofStatus
    admitted: bool
    nodes: int
    pending: int
    failing: int
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
            f'    stuck: {self.stuck}',
            f'    terminal: {self.terminal}',
            f'    refuted: {self.refuted}',
            f'Subproofs: {self.subproofs}',
        ]


@dataclass(frozen=True)
class APRFailureInfo:
    failing_nodes: FrozenDict[int, tuple[str, str]]
    pending_nodes: frozenset[int]

    def __init__(self, failing_nodes: Mapping[int, tuple[str, str]], pending_nodes: Iterable[int]):
        object.__setattr__(self, 'failing_nodes', FrozenDict(failing_nodes))
        object.__setattr__(self, 'pending_nodes', frozenset(pending_nodes))

    @staticmethod
    def from_proof(proof: APRProof, kcfg_explore: KCFGExplore) -> APRFailureInfo:
        target = proof.kcfg_exploration.kcfg.node(proof.target)
        pending_nodes = {node.id for node in proof.pending}
        failing_nodes = {}
        for node in proof.failing:
            simplified_node, _ = kcfg_explore.cterm_simplify(node.cterm)
            simplified_target, _ = kcfg_explore.cterm_simplify(target.cterm)
            node_cterm = CTerm.from_kast(simplified_node)
            target_cterm = CTerm.from_kast(simplified_target)
            _, reason = kcfg_explore.implication_failure_reason(node_cterm, target_cterm)
            path_condition = kcfg_explore.kprint.pretty_print(proof.path_constraints(node.id))
            failing_nodes[node.id] = (reason, path_condition)
        return APRFailureInfo(failing_nodes=failing_nodes, pending_nodes=pending_nodes)

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
            print(self.failing_nodes)
            for node_id, info in self.failing_nodes.items():
                print(info)
                (reason, path_condition) = info
                res_lines.append('')
                res_lines.append(f'  Node id: {str(node_id)}')

                res_lines.append('  Failure reason:')
                res_lines += [f'    {line}' for line in reason.split('\n')]

                res_lines.append('  Path condition:')
                res_lines += [f'    {path_condition}']

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
    ) -> None:
        super().__init__(
            proof,
            kcfg_explore=kcfg_explore,
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
                    self.proof.kcfg_exploration.kcfg.zero_depth_between(_pl, node.id)
                    or any(self.proof.kcfg_exploration.kcfg.zero_depth_between(_pl, pl) for pl in prior_loops)
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
            f'    stuck: {self.stuck}',
            f'    terminal: {self.terminal}',
            f'    refuted: {self.refuted}',
            f'    bounded: {self.bounded}',
            f'Subproofs: {self.subproofs}',
        ]
