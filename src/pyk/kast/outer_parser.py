from __future__ import annotations

from typing import TYPE_CHECKING

from .outer_lexer import TokenType, outer_lexer
from .outer_syntax import (
    EMPTY_ATT,
    Alias,
    Att,
    Claim,
    Config,
    Context,
    Definition,
    Import,
    Module,
    Require,
    Rule,
    SortDecl,
    SyntaxAssoc,
    SyntaxDecl,
    SyntaxLexical,
    SyntaxPriority,
)

if TYPE_CHECKING:
    from collections.abc import Collection, Iterable, Iterator
    from typing import Final

    from .outer_lexer import Token
    from .outer_syntax import Sentence, StringSentence, SyntaxSentence


class OuterParser:
    _lexer: Iterator[Token]
    _la: Token

    def __init__(self, it: Iterable[str]):
        self._lexer = outer_lexer(it)
        self._la = next(self._lexer)

    def _consume(self) -> str:
        res = self._la.text
        self._la = next(self._lexer)
        return res

    def _match(self, token_type: TokenType) -> str:
        # Do not call on EOF
        if self._la.type != token_type:
            raise ValueError(f'Expected {token_type.name}, got: {self._la.type.name}')
        # _consume() inlined for efficiency
        res = self._la.text
        self._la = next(self._lexer)
        return res

    def _match_any(self, token_types: Collection[TokenType]) -> str:
        # Do not call on EOF
        if self._la.type not in token_types:
            expected_types = ', '.join(token_type.name for token_type in token_types)
            raise ValueError(f'Expected {expected_types}, got: {self._la.type.name}')
        res = self._la.text
        self._la = next(self._lexer)
        return res

    def definition(self) -> Definition:
        requires: list[Require] = []
        while self._la.type in {TokenType.KW_REQUIRE, TokenType.KW_REQUIRES}:
            requires.append(self.require())

        modules: list[Module] = []
        while self._la.type is TokenType.KW_MODULE:
            modules.append(self.module())

        return Definition(modules, requires)

    def require(self) -> Require:
        self._match_any({TokenType.KW_REQUIRE, TokenType.KW_REQUIRES})
        path = self._match(TokenType.STRING)
        return Require(path)  # TODO dequote

    def module(self) -> Module:
        self._match(TokenType.KW_MODULE)

        name = self._match(TokenType.MODNAME)

        att: Att
        if self._la.type is TokenType.LBRACK:
            att = self.att()
        else:
            att = EMPTY_ATT

        imports: list[Import] = []
        while self._la.type in {TokenType.KW_IMPORT, TokenType.KW_IMPORTS}:
            imports.append(self.importt())

        sentences: list[Sentence] = []
        while self._la.type is not TokenType.KW_ENDMODULE:
            sentences.append(self.sentence())

        self._consume()

        return Module(name, sentences, imports, att)

    def importt(self) -> Import:
        self._match_any({TokenType.KW_IMPORT, TokenType.KW_IMPORTS})

        public = True
        if self._la.type is TokenType.KW_PRIVATE:
            public = False
            self._consume()
        elif self._la.type is TokenType.KW_PUBLIC:
            self._consume()

        module_name = self._match(TokenType.MODNAME)

        return Import(module_name, public=public)

    def sentence(self) -> Sentence:
        if self._la.type is TokenType.KW_SYNTAX:
            return self.syntax_sentence()

        return self.string_sentence()

    def syntax_sentence(self) -> SyntaxSentence:
        self._match(TokenType.KW_SYNTAX)

        if self._la.type in {TokenType.LBRACE, TokenType.ID_UPPER}:
            decl = self._sort_decl()

            if self._la.type is TokenType.EQ:
                raise RuntimeError('TODO alias')

            if self._la.type is TokenType.DCOLONEQ:
                raise RuntimeError('TODO defn')

            att: Att
            if self._la.type is TokenType.LBRACK:
                att = self.att()
            else:
                att = EMPTY_ATT

            return SyntaxDecl(decl, att)

        if self._la.type in {TokenType.KW_PRIORITY, TokenType.KW_PRIORITIES}:
            self._consume()
            groups: list[list[str]] = []
            group: list[str] = []
            group.append(self._match(TokenType.KLABEL))
            while self._la.type is TokenType.KLABEL:
                group.append(self._consume())
            groups.append(group)
            while self._la.type is TokenType.GT:
                self._consume()
                group = []
                group.append(self._match(TokenType.KLABEL))
                while self._la.type is TokenType.KLABEL:
                    group.append(self._consume())
                groups.append(group)
            return SyntaxPriority(groups)

        if self._la.type in {TokenType.KW_LEFT, TokenType.KW_RIGHT, TokenType.KW_NONASSOC}:
            kind = SyntaxAssoc.Kind(self._consume())
            klabels: list[str] = []
            klabels.append(self._match(TokenType.KLABEL))
            while self._la.type is TokenType.KLABEL:
                klabels.append(self._consume())
            return SyntaxAssoc(kind, klabels)

        if self._la.type is TokenType.KW_LEXICAL:
            self._consume()
            name = self._match(TokenType.ID_UPPER)
            self._match(TokenType.EQ)
            regex = self._match(TokenType.REGEX)  # TODO dequote
            return SyntaxLexical(name, regex)

        raise ValueError(f'Unexpected token: {self._la.text}')

    def _sort_decl(self) -> SortDecl:
        params: list[str] = []
        if self._la.type is TokenType.LBRACE:
            self._consume()
            params.append(self._match(TokenType.ID_UPPER))
            while self._la.type is TokenType.COMMA:
                self._consume()
                params.append(self._match(TokenType.ID_UPPER))
            self._match(TokenType.RBRACE)

        name = self._match(TokenType.ID_UPPER)

        args: list[str] = []
        if self._la.type is TokenType.LBRACE:
            self._consume()
            args.append(self._match(TokenType.ID_UPPER))
            while self._la.type is TokenType.COMMA:
                self._consume()
                args.append(self._match(TokenType.ID_UPPER))
            self._match(TokenType.RBRACE)

        return SortDecl(name, params, args)

    def string_sentence(self) -> StringSentence:
        tag: str
        if self._la.type is TokenType.KW_CONTEXT:
            tag = self._consume()
            if self._la.type is TokenType.KW_ALIAS:
                tag = self._consume()
        else:
            tag = self._match_any({TokenType.KW_CLAIM, TokenType.KW_CONFIG, TokenType.KW_RULE})

        cls = _STRING_SENTENCE[tag]

        label: str
        if self._la.type == TokenType.LBRACK:
            self._consume()
            label = self._match(TokenType.RULE_LABEL)
            self._match(TokenType.RBRACK)
            self._match(TokenType.COLON)
        else:
            label = ''

        bubble = self._match(TokenType.BUBBLE)

        att: Att
        if self._la.type == TokenType.LBRACK:
            att = self.att()
        else:
            att = EMPTY_ATT

        return cls(bubble, label, att)

    def att(self) -> Att:
        items: list[tuple[str, str]] = []

        self._match(TokenType.LBRACK)

        while True:
            key = self._match(TokenType.ATTR_KEY)

            value: str
            if self._la.type == TokenType.LPAREN:
                self._consume()
                value = self._match_any({TokenType.STRING, TokenType.ATTR_CONTENT})
                self._match(TokenType.RPAREN)  # TODO dequote STRING
            else:
                value = ''

            items.append((key, value))

            if self._la.type != TokenType.COMMA:
                break
            else:
                self._consume()

        self._match(TokenType.RBRACK)

        return Att(items)


_STRING_SENTENCE: Final = {
    'alias': Alias,
    'claim': Claim,
    'configuration': Config,
    'context': Context,
    'rule': Rule,
}
