from __future__ import annotations

from typing import TYPE_CHECKING

from .outer_lexer import TokenType, outer_lexer
from .outer_syntax import EMPTY_ATT, Att, Rule

if TYPE_CHECKING:
    from collections.abc import Collection, Iterable, Iterator

    from .outer_lexer import Token


class OuterParser:
    _lexer: Iterator[Token]
    _la: Token

    def __init__(self, it: Iterable[str]):
        self._lexer = outer_lexer(it)
        self._la = next(self._lexer)

    def _consume(self) -> None:
        self._la = next(self._lexer)

    def _match(self, token_type: TokenType) -> str:
        # Do not call on EOF
        if self._la.type != token_type:
            raise ValueError(f'Expected {token_type.name}, got: {self._la.type.name}')
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

    def rule(self) -> Rule:
        self._match(TokenType.KW_RULE)

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

        return Rule(bubble, label, att)

    def att(self) -> Att:
        items: list[tuple[str, str]] = []

        self._match(TokenType.LBRACK)

        while True:
            key = self._match(TokenType.ATTR_KEY)

            value: str
            if self._la.type == TokenType.LPAREN:
                self._consume()
                value = self._match_any({TokenType.STRING, TokenType.ATTR_CONTENT})
                self._match(TokenType.RPAREN)
            else:
                value = ''

            items.append((key, value))

            if self._la.type != TokenType.COMMA:
                break
            else:
                self._consume()

        self._match(TokenType.RBRACK)

        return Att(items)
