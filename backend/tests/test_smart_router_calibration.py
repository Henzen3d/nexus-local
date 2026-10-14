"""
backend/tests/test_smart_router_calibration.py
Calibração do Smart Router com um catálogo gratuito realista (2026).

Garante que:
- o perfil heurístico de modelos (tamanho / raciocínio / especialidade) é inferido do nome;
- intenções distintas roteiam para modelos distintos e apropriados;
- dentro da MESMA conversa o roteador troca de modelo quando a intenção/complexidade muda
  ("Oi" → modelo pequeno e rápido; pergunta complexa → modelo pensante) e mantém o
  modelo anterior apenas em follow-ups do mesmo tema;
- o esforço de raciocínio adaptativo respeita o dial de cada modelo.

Banco: arquivo temporário exclusivo (nunca o backend/nexuslocal.db), conforme AGENTS.md.
"""

from __future__ import annotations

import json
from pathlib import Path

import aiosqlite
import pytest

from backend import database as dbmod
from backend.ranking.model_profile import (
    REASONING_ALWAYS_ON,
    REASONING_DIAL,
    REASONING_HYBRID,
    REASONING_NONE,
    SIZE_FRONTIER,
    SIZE_LARGE,
    SIZE_MEDIUM,
    SIZE_NANO,
    SIZE_SMALL,
    profile_model,
)
from backend.ranking.smart_router import (
    ComplexityTier,
    IntentKey,
    classify_intent,
    estimate_complexity,
    invalidate_model_cache,
    rank_candidates,
    recommend_reasoning_effort,
    select_best_model,
)

# ── Catálogo realista (provedor, nome, contexto, free, reasoning_control, níveis, visão) ──
CATALOG = [
    ("groq", "llama-3.3-70b-versatile", 131072, 1, "none", None, 0),
    ("groq", "llama-3.1-8b-instant", 131072, 1, "none", None, 0),
    ("groq", "openai/gpt-oss-120b", 131072, 1, "openai_effort", ["low", "medium", "high"], 0),
    ("groq", "openai/gpt-oss-20b", 131072, 1, "openai_effort", ["low", "medium", "high"], 0),
    ("groq", "qwen/qwen3-32b", 131072, 1, "none", None, 0),
    ("groq", "moonshotai/kimi-k2-instruct-0905", 262144, 1, "none", None, 0),
    ("groq", "meta-llama/llama-4-scout-17b-16e-instruct", 131072, 1, "none", None, 1),
    ("cerebras", "llama3.1-8b", 8192, 1, "none", None, 0),
    ("cerebras", "llama-3.3-70b", 65536, 1, "none", None, 0),
    ("cerebras", "gpt-oss-120b", 65536, 1, "openai_effort", ["low", "medium", "high"], 0),
    ("gemini", "gemini-2.5-flash", 1048576, 1, "gemini_thinking", ["off", "low", "medium", "high"], 1),
    ("gemini", "gemini-2.5-flash-lite", 1048576, 1, "gemini_thinking", ["off", "low", "medium", "high"], 1),
    ("gemini", "gemini-2.5-pro", 1048576, 1, "gemini_thinking", ["off", "low", "medium", "high"], 1),
    ("gemini", "gemma-3-27b-it", 131072, 1, "none", None, 1),
    ("openrouter", "deepseek/deepseek-r1:free", 163840, 1, "always_on", None, 0),
    ("openrouter", "deepseek/deepseek-chat-v3.1:free", 163840, 1, "none", None, 0),
    ("openrouter", "qwen/qwen3-coder:free", 262144, 1, "none", None, 0),
    ("openrouter", "moonshotai/kimi-k2:free", 65536, 1, "none", None, 0),
    ("openrouter", "nvidia/nemotron-3-nano-30b-a3b:free", 131072, 1, "none", None, 0),
    ("cloudflare", "@cf/meta/llama-3.1-8b-instruct-fast", 128000, 1, "none", None, 0),
    ("cloudflare", "@cf/qwen/qwq-32b", 24000, 1, "always_on", None, 0),
    ("cloudflare", "@cf/zai-org/glm-5.2", 128000, 1, "none", None, 0),
    ("cloudflare", "@cf/moonshotai/kimi-k2.5", 128000, 1, "none", None, 1),
    ("cloudflare", "@cf/qwen/qwen2.5-coder-32b-instruct", 32768, 1, "none", None, 0),
    ("zai", "glm-5", 131072, 0, "none", None, 0),  # pago
    ("ollama", "gemma3:4b", 32768, 1, "none", None, 1),
]

