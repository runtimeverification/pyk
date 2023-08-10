from __future__ import annotations

from typing import TYPE_CHECKING

from ..kore.syntax import (
    ML_SYMBOLS,
    AliasDecl,
    App,
    Axiom,
    Claim,
    Definition,
    EVar,
    Import,
    MLPattern,
    Module,
    SortApp,
    SortDecl,
    SortVar,
    String,
    SVar,
    Symbol,
    SymbolDecl,
    VarPattern,
)
from . import ast as kllvm

if TYPE_CHECKING:
    from collections.abc import Iterable
    from typing import Any

    from ..kore.syntax import Pattern, Sentence, Sort


# -----------
# pyk -> llvm
# -----------


def _add_attributes(term: Any, attrs: tuple[App, ...]) -> None:
    for attr in attrs:
        term.add_attribute(_composite_pattern(attr.symbol, attr.sorts, attr.args))


def kore_definition_to_llvm(definition: Definition) -> kllvm.Definition:
    res = kllvm.Definition()
    for mod in definition.modules:
        res.add_module(kore_module_to_llvm(mod))
    _add_attributes(res, definition.attrs)
    return res


def kore_module_to_llvm(module: Module) -> kllvm.Module:
    res = kllvm.Module(module.name)
    for sentence in module.sentences:
        res.add_declaration(kore_sentence_to_llvm(sentence))
    _add_attributes(res, module.attrs)
    return res


def kore_sentence_to_llvm(sentence: Sentence) -> kllvm.Declaration:
    match sentence:
        case Import(mod_name, attrs):
            res = kllvm.ModuleImportDeclaration(mod_name)
            _add_attributes(res, attrs)
            return res
        case SortDecl(name, vars, attrs, hooked):
            res = kllvm.CompositeSortDeclaration(name, hooked)
            for var in vars:
                res.add_object_sort_variable(kore_sort_to_llvm(var))
            _add_attributes(res, attrs)
            return res
        case SymbolDecl(symbol, param_sorts, sort, attrs, hooked):
            res = kllvm.SymbolDeclaration(symbol.name, hooked)
            for var in symbol.vars:
                res.add_object_sort_variable(kore_sort_to_llvm(var))
            for param_sort in param_sorts:
                res.symbol.add_argument(kore_sort_to_llvm(param_sort))
            res.symbol.add_sort(kore_sort_to_llvm(sort))
            _add_attributes(res, attrs)
            return res
        case AliasDecl(alias, param_sorts, sort, left, right, attrs):
            res = kllvm.AliasDeclaration(alias.name)
            for var in alias.vars:
                res.add_object_sort_variable(kore_sort_to_llvm(var))
            for param_sort in param_sorts:
                res.symbol.add_argument(kore_sort_to_llvm(param_sort))
            res.symbol.add_sort(kore_sort_to_llvm(sort))
            res.add_variables(_composite_pattern(left.symbol, left.sorts, left.args))
            res.add_pattern(kore_pattern_to_llvm(right))
            _add_attributes(res, attrs)
            return res
        case Axiom(vars, pattern, attrs):
            res = kllvm.AxiomDeclaration(False)
            for var in vars:
                res.add_object_sort_variable(kore_sort_to_llvm(var))
            res.add_pattern(kore_pattern_to_llvm(pattern))
            _add_attributes(res, attrs)
            return res
        case Claim(vars, pattern, attrs):
            res = kllvm.AxiomDeclaration(True)
            for var in vars:
                res.add_object_sort_variable(kore_sort_to_llvm(var))
            res.add_pattern(kore_pattern_to_llvm(pattern))
            _add_attributes(res, attrs)
            return res
        case _:
            raise AssertionError()


def kore_pattern_to_llvm(pattern: Pattern) -> kllvm.Pattern:
    match pattern:
        case String(value):
            return kllvm.StringPattern(value)
        case VarPattern(name, sort):
            return kllvm.VariablePattern(name, kore_sort_to_llvm(sort))
        case App(symbol, sorts, args):
            return _composite_pattern(symbol, sorts, args)
        case MLPattern():
            return _composite_pattern(pattern.symbol(), pattern.sorts, pattern.ctor_patterns)
        case _:
            raise AssertionError()


def kore_sort_to_llvm(sort: Sort) -> kllvm.Sort:
    match sort:
        case SortVar(name):
            return kllvm.SortVariable(name)
        case SortApp(name, sorts):
            res = kllvm.CompositeSort(sort.name, kllvm.ValueType(kllvm.SortCategory(0)))
            for subsort in sorts:
                res.add_argument(kore_sort_to_llvm(subsort))
            return res
        case _:
            raise AssertionError()


