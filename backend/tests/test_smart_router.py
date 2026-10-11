"""
backend/tests/test_smart_router.py
Testes unitários e benchmark de desempenho para o Smart Intent Router.
Garante latência < 2ms, histerese de tópico, anti-amnésia e integridade de seleção.
"""

import time
import pytest
import aiosqlite

from backend.ranking.smart_router import (
    IntentKey,
    ComplexityTier,
    RoutingPolicy,
    classify_intent,
    select_best_model,
)
from backend.database import DB_PATH, init_db


def test_classify_trivial_short_greetings():
    """Valida identificação instantânea de saudações e mensagens fáticas."""
    res = classify_intent("olá, bom dia!")
    assert res.intent == IntentKey.TRIVIAL_QUICK
    assert res.confidence == 1.0
    assert "trivial_short_greeting" in res.matched_signals
    assert res.processing_time_ms < 2.0


def test_classify_code_engineering_syntax():
    """Valida detecção de código e precisão sintática."""
    prompt = "Como corrigir este erro? def process_data(items: list):\n    return items.sort()"
    res = classify_intent(prompt)
    assert res.intent == IntentKey.CODE_ENGINEERING
    assert res.complexity in (ComplexityTier.MEDIUM, ComplexityTier.HEAVY)
    assert res.recommended_temperature == 0.2
    assert res.confidence >= 0.90


def test_classify_code_sql_and_traceback():
    """Valida termos SQL e tracebacks."""
    prompt = "Traceback (most recent call last): SELECT * FROM users WHERE id = 1"
    res = classify_intent(prompt)
    assert res.intent == IntentKey.CODE_ENGINEERING
    assert any("code_syntax" in s for s in res.matched_signals)


def test_classify_deep_reasoning():
    """Valida problemas lógicos, equações e deduções."""
    prompt = "Resolva o problema dos três prisioneiros e faça uma análise lógica detalhada passo a passo."
    res = classify_intent(prompt)
    assert res.intent == IntentKey.DEEP_REASONING
    assert res.recommended_temperature == 0.6
    assert any("deep_thought" in s for s in res.matched_signals)


def test_classify_creative_longform():
    """Valida redação e escrita de formato longo."""
    prompt = "Escreva uma redação sobre o impacto da inteligência artificial na sociedade moderna."
    res = classify_intent(prompt)
    assert res.intent == IntentKey.CREATIVE_LONGFORM
    assert res.recommended_temperature == 0.7
    assert any("creative_intent" in s for s in res.matched_signals)


def test_classify_web_search_active():
    """Valida que o toggle web tem prioridade imediata."""
    prompt = "Qual é a cotação do dólar hoje?"
    res = classify_intent(prompt, web_search=True)
    assert res.intent == IntentKey.WEB_RESEARCH
    assert "web_search_active" in res.matched_signals


def test_retrospective_multimodality_current_attachment():
    """Valida quando há anexo na mensagem atual."""
    res = classify_intent("O que tem nesta imagem?", attachments=[{"id": "att-1", "type": "image/png"}])
    assert res.intent == IntentKey.MULTIMODAL_VISION
    assert res.inherited_from_history is False
    assert "attachment_current" in res.matched_signals


def test_retrospective_multimodality_history():
    """Valida quando uma imagem foi enviada em turno anterior no histórico (anti-amnésia)."""
    history = [
        {"role": "user", "content": [{"type": "image_url", "image_url": {"url": "data:image/png;base64,..."}}]},
        {"role": "assistant", "content": "Analisei o print do seu gráfico."},
    ]
    res = classify_intent("Explique melhor a barra azul", history=history)
    assert res.intent == IntentKey.MULTIMODAL_VISION
    assert res.inherited_from_history is True
    assert "retrospective_vision_history" in res.matched_signals