PROVIDERS = {
    "groq": ("Groq", 1, 0),
    "cerebras": ("Cerebras", 1, 0),
    "gemini": ("Google Gemini", 1, 0),
    "openrouter": ("OpenRouter", 1, 0),
    "cloudflare": ("Cloudflare", 1, 0),
    "zai": ("Z.ai", 0, 0),
    "ollama": ("Ollama", 0, 1),
}


def _mid(pid: str, name: str) -> str:
    return f"{pid}/{name}"


def _catalog_rows():
    """Linhas no formato consumido por rank_candidates (sem banco)."""
    rows = []
    for pid, name, ctx, free, rc, levels, vis in CATALOG:
        mid = _mid(pid, name)
        prof = profile_model(mid, name, pid, rc, vis)
        rows.append({
            "id": mid,
            "provider_id": pid,
            "name": name,
            "display_name": name,
            "context_length": ctx,
            "confirmed_free": free,
            "prov_is_free": PROVIDERS[pid][1],
            "is_free": 1 if (free or PROVIDERS[pid][1] or PROVIDERS[pid][2]) else 0,
            "nexuslocal_score": prof.baseline_quality,
            "quality_score": prof.baseline_quality,
            "has_ranking": False,
            "quota_status": "available",
            "supports_vision": vis,
            "reasoning_control": rc,
            "reasoning_levels": levels or [],
            "is_local": PROVIDERS[pid][2],
            "tags": list(prof.tags()),
        })
    return rows


# ── Perfil de modelos ────────────────────────────────────────────────────────

@pytest.mark.parametrize(
    "pid,name,tier,mode",
    [
        ("groq", "llama-3.1-8b-instant", SIZE_SMALL, REASONING_NONE),
        ("cerebras", "llama3.1-8b", SIZE_SMALL, REASONING_NONE),
        ("ollama", "gemma3:4b", SIZE_NANO, REASONING_NONE),
        ("groq", "openai/gpt-oss-20b", SIZE_MEDIUM, REASONING_DIAL),
        ("groq", "openai/gpt-oss-120b", SIZE_LARGE, REASONING_DIAL),
        ("groq", "llama-3.3-70b-versatile", SIZE_LARGE, REASONING_NONE),
        ("groq", "meta-llama/llama-4-scout-17b-16e-instruct", SIZE_LARGE, REASONING_NONE),
        ("groq", "qwen/qwen3-32b", SIZE_MEDIUM, REASONING_HYBRID),
        ("cloudflare", "@cf/qwen/qwq-32b", SIZE_MEDIUM, REASONING_ALWAYS_ON),
        ("openrouter", "deepseek/deepseek-r1:free", SIZE_FRONTIER, REASONING_ALWAYS_ON),
        ("openrouter", "qwen/qwen3-coder:free", SIZE_FRONTIER, REASONING_NONE),
        ("cloudflare", "@cf/moonshotai/kimi-k2.5", SIZE_FRONTIER, REASONING_HYBRID),
        ("cloudflare", "@cf/zai-org/glm-5.2", SIZE_FRONTIER, REASONING_HYBRID),
        ("gemini", "gemini-2.5-pro", SIZE_FRONTIER, REASONING_DIAL),
        ("gemini", "gemini-2.5-flash-lite", SIZE_SMALL, REASONING_DIAL),
        ("openrouter", "nvidia/nemotron-3-nano-30b-a3b:free", SIZE_MEDIUM, REASONING_HYBRID),
        ("mistral", "magistral-medium-latest", SIZE_LARGE, REASONING_ALWAYS_ON),
        ("siliconflow", "Qwen/Qwen3.5-397B-A17B", SIZE_FRONTIER, REASONING_HYBRID),
    ],
)
def test_profile_size_and_reasoning(pid, name, tier, mode):
    prof = profile_model(_mid(pid, name), name, pid)
    assert prof.size_tier == tier, prof
    assert prof.reasoning_mode == mode, prof


