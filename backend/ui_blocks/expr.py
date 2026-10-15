"""Validador sintático e estático de expressões matemáticas para o Intelligent UI.

Regras do contrato (Plano 12 §7 e §8):
- Expressão começa com '='.
- Teto de 160 caracteres e 40 tokens.
- Operadores permitidos: +, -, *, /, parênteses (, ).
- Proibido operador '^' (evita ambiguidades de precedência).
- Variáveis na sintaxe {id}, onde id é alfanumérico/underscore até 32 caracteres.
- Funções permitidas: round(x, casas), abs(x), min(...), max(...), floor(x), ceil(x), sqrt(x), pow(x, y).
- Validação estática de identificadores contra known_ids (campos de controls do envelope).
- Detecção estática de dependências circulares entre computeds.
- Apenas valida; a avaliação ocorre no frontend.
"""
from __future__ import annotations

import re
from typing import Any

MAX_EXPR_LENGTH = 160
MAX_EXPR_TOKENS = 40

ALLOWED_FUNCTIONS: dict[str, int] = {
    "round": 2,
    "pow": 2,
    "abs": 1,
    "floor": 1,
    "ceil": 1,
    "sqrt": 1,
    "min": -1,  # 1 ou mais
    "max": -1,  # 1 ou mais
}

IDENTIFIER_REGEX = re.compile(r"^[a-zA-Z0-9_]{1,32}$")


def is_expression(val: Any) -> bool:
    """Verifica se o valor é uma string de fórmula com prefixo '='."""
    return isinstance(val, str) and val.startswith("=") and len(val.strip()) > 1


class Token:
    def __init__(self, kind: str, value: Any):
        self.kind = kind
        self.value = value

    def __repr__(self):
        return f"Token({self.kind}, {self.value})"


def tokenize_expression(expr: str) -> tuple[list[Token] | None, str | None]:
    """Tokeniza a expressão matemática (sem o prefixo '=')."""
    text = expr.strip()
    if text.startswith("="):
        text = text[1:].strip()

    if not text:
        return None, "empty_expression"

    if len(expr) > MAX_EXPR_LENGTH:
        return None, "limit_exceeded"

    tokens: list[Token] = []
    i = 0
    n = len(text)

    while i < n:
        c = text[i]

        if c.isspace():
            i += 1
            continue

        if c in "+-*/(),":
            tokens.append(Token(c, c))
            i += 1
        elif c == "^":
            return None, "invalid_operator"
        elif c == "{":
            end_brace = text.find("}", i + 1)
            if end_brace == -1:
                return None, "invalid_identifier"
            var_name = text[i + 1 : end_brace].strip()
            if not IDENTIFIER_REGEX.match(var_name):
                return None, "invalid_identifier"
            tokens.append(Token("VAR", var_name))
            i = end_brace + 1
        elif c.isdigit() or (c == "." and i + 1 < n and text[i + 1].isdigit()):
            start = i
            while i < n and (text[i].isdigit() or text[i] == "."):
                i += 1
            num_str = text[start:i]
            try:
                val = float(num_str) if "." in num_str else int(num_str)
                tokens.append(Token("NUMBER", val))
            except ValueError:
                return None, "syntax_error"
        elif c.isalpha() or c == "_":
            start = i
            while i < n and (text[i].isalnum() or text[i] == "_"):
                i += 1
            name = text[start:i].lower()
            if name not in ALLOWED_FUNCTIONS:
                return None, "unknown_function"
            tokens.append(Token("FUNC", name))
        else:
            return None, "syntax_error"

        if len(tokens) > MAX_EXPR_TOKENS:
            return None, "limit_exceeded"

    return tokens, None


