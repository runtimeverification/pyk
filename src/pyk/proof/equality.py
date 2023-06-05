from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from ..cterm import CSubst, CTerm
from ..kast.inner import KInner, KSort, Subst
from ..kast.manip import extract_lhs, extract_rhs, flatten_label
from ..prelude.k import GENERATED_TOP_CELL
from ..prelude.kbool import BOOL, TRUE
from ..prelude.ml import is_bottom, is_top, mlAnd, mlEquals
from .proof import Proof, ProofStatus

if TYPE_CHECKING:
    from collections.abc import Iterable, Mapping
    from pathlib import Path
    from typing import Any, Final, TypeVar

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
    csubst: CSubst | None

    def __init__(
        self,
        id: str,
        lhs_body: KInner,
        rhs_body: KInner,
        sort: KSort,
        constraints: Iterable[KInner] = (),
        csubst: CSubst | None = None,
        simplified_constraints: KInner | None = None,
        simplified_equality: KInner | None = None,
        proof_dir: Path | None = None,
    ):
        super().__init__(id, proof_dir=proof_dir)
        self.lhs_body = lhs_body
        self.rhs_body = rhs_body
        self.sort = sort
        self.constraints = tuple(constraints)
        self.csubst = csubst
        self.simplified_constraints = simplified_constraints
        self.simplified_equality = simplified_equality

    @staticmethod
    def from_claim(claim: KClaim, defn: KDefinition, proof_dir: Path | None = None) -> EqualityProof:
        claim_body = defn.add_sort_params(claim.body)
        sort = defn.sort_strict(claim_body)
        lhs_body = extract_lhs(claim_body)
        rhs_body = extract_rhs(claim_body)
        if not (claim.ensures is None or claim.ensures == TRUE):
            raise ValueError(f'Cannot convert claim to EqualityProof due to non-trival ensures clause {claim.ensures}')
        constraints = [mlEquals(TRUE, c, arg_sort=BOOL) for c in flatten_label('_andBool_', claim.requires)]
        return EqualityProof(claim.label, lhs_body, rhs_body, sort, constraints=constraints, proof_dir=proof_dir)

    @property
    def equality(self) -> KInner:
        return mlEquals(self.lhs_body, self.rhs_body, arg_sort=self.sort, sort=GENERATED_TOP_CELL)

    @property
    def constraint(self) -> KInner:
        return mlAnd(self.constraints)

    def add_constraint(self, new_constraint: KInner) -> None:
        self.constraints = (*self.constraints, new_constraint)

    def set_satisfiable(self, satisfiable: bool) -> None:
        self.satisfiable = satisfiable

    def set_csubst(self, csubst: CSubst) -> None:
        self.csubst = csubst

    def set_simplified_constraints(self, simplified: KInner) -> None:
        self.simplified_constraints = simplified

    def set_simplified_equality(self, simplified: KInner) -> None:
        self.simplified_equality = simplified

    @property
    def status(self) -> ProofStatus:
        if self.simplified_constraints is None or self.simplified_equality is None:
            return ProofStatus.PENDING
        elif self.csubst is None:
            return ProofStatus.FAILED
        else:
            return ProofStatus.PASSED

    @classmethod
    def from_dict(cls: type[EqualityProof], dct: Mapping[str, Any], proof_dir: Path | None = None) -> EqualityProof:
        id = dct['id']
        lhs_body = KInner.from_dict(dct['lhs_body'])
        rhs_body = KInner.from_dict(dct['rhs_body'])
        sort = KSort.from_dict(dct['sort'])
        constraints = [KInner.from_dict(c) for c in dct['constraints']]
        simplified_constraints = (
            KInner.from_dict(dct['simplified_constraints']) if 'simplified_constraints' in dct else None
        )
        simplified_equality = KInner.from_dict(dct['simplified_equality']) if 'simplified_equality' in dct else None
        csubst = CSubst.from_dict(dct['csubst']) if 'csubst' in dct else None
        return EqualityProof(
            id,
            lhs_body,
            rhs_body,
            sort,
            constraints=constraints,
            csubst=csubst,
            simplified_constraints=simplified_constraints,
            simplified_equality=simplified_equality,
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
        if self.simplified_constraints is not None:
            dct['simplified_constraints'] = self.simplified_constraints.to_dict()
        if self.simplified_equality is not None:
            dct['simplified_equality'] = self.simplified_equality.to_dict()
        if self.csubst is not None:
            dct['csubst'] = self.csubst.to_dict()
        return dct

    def pretty(self, kprint: KPrint) -> Iterable[str]:
        lines = [
            f'LHS: {kprint.pretty_print(self.lhs_body)}',
            f'RHS: {kprint.pretty_print(self.rhs_body)}',
            f'Constraints: {kprint.pretty_print(mlAnd(self.constraints))}',
            f'Equality: {kprint.pretty_print(self.equality)}',
        ]
        if self.simplified_constraints:
            lines.append(f'Simplified constraints: {kprint.pretty_print(self.simplified_constraints)}')
        if self.simplified_equality:
            lines.append(f'Simplified equality: {kprint.pretty_print(self.simplified_equality)}')
        if self.csubst is not None:
            lines.append(f'Implication csubst: {self.csubst}')
        lines.append(f'Status: {self.status}')
        return lines

    @property
    def summary(self) -> Iterable[str]:
        return [
            f'EqualityProof: {self.id}',
            f'  status: {self.status}',
        ]


class RefutationProof(Proof):
    def __init__(
        self,
        id: str,
        sort: KSort,
        constraints: Iterable[KInner] = (),
        csubst: CSubst | None = None,
        simplified_constraints: KInner | None = None,
        proof_dir: Path | None = None,
    ):
        super().__init__(id, proof_dir=proof_dir)
        self.sort = sort
        self.constraints = tuple(constraints)
        self.csubst = csubst
        self.simplified_constraints = simplified_constraints

    def add_constraint(self, new_constraint: KInner) -> None:
        self.constraints = (*self.constraints, new_constraint)

    def set_simplified_constraints(self, simplified: KInner) -> None:
        self.simplified_constraints = simplified

    def set_csubst(self, csubst: CSubst) -> None:
        self.csubst = csubst

    @property
    def status(self) -> ProofStatus:
        if self.simplified_constraints is None:
            return ProofStatus.PENDING
        elif self.csubst is not None:
            return ProofStatus.FAILED
        else:
            return ProofStatus.PASSED

    @property
    def dict(self) -> dict[str, Any]:
        dct = {
            'type': 'RefutationProof',
            'id': self.id,
            'sort': self.sort.to_dict(),
            'constraints': [c.to_dict() for c in self.constraints],
        }
        if self.simplified_constraints is not None:
            dct['simplified_constraints'] = self.simplified_constraints.to_dict()
        if self.csubst is not None:
            dct['csubst'] = self.csubst.to_dict()
        return dct

    @classmethod
    def from_dict(cls: type[RefutationProof], dct: Mapping[str, Any], proof_dir: Path | None = None) -> RefutationProof:
        id = dct['id']
        sort = KSort.from_dict(dct['sort'])
        constraints = [KInner.from_dict(c) for c in dct['constraints']]
        simplified_constraints = (
            KInner.from_dict(dct['simplified_constraints']) if 'simplified_constraints' in dct else None
        )
        csubst = CSubst.from_dict(dct['csubst']) if 'csubst' in dct else None
        return RefutationProof(
            id=id,
            sort=sort,
            constraints=constraints,
            csubst=csubst,
            simplified_constraints=simplified_constraints,
            proof_dir=proof_dir,
        )

    @property
    def summary(self) -> Iterable[str]:
        return [
            f'RefutationProof: {self.id}',
            f'  status: {self.status}',
        ]

    def pretty(self, kprint: KPrint) -> Iterable[str]:
        lines = [
            f'Constraints: {kprint.pretty_print(mlAnd(self.constraints))}',
        ]
        if self.csubst is not None:
            lines.append(f'Implication csubst: {self.csubst}')
        lines.append(f'Status: {self.status}')
        return lines


class EqualityProver:
    proof: EqualityProof

    def __init__(self, proof: EqualityProof) -> None:
        self.proof = proof

    def advance_proof(self, kcfg_explore: KCFGExplore) -> None:
        _LOGGER.info(f'Attempting EqualityProof {self.proof.id}')

        if self.proof.status is not ProofStatus.PENDING:
            _LOGGER.info(f'EqualityProof finished {self.proof.id}: {self.proof.status}')
            return

        # to prove the equality, we check the implication of the form `constraints #Implies LHS #Equals RHS`, i.e.
        # "LHS equals RHS under these constraints"
        antecedent_kast = self.proof.constraint
        consequent_kast = self.proof.equality

        antecedent_simplified_kast, _ = kcfg_explore.kast_simplify(antecedent_kast)
        consequent_simplified_kast, _ = kcfg_explore.kast_simplify(consequent_kast)
        self.proof.set_simplified_constraints(antecedent_simplified_kast)
        self.proof.set_simplified_equality(consequent_simplified_kast)
        _LOGGER.info(f'Simplified antecedent: {kcfg_explore.kprint.pretty_print(antecedent_simplified_kast)}')
        _LOGGER.info(f'Simplified consequent: {kcfg_explore.kprint.pretty_print(consequent_simplified_kast)}')

        if is_bottom(antecedent_simplified_kast):
            _LOGGER.warning(f'Antecedent of implication (proof constraints) simplifies to #Bottom {self.proof.id}')
            self.proof.set_csubst(CSubst(Subst({}), ()))

        elif is_top(consequent_simplified_kast):
            _LOGGER.warning(f'Consequent of implication (proof equality) simplifies to #Top {self.proof.id}')
            self.proof.set_csubst(CSubst(Subst({}), ()))

        else:
            # TODO: we should not be forced to include the dummy configuration in the antecedent and consequent
            dummy_config = kcfg_explore.kprint.definition.empty_config(sort=GENERATED_TOP_CELL)
            result = kcfg_explore.cterm_implies(
                antecedent=CTerm(config=dummy_config, constraints=[antecedent_kast]),
                consequent=CTerm(config=dummy_config, constraints=[consequent_kast]),
            )
            if result is not None:
                self.proof.set_csubst(result)

        _LOGGER.info(f'EqualityProof finished {self.proof.id}: {self.proof.status}')
        self.proof.write_proof()


class RefutationProver:
    proof: RefutationProof

    def __init__(self, proof: RefutationProof) -> None:
        self.proof = proof

    def advance_proof(self, kcfg_explore: KCFGExplore) -> None:
        if self.proof.status is not ProofStatus.PENDING:
            return

        consequent_kast = mlAnd(self.proof.constraints)

        _, kore_client = kcfg_explore._kore_rpc

        _LOGGER.info(f'Attempting RefutationProof {self.proof.id}')

        proof_failed_trivially = False
        consequent_simplified_kore, _ = kore_client.simplify(kcfg_explore.kprint.kast_to_kore(consequent_kast))
        consequent_simplified_kast = kcfg_explore.kprint.kore_to_kast(consequent_simplified_kore)
        _LOGGER.info(f'Simplified consequent: {kcfg_explore.kprint.pretty_print(consequent_simplified_kast)}')
        self.proof.set_simplified_constraints(consequent_simplified_kast)
        if is_top(consequent_simplified_kast):
            _LOGGER.warning(
                'Consequent of implication (proof equality) simplifies to #Top. The constraitns are satisfiable, the implication will not be checked.'
            )
            proof_failed_trivially = True
            self.proof.set_csubst(CSubst(Subst({}), ()))

        if not proof_failed_trivially:
            # third, check implication from antecedent to consequent
            # TODO: we should not be forced to include the dummy configuration in the antecedent and consequent
            dummy_config = kcfg_explore.kprint.definition.empty_config(sort=GENERATED_TOP_CELL)
            result = kcfg_explore.cterm_implies(
                antecedent=CTerm(config=dummy_config, constraints=[]),
                consequent=CTerm(config=dummy_config, constraints=[consequent_kast]),
            )
            if result is None:
                _LOGGER.warning('cterm_implies returned None, the implication is unsatisfiable')
            else:
                self.proof.set_csubst(result)
        self.proof.write_proof()