def test_profile_specialties_and_speed():
    coder = profile_model("openrouter/qwen/qwen3-coder:free", "qwen/qwen3-coder:free", "openrouter")
    assert coder.is_coder
    devstral = profile_model("mistral/devstral-small-2:24b", "devstral-small-2:24b", "mistral")
    assert devstral.is_coder and devstral.size_tier == SIZE_MEDIUM

    vision = profile_model("cloudflare/@cf/meta/llama-3.2-11b-vision-instruct", "@cf/meta/llama-3.2-11b-vision-instruct", "cloudflare")
    assert vision.is_vision
    gemini = profile_model("gemini/gemini-2.5-flash", "gemini-2.5-flash", "gemini")
    assert gemini.is_vision

    fast = profile_model("groq/llama-3.1-8b-instant", "llama-3.1-8b-instant", "groq")
    slow = profile_model("openrouter/deepseek/deepseek-r1:free", "deepseek/deepseek-r1:free", "openrouter")
    assert fast.fast_provider and fast.speed_score > 0.8
    assert slow.speed_score < 0.1

    embed = profile_model("mistral/mistral-embed", "mistral-embed", "mistral")
    assert not embed.is_chat_capable


def test_profile_baseline_quality_is_not_flat():
    """O antigo 'default 60 para todo mundo' foi a causa raiz do empate; agora há gradiente."""
    q8b = profile_model("groq/llama-3.1-8b-instant", "llama-3.1-8b-instant", "groq").baseline_quality
    q70b = profile_model("groq/llama-3.3-70b-versatile", "llama-3.3-70b-versatile", "groq").baseline_quality
    qk2 = profile_model("cloudflare/@cf/moonshotai/kimi-k2.5", "@cf/moonshotai/kimi-k2.5", "cloudflare").baseline_quality
    qunknown = profile_model("x/foo-bar-123", "foo-bar-123", "x").baseline_quality
    assert q8b < q70b < qk2
    assert 50 <= qunknown <= 90


def test_db_reasoning_control_overrides_name_heuristics():
    """Quando o catálogo informa reasoning_control, ele prevalece sobre o nome."""
    p = profile_model("groq/qwen/qwen3-32b", "qwen/qwen3-32b", "groq", "openai_effort", 0)
    assert p.reasoning_mode == REASONING_DIAL
    p2 = profile_model("x/misterioso-9000", "misterioso-9000", "x", "always_on", 0)
    assert p2.reasoning_mode == REASONING_ALWAYS_ON


# ── Classificador: complexidade e inglês ─────────────────────────────────────

def test_estimate_complexity_gradient():
    low, _ = estimate_complexity("qual a capital da França?")
    mid, _ = estimate_complexity(
        "Preciso decidir entre comprar um apartamento financiado ou continuar alugando e investir a diferença. "
        "Considere juros de 11% ao ano, aluguel de R$ 2.500 e imóvel de R$ 600 mil. O que faz mais sentido e por quê?"
    )
    high, cues = estimate_complexity(
        "Analise a viabilidade financeira de abrir uma franquia de açaí em Joinville considerando investimento "
        "inicial de R$ 250 mil, ticket médio de R$ 28 e 120 clientes por dia. Quais são os riscos? Qual o payback? "
        "Quais cenários devo simular?\n- otimista\n- base\n- pessimista"
    )
    assert low < 0.3
    assert mid >= 0.5
    assert high >= 0.6
    assert "enumeration" in cues and "multi_question" in cues