class Parser:
    def __init__(self, tokens: list[Token]):
        self.tokens = tokens
        self.pos = 0
        self.variables: list[str] = []

    def peek(self) -> Token | None:
        if self.pos < len(self.tokens):
            return self.tokens[self.pos]
        return None

    def advance(self) -> Token | None:
        tok = self.peek()
        if tok is not None:
            self.pos += 1
        return tok

    def parse(self) -> str | None:
        """Retorna None se a sintaxe for válida, ou código de erro string."""
        err = self._parse_expr()
        if err:
            return err
        if self.pos < len(self.tokens):
            tok = self.peek()
            if tok and tok.kind == ")":
                return "unbalanced_parentheses"
            return "syntax_error"
        return None

    def _parse_expr(self) -> str | None:
        err = self._parse_term()
        if err:
            return err
        while self.peek() and self.peek().kind in ("+", "-"):
            self.advance()
            err = self._parse_term()
            if err:
                return err
        return None

    def _parse_term(self) -> str | None:
        err = self._parse_factor()
        if err:
            return err
        while self.peek() and self.peek().kind in ("*", "/"):
            self.advance()
            err = self._parse_factor()
            if err:
                return err
        return None

    def _parse_factor(self) -> str | None:
        tok = self.peek()
        if tok and tok.kind in ("+", "-"):
            self.advance()
        return self._parse_primary()

    def _parse_primary(self) -> str | None:
        tok = self.peek()
        if not tok:
            return "syntax_error"

        if tok.kind == "NUMBER":
            self.advance()
            return None

        if tok.kind == "VAR":
            self.variables.append(tok.value)
            self.advance()
            return None

        if tok.kind == "(":
            self.advance()
            err = self._parse_expr()
            if err:
                return err
            close_tok = self.peek()
            if not close_tok or close_tok.kind != ")":
                return "unbalanced_parentheses"
            self.advance()
            return None

        if tok.kind == "FUNC":
            func_name = tok.value
            self.advance()
            if not self.peek() or self.peek().kind != "(":
                return "syntax_error"
            self.advance()  # consome '('

            # Conta e analisa argumentos separados por vírgula
            arg_count = 0
            if self.peek() and self.peek().kind != ")":
                err = self._parse_expr()
                if err:
                    return err
                arg_count += 1
                while self.peek() and self.peek().kind == ",":
                    self.advance()
                    err = self._parse_expr()
                    if err:
                        return err
                    arg_count += 1

            if not self.peek() or self.peek().kind != ")":
                return "unbalanced_parentheses"
            self.advance()  # consome ')'

            expected_arity = ALLOWED_FUNCTIONS.get(func_name, 1)
            if expected_arity == -1:
                if arg_count < 1:
                    return "invalid_arity"
            elif arg_count != expected_arity:
                return "invalid_arity"

            return None

        return "syntax_error"


def validate_expression(
    expr: str, known_ids: set[str] | None = None
) -> tuple[bool, str | None, list[str]]:
    """Valida a expressão matemática e extrai as variáveis usadas.

    Retorna: (is_valid, error_code, list_of_variables)
    """
    if not isinstance(expr, str) or not expr.strip():
        return False, "empty_expression", []

    text = expr.strip()
    if not text.startswith("="):
        return False, "invalid_expression", []

    tokens, err = tokenize_expression(text)
    if err or tokens is None:
        return False, err or "syntax_error", []

    parser = Parser(tokens)
    syntax_err = parser.parse()
    if syntax_err:
        return False, syntax_err, []

    # Extrai variáveis únicas preservando ordem
    unique_vars: list[str] = []
    seen = set()
    for v in parser.variables:
        if v not in seen:
            seen.add(v)
            unique_vars.append(v)

    if known_ids is not None:
        for v in unique_vars:
            if v not in known_ids:
                return False, "unknown_identifier", unique_vars

    return True, None, unique_vars


def check_dependency_cycles(
    computeds: list[dict[str, Any]], field_ids: set[str]
) -> tuple[bool, str | None, list[str]]:
    """Analisa a lista de computeds para validar dependências e detectar ciclos.

    Retorna: (is_valid, error_code, list_of_ids_in_topological_order)
    """
    if not isinstance(computeds, list):
        return False, "invalid_computed", []

    all_known = set(field_ids)
    computed_map: dict[str, list[str]] = {}
    computed_ids: list[str] = []

    for comp in computeds:
        if not isinstance(comp, dict):
            return False, "invalid_computed", []
        c_id = comp.get("id") or "resultado"
        if not isinstance(c_id, str) or not IDENTIFIER_REGEX.match(c_id):
            return False, "invalid_identifier", []
        if c_id in computed_map or c_id in field_ids:
            return False, "duplicate_id", []

        formula = comp.get("formula")
        if not isinstance(formula, str):
            return False, "invalid_expression", []

        # Valida a sintaxe da fórmula
        # Se não começar com '=', adiciona prefixo para validar com o mesmo parser
        test_expr = formula if formula.startswith("=") else f"={formula}"
        valid, err, used_vars = validate_expression(test_expr)
        if not valid:
            return False, err or "invalid_expression", []

        computed_map[c_id] = used_vars
        computed_ids.append(c_id)
        all_known.add(c_id)

    # Verifica se todas as variáveis existem nos campos ou em computeds
    for c_id, deps in computed_map.items():
        for d in deps:
            if d not in all_known:
                return False, "unknown_identifier", []

    # Detecção de ciclos via ordenação topológica (Kahn ou DFS)
    WHITE, GRAY, BLACK = 0, 1, 2
    state: dict[str, int] = {c_id: WHITE for c_id in computed_ids}
    order: list[str] = []

    def dfs(u: str) -> bool:
        state[u] = GRAY
        for v in computed_map.get(u, []):
            if v in state:  # v é um computed
                if state[v] == GRAY:
                    return True  # ciclo detectado!
                if state[v] == WHITE:
                    if dfs(v):
                        return True
        state[u] = BLACK
        order.append(u)
        return False

    for c_id in computed_ids:
        if state[c_id] == WHITE:
            if dfs(c_id):
                return False, "cycle_detected", []

    return True, None, order
