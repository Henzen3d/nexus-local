"""Testes automatizados para Reasoning Effort & Thinking Controls.

Multi+ / NexusLocal — Fase 1, 2, 3, 4
REGRA DE OURO (AGENTS.md): Todos os testes com banco utilizam banco temporário descartável.
NUNCA conecta ao nexuslocal.db de produção.
"""
from __future__ import annotations

import asyncio
import json
import os
import sys
import tempfile
from pathlib import Path

os.environ.setdefault("JWT_SECRET", "test-reasoning-secret")
import pytest
import aiosqlite

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.reasoning.families import (
    ReasoningControl,
    resolve_family,
    VALID_REASONING_LEVELS,
)
from backend.reasoning.payload import (
    build_effort_payload,
    build_gemini_thinking_config,
)


def test_taxonomy_pure():
    """1.4: R1 -> always_on; Llama/Groq -> none; Gemini thinking -> gemini_thinking; vazio -> none."""
    # DeepSeek R1
    r1 = resolve_family("deepseek", "deepseek-r1")
    assert r1.control == ReasoningControl.ALWAYS_ON.value
    assert r1.levels == []
    assert r1.default is None

    # Llama / Groq genérico
    llama = resolve_family("groq", "llama-3.3-70b-versatile")
    assert llama.control == ReasoningControl.NONE.value
    assert llama.levels == []

    # Gemini thinking
    gem = resolve_family("gemini", "gemini-2.0-flash-thinking-exp-1219")
    assert gem.control == ReasoningControl.GEMINI_THINKING.value
    assert "medium" in gem.levels
    assert "off" in gem.levels
    assert gem.default == "medium"

    # Claude 3.7 Sonnet via OpenRouter
    cl_or = resolve_family("openrouter", "anthropic/claude-3.7-sonnet")
    assert cl_or.control == ReasoningControl.OPENROUTER_REASONING.value
    assert cl_or.levels == ["low", "medium", "high", "xhigh", "max"]
    assert cl_or.default == "medium"

    # Claude via Anthropic direto
    cl_dir = resolve_family("anthropic", "claude-3-7-sonnet-20250219")
    assert cl_dir.control == ReasoningControl.ANTHROPIC_EFFORT.value

    # OpenAI o1 e o3-mini
    o1 = resolve_family("openai", "o1-preview")
    assert o1.control == ReasoningControl.OPENAI_EFFORT.value
    assert o1.levels == ["low", "medium", "high"]

    o3_or = resolve_family("openrouter", "openai/o3-mini")
    assert o3_or.control == ReasoningControl.OPENROUTER_REASONING.value

    # Vazio / None
    assert resolve_family(None, "").control == ReasoningControl.NONE.value
    assert resolve_family("groq", None).control == ReasoningControl.NONE.value

    # Agnes texto no provedor oficial tem dial; imagem/vídeo e gateway não.
    agnes = resolve_family("agnes", "agnes-3.0-flash")
    assert agnes.control == ReasoningControl.AGNES_EFFORT.value
    assert agnes.levels == ["off", "minimal", "low", "medium", "high", "xhigh", "max"]
    assert agnes.default == "off"
    assert resolve_family("agnes", "agnes-2.5-flash").control == ReasoningControl.AGNES_EFFORT.value
    assert resolve_family("agnes", "agnes-image-2.5-flash").control == ReasoningControl.NONE.value
    assert resolve_family("agnes", "agnes-video-2.5").control == ReasoningControl.NONE.value
    assert resolve_family("zenmux", "sapiens-ai/agnes-2.5-flash").control == ReasoningControl.NONE.value


