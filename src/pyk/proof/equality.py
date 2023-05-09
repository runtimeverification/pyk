from __future__ import annotations

import json
import logging
from typing import TYPE_CHECKING

from ..kast.inner import KApply, KInner, KLabel, KSort, KVariable
from ..kast.manip import extract_lhs, extract_rhs, flatten_label, free_vars
from ..prelude.k import GENERATED_TOP_CELL
from ..prelude.kbool import BOOL, FALSE, TRUE
from ..prelude.ml import is_bottom, mlAnd, mlEquals, mlImplies
from ..utils import hash_str
from .proof import Proof, ProofStatus

if TYPE_CHECKING:
    from collections.abc import Iterable, Mapping
    from pathlib import Path
    from typing import Any, Final, TypeVar

    from ..cterm import CSubst
    from ..kast.outer import KClaim, KDefinition
    from ..kcfg import KCFGExplore
    from ..ktool.kprint import KPrint

    T = TypeVar('T', bound='Proof')

_LOGGER: Final = logging.getLogger(__name__)


class EqualityProof(Proof):
    lhs_body: KInner
    rhs_body: KInner
    sort: KSort
    constraints: tuple[KInner, ...]
    implication_check_result: CSubst | None
    satisfiable: bool | None
    predicate: KInner | None

    def __init__(
        self,
        id: str,
        lhs_body: KInner,
        rhs_body: KInner,
        sort: KSort,
        constraints: Iterable[KInner] = (),
        satisfiable: bool | None = None,
        predicate: KInner | None = None,
        simplified_constraints: KInner | None = None,
        proof_dir: Path | None = None,
    ):
        super().__init__(id, proof_dir=proof_dir)
        self.lhs_body = lhs_body
        self.rhs_body = rhs_body
        self.sort = sort
        self.constraints = tuple(constraints)
        self.satisfiable = satisfiable
        self.predicate = predicate
        self.simplified_constraints = simplified_constraints

    @staticmethod
    def from_claim(claim: KClaim, defn: KDefinition) -> EqualityProof:
        lhs_body = extract_lhs(claim.body)
        rhs_body = extract_rhs(claim.body)
        assert type(lhs_body) is KApply
        sort = defn.return_sort(lhs_body.label)
        constraints = [mlEquals(TRUE, c, arg_sort=BOOL) for c in flatten_label('_andBool_', claim.requires)]
        return EqualityProof(claim.label, lhs_body, rhs_body, sort, constraints=constraints)

    @property
    def equality(self) -> KInner:
        return KApply('_==K_', [self.lhs_body, self.rhs_body])

    @property
    def implication(self) -> tuple[KInner, KInner]:
        antecedent_kast = mlAnd(self.constraints)
        consequent_kast = mlEquals(TRUE, self.equality, arg_sort=BOOL, sort=GENERATED_TOP_CELL)
        return antecedent_kast, consequent_kast

    def add_constraint(self, new_constraint: KInner) -> None:
        self.constraints = (*self.constraints, new_constraint)

    def set_satisfiable(self, satisfiable: bool) -> None:
        self.satisfiable = satisfiable

    def set_predicate(self, predicate: KInner) -> None:
        self.predicate = predicate

    def set_simplified_constraints(self, simplified: KInner) -> None:
        self.simplified_constraints = simplified

    @staticmethod
    def read_proof(id: str, proof_dir: Path) -> EqualityProof:
        proof_path = proof_dir / f'{hash_str(id)}.json'
        if EqualityProof.proof_exists(id, proof_dir):
            proof_dict = json.loads(proof_path.read_text())
            _LOGGER.info(f'Reading EqualityProof from file {id}: {proof_path}')
            return EqualityProof.from_dict(proof_dict, proof_dir=proof_dir)
        raise ValueError(f'Could not load EqualityProof from file {id}: {proof_path}')

    @property
    def is_sastisfiable(self) -> bool:
        return self.satisfiable is not None and self.satisfiable

    @property
    def status(self) -> ProofStatus:
        if self.satisfiable is None:
            return ProofStatus.PENDING
        elif self.satisfiable:
            if self.rhs_body == FALSE:
                return ProofStatus.FAILED
            else:
                return ProofStatus.PASSED
        else:
            if self.rhs_body == FALSE:
                return ProofStatus.PASSED
            else:
                return ProofStatus.FAILED

    @classmethod
    def from_dict(cls: type[EqualityProof], dct: Mapping[str, Any], proof_dir: Path | None = None) -> EqualityProof:
        id = dct['id']
        lhs_body = KInner.from_dict(dct['lhs_body'])
        rhs_body = KInner.from_dict(dct['rhs_body'])
        sort = KSort.from_dict(dct['sort'])
        constraints = [KInner.from_dict(c) for c in dct['constraints']]
        satisfiable = dct['satisfiable'] if 'satisfiable' in dct else None
        predicate = KInner.from_dict(dct['predicate']) if 'predicate' in dct else None
        return EqualityProof(
            id,
            lhs_body,
            rhs_body,
            sort,
            constraints=constraints,
            satisfiable=satisfiable,
            predicate=predicate,
            proof_dir=proof_dir,
        )

    @property
    def dict(self) -> dict[str, Any]:
        dct = {
            'type': 'EqualityProof',
            'id': self.id,
            'lhs_body': self.lhs_body.to_dict(),
            'rhs_body': self.rhs_body.to_dict(),
            'sort': self.sort.to_dict(),
            'constraints': [c.to_dict() for c in self.constraints],
        }
        if self.satisfiable is not None:
            dct['satisfiable'] = self.satisfiable  # type: ignore
        if self.predicate is not None:
            dct['predicate'] = self.predicate.to_dict()
        return dct

    def pretty(self, kprint: KPrint) -> Iterable[str]:
        lines = [
            f'LHS: {kprint.pretty_print(self.lhs_body)}',
            f'RHS: {kprint.pretty_print(self.rhs_body)}',
            f'Implication: {kprint.pretty_print(mlImplies(self.implication[0], self.implication[1]))}',
        ]
        if self.simplified_constraints:
            lines.append(f'Simplified constraints: {kprint.pretty_print(self.simplified_constraints)}')
        if self.satisfiable is not None:
            lines.append(f'Implication satisfiable: {self.satisfiable}')
        if self.predicate is not None:
            lines.append(f'Implication predicate: {self.predicate}')
        return lines

    @property
    def summary(self) -> Iterable[str]:
        return [
            f'EqualityProof: {self.id}',
            f'    satisfiable: {self.satisfiable}',
        ]


