from __future__ import annotations

from typing import TYPE_CHECKING

from .outer_lexer import TokenType, outer_lexer
from .outer_syntax import (
    EMPTY_ATT,
    Alias,
    Assoc,
    Att,
    Claim,
    Config,
    Context,
    Definition,
    Import,
    Lexical,
    Module,
    NonTerminal,
    PriorityBlock,
    Production,
    Require,
    Rule,
    Sort,
    SortDecl,
    SyntaxAssoc,
    SyntaxDecl,
    SyntaxDefn,
    SyntaxLexical,
    SyntaxPriority,
    SyntaxSynonym,
    Terminal,
    UserList,
)

if TYPE_CHECKING:
    from collections.abc import Collection, Iterable, Iterator
    from typing import Final

    from .outer_lexer import Token
    from .outer_syntax import ProductionItem, ProductionLike, Sentence, StringSentence, SyntaxSentence


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
        att = self._maybe_att()

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
                self._consume()
                sort = self._sort()
                att = self._maybe_att()
                return SyntaxSynonym(decl, sort, att)

            if self._la.type is TokenType.DCOLONEQ:
                self._consume()
                blocks: list[PriorityBlock] = []
                blocks.append(self._priority_block())
                while self._la.type is TokenType.GT:
                    self._consume()
                    blocks.append(self._priority_block())
                return SyntaxDefn(decl, blocks)

            att = self._maybe_att()
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
            assoc = Assoc(self._consume())
            klabels: list[str] = []
            klabels.append(self._match(TokenType.KLABEL))
            while self._la.type is TokenType.KLABEL:
                klabels.append(self._consume())
            return SyntaxAssoc(assoc, klabels)

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

    def _sort(self) -> Sort:
        name = self._match(TokenType.ID_UPPER)

        args: list[int | str] = []
        if self._la.type is TokenType.LBRACE:
            self._consume()
            if self._la.type is TokenType.NAT:
                args.append(int(self._consume()))
            else:
                args.append(self._match(TokenType.ID_UPPER))

            while self._la.type is TokenType.COMMA:
                self._consume()
                if self._la.type is TokenType.NAT:
                    args.append(int(self._consume()))
                else:
                    args.append(self._match(TokenType.ID_UPPER))

            self._match(TokenType.RBRACE)

        return Sort(name, args)

    def _priority_block(self) -> PriorityBlock:
        assoc: Assoc | None
        if self._la.type in {TokenType.KW_LEFT, TokenType.KW_RIGHT, TokenType.KW_NONASSOC}:  # TODO sets
            assoc = Assoc(self._consume())
            self._match(TokenType.COLON)
        else:
            assoc = None

        productions: list[ProductionLike] = []
        productions.append(self._production_like())
        while self._la.type is TokenType.VBAR:
            self._consume()
            productions.append(self._production_like())
        return PriorityBlock(productions, assoc)

    def _production_like(self) -> ProductionLike:
        la1 = self._la
        self._match_any(
            {
                TokenType.ID_LOWER,
                TokenType.ID_UPPER,
                TokenType.STRING,
                TokenType.REGEX,
            }
        )

        if la1.type is TokenType.REGEX:
            regex = la1.text  # TODO dequote
            att = self._maybe_att()
            return Lexical(regex, att)

        if self._la.type is TokenType.LBRACE and la1.text in {'List', 'NeList'}:
            non_empty = la1.text == 'NeList'
            self._consume()
            sort = self._match(TokenType.ID_UPPER)
            self._match(TokenType.COMMA)
            sep = self._match(TokenType.STRING)
            self._match(TokenType.RBRACE)
            att = self._maybe_att()
            return UserList(sort, sep, non_empty, att)

        items: list[ProductionItem] = []

        if la1.type is TokenType.STRING:
            items.append(Terminal(la1.text))  # TODO dequote
        else:
            assert la1.type in {TokenType.ID_LOWER, TokenType.ID_UPPER}
            if self._la.type is TokenType.LPAREN:
                items.append(Terminal(la1.text))
                items.append(Terminal(self._consume()))
                while self._la.type is not TokenType.RPAREN:
                    items.append(self._non_terminal())
                    if self._la.type is TokenType.COMMA:
                        items.append(Terminal(self._consume()))
                        continue
                    break
                items.append(Terminal(self._match(TokenType.RPAREN)))
            else:
                items.append(self._non_terminal_with_la(la1))

        while self._la.type in {
            TokenType.STRING,
            TokenType.ID_LOWER,
            TokenType.ID_UPPER,
        }:
            items.append(self._production_item())

        att = self._maybe_att()
        return Production(items, att)

    def _production_item(self) -> ProductionItem:
        if self._la.type is TokenType.STRING:
            return Terminal(self._consume())  # TODO dequote

        return self._non_terminal()

    def _non_terminal(self) -> NonTerminal:
        la1 = self._la
        self._match_any({TokenType.ID_LOWER, TokenType.ID_UPPER})
        return self._non_terminal_with_la(la1)

    def _non_terminal_with_la(self, la: Token) -> NonTerminal:
        if la.type is TokenType.ID_LOWER or self._la.type is TokenType.COLON:
            self._match(TokenType.COLON)
            sort = self._sort()
            return NonTerminal(sort, la.text)

        return NonTerminal(self._sort_with_la(la))

    def _sort_with_la(self, la: Token) -> Sort:
        assert la.type is TokenType.ID_UPPER

        args: list[int | str] = []
        if self._la.type is TokenType.LBRACE:
            self._consume()
            if self._la.type is TokenType.NAT:
                args.append(int(self._consume()))
            else:
                args.append(self._match(TokenType.ID_UPPER))

            while self._la.type is TokenType.COMMA:
                self._consume()
                if self._la.type is TokenType.NAT:
                    args.append(int(self._consume()))
                else:
                    args.append(self._match(TokenType.ID_UPPER))

            self._match(TokenType.RBRACE)

        return Sort(la.text, args)

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
        att = self._maybe_att()
        return cls(bubble, label, att)

    def _maybe_att(self) -> Att:
        items: list[tuple[str, str]] = []

        if self._la.type is not TokenType.LBRACK:
            return EMPTY_ATT

        self._consume()

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
