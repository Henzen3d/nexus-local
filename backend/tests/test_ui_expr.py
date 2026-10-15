import json
from pathlib import Path
import pytest
from backend.ui_blocks.expr import (
    validate_expression,
    is_expression,
    check_dependency_cycles,
    MAX_EXPR_LENGTH,
    MAX_EXPR_TOKENS,
)


def test_fixture_expressions_parity():
    fixture_path = Path(__file__).parent / "fixtures" / "expressions.json"
    with open(fixture_path, "r", encoding="utf-8") as f:
        cases = json.load(f)

    for case in cases:
        expr = case["expr"]
        expected_valid = case["valid"]
        valid, err, variables = validate_expression(expr)

        assert valid == expected_valid, f"Expr: {expr!r} expected valid={expected_valid}, got {valid} (err={err})"

        if expected_valid:
            assert err is None
            expected_vars = case.get("variables", [])
            assert set(variables) == set(expected_vars), f"Variables mismatch for {expr}: {variables} vs {expected_vars}"
        else:
            assert err is not None
            expected_err = case.get("error")
            if expected_err:
                assert err == expected_err, f"Error mismatch for {expr}: expected {expected_err}, got {err}"


def test_expression_known_ids_validation():
    expr = "={x} + {y}"
    # Se known_ids tiver x e y, passa
    valid, err, _ = validate_expression(expr, known_ids={"x", "y", "z"})
    assert valid is True
    assert err is None

    # Se known_ids não tiver y, rejeita com unknown_identifier
    valid, err, _ = validate_expression(expr, known_ids={"x"})
    assert valid is False
    assert err == "unknown_identifier"


def test_expression_length_and_tokens_limit():
    # Teste de tamanho > 160 caracteres
    long_expr = "=" + "1 + " * 50 + "1"
    assert len(long_expr) > MAX_EXPR_LENGTH
    valid, err, _ = validate_expression(long_expr)
    assert valid is False
    assert err == "limit_exceeded"

    # Teste de tokens > 40 tokens
    many_tokens_expr = "=1" + "+1" * 30
    assert len(many_tokens_expr) <= MAX_EXPR_LENGTH
    valid, err, _ = validate_expression(many_tokens_expr)
    assert valid is False
    assert err == "limit_exceeded"


def test_check_dependency_cycles():
    field_ids = {"preco", "desconto"}

    # Caso 1: Encadeamento linear sem ciclo
    computeds = [
        {"id": "subtotal", "formula": "{preco} - {desconto}"},
        {"id": "total", "formula": "{subtotal} * 1.1"},
    ]
    valid, err, order = check_dependency_cycles(computeds, field_ids)
    assert valid is True
    assert err is None
    assert order == ["subtotal", "total"]

    # Caso 2: Ciclo direto A -> B -> A
    cycle_computeds = [
        {"id": "a", "formula": "{b} + 1"},
        {"id": "b", "formula": "{a} * 2"},
    ]
    valid, err, _ = check_dependency_cycles(cycle_computeds, field_ids)
    assert valid is False
    assert err == "cycle_detected"

    # Caso 3: Id duplicado com field_ids
    dup_computeds = [
        {"id": "preco", "formula": "100"},
    ]
    valid, err, _ = check_dependency_cycles(dup_computeds, field_ids)
    assert valid is False
    assert err == "duplicate_id"

    # Caso 4: Identificador desconhecido
    unknown_computeds = [
        {"id": "total", "formula": "{inexistente} * 2"},
    ]
    valid, err, _ = check_dependency_cycles(unknown_computeds, field_ids)
    assert valid is False
    assert err == "unknown_identifier"