def _composite_pattern(symbol_id: str, sorts: Iterable, patterns: Iterable[Pattern]) -> kllvm.CompositePattern:
    symbol = kllvm.Symbol(symbol_id)
    for sort in sorts:
        symbol.add_formal_argument(kore_sort_to_llvm(sort))
    res = kllvm.CompositePattern(symbol)
    for pattern in patterns:
        res.add_argument(kore_pattern_to_llvm(pattern))
    return res


# -----------
# llvm -> pyk
# -----------


def llvm_definition_to_kore(definition: kllvm.Definition) -> Definition:
    modules = (llvm_module_to_kore(mod) for mod in definition.modules)
    attrs = _attrs(definition.attributes)
    return Definition(modules, attrs)


def llvm_module_to_kore(module: kllvm.Module) -> Module:
    sentences = (llvm_declaration_to_kore(decl) for decl in module.declarations)
    attrs = _attrs(module.attributes)
    return Module(module.name, sentences, attrs)


def llvm_declaration_to_kore(decl: kllvm.Declaration) -> Sentence:
    attrs = _attrs(decl.attributes)
    vars = (llvm_sort_to_kore(var) for var in decl.object_sort_variables)
    match decl:
        case kllvm.ModuleImportDeclaration():  # type: ignore
            return Import(decl.module_name, attrs)
        case kllvm.CompositeSortDeclaration():  # type: ignore
            return SortDecl(decl.name, vars, attrs, hooked=decl.is_hooked)
        case kllvm.SymbolDeclaration():  # type: ignore
            llvm_symbol = decl.symbol
            symbol = Symbol(llvm_symbol.name, vars)
            param_sorts = (llvm_sort_to_kore(sort) for sort in llvm_symbol.arguments)
            sort = llvm_sort_to_kore(llvm_symbol.sort)
            return SymbolDecl(symbol, param_sorts, sort, attrs, hooked=decl.is_hooked)
        case kllvm.AliasDeclaration():  # type: ignore
            llvm_symbol = decl.symbol
            symbol = Symbol(llvm_symbol.name, vars)
            param_sorts = (llvm_sort_to_kore(sort) for sort in llvm_symbol.arguments)
            sort = llvm_sort_to_kore(llvm_symbol.sort)
            left = App(*_unpack_composite_pattern(decl.variables))
            right = llvm_pattern_to_kore(decl.pattern)
            return AliasDecl(symbol, param_sorts, sort, left, right, attrs)
        case kllvm.AxiomDeclaration():  # type: ignore
            pattern = llvm_pattern_to_kore(decl.pattern)
            if decl.is_claim:
                return Claim(vars, pattern, attrs)
            else:
                return Axiom(vars, pattern, attrs)
        case _:
            raise AssertionError()


def llvm_pattern_to_kore(pattern: kllvm.Pattern) -> Pattern:
    match pattern:
        case kllvm.StringPattern():  # type: ignore
            return String(pattern.contents)
        case kllvm.VariablePattern():  # type: ignore
            if pattern.name and pattern.name[0] == '@':
                return SVar(pattern.name, llvm_sort_to_kore(pattern.sort))
            else:
                return EVar(pattern.name, llvm_sort_to_kore(pattern.sort))
        case kllvm.CompositePattern():  # type: ignore
            symbol, sorts, patterns = _unpack_composite_pattern(pattern)
            if symbol in ML_SYMBOLS:
                return MLPattern.of(symbol, sorts, patterns)
            else:
                return App(symbol, sorts, patterns)
        case _:
            raise AssertionError()


def llvm_sort_to_kore(sort: kllvm.Sort) -> Sort:
    match sort:
        case kllvm.SortVariable():  # type: ignore
            return SortVar(sort.name)
        case kllvm.CompositeSort():  # type: ignore
            return SortApp(sort.name, (llvm_sort_to_kore(subsort) for subsort in sort.arguments))
        case _:
            raise AssertionError()


def _attrs(attributes: dict[str, kllvm.CompositePattern]) -> tuple[App, ...]:
    return tuple(App(*_unpack_composite_pattern(attr)) for _, attr in attributes.items())


def _unpack_composite_pattern(pattern: kllvm.CompositePattern) -> tuple[str, tuple[Sort, ...], tuple[Pattern, ...]]:
    symbol = pattern.constructor.name
    sorts = tuple(llvm_sort_to_kore(sort) for sort in pattern.constructor.formal_arguments)
    patterns = tuple(llvm_pattern_to_kore(subpattern) for subpattern in pattern.arguments)
    return symbol, sorts, patterns
