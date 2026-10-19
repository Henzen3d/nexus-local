"""
backend/tests/test_failover_a1_taxonomia.py
Testes unitários da Etapa A1: Taxonomia única de falhas (classify_failure) e persistência de desativação contra sync de catálogo.
"""

import aiosqlite
import pytest
from backend.ranking.classifier import classify_failure, extract_suggested_model
from backend.database import check_and_deactivate_model
from backend.routers.admin import sync_provider_models


def test_classify_failure_gemini_404_deprecated():
    gemini_body = (
        '{"error": {"code": 404, "message": "This model models/gemini-2.5-pro is no longer available '
        'to new users. Please update your code to use models/gemini-3.1-pro-preview.", "status": "NOT_FOUND"}}'
    )
    res = classify_failure(provider="gemini", http_status=404, body=gemini_body)

    assert res["outcome"] == "MODEL_DEPRECATED"
    assert res["scope"] == "provider_model"
    assert res["retryable"] is False
    assert res["suggested_model"] == "models/gemini-3.1-pro-preview"
    assert "model_deprecated" in res["status_message"]


def test_classify_failure_longcat_402_app_quota():
    longcat_body = (
        '{"error":{"code":"too_many_requests","message":"AppId:**jt51 Usage limit reached.","type":"rate_limit_error"}}'
    )
    res = classify_failure(provider="longcat", http_status=402, body=longcat_body)

    assert res["outcome"] == "QUOTA_402"
    assert res["scope"] == "provider"  # Escopo da credencial/provedor!
    assert res["retryable"] is False
    assert res["cooldown"] >= 3600


def test_classify_failure_rate_limit_429_with_retry_after():
    body = "Rate limit exceeded. Please wait 45 seconds before retrying."
    res = classify_failure(provider="groq", http_status=429, body=body)

    assert res["outcome"] == "RATE_LIMIT_429"
    assert res["scope"] == "provider"
    assert res["retryable"] is True
    assert res["cooldown"] == 45


def test_classify_failure_auth_401_403():
    body = '{"error": "access_denied", "message": "Invalid API key"}'
    res = classify_failure(provider="zenmux", http_status=403, body=body)

    assert res["outcome"] == "AUTH_401_403"
    assert res["scope"] == "provider"
    assert res["retryable"] is False
    assert res["cooldown"] >= 86400


def test_classify_failure_zero_token():
    res = classify_failure(
        provider="nvidia",
        http_status=200,
        body="Silent failure: 0 tokens returned",
        tokens_emitted=0,
        stream_shape="empty",
    )

    assert res["outcome"] == "ZERO_TOKEN"
    assert res["scope"] == "provider_model"
    assert res["retryable"] is False
    assert res["cooldown"] == 600


def test_classify_failure_user_cancelled():
    res = classify_failure(
        provider="openai",
        http_status=None,
        body="Client disconnected / CancelledError",
        stage="cancelled",
    )

    assert res["outcome"] == "CANCELLED"
    assert res["scope"] == "none"
    assert res["retryable"] is False
    assert res["cooldown"] == 0


def test_classify_failure_invalid_request_400():
    body = '{"error": "Unsupported parameter: reasoning_effort"}'
    res = classify_failure(provider="together", http_status=400, body=body)

    assert res["outcome"] == "INVALID_REQUEST"
    assert res["scope"] == "request"
    assert res["retryable"] is False


def test_classify_failure_transient_5xx():
    res = classify_failure(provider="openrouter", http_status=502, body="Bad Gateway from upstream")

    assert res["outcome"] == "PRE_STREAM_ERR"
    assert res["scope"] == "provider_model"
    assert res["retryable"] is True
    assert res["cooldown"] == 30


