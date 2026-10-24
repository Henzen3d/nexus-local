"""
backend/tests/test_pre_router_triage.py
Testes unitários da arquitetura Pré-Router & Triage Agent do Nexus Local.
"""

import pytest
from unittest.mock import AsyncMock, patch

from backend.orchestration.pre_router import (
    IntentRouting,
    extract_heuristic_constraints,
    classify_heuristic_triage,
    build_modular_system_prompt_addition,
    format_triage_mode_status,
    run_pre_router_triage,
)


def test_heuristic_triage_trivial_greetings():
    for text in ["oi", "Olá, tudo bem?", "bom dia", "valeu!", "obrigado pela ajuda"]:
        res = classify_heuristic_triage(text)
        assert res.intent_tier == "trivial", f"Falhou para: {text}"
        assert res.reasoning_effort == "low"
        assert res.needs_web_search is False
        assert "Casual" in res.mode_status_pt


def test_heuristic_triage_specific_lookup():
    queries = [
        ("quem é o primeiro-ministro do reino unido?", False),
        ("qual a capital da austrália?", False),
        ("quem está no debate da globo hoje 23/10/2026?", True),
        ("cotação do dólar hoje", True),
    ]
    for prompt, expected_web in queries:
        res = classify_heuristic_triage(prompt)
        assert res.intent_tier == "specific_lookup", f"Falhou para: {prompt}"
        if expected_web:
            assert res.needs_web_search is True
            assert len(res.search_queries) > 0
        assert "Direto" in res.mode_status_pt


def test_heuristic_triage_deep_technical():
    tech_prompts = [
        "escreva uma função em rust para calcular fibonacci",
        "implemente um algoritmo de raft consensus em python",
        "debug este código: traceback TypeError in line 42",
        "calcule a integral dupla e demonstre a prova matemática com rigor",
    ]
    for prompt in tech_prompts:
        res = classify_heuristic_triage(prompt)
        assert res.intent_tier == "deep_technical", f"Falhou para: {prompt}"
        assert res.reasoning_effort in ("medium", "high")
        assert "Engenharia Profunda" in res.mode_status_pt


def test_extract_heuristic_strict_constraints():
    prompt = "Crie uma API em fastapi sem usar bibliotecas externas, máximo de 3 linhas e apenas o código."
    constraints = extract_heuristic_constraints(prompt)

    # Verifica se as restrições foram extraídas
    c_lower = [c.lower() for c in constraints]
    assert any("bibliotecas externas" in c for c in c_lower)
    assert any("3 linhas" in c for c in c_lower)
    assert any("apenas o código" in c for c in c_lower)


def test_extract_format_constraints_table_and_json():
    t_table = extract_heuristic_constraints("compare os dois modelos em formato de tabela")
    assert any("tabela" in c.lower() for c in t_table)

    t_json = extract_heuristic_constraints("retorne os dados em formato json")
    assert any("json" in c.lower() for c in t_json)


def test_build_modular_system_prompt_addition():
    # 1. Tier trivial
    routing_trivial = IntentRouting(intent_tier="trivial")
    addition_trivial = build_modular_system_prompt_addition(routing_trivial)
    assert "[MODO CONVERSA CASUAL / TRIVIAL]" in addition_trivial

    # 2. Tier specific_lookup
    routing_lookup = IntentRouting(intent_tier="specific_lookup")
    addition_lookup = build_modular_system_prompt_addition(routing_lookup)
    assert "[MODO RESPOSTA RÁPIDA & EMBASAMENTO]" in addition_lookup

    # 3. Tier deep_technical
    routing_tech = IntentRouting(
        intent_tier="deep_technical",
        strict_constraints=["Sem bibliotecas externas", "Apenas código"],
    )
    addition_tech = build_modular_system_prompt_addition(routing_tech)
    assert "[MODO ENGENHARIA PROFUNDA & RIGOR TÉCNICO]" in addition_tech
    assert "[RESTRIÇÕES OBRIGATÓRIAS DESTA RESPOSTA]:" in addition_tech
    assert "- Sem bibliotecas externas" in addition_tech
    assert "- Apenas código" in addition_tech


@pytest.mark.asyncio
async def test_run_pre_router_triage_short_circuit():
    fake_db = AsyncMock()
    res = await run_pre_router_triage(fake_db, "Oi, boa tarde!")
    assert res.intent_tier == "trivial"
    assert res.triage_source == "short_circuit"
    assert res.latency_ms >= 0.0


@pytest.mark.asyncio
async def test_run_pre_router_triage_fast_llm_success():
    fake_db = AsyncMock()

    class FakeFastProvider:
        async def stream_chat(self, *args, **kwargs):
            yield '{"intent_tier": "deep_technical", "reasoning_effort": "high", "needs_web_search": false, "search_queries": [], "strict_constraints": ["Apenas JSON"]}'

    with patch("backend.providers.utility_model.resolve_utility_model", return_value=(FakeFastProvider(), "mock-fast-model", "override")):
        res = await run_pre_router_triage(
            fake_db,
            "Crie um compilador em C sem bibliotecas externas",
        )
        assert res.intent_tier == "deep_technical"
        assert res.reasoning_effort == "high"
        assert res.triage_source == "fast_llm"
        assert any("json" in c.lower() for c in res.strict_constraints)


@pytest.mark.asyncio
async def test_run_pre_router_triage_fallback_on_error():
    fake_db = AsyncMock()

    with patch("backend.providers.utility_model.resolve_utility_model", side_effect=RuntimeError("Provedor offline")):
        res = await run_pre_router_triage(
            fake_db,
            "quem é o atual presidente da argentina?",
        )
        assert res.intent_tier == "specific_lookup"
        assert res.triage_source == "heuristic_rules"