def test_classify_heavy_analysis_without_strong_keywords_goes_to_reasoning():
    prompt = (
        "Preciso decidir entre comprar um apartamento financiado ou continuar alugando e investir a diferença. "
        "Considere juros de 11% ao ano, aluguel de R$ 2.500 e imóvel de R$ 600 mil. O que faz mais sentido e por quê?"
    )
    res = classify_intent(prompt)
    assert res.intent == IntentKey.DEEP_REASONING
    assert res.complexity == ComplexityTier.HEAVY
    assert any(s.startswith("complexity_high") for s in res.matched_signals)


def test_classify_english_prompts():
    assert classify_intent("hello, good morning!").intent == IntentKey.TRIVIAL_QUICK
    code = classify_intent("Can you refactor this function and add unit tests for the edge cases?")
    assert code.intent == IntentKey.CODE_ENGINEERING
    deep = classify_intent("Compare and contrast Keynesian and Austrian economics, with pros and cons of each approach.")
    assert deep.intent == IntentKey.DEEP_REASONING
    creative = classify_intent("Write a short story about a lighthouse keeper who befriends a storm.")
    assert creative.intent == IntentKey.CREATIVE_LONGFORM


def test_short_greeting_after_code_is_not_momentum():
    """'valeu!' depois de código não deve herdar o especialista (economia)."""
    res = classify_intent("valeu!", previous_intent="code_engineering")
    assert res.intent == IntentKey.TRIVIAL_QUICK
    assert "trivial_short_greeting" in res.matched_signals


# ── Seleção pura (rank_candidates) ───────────────────────────────────────────

def _top(prompt: str, policy: str = "balanced_smart", **kw):
    res = classify_intent(prompt, **kw)
    ranked = rank_candidates(_catalog_rows(), res, policy)
    return res, ranked


def test_distinct_intents_pick_distinct_appropriate_models():
    _, trivial = _top("Oi")
    _, code = _top("Tenho esse erro no meu código python: TypeError: 'NoneType' object is not subscriptable")
    _, deep = _top("Prove que a raiz quadrada de 2 é irracional usando contradição")
    _, creative = _top("Escreva um poema sobre o mar em estilo de Fernando Pessoa")

    t, c, d, w = (trivial[0], code[0], deep[0], creative[0])

    # Trivial → pequeno, provedor rápido, sem thinking forçado
    assert t["profile"].size_tier <= SIZE_SMALL
    assert t["profile"].fast_provider
    assert t["profile"].reasoning_mode != REASONING_ALWAYS_ON

    # Código → especialista em código ou fronteira
    assert c["profile"].is_coder or c["profile"].size_tier == SIZE_FRONTIER

    # Raciocínio → modelo pensante e grande
    assert d["profile"].is_reasoning
    assert d["profile"].size_tier >= SIZE_LARGE

    # Criativo → grande, sem thinking forçado
    assert w["profile"].size_tier >= SIZE_LARGE
    assert w["profile"].reasoning_mode != REASONING_ALWAYS_ON

    chosen = {t["model"]["id"], c["model"]["id"], d["model"]["id"], w["model"]["id"]}
    assert len(chosen) >= 3, chosen
    assert t["model"]["id"] not in {c["model"]["id"], d["model"]["id"]}


def test_vision_intent_filters_non_vision_models():
    res = classify_intent("o que tem nessa foto?", attachments=["img-1"])
    ranked = rank_candidates(_catalog_rows(), res, "balanced_smart")
    assert res.intent == IntentKey.MULTIMODAL_VISION
    assert all(c["profile"].is_vision for c in ranked)


def test_economical_policy_never_prefers_paid_model_when_free_exists():
    for prompt in ("Oi", "Prove que a raiz quadrada de 2 é irracional", "def soma(a, b): return a + b"):
        _, ranked = _top(prompt, policy="economical_free")
        assert ranked[0]["model"]["is_free"] == 1