@pytest.mark.asyncio
async def test_deprecated_model_remains_disabled_after_catalog_sync():
    """Garante que modelo desativado por MODEL_DEPRECATED permanece enabled=0 mesmo após sync de catálogo."""
    async with aiosqlite.connect(":memory:") as db:
        await db.execute("""
            CREATE TABLE providers (
                id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                enabled INTEGER DEFAULT 1,
                is_free INTEGER DEFAULT 0,
                api_key TEXT DEFAULT 'test_key',
                base_url TEXT DEFAULT ''
            )
        """)
        await db.execute("""
            CREATE TABLE models (
                id TEXT PRIMARY KEY,
                provider_id TEXT NOT NULL,
                name TEXT NOT NULL,
                display_name TEXT,
                context_length INTEGER DEFAULT 8192,
                context_source TEXT DEFAULT 'api',
                enabled INTEGER DEFAULT 1,
                confirmed_free INTEGER DEFAULT 0,
                supports_vision INTEGER DEFAULT 0,
                reasoning_control TEXT DEFAULT 'none',
                reasoning_levels TEXT,
                reasoning_default TEXT,
                reasoning_control_source TEXT DEFAULT 'unset'
            )
        """)
        await db.execute("""
            CREATE TABLE model_quota_status (
                model_id TEXT PRIMARY KEY,
                status TEXT DEFAULT 'available',
                consecutive_errors INTEGER DEFAULT 0,
                exhausted_at TEXT,
                estimated_reset_at TEXT,
                last_error_message TEXT
            )
        """)
        await db.execute("CREATE TABLE meta (key TEXT PRIMARY KEY, value TEXT)")
        await db.execute("CREATE TABLE sync_log (id TEXT PRIMARY KEY, provider_id TEXT, synced_at TEXT, models_updated INTEGER, status TEXT, error_msg TEXT)")
        await db.execute("CREATE TABLE model_overrides (model_id TEXT PRIMARY KEY)")
        await db.execute("CREATE TABLE free_model_registry (id TEXT PRIMARY KEY, provider_name TEXT, model_id_raw TEXT)")
        await db.execute("CREATE TABLE model_rankings (model_id TEXT PRIMARY KEY, quality_score REAL, popularity_rank INTEGER, nexuslocal_score REAL, source TEXT, updated_at TEXT)")
        await db.execute("CREATE TABLE model_family_members (family_id TEXT, model_id TEXT, fallback_order INTEGER)")
        await db.execute("CREATE TABLE model_families (id TEXT PRIMARY KEY, display_name TEXT)")

        # Insere provedor e modelo
        await db.execute("INSERT INTO providers (id, name, enabled, is_free) VALUES ('gemini', 'Google Gemini', 1, 1)")
        await db.execute("""
            INSERT INTO models (id, provider_id, name, display_name, enabled, confirmed_free)
            VALUES ('gemini/gemini-2.5-pro', 'gemini', 'models/gemini-2.5-pro', 'Gemini 2.5 Pro', 1, 1)
        """)
        await db.commit()

        # 1. Desativa por 404 deprecated
        gemini_404 = (
            'This model models/gemini-2.5-pro is no longer available to new users. '
            'Please update your code to use models/gemini-3.1-pro-preview.'
        )
        deactivated = await check_and_deactivate_model("gemini/gemini-2.5-pro", gemini_404, db=db)
        assert deactivated is True

        # Verifica que enabled = 0
        async with db.execute("SELECT enabled FROM models WHERE id = 'gemini/gemini-2.5-pro'") as cur:
            row = await cur.fetchone()
            assert row[0] == 0

        # 2. Simula o sync do catálogo retornando o modelo ainda na lista de modelos do provedor
        from unittest.mock import patch
        from backend.providers.model_fetcher import ModelFetcher
        fake_api_models = [
            {"model_name": "gemini-2.5-pro", "context_length": 1000000, "supports_vision": False}
        ]
        with patch.object(ModelFetcher, "fetch_gemini", return_value=fake_api_models), \
             patch("backend.free_registry.matcher.match_registry_to_models", return_value=0), \
             patch("backend.ranking.sync.seed_missing_rankings", return_value=0):
            res = await sync_provider_models("gemini", db)

        # 3. VERIFICAÇÃO CRÍTICA DO Golden Prompt v3.0:
        # O modelo desativado por MODEL_DEPRECATED DEVE PERMANECER enabled = 0 após o sync!
        async with db.execute("SELECT enabled FROM models WHERE id = 'gemini/gemini-2.5-pro'") as cur:
            row = await cur.fetchone()
            assert row[0] == 0, "Erro: modelo descontinuado foi reabilitado indevidamente pelo sync de catálogo!"