def test_payload_builder_pure():
    """3.7: Builder sem rede: none igual ao dict; OpenRouter ganha reasoning; inválido é omitido."""
    base = {"model": "test", "messages": [], "temperature": 0.7}

    # none / always_on não altera
    p_none = build_effort_payload(ReasoningControl.NONE.value, "high", base)
    assert p_none == base

    p_always = build_effort_payload(ReasoningControl.ALWAYS_ON.value, "high", base)
    assert p_always == base

    # Nível inválido não altera
    p_inv = build_effort_payload(ReasoningControl.OPENAI_EFFORT.value, "invalid_level", base)
    assert p_inv == base

    # Nível fora dos permitidos do modelo não altera
    p_not_allowed = build_effort_payload(
        ReasoningControl.OPENAI_EFFORT.value,
        "max",  # OpenAI não aceita max
        base,
        allowed_levels=["low", "medium", "high"],
    )
    assert p_not_allowed == base

    # OpenAI effort válido
    p_openai = build_effort_payload(
        ReasoningControl.OPENAI_EFFORT.value,
        "high",
        base,
        allowed_levels=["low", "medium", "high"],
    )
    assert p_openai["reasoning_effort"] == "high"

    # OpenRouter reasoning
    p_or = build_effort_payload(
        ReasoningControl.OPENROUTER_REASONING.value,
        "medium",
        base,
    )
    assert p_or["reasoning"] == {"effort": "medium"}

    # Gemini nativo com generationConfig
    gem_base = {
        "contents": [],
        "generationConfig": {"temperature": 0.7, "maxOutputTokens": 2048},
    }
    p_gem = build_effort_payload(ReasoningControl.GEMINI_THINKING.value, "high", gem_base)
    assert p_gem["generationConfig"]["thinkingConfig"]["thinkingBudget"] == 16384

    # Gemini off
    p_gem_off = build_effort_payload(ReasoningControl.GEMINI_THINKING.value, "off", gem_base)
    assert p_gem_off["generationConfig"]["thinkingConfig"]["thinkingBudget"] == 0

    # Agnes: off da UI vira none; high passa direto
    p_agnes_off = build_effort_payload(ReasoningControl.AGNES_EFFORT.value, "off", base)
    assert p_agnes_off["reasoning_effort"] == "none"
    p_agnes_high = build_effort_payload(ReasoningControl.AGNES_EFFORT.value, "high", base)
    assert p_agnes_high["reasoning_effort"] == "high"


@pytest.mark.asyncio
async def test_migration_and_seed_in_temp_db():
    """2.5: Seed em banco temporário descartável. Admin não é sobrescrito."""
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as tmp:
        tmp_path = Path(tmp.name)

    try:
        async with aiosqlite.connect(tmp_path) as db:
            # Cria esquema simplificado similar ao inicial
            await db.execute("""
                CREATE TABLE providers (
                    id TEXT PRIMARY KEY,
                    name TEXT,
                    base_url TEXT,
                    api_key TEXT,
                    enabled INTEGER DEFAULT 1,
                    is_free INTEGER DEFAULT 0,
                    share_admin_key INTEGER DEFAULT 0
                );
            """)
            await db.execute("""
                CREATE TABLE models (
                    id TEXT PRIMARY KEY,
                    provider_id TEXT,
                    name TEXT,
                    display_name TEXT,
                    context_length INTEGER DEFAULT 8192,
                    context_source TEXT DEFAULT 'default',
                    confirmed_free INTEGER DEFAULT 0,
                    enabled INTEGER DEFAULT 1
                );
            """)
            # Insere dados de teste
            await db.execute(
                "INSERT INTO providers (id, name, base_url) VALUES ('openrouter', 'OpenRouter', 'https://openrouter.ai/api/v1')"
            )
            # Modelo que receberá override de admin
            await db.execute(
                "INSERT INTO models (id, provider_id, name, display_name) VALUES ('m-admin', 'openrouter', 'anthropic/claude-3.7-sonnet', 'Claude 3.7')"
            )
            # Modelo novo unset
            await db.execute(
                "INSERT INTO models (id, provider_id, name, display_name) VALUES ('m-gemini', 'openrouter', 'gemini-2.0-flash-thinking', 'Gemini Thinking')"
            )
            # Modelo sem dial
            await db.execute(
                "INSERT INTO models (id, provider_id, name, display_name) VALUES ('m-llama', 'openrouter', 'meta-llama/llama-3.3-70b-instruct', 'Llama 3.3')"
            )
            await db.commit()

            # Executa as migrações incrementais
            for col, col_def in [
                ("reasoning_control", "TEXT DEFAULT 'none'"),
                ("reasoning_levels", "TEXT"),
                ("reasoning_default", "TEXT"),
                ("reasoning_control_source", "TEXT DEFAULT 'unset'"),
            ]:
                await db.execute(f"ALTER TABLE models ADD COLUMN {col} {col_def}")
            await db.execute(
                "CREATE INDEX IF NOT EXISTS idx_models_reasoning_control ON models(reasoning_control)"
            )
            await db.commit()

            # Seta override de admin em m-admin ANTES do seed
            await db.execute(
                """UPDATE models
                   SET reasoning_control = 'custom_override',
                       reasoning_levels = '["low"]',
                       reasoning_default = 'low',
                       reasoning_control_source = 'admin'
                   WHERE id = 'm-admin'"""
            )
            await db.execute(
                """INSERT INTO models (id, provider_id, name, display_name, reasoning_control, reasoning_levels, reasoning_default, reasoning_control_source)
                   VALUES ('m-agnes', 'agnes', 'agnes-3.0-flash', 'Agnes 3.0 Flash', 'none', NULL, NULL, 'family')"""
            )
            await db.commit()

            # Roda o seed
            from backend.database import seed_reasoning_controls
            updated = await seed_reasoning_controls(db)
            assert updated >= 2

            # Verifica que o admin NÃO foi alterado
            async with db.execute("SELECT reasoning_control, reasoning_control_source FROM models WHERE id = 'm-admin'") as cur:
                row_admin = await cur.fetchone()
                assert row_admin[0] == "custom_override"
                assert row_admin[1] == "admin"

            # Verifica que m-gemini virou gemini_thinking com source family
            async with db.execute("SELECT reasoning_control, reasoning_control_source, reasoning_levels FROM models WHERE id = 'm-gemini'") as cur:
                row_gem = await cur.fetchone()
                assert row_gem[0] == ReasoningControl.GEMINI_THINKING.value
                assert row_gem[1] == "family"
                levels = json.loads(row_gem[2])
                assert "medium" in levels

            # Verifica que m-llama virou none com source family
            async with db.execute("SELECT reasoning_control, reasoning_control_source FROM models WHERE id = 'm-llama'") as cur:
                row_llama = await cur.fetchone()
                assert row_llama[0] == "none"
                assert row_llama[1] == "family"

            # Família antiga gravada como none é recalculada; admin continua intocado
            async with db.execute(
                "SELECT reasoning_control, reasoning_default, reasoning_control_source FROM models WHERE id = 'm-agnes'"
            ) as cur:
                row_agnes = await cur.fetchone()
                assert row_agnes is not None
                assert row_agnes[0] == ReasoningControl.AGNES_EFFORT.value
                assert row_agnes[1] == "off"
                assert row_agnes[2] == "family"

    finally:
        if tmp_path.exists():
            try:
                os.remove(tmp_path)
            except Exception:
                pass