def test_non_chat_models_never_win():
    rows = _catalog_rows()
    prof = profile_model("mistral/mistral-embed", "mistral-embed", "mistral")
    rows.append({
        "id": "mistral/mistral-embed", "provider_id": "mistral", "name": "mistral-embed",
        "display_name": "mistral-embed", "context_length": 32768, "confirmed_free": 1, "prov_is_free": 1,
        "is_free": 1, "nexuslocal_score": 99.0, "quality_score": 99.0, "has_ranking": True,
        "quota_status": "available", "supports_vision": 0, "reasoning_control": "none",
        "reasoning_levels": [], "is_local": 0, "tags": list(prof.tags()),
    })
    res = classify_intent("Oi")
    ranked = rank_candidates(rows, res, "balanced_smart")
    assert ranked[0]["model"]["id"] != "mistral/mistral-embed"


# ── Esforço adaptativo ───────────────────────────────────────────────────────

def test_recommend_reasoning_effort():
    levels = ["low", "medium", "high"]
    assert recommend_reasoning_effort(IntentKey.TRIVIAL_QUICK, ComplexityTier.LIGHT, "medium", "openai_effort", levels) == "low"
    assert recommend_reasoning_effort(IntentKey.DEEP_REASONING, ComplexityTier.HEAVY, "medium", "openai_effort", levels) == "high"
    assert recommend_reasoning_effort(IntentKey.GENERAL_CHAT, ComplexityTier.MEDIUM, "medium", "openai_effort", levels) == "medium"
    # Nível do usuário maior que o alvo prevalece em tarefas pesadas
    assert recommend_reasoning_effort(IntentKey.DEEP_REASONING, ComplexityTier.HEAVY, "xhigh", "anthropic_effort",
                                      ["low", "medium", "high", "xhigh", "max"]) == "xhigh"
    # Aproximação ao nível permitido mais próximo
    assert recommend_reasoning_effort(IntentKey.TRIVIAL_QUICK, ComplexityTier.LIGHT, "medium", "agnes_effort",
                                      ["off", "minimal", "low", "medium", "high"]) == "low"
    assert recommend_reasoning_effort(IntentKey.DEEP_REASONING, ComplexityTier.HEAVY, "medium", "gemini_thinking",
                                      ["off", "medium"]) == "medium"
    # Sem dial → None (não envia parâmetro, sem aviso na UI)
    assert recommend_reasoning_effort(IntentKey.DEEP_REASONING, ComplexityTier.HEAVY, "medium", "none", []) is None
    assert recommend_reasoning_effort(IntentKey.DEEP_REASONING, ComplexityTier.HEAVY, "medium", "always_on", []) is None


# ── Fluxo de conversa com banco temporário (select_best_model) ──────────────

@pytest.fixture
async def router_db(monkeypatch, tmp_path: Path):
    """Banco SQLite temporário exclusivo com o catálogo realista (nunca o DB real)."""
    monkeypatch.setattr(dbmod, "DB_PATH", tmp_path / "router-calibration.db", raising=True)
    await dbmod.init_db()
    invalidate_model_cache()
    db = await aiosqlite.connect(dbmod.DB_PATH)
    try:
        await db.execute("DELETE FROM model_rankings")
        await db.execute("DELETE FROM model_quota_status")
        await db.execute("DELETE FROM models")
        await db.execute("UPDATE providers SET enabled = 0")
        for pid, (pname, is_free, is_local) in PROVIDERS.items():
            await db.execute(
                "INSERT INTO providers (id, name, base_url, api_key, enabled, is_free, is_local) VALUES (?, ?, ?, 'k', 1, ?, ?) "
                "ON CONFLICT(id) DO UPDATE SET enabled = 1, is_free = excluded.is_free, is_local = excluded.is_local",
                (pid, pname, f"https://{pid}.example/v1", is_free, is_local),
            )
        for pid, name, ctx, free, rc, levels, vis in CATALOG:
            await db.execute(
                "INSERT INTO models (id, provider_id, name, display_name, context_length, confirmed_free, enabled, "
                "supports_vision, reasoning_control, reasoning_levels) VALUES (?, ?, ?, ?, ?, ?, 1, ?, ?, ?)",
                (_mid(pid, name), pid, name, name, ctx, free, vis, rc, json.dumps(levels) if levels else None),
            )
        await db.commit()
        yield db
    finally:
        await db.close()
        invalidate_model_cache()