class EqualityProver:
    proof: EqualityProof

    def __init__(self, proof: EqualityProof) -> None:
        self.proof = proof

    def advance_proof(self, kcfg_explore: KCFGExplore, bind_consequent_variables: bool = True) -> None:
        if self.proof.satisfiable is not None:
            return

        antecedent, consequent = self.proof.implication

        _, kore_client = kcfg_explore._kore_rpc

        # first simplify the antecedent to make sure it makes sense
        antecedent_simplified_kore = kore_client.simplify(kcfg_explore.kprint.kast_to_kore(antecedent))
        antecedent_simplified_kast = kcfg_explore.kprint.kore_to_kast(antecedent_simplified_kore)
        _LOGGER.info(f'Simplified antecedent: {kcfg_explore.kprint.pretty_print(antecedent_simplified_kast)}')
        self.proof.set_simplified_constraints(antecedent_simplified_kast)
        if is_bottom(antecedent_simplified_kast):
            _LOGGER.warning(
                'Antecedent of implication (proof constraints) simplify to #Bottom, the implication will not be checked.'
            )
            self.proof.write_proof()
            return None

        # second, check implication from antecedent to consequent
        dummy_config = kcfg_explore.kprint.definition.empty_config(sort=GENERATED_TOP_CELL)
        antecedent_with_config = mlAnd([dummy_config, antecedent])
        consequent_with_config = mlAnd([dummy_config, consequent])
        _consequent = consequent_with_config
        if bind_consequent_variables:
            _consequent = consequent_with_config
            fv_antecedent = free_vars(antecedent_with_config)
            unbound_consequent = [v for v in free_vars(_consequent) if v not in fv_antecedent]
            if len(unbound_consequent) > 0:
                _LOGGER.debug(f'Binding variables in consequent: {unbound_consequent}')
                for uc in unbound_consequent:
                    _consequent = KApply(KLabel('#Exists', [GENERATED_TOP_CELL]), [KVariable(uc), _consequent])

        _LOGGER.info(f'Attempting EqualityProof {self.proof.id}')
        result = kore_client.implies(
            kcfg_explore.kprint.kast_to_kore(antecedent_with_config, GENERATED_TOP_CELL),
            kcfg_explore.kprint.kast_to_kore(_consequent, GENERATED_TOP_CELL),
        )
        if not result.satisfiable:
            if result.substitution is not None:
                _LOGGER.debug(f'Received a non-empty substitution for unsatisfiable implication: {result.substitution}')
            if result.predicate is not None:
                _LOGGER.debug(f'Received a non-empty predicate for unsatisfiable implication: {result.predicate}')
        if result.substitution is None:
            raise ValueError('Received empty substutition for satisfiable implication.')
        if result.predicate is None:
            raise ValueError('Received empty predicate for satisfiable implication.')

        self.proof.set_satisfiable(result.satisfiable)
        self.proof.set_predicate(kcfg_explore.kprint.kore_to_kast(result.predicate))
        self.proof.write_proof()
