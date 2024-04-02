from ..kore.syntax import (Axiom, Pattern)
from convert import sentence_to_llvm, llvm_to_pattern

def get_requires(axiom: Axiom) -> Pattern:
    llvm_axiom = sentence_to_llvm(axiom)
    pattern = llvm_axiom.get_requires()
    return llvm_to_pattern(pattern)