def test_topic_momentum_code_hysteresis():
    """
    Valida histerese de tópico: pergunta curta (< 35 chars) após turno de código
    mantém a intenção de código e NÃO rebaixa para TRIVIAL_QUICK.
    """
    history = [
        {"role": "user", "content": "Como criar um servidor fastapi com websockets?"},
        {"role": "assistant", "content": "```python\nfrom fastapi import FastAPI\napp = FastAPI()\n```"},
    ]
    # Prompt curto que sem histórico pareceria trivial
    prompt = "e no Windows?"
    res = classify_intent(prompt, history=history, previous_intent="code_engineering")
    assert res.intent == IntentKey.CODE_ENGINEERING
    assert res.inherited_from_history is True
    assert "topic_momentum_code_engineering" in res.matched_signals
    assert "Código & Programação (Continuidade)" in res.reason_label_pt


def test_topic_momentum_reasoning_hysteresis():
    """Valida histerese para raciocínio lógico em pergunta curta subsequente."""
    history = [
        {"role": "user", "content": "Demonstre matematicamente o teorema de Pitágoras."},
        {"role": "assistant", "content": "Considere o quadrado com lados a + b..."},
    ]
    prompt = "e se for no espaço 3D?"
    res = classify_intent(prompt, history=history, previous_intent="deep_reasoning")
    assert res.intent == IntentKey.DEEP_REASONING
    assert res.inherited_from_history is True
    assert "topic_momentum_deep_reasoning" in res.matched_signals


def test_benchmark_under_2_milliseconds():
    """
    Benchmark estrito de performance: garante que 50 prompts variados
    executam com média bem inferior a 2 milissegundos por chamada (< 0.5ms).
    """
    test_prompts = [
        "bom dia",
        "como vai?",
        "def quicksort(arr): return arr",
        "explique o teorema de bayes e deduza a fórmula",
        "escreva uma redação persuasiva sobre educação",
        "qual a capital da frança?",
        "import torch; model = torch.nn.Linear(10, 2)",
        "calcule a integral de x^2 dx de 0 a 1",
        "ok, entendi!",
        "SELECT u.name, COUNT(o.id) FROM users u JOIN orders o ON o.user_id = u.id GROUP BY u.name",
    ] * 5  # 50 execuções

    durations = []
    for p in test_prompts:
        t0 = time.perf_counter()
        res = classify_intent(p)
        t1 = time.perf_counter()
        durations.append((t1 - t0) * 1000)
        assert res.processing_time_ms < 2.0

    avg_ms = sum(durations) / len(durations)
    max_ms = max(durations)
    assert avg_ms < 1.0, f"Tempo médio muito alto: {avg_ms:.3f}ms"
    assert max_ms < 2.0, f"Tempo máximo excedeu 2ms: {max_ms:.3f}ms"


@pytest.mark.asyncio
async def test_select_best_model_balanced_smart():
    """Valida seleção de modelo com política balanced_smart."""
    await init_db()
    async with aiosqlite.connect(DB_PATH) as db:
        res = classify_intent("def somar(a, b): return a + b")
        decision = await select_best_model(res, "balanced_smart", db)
        assert decision.chosen_model_id is not None
        assert decision.provider_id is not None
        assert decision.temperature == 0.2
        assert decision.intent == IntentKey.CODE_ENGINEERING


@pytest.mark.asyncio
async def test_select_best_model_economical_free():
    """Valida que a política econômica prioriza modelos com is_free == 1."""
    await init_db()
    async with aiosqlite.connect(DB_PATH) as db:
        res = classify_intent("olá tudo bem?")
        decision = await select_best_model(res, "economical_free", db)
        assert decision.chosen_model_id is not None
        assert decision.policy == "economical_free"


@pytest.mark.asyncio
async def test_select_best_model_sticky_routing():
    """Valida que o Sticky Routing mantém o modelo do turno anterior se score próximo."""
    await init_db()
    async with aiosqlite.connect(DB_PATH) as db:
        res1 = classify_intent("def calcula(): pass")
        decision1 = await select_best_model(res1, "balanced_smart", db)

        # Segundo turno técnico: passa previous_model_id
        res2 = classify_intent("como tipar o retorno dessa função?", previous_intent="code_engineering")
        decision2 = await select_best_model(res2, "balanced_smart", db, previous_model_id=decision1.chosen_model_id)

        assert decision2.chosen_model_id == decision1.chosen_model_id
        assert "KV-Cache" in decision2.reason_pt
