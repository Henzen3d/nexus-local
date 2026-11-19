"""
backend/tests/test_failover_t1_t2_incident.py
Testes unitários e de integração das tarefas T1 e T2 do plano de correção do failover (19/11/2026).
- T1: Classificação refinada de erros com ProviderHTTPError estruturado, separação de 402, 429,
      model_unavailable (400) e INVALID_REQUEST (400).
- T2: Quarentena por credencial para 402 sem bloqueio de chaves alternativas nem cooldown canônico global;
      cooldown temporário para 400 model_unavailable preservando enabled e confirmed_free;
      descarte limpo de already_attempted_in_cascade.
"""

import asyncio
from datetime import datetime, timedelta, timezone
from unittest.mock import patch, MagicMock

import aiosqlite
import pytest

from backend.ranking.classifier import classify_failure, extract_structured_error
from backend.ranking.eligibility import check_candidate_eligibility
from backend.ranking.quota import (
    get_credential_hash,
    make_quarantine_key,
    quarantine_credential,
    is_credential_quarantined,
    resolve_provider_credential,
    release_expired_quarantines,
    mark_model_exhausted,
    get_quota_status,
)
from backend.ranking.failover import resolve_model_with_failover
from backend.providers.base import ProviderHTTPError, RateLimitError
from backend.orchestration.resolve_request import stream_from_llm


# ─── T1 Tests ───────────────────────────────────────────────────────────────

def test_t1_orcarouter_402_classification():
    """T1.1 & T1.3: OrcaRouter HTTP 402 classificado como QUOTA_402, escopo provider, cooldown 1h."""
    body = '{"error": {"code": "insufficient_user_quota", "message": "Credit gate rejected", "type": "err_credit_gate"}}'
    exc = ProviderHTTPError(402, f"Provider error 402: {body}", provider="orcarouter")
    structured = extract_structured_error(exc)
    assert structured["status_code"] == 402
    assert structured["error_code"] == "insufficient_user_quota"
    assert structured["error_type"] == "err_credit_gate"

    res = classify_failure(provider="orcarouter", http_status=structured["status_code"], body=structured["raw_message"])
    assert res["outcome"] == "QUOTA_402"
    assert res["scope"] == "provider"
    assert res["reason"] == "quota_exhausted"
    assert res["retryable"] is False
    assert res["cooldown"] >= 3600


def test_t1_llm7_400_model_unavailable_classification():
    """T1.2 & T1.3: LLM7 HTTP 400 model_unavailable classificado como MODEL_UNAVAILABLE, escopo model/provider_model."""
    body = '{"error": {"code": "model_unavailable", "message": "The requested model is currently unavailable."}}'
    exc = ProviderHTTPError(400, f"Provider error 400: {body}", provider="llm7")
    structured = extract_structured_error(exc)
    assert structured["status_code"] == 400
    assert structured["error_code"] == "model_unavailable"

    res = classify_failure(provider="llm7", http_status=structured["status_code"], body=structured["raw_message"])
    assert res["outcome"] == "MODEL_UNAVAILABLE"
    # Escopo compatível tanto com 'model' quanto 'provider_model'
    assert res["scope"] == "model"
    assert res["scope"] == "provider_model"
    assert res["reason"] == "model_unavailable"
    assert res["retryable"] is False
    assert res["cooldown"] > 0


def test_t1_http400_schema_invalid_request_classification():
    """T1.2: HTTP 400 de schema/payload é INVALID_REQUEST, escopo request, cooldown 0."""
    body = '{"error": {"code": "invalid_parameter", "message": "schema validation error: unknown field foo"}}'
    res = classify_failure(provider="together", http_status=400, body=body)
    assert res["outcome"] == "INVALID_REQUEST"
    assert res["scope"] == "request"
    assert res["cooldown"] == 0
    assert res["retryable"] is False


def test_t1_rate_limit_429_classification():
    """T1.3: Rate limit 429 tem código distinto rate_limit e outcome RATE_LIMIT_429."""
    res = classify_failure(provider="groq", http_status=429, body="Rate limit reached. Please retry after 30 seconds.")
    assert res["outcome"] == "RATE_LIMIT_429"
    assert res["scope"] == "provider"
    assert res["reason"] == "rate_limit"
    assert res["cooldown"] == 30