@pytest.mark.asyncio
async def test_conversation_switches_models_per_message(router_db):
    """
    Mesma conversa: 'Oi' → modelo pequeno/rápido; pergunta complexa → modelo pensante;
    follow-up curto do mesmo tema → mantém (KV-Cache); pergunta leve de outro tema → volta ao pequeno.
    """
    db = router_db

    r1 = classify_intent("Oi")
    d1 = await select_best_model(r1, "balanced_smart", db)
    p1 = profile_model(d1.chosen_model_id, d1.chosen_model_id.split("/", 1)[1], d1.provider_id)
    assert d1.intent == IntentKey.TRIVIAL_QUICK
    assert p1.size_tier <= SIZE_SMALL and p1.fast_provider
    assert d1.reasoning_effort is None
    assert d1.alternatives, "decisão deve expor alternativas"

    heavy = (
        "Analise a viabilidade financeira de abrir uma franquia de açaí em Joinville considerando investimento "
        "inicial de R$ 250 mil, ticket médio de R$ 28 e 120 clientes por dia. Quais são os riscos e qual o payback?"
    )
    r2 = classify_intent(heavy, previous_intent=d1.intent.value)
    d2 = await select_best_model(r2, "balanced_smart", db, previous_model_id=d1.chosen_model_id)
    p2 = profile_model(d2.chosen_model_id, d2.chosen_model_id.split("/", 1)[1], d2.provider_id)
    assert d2.intent == IntentKey.DEEP_REASONING and d2.complexity == ComplexityTier.HEAVY.value
    assert d2.chosen_model_id != d1.chosen_model_id, "pergunta complexa deve trocar o modelo"
    assert p2.is_reasoning and p2.size_tier >= SIZE_LARGE
    assert "sticky_routing_cache" not in d2.matched_signals
    assert "model_switch" in d2.matched_signals
    if p2.reasoning_mode == REASONING_DIAL:
        assert d2.reasoning_effort == "high"

    r3 = classify_intent("e se o aluguel subir 20%?", previous_intent=d2.intent.value)
    d3 = await select_best_model(r3, "balanced_smart", db, previous_model_id=d2.chosen_model_id)
    assert r3.inherited_from_history is True
    assert d3.chosen_model_id == d2.chosen_model_id, "follow-up do mesmo tema mantém o especialista"
    assert "sticky_routing_cache" in d3.matched_signals
    assert "KV-Cache" in d3.reason_pt

    r4 = classify_intent("me indica um filme leve pra hoje à noite?", previous_intent=d3.intent.value)
    d4 = await select_best_model(r4, "balanced_smart", db, previous_model_id=d3.chosen_model_id)
    p4 = profile_model(d4.chosen_model_id, d4.chosen_model_id.split("/", 1)[1], d4.provider_id)
    assert d4.intent == IntentKey.TRIVIAL_QUICK
    assert d4.chosen_model_id != d3.chosen_model_id, "pergunta trivial não deve ficar presa ao modelo pesado"
    assert p4.size_tier <= SIZE_SMALL


