from __future__ import annotations

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING, Any, Generic, TypeVar

if TYPE_CHECKING:
    from collections.abc import Iterable

    from pyk.proof.proof import ProofStatus

P = TypeVar('P', bound='Proof')
S = TypeVar('S', bound='ProofStep')
U = TypeVar('U', bound='Any')


class Prover(ABC, Generic[P, S, U]):
    @abstractmethod
    def steps(self, proof: P) -> Iterable[S]:
        ...

    @abstractmethod
    def commit(self, proof: P, update: U) -> None:
        ...


class Proof(ABC):
    @property
    @abstractmethod
    def status(self) -> ProofStatus:
        ...


class ProofStep(ABC, Generic[U]):
    @abstractmethod
    def exec(self) -> U:
        ...


#  @dataclass
#  class APRProverTask:
#      cterm: CTerm
#      node_id: int
#      module_name: str
#      execute_depth: int
#      cut_point_rules: Iterable[str]
#      terminal_rules: Iterable[str]
#
#
#  class APRProverResult:
#      ...
#
#
#  class NewAPRProver(Prover[APRProof, APRProverTask, APRProverResult]):
#      prover: APRProver
#      execute_depth: int
#      cut_point_rules: Iterable[str]
#      terminal_rules: Iterable[str]
#
#      def __init__(self, prover: APRProver) -> None:
#          self.prover = prover
#
#      def steps(self, proof: APRProof) -> Iterable[APRProverTask]:
#          steps = []
#          for node in proof.pending:
#              module_name = (
#                  self.prover.circularities_module_name
#                  if self.prover.nonzero_depth(node)
#                  else self.prover.dependencies_module_name
#              )
#              steps.append(
#                  APRProverTask(
#                      cterm=node.cterm,
#                      node_id=node.id,
#                      module_name=module_name,
#                      execute_depth=self.execute_depth,
#                      cut_point_rules=self.cut_point_rules,
#                      terminal_rules=self.terminal_rules,
#                  )
#              )
#          return steps
#
#      @classmethod
#      def advance(cls, step: APRProverTask) -> APRProverResult:
#          return APRProverResult()
#
#      def commit(self, proof: APRProof, update: APRProverResult) -> None:
#          ...