# ─── T2 Tests ───────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_t2_credential_quarantine_blocks_only_affected_key():
    """
    T2.1: Quarentena de credencial bloqueia chamadas que usam a mesma chave esgotada (402),
    mas mantém elegíveis chaves alternativas do mesmo provedor e o mesmo modelo canônico em outro provedor.
    """
    async with aiosqlite.connect(":memory:") as db:
        await db.execute("""
            CREATE TABLE providers (
                id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                enabled INTEGER DEFAULT 1,
                api_key TEXT DEFAULT 'shared_key_123',
                is_free INTEGER DEFAULT 0
            )
        """)
        await db.execute("""
            CREATE TABLE models (
                id TEXT PRIMARY KEY,
                provider_id TEXT NOT NULL,
                name TEXT NOT NULL,
                display_name TEXT,
                enabled INTEGER DEFAULT 1,
                confirmed_free INTEGER DEFAULT 1
            )
        """)
        await db.execute("""
            CREATE TABLE user_api_keys (
                id TEXT PRIMARY KEY,
                user_id TEXT NOT NULL,
                provider_id TEXT NOT NULL,
                api_key TEXT NOT NULL
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
        await db.execute("""
            CREATE TABLE provider_quarantine (
                provider_id TEXT PRIMARY KEY,
                quarantined_until TEXT NOT NULL,
                reason TEXT,
                updated_at TEXT DEFAULT (datetime('now'))
            )
        """)

        # Insere orcarouter com chave compartilhada e openrouter com chave própria
        await db.execute("INSERT INTO providers (id, name, api_key) VALUES ('orcarouter', 'OrcaRouter', 'shared_key_123')")
        await db.execute("INSERT INTO providers (id, name, api_key) VALUES ('openrouter', 'OpenRouter', 'openrouter_key_abc')")

        # Modelo DeepSeek V4.1 Flash no OrcaRouter e no OpenRouter (mesmo canônico)
        await db.execute("""
            INSERT INTO models (id, provider_id, name, display_name)
            VALUES ('orcarouter/deepseek/deepseek-v4.1-flash', 'orcarouter', 'deepseek-v4.1-flash', 'DeepSeek Orca')
        """)
        await db.execute("""
            INSERT INTO models (id, provider_id, name, display_name)
            VALUES ('openrouter/deepseek/deepseek-v4.1-flash', 'openrouter', 'deepseek-v4.1-flash', 'DeepSeek OpenRouter')
        """)

        # user_with_personal_key tem chave própria no OrcaRouter
        await db.execute("""
            INSERT INTO user_api_keys (id, user_id, provider_id, api_key)
            VALUES ('k1', 'user_with_personal_key', 'orcarouter', 'personal_key_456')
        """)
        await db.commit()

        # 1. Aplica quarentena na chave compartilhada do OrcaRouter (simulando 402)
        await quarantine_credential("orcarouter", "shared_key_123", db, duration_seconds=3600, reason="quota_exhausted")
        await mark_model_exhausted("orcarouter/deepseek/deepseek-v4.1-flash", db, retry_after=3600, error_msg="quota_exhausted")

        # 2. Usuário sem chave pessoal (user_shared) tenta usar OrcaRouter -> DEVE ser bloqueado
        elig_shared = await check_candidate_eligibility(
            "orcarouter/deepseek/deepseek-v4.1-flash", "orcarouter", db, user_id="user_shared"
        )
        assert not elig_shared.eligible
        # Bloqueado por quarentena de credencial ou cooldown de modelo
        assert elig_shared.reason in ("credential_quarantined", "model_cooldown_active")

        # 3. Usuário com chave pessoal (user_with_personal_key) tenta outro modelo do OrcaRouter
        # Insere um segundo modelo no OrcaRouter para validar que a chave pessoal não está em quarentena
        await db.execute("""
            INSERT INTO models (id, provider_id, name, display_name)
            VALUES ('orcarouter/other-model', 'orcarouter', 'other-model', 'Other Model Orca')
        """)
        await db.commit()
        elig_personal = await check_candidate_eligibility(
            "orcarouter/other-model", "orcarouter", db, user_id="user_with_personal_key"
        )
        assert elig_personal.eligible is True, f"Esperava elegível mas obteve: {elig_personal.reason}"

        # 4. T2.2: O modelo equivalente no OpenRouter (mesmo canonical_model_id) NÃO DEVE sofrer cooldown canônico!
        elig_openrouter = await check_candidate_eligibility(
            "openrouter/deepseek/deepseek-v4.1-flash", "openrouter", db, user_id="user_shared"
        )
        assert elig_openrouter.eligible is True, f"OpenRouter bloqueado indevidamente por canonical cooldown: {elig_openrouter.reason}"


@pytest.mark.asyncio
async def test_t2_llm7_model_unavailable_does_not_deactivate_and_does_not_block_canonical():
    """
    T2.2: LLM7 HTTP 400 model_unavailable aplica cooldown transitório sem alterar enabled=1 nem confirmed_free=1,
    e sem disparar cooldown canônico em outros provedores.
    """
    async with aiosqlite.connect(":memory:") as db:
        await db.execute("""
            CREATE TABLE providers (
                id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                enabled INTEGER DEFAULT 1,
                api_key TEXT DEFAULT 'key_llm7',
                is_free INTEGER DEFAULT 0
            )
        """)
        await db.execute("""
            CREATE TABLE models (
                id TEXT PRIMARY KEY,
                provider_id TEXT NOT NULL,
                name TEXT NOT NULL,
                display_name TEXT,
                enabled INTEGER DEFAULT 1,
                confirmed_free INTEGER DEFAULT 1
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
        await db.execute("INSERT INTO providers (id, name) VALUES ('llm7', 'LLM7')")
        await db.execute("INSERT INTO providers (id, name) VALUES ('openrouter', 'OpenRouter')")

        await db.execute("""
            INSERT INTO models (id, provider_id, name, display_name, enabled, confirmed_free)
            VALUES ('llm7/deepseek-v4.1-flash', 'llm7', 'deepseek-v4.1-flash', 'DeepSeek LLM7', 1, 1)
        """)
        await db.execute("""
            INSERT INTO models (id, provider_id, name, display_name, enabled, confirmed_free)
            VALUES ('openrouter/deepseek/deepseek-v4.1-flash', 'openrouter', 'deepseek-v4.1-flash', 'DeepSeek OpenRouter', 1, 1)
        """)
        await db.commit()

        # Simula erro model_unavailable no LLM7
        await mark_model_exhausted("llm7/deepseek-v4.1-flash", db, retry_after=300, error_msg="model_unavailable")

        # Verifica que enabled e confirmed_free continuam 1 (não foi desativado no banco!)
        async with db.execute("SELECT enabled, confirmed_free FROM models WHERE id = 'llm7/deepseek-v4.1-flash'") as cur:
            row = await cur.fetchone()
            assert row[0] == 1, "Erro: modelo foi desativado indevidamente!"
            assert row[1] == 1, "Erro: confirmed_free foi zerado indevidamente!"

        # LLM7 deve estar em cooldown temporário
        q_llm7 = await get_quota_status("llm7/deepseek-v4.1-flash", db)
        assert q_llm7["status"] == "exhausted"

        # Candidato LLM7 não está elegível durante o cooldown
        elig_llm7 = await check_candidate_eligibility("llm7/deepseek-v4.1-flash", "llm7", db)
        assert not elig_llm7.eligible
        assert elig_llm7.reason == "model_cooldown_active"

        # T2.2: OpenRouter com o mesmo modelo canônico CONTINUA elegível (sem canonical cooldown cruzado!)
        elig_openrouter = await check_candidate_eligibility("openrouter/deepseek/deepseek-v4.1-flash", "openrouter", db)
        assert elig_openrouter.eligible is True, f"OpenRouter bloqueado indevidamente: {elig_openrouter.reason}"


from backend.tests.test_failover_ttft_sqlite import _make_two_model_db


@pytest.mark.asyncio
async def test_t1_invalid_request_terminates_cascade_immediately():
    """
    T1.2: Requisição com schema/parâmetro comprovadamente inválido (INVALID_REQUEST)
    interrompe a cascata imediatamente sem tentar os demais candidatos com o mesmo payload.
    """
    db = await _make_two_model_db()
    sent = []
    class Socket:
        async def send_json(self, event):
            sent.append(event)

    class BadSchemaProvider:
        async def stream_chat(self, **kwargs):
            if False:
                yield ""
            raise ProviderHTTPError(400, "HTTP 400 Bad Request: schema validation error in messages", provider="p1")

    with patch("backend.orchestration.resolve_request.get_provider", return_value=BadSchemaProvider()):
        result = await stream_from_llm(
            ws=Socket(),
            db=db,
            conversation_id="conv-invalid-req",
            user_id="u_t22",
            model_id="p1/m1",
            provider_id="p1",
            history=[{"role": "user", "content": "teste"}],
            turn_id="turn-invalid-req",
        )

    assert result is None
    # Verifica que encerrou com motivo 'invalid_request'
    end_events = [e for e in sent if e.get("type") == "stream_end"]
    assert len(end_events) == 1
    assert end_events[0]["reason"] == "invalid_request"
    assert end_events[0]["outcome"] == "error"
    await db.close()