@pytest.mark.asyncio
async def test_code_turn_switches_from_small_model_and_sticks_on_follow_up(router_db):
    db = router_db
    d1 = await select_best_model(classify_intent("bom dia!"), "balanced_smart", db)

    r2 = classify_intent(
        "Tenho esse erro: Traceback (most recent call last): KeyError: 'user_id' ao rodar o script de importação",
        previous_intent=d1.intent.value,
    )
    d2 = await select_best_model(r2, "balanced_smart", db, previous_model_id=d1.chosen_model_id)
    p2 = profile_model(d2.chosen_model_id, d2.chosen_model_id.split("/", 1)[1], d2.provider_id)
    assert d2.intent == IntentKey.CODE_ENGINEERING
    assert d2.chosen_model_id != d1.chosen_model_id
    assert p2.is_coder or p2.size_tier == SIZE_FRONTIER
    assert d2.temperature == 0.2

    r3 = classify_intent("e no Windows?", previous_intent="code_engineering")
    d3 = await select_best_model(r3, "balanced_smart", db, previous_model_id=d2.chosen_model_id)
    assert d3.chosen_model_id == d2.chosen_model_id
    assert "sticky_routing_cache" in d3.matched_signals


@pytest.mark.asyncio
async def test_exhausted_quota_is_skipped_and_cache_refreshes(router_db):
    db = router_db
    res = classify_intent("Oi")
    d1 = await select_best_model(res, "balanced_smart", db)
    await db.execute(
        "INSERT INTO model_quota_status (model_id, status) VALUES (?, 'exhausted') "
        "ON CONFLICT(model_id) DO UPDATE SET status = 'exhausted'",
        (d1.chosen_model_id,),
    )
    await db.commit()
    d2 = await select_best_model(res, "balanced_smart", db)
    assert d2.chosen_model_id != d1.chosen_model_id
    p2 = profile_model(d2.chosen_model_id, d2.chosen_model_id.split("/", 1)[1], d2.provider_id)
    assert p2.size_tier <= SIZE_MEDIUM


@pytest.mark.asyncio
async def test_real_ranking_beats_heuristic_baseline(router_db):
    """Um ranking real (model_rankings) deve prevalecer sobre a qualidade heurística."""
    db = router_db
    invalidate_model_cache()
    target = _mid("groq", "llama-3.3-70b-versatile")
    await db.execute(
        "INSERT INTO model_rankings (model_id, nexuslocal_score, quality_score, popularity_rank) VALUES (?, 99.0, 99.0, 1) "
        "ON CONFLICT(model_id) DO UPDATE SET nexuslocal_score = 99.0, quality_score = 99.0",
        (target,),
    )
    await db.commit()
    res = classify_intent("Escreva um poema sobre o mar em estilo de Fernando Pessoa")
    d = await select_best_model(res, "balanced_smart", db)
    assert d.chosen_model_id == target


# ── Endpoint "Testar roteador" (dry-run) ─────────────────────────────────────

@pytest.mark.asyncio
async def test_preview_endpoint_dry_run(router_db):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from backend.auth import get_current_user
    from backend.routers.dashboard import router as dashboard_router

    app = FastAPI()
    app.include_router(dashboard_router)
    app.dependency_overrides[get_current_user] = lambda: {"id": "preview-user", "username": "p", "role": "user"}
    client = TestClient(app)

    res = client.post("/api/dashboard/auto-router/preview", json={"prompt": "Oi"})
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["intent"]["intent"] == "trivial_quick"
    assert body["decision"]["chosen_model_id"]
    assert body["ranking"] and body["ranking"][0]["model_id"] == body["decision"]["chosen_model_id"]
    assert "fit_score" in body["ranking"][0] and "tags" in body["ranking"][0]
    assert body["candidates_considered"] >= len(body["ranking"])

    res2 = client.post(
        "/api/dashboard/auto-router/preview",
        json={
            "prompt": "Prove que a raiz quadrada de 2 é irracional usando contradição",
            "previous_model_id": body["decision"]["chosen_model_id"],
            "policy": "max_performance",
        },
    )
    assert res2.status_code == 200, res2.text
    body2 = res2.json()
    assert body2["intent"]["intent"] == "deep_reasoning"
    assert body2["policy"] == "max_performance"
    assert body2["decision"]["chosen_model_id"] != body["decision"]["chosen_model_id"]

    bad = client.post("/api/dashboard/auto-router/preview", json={"prompt": "Oi", "policy": "turbo"})
    assert bad.status_code == 400