class MockWebSocket:
    def __init__(self):
        self.sent_messages: list[dict] = []

    async def send_json(self, data: dict):
        self.sent_messages.append(data)


@pytest.mark.asyncio
async def test_resolve_and_stream_reasoning_behavior():
    """4.6: Testes do resolvedor com provider falso, sem rede e sem banco vivo."""
    from unittest.mock import AsyncMock, patch
    from backend.orchestration.resolve_request import stream_from_llm

    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as tmp:
        tmp_path = Path(tmp.name)

    try:
        async with aiosqlite.connect(tmp_path) as db:
            await db.execute("""
                CREATE TABLE models (
                    id TEXT PRIMARY KEY,
                    provider_id TEXT,
                    name TEXT,
                    display_name TEXT,
                    enabled INTEGER DEFAULT 1,
                    reasoning_control TEXT,
                    reasoning_levels TEXT,
                    reasoning_default TEXT
                );
            """)
            await db.execute("""
                CREATE TABLE model_usage_log (
                    id TEXT PRIMARY KEY,
                    model_id TEXT,
                    provider_id TEXT,
                    conversation_id TEXT,
                    user_id TEXT,
                    was_fallback INTEGER,
                    fallback_from_model_id TEXT,
                    fallback_reason TEXT,
                    was_auto_routed INTEGER,
                    route_intent TEXT,
                    route_confidence REAL,
                    route_latency_ms REAL,
                    route_policy TEXT
                );
            """)
            await db.execute(
                "INSERT INTO models VALUES ('m-dial', 'openai', 'o3-mini', 'o3-mini', 1, 'openai_effort', '[\"low\",\"medium\",\"high\"]', 'medium')"
            )
            await db.execute(
                "INSERT INTO models VALUES ('m-nodial', 'groq', 'llama-3', 'Llama 3', 1, 'none', NULL, NULL)"
            )
            await db.commit()

            # Cenário 1: Modelo sem dial com reasoning_effort pedido -> emite effort_dropped (unsupported_model)
            ws1 = MockWebSocket()
            mock_provider1 = AsyncMock()

            async def fake_stream_1(**kwargs):
                yield "hello"

            mock_provider1.stream_chat = fake_stream_1

            with patch("backend.orchestration.resolve_request.get_provider", return_value=mock_provider1), \
                 patch("backend.orchestration.resolve_request.get_model_name", return_value="llama-3"), \
                 patch("backend.orchestration.resolve_request.resolve_model_with_failover") as mock_res, \
                 patch("backend.orchestration.resolve_request.mark_model_success"), \
                 patch("backend.orchestration.resolve_request.record_request"):
                resolved_mock = AsyncMock()
                resolved_mock.was_failover = False
                resolved_mock.model_id = "m-nodial"
                resolved_mock.provider_id = "groq"
                resolved_mock.display_name = "Llama 3"
                mock_res.return_value = resolved_mock

                res = await stream_from_llm(
                    ws=ws1,
                    db=db,
                    conversation_id="conv-1",
                    user_id="user-1",
                    model_id="m-nodial",
                    provider_id="groq",
                    history=[{"role": "user", "content": "hi"}],
                    reasoning_effort="high",
                )
                assert res is not None
                # Verifica que foi emitido effort_dropped com unsupported_model
                dropped_events = [m for m in ws1.sent_messages if m.get("type") == "effort_dropped"]
                assert len(dropped_events) == 1
                assert dropped_events[0]["reason"] == "unsupported_model"
                assert dropped_events[0]["requested"] == "high"

            # Cenário 2: Modelo com dial recebe reasoning_effort e repassa kwargs
            ws2 = MockWebSocket()
            captured_kwargs = {}

            async def fake_stream_2(**kwargs):
                captured_kwargs.update(kwargs)
                yield "thinking response"

            mock_provider2 = AsyncMock()
            mock_provider2.stream_chat = fake_stream_2

            with patch("backend.orchestration.resolve_request.get_provider", return_value=mock_provider2), \
                 patch("backend.orchestration.resolve_request.get_model_name", return_value="o3-mini"), \
                 patch("backend.orchestration.resolve_request.resolve_model_with_failover") as mock_res, \
                 patch("backend.orchestration.resolve_request.mark_model_success"), \
                 patch("backend.orchestration.resolve_request.record_request"):
                resolved_mock = AsyncMock()
                resolved_mock.was_failover = False
                resolved_mock.model_id = "m-dial"
                resolved_mock.provider_id = "openai"
                resolved_mock.display_name = "o3-mini"
                mock_res.return_value = resolved_mock

                res = await stream_from_llm(
                    ws=ws2,
                    db=db,
                    conversation_id="conv-2",
                    user_id="user-1",
                    model_id="m-dial",
                    provider_id="openai",
                    history=[{"role": "user", "content": "hi"}],
                    reasoning_effort="medium",
                )
                assert res is not None
                assert captured_kwargs.get("reasoning_effort") == "medium"
                assert captured_kwargs.get("reasoning_control") == "openai_effort"

            # Cenário 3: Rede de segurança contra HTTP 400 citando reasoning_effort
            ws3 = MockWebSocket()
            attempts = 0

            async def fake_stream_3(**kwargs):
                nonlocal attempts
                attempts += 1
                if attempts == 1:
                    raise RuntimeError("Provider error 400: Unsupported parameter: reasoning_effort")
                yield "recovered without effort"

            mock_provider3 = AsyncMock()
            mock_provider3.stream_chat = fake_stream_3

            with patch("backend.orchestration.resolve_request.get_provider", return_value=mock_provider3), \
                 patch("backend.orchestration.resolve_request.get_model_name", return_value="o3-mini"), \
                 patch("backend.orchestration.resolve_request.resolve_model_with_failover") as mock_res, \
                 patch("backend.orchestration.resolve_request.mark_model_success"), \
                 patch("backend.orchestration.resolve_request.record_request"):
                resolved_mock = AsyncMock()
                resolved_mock.was_failover = False
                resolved_mock.model_id = "m-dial"
                resolved_mock.provider_id = "openai"
                resolved_mock.display_name = "o3-mini"
                mock_res.return_value = resolved_mock

                res = await stream_from_llm(
                    ws=ws3,
                    db=db,
                    conversation_id="conv-3",
                    user_id="user-1",
                    model_id="m-dial",
                    provider_id="openai",
                    history=[{"role": "user", "content": "hi"}],
                    reasoning_effort="high",
                )
                assert res is not None
                full_resp, _, _ = res
                assert full_resp == "recovered without effort"
                # Verifica que emitiu effort_dropped com provider_rejected
                rejected_events = [m for m in ws3.sent_messages if m.get("type") == "effort_dropped"]
                assert len(rejected_events) == 1
                assert rejected_events[0]["reason"] == "provider_rejected"
    finally:
        if tmp_path.exists():
            try:
                os.remove(tmp_path)
            except Exception:
                pass


def test_parse_reasoning_levels_does_not_require_local_import():
    """GET /admin/providers 500'd because json lived only inside sync_provider_models."""
    from backend.routers.admin import parse_reasoning_levels

    assert parse_reasoning_levels('["low", "high"]') == ["low", "high"]
    assert parse_reasoning_levels(None) is None
    assert parse_reasoning_levels("") is None
    assert parse_reasoning_levels(["medium"]) == ["medium"]
    assert parse_reasoning_levels("not-json") is None
