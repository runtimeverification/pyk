from __future__ import annotations

from typing import TYPE_CHECKING, TypeVar

from ..utils import dequote_str
from .lexer import KoreLexer, TokenType
from .syntax import (
    DV,
    AliasDecl,
    And,
    App,
    Axiom,
    Bottom,
    Ceil,
    Claim,
    Definition,
    Equals,
    EVar,
    Exists,
    Floor,
    Forall,
    Iff,
    Implies,
    Import,
    In,
    LeftAssoc,
    Module,
    Mu,
    Next,
    Not,
    Nu,
    Or,
    Rewrites,
    RightAssoc,
    SortApp,
    SortDecl,
    SortVar,
    String,
    SVar,
    Symbol,
    SymbolDecl,
    Top,
)

if TYPE_CHECKING:
    from typing import Callable, Iterator, List, Mapping, Type, Union

    from .lexer import KoreToken
    from .syntax import (
        Assoc,
        BinaryConn,
        BinaryPred,
        MLFixpoint,
        MLPattern,
        MLQuant,
        NullaryConn,
        Pattern,
        RoundPred,
        Sentence,
        Sort,
        UnaryConn,
        VarPattern,
    )

    NC = TypeVar('NC', bound=NullaryConn)
    UC = TypeVar('UC', bound=Union[UnaryConn, Next])
    BC = TypeVar('BC', bound=Union[BinaryConn, Rewrites])
    QF = TypeVar('QF', bound=MLQuant)
    FP = TypeVar('FP', bound=MLFixpoint)
    RP = TypeVar('RP', bound=RoundPred)
    BP = TypeVar('BP', bound=BinaryPred)
    AS = TypeVar('AS', bound=Assoc)

T = TypeVar('T')


class KoreParser:
    _iter: Iterator[KoreToken]
    _la: KoreToken

    _ml_symbols: Mapping[TokenType, Callable[[], MLPattern]]
    _sentence_keywords: Mapping[TokenType, Callable[[], Sentence]]

    def __init__(self, text: str):
        self._iter = KoreLexer(text)
        self._la = next(self._iter)

        self._ml_symbols = {
            TokenType.ML_TOP: self.top,
            TokenType.ML_BOTTOM: self.bottom,
            TokenType.ML_NOT: self.nott,
            TokenType.ML_AND: self.andd,
            TokenType.ML_OR: self.orr,
            TokenType.ML_IMPLIES: self.implies,
            TokenType.ML_IFF: self.iff,
            TokenType.ML_EXISTS: self.exists,
            TokenType.ML_FORALL: self.forall,
            TokenType.ML_MU: self.mu,
            TokenType.ML_NU: self.nu,
            TokenType.ML_CEIL: self.ceil,
            TokenType.ML_FLOOR: self.floor,
            TokenType.ML_EQUALS: self.equals,
            TokenType.ML_IN: self.inn,
            TokenType.ML_NEXT: self.next,
            TokenType.ML_REWRITES: self.rewrites,
            TokenType.ML_DV: self.dv,
            TokenType.ML_LEFT_ASSOC: self.left_assoc,
            TokenType.ML_RIGHT_ASSOC: self.right_assoc,
        }

        self._sentence_kws = {
            TokenType.KW_IMPORT: self.importt,
            TokenType.KW_SORT: self.sort_decl,
            TokenType.KW_HOOKED_SORT: self.hooked_sort_decl,
            TokenType.KW_SYMBOL: self.symbol_decl,
            TokenType.KW_HOOKED_SYMBOL: self.hooked_symbol_decl,
            TokenType.KW_ALIAS: self.alias_decl,
            TokenType.KW_AXIOM: self.axiom,
            TokenType.KW_CLAIM: self.claim,
        }

    @property
    def eof(self) -> bool:
        return self._la.type == TokenType.EOF

    def _consume(self) -> str:
        text = self._la.text
        self._la = next(self._iter)
        return text

    def _match(self, token_type: TokenType) -> str:
        if self._la.type != token_type:
            raise ValueError(f'Expected {token_type.name}, found: {self._la.type.name}')

        return self._consume()

    def _delimited_list_of(
        self,
        parse: Callable[[], T],
        ldelim: TokenType,
        rdelim: TokenType,
        sep: TokenType = TokenType.COMMA,
    ) -> List[T]:
        res: List[T] = []

        self._match(ldelim)
        while self._la.type != rdelim:
            res.append(parse())
            if self._la.type != sep:
                break
            self._consume()
        self._consume()

        return res

    def id(self) -> str:
        return self._match(TokenType.ID)

    def symbol_id(self) -> str:
        if self._la.type == TokenType.SYMBOL_ID:
            return self._consume()

        return self._match(TokenType.ID)

    def set_var_id(self) -> str:
        return self._match(TokenType.SET_VAR_ID)

    def sort(self) -> Sort:
        name = self.id()

        if self._la.type == TokenType.LBRACE:
            sorts = self._sort_list()
            return SortApp(name, sorts)

        return SortVar(name)

    def _sort_list(self) -> List[Sort]:
        return self._delimited_list_of(self.sort, TokenType.LBRACE, TokenType.RBRACE)

    def sort_var(self) -> SortVar:
        name = self._match(TokenType.ID)
        return SortVar(name)

    def sort_app(self) -> SortApp:
        name = self._match(TokenType.ID)
        sorts = self._sort_list()
        return SortApp(name, sorts)

    def pattern(self) -> Pattern:
        if self._la.type == TokenType.STRING:
            return self.string()

        if self._la.type in self._ml_symbols:
            return self.ml_pattern()

        if self._la.type == TokenType.SYMBOL_ID:
            return self.app()

        if self._la.type == TokenType.SET_VAR_ID:
            return self.set_var()

        name = self._match(TokenType.ID)
        if self._la.type == TokenType.COLON:
            self._consume()
            sort = self.sort()
            return EVar(name, sort)

        sorts = self._sort_list()
        patterns = self._pattern_list()
        return App(name, sorts, patterns)

    def _pattern_list(self) -> List[Pattern]:
        return self._delimited_list_of(self.pattern, TokenType.LPAREN, TokenType.RPAREN)

    def string(self) -> String:
        value = self._match(TokenType.STRING)
        return String(dequote_str(value[1:-1]))

    def app(self) -> App:
        symbol = self.symbol_id()
        sorts = self._sort_list()
        patterns = self._pattern_list()
        return App(symbol, sorts, patterns)

    def var_pattern(self) -> VarPattern:
        if self._la.type == TokenType.SET_VAR_ID:
            return self.set_var()

        return self.elem_var()

    def set_var(self) -> SVar:
        name = self._match(TokenType.SET_VAR_ID)
        self._match(TokenType.COLON)
        sort = self.sort()
        return SVar(name, sort)

    def elem_var(self) -> EVar:
        name = self._match(TokenType.ID)
        self._match(TokenType.COLON)
        sort = self.sort()
        return EVar(name, sort)

    def ml_pattern(self) -> MLPattern:
        token_type = self._la.type
        if token_type not in self._ml_symbols:
            raise ValueError(f'Exected matching logic symbol, found: {self._la.text}')
        parse = self._ml_symbols[token_type]
        return parse()

    def _nullary(self, token_type: TokenType, cls: Type[NC]) -> NC:
        self._match(token_type)
        self._match(TokenType.LBRACE)
        sort = self.sort()
        self._match(TokenType.RBRACE)
        self._match(TokenType.LPAREN)
        self._match(TokenType.RPAREN)
        # TODO Implement NullaryConn.create(symbol, sort) instead
        # TODO Consider MLConn.create(symbol, sort, patterns) as well
        return cls(sort)  # type: ignore

    def top(self) -> Top:
        return self._nullary(TokenType.ML_TOP, Top)

    def bottom(self) -> Bottom:
        return self._nullary(TokenType.ML_BOTTOM, Bottom)

    def _unary(self, token_type: TokenType, cls: Type[UC]) -> UC:
        self._match(token_type)
        self._match(TokenType.LBRACE)
        sort = self.sort()
        self._match(TokenType.RBRACE)
        self._match(TokenType.LPAREN)
        pattern = self.pattern()
        self._match(TokenType.RPAREN)
        return cls(sort, pattern)  # type: ignore

    def nott(self) -> Not:
        return self._unary(TokenType.ML_NOT, Not)

    def _binary(self, token_type: TokenType, cls: Type[BC]) -> BC:
        self._match(token_type)
        self._match(TokenType.LBRACE)
        sort = self.sort()
        self._match(TokenType.RBRACE)
        self._match(TokenType.LPAREN)
        left = self.pattern()
        self._match(TokenType.COMMA)
        right = self.pattern()
        self._match(TokenType.RPAREN)
        return cls(sort, left, right)  # type: ignore

    def andd(self) -> And:
        return self._binary(TokenType.ML_AND, And)

    def orr(self) -> Or:
        return self._binary(TokenType.ML_OR, Or)

    def implies(self) -> Implies:
        return self._binary(TokenType.ML_IMPLIES, Implies)

    def iff(self) -> Iff:
        return self._binary(TokenType.ML_IFF, Iff)

    def _quantifier(self, token_type: TokenType, cls: Type[QF]) -> QF:
        self._match(token_type)
        self._match(TokenType.LBRACE)
        sort = self.sort()
        self._match(TokenType.RBRACE)
        self._match(TokenType.LPAREN)
        var = self.elem_var()
        self._match(TokenType.COMMA)
        pattern = self.pattern()
        self._match(TokenType.RPAREN)
        return cls(sort, var, pattern)  # type: ignore

    def exists(self) -> Exists:
        return self._quantifier(TokenType.ML_EXISTS, Exists)

    def forall(self) -> Forall:
        return self._quantifier(TokenType.ML_FORALL, Forall)

    def _fixpoint(self, token_type: TokenType, cls: Type[FP]) -> FP:
        self._match(token_type)
        self._match(TokenType.LBRACE)
        self._match(TokenType.RBRACE)
        self._match(TokenType.LPAREN)
        var = self.set_var()
        self._match(TokenType.COMMA)
        pattern = self.pattern()
        self._match(TokenType.RPAREN)
        return cls(var, pattern)  # type: ignore

    def mu(self) -> Mu:
        return self._fixpoint(TokenType.ML_MU, Mu)

    def nu(self) -> Nu:
        return self._fixpoint(TokenType.ML_NU, Nu)

    def _round_pred(self, token_type: TokenType, cls: Type[RP]) -> RP:
        self._match(token_type)
        self._match(TokenType.LBRACE)
        op_sort = self.sort()
        self._match(TokenType.COMMA)
        sort = self.sort()
        self._match(TokenType.RBRACE)
        self._match(TokenType.LPAREN)
        pattern = self.pattern()
        self._match(TokenType.RPAREN)
        return cls(op_sort, sort, pattern)  # type: ignore

    def ceil(self) -> Ceil:
        return self._round_pred(TokenType.ML_CEIL, Ceil)

    def floor(self) -> Floor:
        return self._round_pred(TokenType.ML_FLOOR, Floor)

    def _binary_pred(self, token_type: TokenType, cls: Type[BP]) -> BP:
        self._match(token_type)
        self._match(TokenType.LBRACE)
        left_sort = self.sort()
        self._match(TokenType.COMMA)
        right_sort = self.sort()
        self._match(TokenType.RBRACE)
        self._match(TokenType.LPAREN)
        left = self.pattern()
        self._match(TokenType.COMMA)
        right = self.pattern()
        self._match(TokenType.RPAREN)
        return cls(left_sort, right_sort, left, right)  # type: ignore

    def equals(self) -> Equals:
        return self._binary_pred(TokenType.ML_EQUALS, Equals)

    def inn(self) -> In:
        return self._binary_pred(TokenType.ML_IN, In)

    def next(self) -> Next:
        return self._unary(TokenType.ML_NEXT, Next)

    def rewrites(self) -> Rewrites:
        return self._binary(TokenType.ML_REWRITES, Rewrites)

    def dv(self) -> DV:
        self._match(TokenType.ML_DV)
        self._match(TokenType.LBRACE)
        sort = self.sort()
        self._match(TokenType.RBRACE)
        self._match(TokenType.LPAREN)
        value = self.string()
        self._match(TokenType.RPAREN)
        return DV(sort, value)

    def _assoc(self, token_type: TokenType, cls: Type[AS]) -> AS:
        self._match(token_type)
        self._match(TokenType.LBRACE)
        self._match(TokenType.RBRACE)
        self._match(TokenType.LPAREN)
        app = self.app()
        self._match(TokenType.RPAREN)
        return cls(app)  # type: ignore

    def left_assoc(self) -> LeftAssoc:
        return self._assoc(TokenType.ML_LEFT_ASSOC, LeftAssoc)

    def right_assoc(self) -> RightAssoc:
        return self._assoc(TokenType.ML_RIGHT_ASSOC, RightAssoc)

    def _attr_list(self) -> List[App]:
        return self._delimited_list_of(self.app, TokenType.LBRACK, TokenType.RBRACK)

    def sentence(self) -> Sentence:
        token_type = self._la.type

        if token_type not in self._sentence_kws:
            raise ValueError(f'Expected {[kw.name for kw in self._sentence_kws]}, found: {token_type.name}')

        parse = self._sentence_kws[token_type]
        return parse()

    def importt(self) -> Import:
        self._match(TokenType.KW_IMPORT)
        module_name = self.id()
        attrs = self._attr_list()
        return Import(module_name, attrs)

    def sort_decl(self) -> SortDecl:
        self._match(TokenType.KW_SORT)
        name = self.id()
        vars = self._sort_var_list()
        attrs = self._attr_list()
        return SortDecl(name, vars, attrs, hooked=False)

    def hooked_sort_decl(self) -> SortDecl:
        self._match(TokenType.KW_HOOKED_SORT)
        name = self.id()
        vars = self._sort_var_list()
        attrs = self._attr_list()
        return SortDecl(name, vars, attrs, hooked=True)

    def _sort_var_list(self) -> List[SortVar]:
        return self._delimited_list_of(self.sort_var, TokenType.LBRACE, TokenType.RBRACE)

    def symbol_decl(self) -> SymbolDecl:
        self._match(TokenType.KW_SYMBOL)
        symbol = self.symbol()
        sort_params = self._sort_param_list()
        self._match(TokenType.COLON)
        sort = self.sort()
        attrs = self._attr_list()
        return SymbolDecl(symbol, sort_params, sort, attrs, hooked=False)

    def hooked_symbol_decl(self) -> SymbolDecl:
        self._match(TokenType.KW_HOOKED_SYMBOL)
        symbol = self.symbol()
        sort_params = self._sort_param_list()
        self._match(TokenType.COLON)
        sort = self.sort()
        attrs = self._attr_list()
        return SymbolDecl(symbol, sort_params, sort, attrs, hooked=True)

    def alias_decl(self) -> AliasDecl:
        self._match(TokenType.KW_ALIAS)
        symbol = self.symbol()
        sort_params = self._sort_param_list()
        self._match(TokenType.COLON)
        sort = self.sort()
        self._match(TokenType.KW_WHERE)
        left = self.app()
        self._match(TokenType.WALRUS)
        right = self.pattern()
        attrs = self._attr_list()
        return AliasDecl(symbol, sort_params, sort, left, right, attrs)

    def _sort_param_list(self) -> List[Sort]:
        return self._delimited_list_of(self.sort, TokenType.LPAREN, TokenType.RPAREN)

    # TODO remove once \left-assoc{}(\or{...}(...)) is no longer supported
    def multi_or(self) -> List[Pattern]:
        self._match(TokenType.ML_LEFT_ASSOC)
        self._match(TokenType.LBRACE)
        self._match(TokenType.RBRACE)
        self._match(TokenType.LPAREN)
        self._match(TokenType.ML_OR)
        self._match(TokenType.LBRACE)
        self.sort()
        self._match(TokenType.RBRACE)
        patterns = self._pattern_list()
        self._match(TokenType.RPAREN)
        return patterns

    def symbol(self) -> Symbol:
        name = self.symbol_id()
        vars = self._sort_var_list()
        return Symbol(name, vars)

    def axiom(self) -> Axiom:
        self._match(TokenType.KW_AXIOM)
        vars = self._sort_var_list()
        pattern = self.pattern()
        attrs = self._attr_list()
        return Axiom(vars, pattern, attrs)

    def claim(self) -> Claim:
        self._match(TokenType.KW_CLAIM)
        vars = self._sort_var_list()
        pattern = self.pattern()
        attrs = self._attr_list()
        return Claim(vars, pattern, attrs)

    def module(self) -> Module:
        self._match(TokenType.KW_MODULE)
        name = self.id()

        sentences: List[Sentence] = []
        while self._la.type != TokenType.KW_ENDMODULE:
            sentences.append(self.sentence())
        self._consume()

        attrs = self._attr_list()

        return Module(name, sentences, attrs)

    def definition(self) -> Definition:
        attrs = self._attr_list()

        modules: List[Module] = []
        while self._la.type != TokenType.EOF:
            modules.append(self.module())

        return Definition(modules, attrs)
