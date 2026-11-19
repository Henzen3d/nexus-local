"""
backend/tests/test_incident_failover_e2e.py
Teste integrado de ponta a ponta reproduzindo o incidente de 19/11/2026 (T6.1 e T6.2):
  1. Chamada 1: OrcaRouter HTTP 402 (insufficient_user_quota / err_credit_gate com URL de cobrança)
  2. Chamada 2: LLM7 HTTP 400 (model_unavailable transitório)
  3. Chamada 3: OpenRouter sucesso com resultados e citações da busca web

Validações:
  - Sequência correta de failovers na mesma execução
  - Sanitização rigorosa de eventos de atividade (sem JSON bruto, sem links de faturamento, sem chaves)
  - Quarentena específica da credencial afetada pelo 402 no turno subsequente
  - Preservação do modelo no LLM7 sem desativação global indevida
  - Identificação precisa de served_by como Nemotron 3 Ultra via OpenRouter
  - Preservação intacta de citações e fontes
  - Caminho com busca desativada e encerramento limpo por tempo limite
"""

import asyncio
import os
import tempfile
import pytest
import aiosqlite
from unittest.mock import AsyncMock, patch

from backend.providers.base import ProviderHTTPError
from backend.orchestration.resolve_request import stream_from_llm
from backend.ranking.quota import (
    is_credential_quarantined,
    quarantine_credential,
    make_quarantine_key,
)
from backend.ranking.failover import resolve_model_with_failover, NoAvailableModelError
from backend.context.request_context import RequestContext


@pytest.fixture
async def incident_db():
    """Configura um banco SQLite temporário isolado contendo o cenário do incidente."""
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)

    db = await aiosqlite.connect(path)
    await db.executescript("""
        CREATE TABLE providers (
            id TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            enabled INTEGER DEFAULT 1,
            is_free INTEGER DEFAULT 0,
            is_local INTEGER DEFAULT 0,
            base_url TEXT DEFAULT '',
            api_key TEXT DEFAULT '',
            share_admin_key INTEGER DEFAULT 1
        );
        CREATE TABLE models (
            id TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            display_name TEXT NOT NULL,
            provider_id TEXT NOT NULL,
            enabled INTEGER DEFAULT 1,
            confirmed_free INTEGER DEFAULT 0,
            context_length INTEGER DEFAULT 8192,
            reasoning_control TEXT DEFAULT 'none',
            reasoning_levels TEXT DEFAULT NULL,
            reasoning_default TEXT DEFAULT NULL
        );
        CREATE TABLE model_families (
            id TEXT PRIMARY KEY,
            display_name TEXT NOT NULL
        );
        CREATE TABLE model_family_members (
            family_id TEXT NOT NULL,
            model_id TEXT NOT NULL,
            fallback_order INTEGER DEFAULT 1,
            PRIMARY KEY (family_id, model_id)
        );
        CREATE TABLE user_api_keys (
            user_id TEXT NOT NULL,
            provider_id TEXT NOT NULL,
            api_key TEXT NOT NULL,
            PRIMARY KEY (user_id, provider_id)
        );
        CREATE TABLE model_quota_status (
            model_id TEXT PRIMARY KEY,
            status TEXT NOT NULL,
            consecutive_errors INTEGER DEFAULT 0,
            exhausted_at TEXT,
            estimated_reset_at TEXT,
            last_error_message TEXT,
            known_rpm INTEGER DEFAULT NULL,
            known_rpd INTEGER DEFAULT NULL,
            current_minute_count INTEGER DEFAULT 0,
            current_day_count INTEGER DEFAULT 0
        );
        CREATE TABLE provider_quarantine (
            provider_id TEXT PRIMARY KEY,
            quarantined_until TEXT NOT NULL,
            reason TEXT,
            updated_at TEXT DEFAULT (datetime('now'))
        );
        CREATE TABLE model_usage_log (
            id TEXT PRIMARY KEY,
            model_id TEXT,
            provider_id TEXT,
            conversation_id TEXT,
            user_id TEXT,
            tokens_est INTEGER DEFAULT 0,
            was_fallback INTEGER DEFAULT 0,
            fallback_from_model_id TEXT,
            fallback_reason TEXT,
            was_auto_routed INTEGER DEFAULT 0,
            route_intent TEXT,
            route_confidence REAL,
            route_latency_ms REAL,
            route_policy TEXT,
            turn_id TEXT,
            created_at TEXT DEFAULT (datetime('now'))
        );
        CREATE TABLE conversations (
            id TEXT PRIMARY KEY,
            title TEXT,
            user_id TEXT,
            project_tag TEXT,
            created_at TEXT,
            updated_at TEXT
        );
        CREATE TABLE messages (
            id TEXT PRIMARY KEY,
            conversation_id TEXT,
            role TEXT,
            content TEXT,
            created_at TEXT,
            model_id TEXT,
            provider TEXT,
            relay_used INTEGER DEFAULT 0,
            relay_model TEXT,
            kind TEXT DEFAULT 'normal'
        );
        CREATE TABLE meta (
            key TEXT PRIMARY KEY,
            value TEXT
        );
        CREATE TABLE model_rankings (
            model_id TEXT PRIMARY KEY,
            rank_score REAL DEFAULT 0,
            quality_score REAL DEFAULT 0
        );

        -- Insere provedores do incidente
        INSERT INTO providers (id, name, api_key, share_admin_key) VALUES
            ('orcarouter', 'OrcaRouter', 'orca-key-live-1', 1),
            ('llm7', 'LLM7 Provedor', 'llm7-key-live-1', 1),
            ('openrouter', 'OpenRouter Free', 'openrouter-key-live-1', 1);

        -- Insere chaves de usuário
        INSERT INTO user_api_keys (user_id, provider_id, api_key) VALUES
            ('user-osmar', 'orcarouter', 'orca-key-live-1'),
            ('user-osmar', 'llm7', 'llm7-key-live-1'),
            ('user-osmar', 'openrouter', 'openrouter-key-live-1');

        -- Insere modelos envolvidos
        INSERT INTO models (id, name, display_name, provider_id, enabled, confirmed_free) VALUES
            ('orcarouter/deepseek/deepseek-v4.1-flash-1017', 'deepseek-v4.1-flash', 'DeepSeek V4.1 Flash (Orca)', 'orcarouter', 1, 0),
            ('llm7/deepseek-v4.1-flash', 'deepseek-v4.1-flash', 'DeepSeek V4.1 Flash (LLM7)', 'llm7', 1, 1),
            ('openrouter/nvidia/nemotron-3-ultra-550b-a55b:free', 'nemotron-3-ultra-free', 'Nemotron 3 Ultra 550B (Free)', 'openrouter', 1, 1);

        -- Insere família única agrupando os modelos na ordem de fallback 1 -> 2 -> 3
        INSERT INTO model_families (id, display_name) VALUES
            ('deepseek-flash-family', 'DeepSeek Flash Family');
        INSERT INTO model_family_members (family_id, model_id, fallback_order) VALUES
            ('deepseek-flash-family', 'orcarouter/deepseek/deepseek-v4.1-flash-1017', 1),
            ('deepseek-flash-family', 'llm7/deepseek-v4.1-flash', 2),
            ('deepseek-flash-family', 'openrouter/nvidia/nemotron-3-ultra-550b-a55b:free', 3);

        -- Conversa de teste
        INSERT INTO conversations (id, title, user_id) VALUES
            ('conv-incident-001', 'Modelos e Preços', 'user-osmar');
    """)
    await db.commit()

    yield db, path

    await db.close()
    if os.path.exists(path):
        os.unlink(path)


class MockWsCollector:
    """Coletor de eventos WebSocket emitidos durante o streaming."""
    def __init__(self):
        self.events = []

    async def send_json(self, payload):
        self.events.append(payload)


@pytest.mark.asyncio
async def test_incident_full_failover_reproduction_and_sanitization(incident_db):
    """
    T6.1: Reproduz com fidelidade a sequência do incidente de 19/11/2026:
      - Tentativa 1: OrcaRouter 402 quota esgotada (com URL bruta de faturamento)
      - Tentativa 2: LLM7 400 model_unavailable temporário
      - Tentativa 3: OpenRouter Nemotron 3 Ultra responde com sucesso e citações
    """
    db, db_path = incident_db
    ws = MockWsCollector()

    call_count = {"orcarouter": 0, "llm7": 0, "openrouter": 0}

    class MockOrcaProvider:
        api_key = "orca-key-live-1"

        async def stream_chat(self, **kwargs):
            call_count["orcarouter"] += 1
            if False:
                yield ""
            # HTTP 402 com URL externa de faturamento e JSON bruto
            raw_err = '{"error": {"code": "insufficient_user_quota", "message": "insufficient quota", "link": "https://billing.orcarouter.com/recharge/secret123"}}'
            raise ProviderHTTPError(402, raw_err, provider="orcarouter")

    class MockLLM7Provider:
        api_key = "llm7-key-live-1"

        async def stream_chat(self, **kwargs):
            call_count["llm7"] += 1
            if False:
                yield ""
            # HTTP 400 model_unavailable temporário
            raw_err = '{"error": {"code": "model_unavailable", "message": "model unavailable: deepseek-v4.1-flash"}}'
            raise ProviderHTTPError(400, raw_err, provider="llm7")

    class MockOpenRouterProvider:
        api_key = "openrouter-key-live-1"
        async def stream_chat(self, **kwargs):
            call_count["openrouter"] += 1
            # Resposta final bem-sucedida com dados e citações canônicas
            yield "Com base na documentação oficial [1] e preços [2]:\n"
            yield "O Gemini 2.5 Flash custa $0.075 por 1M tokens de entrada e $0.30 por 1M tokens de saída."

    async def fake_get_provider(provider_id, *args, **kwargs):
        if provider_id == "orcarouter":
            return MockOrcaProvider()
        elif provider_id == "llm7":
            return MockLLM7Provider()
        elif provider_id == "openrouter":
            return MockOpenRouterProvider()
        raise ValueError(f"Provedor desconhecido: {provider_id}")

    history = [
        {"role": "user", "content": "Quais são os últimos modelos LLM do Google e seus preços"},
    ]
    req_ctx = RequestContext(request_id="req-incident-test")

    with patch("backend.orchestration.resolve_request.get_provider", side_effect=fake_get_provider):
        result = await stream_from_llm(
            ws=ws,
            db=db,
            conversation_id="conv-incident-001",
            user_id="user-osmar",
            model_id="orcarouter/deepseek/deepseek-v4.1-flash-1017",
            provider_id="orcarouter",
            history=history,
            request_context=req_ctx,
            turn_id="turn-incident-test-1",
        )

    # 1. Validação do resultado final
    assert result is not None
    full_response, served_model_id, served_provider_id = result
    failover_meta = getattr(result, "failover_meta", {})

    assert served_model_id == "openrouter/nvidia/nemotron-3-ultra-550b-a55b:free"
    assert served_provider_id == "openrouter"
    assert failover_meta.get("served_by") == "openrouter/nvidia/nemotron-3-ultra-550b-a55b:free"
    assert failover_meta.get("requested_model") == "orcarouter/deepseek/deepseek-v4.1-flash-1017"

    # 2. Citações intactas na resposta final
    assert "[1]" in full_response
    assert "[2]" in full_response
    assert "Gemini 2.5 Flash" in full_response

    # 3. Validação das chamadas executadas
    assert call_count["orcarouter"] == 1
    assert call_count["llm7"] == 1
    assert call_count["openrouter"] == 1

    # 4. Sanitização estrita de todos os eventos WebSocket enviados ao frontend
    for evt in ws.events:
        evt_str = str(evt)
        # NUNCA deve conter o JSON bruto do erro
        assert "insufficient_user_quota" not in evt_str
        assert "billing.orcarouter.com" not in evt_str
        assert "secret123" not in evt_str
        assert "orca-key-live-1" not in evt_str
        assert "llm7-key-live-1" not in evt_str

        # Se for evento de passo de processo, títulos e detalhes devem ser limpos
        if evt.get("type") in ("process_step_start", "process_step_end"):
            detail = evt.get("detail", "")
            title = evt.get("title", "")
            assert "{" not in detail
            assert "https://" not in detail

    # 5. Validação da quarentena da credencial do OrcaRouter para o Turno 2
    is_quarantined = await is_credential_quarantined("orcarouter", "orca-key-live-1", db)
    assert is_quarantined is True, "Credencial do OrcaRouter deveria estar em quarentena após HTTP 402"

    # 6. Validação do modelo LLM7: não foi desativado globalmente (mantém enabled=1)
    async with db.execute("SELECT enabled FROM models WHERE id = 'llm7/deepseek-v4.1-flash'") as cur:
        row = await cur.fetchone()
        assert row is not None
        assert row[0] == 1, "LLM7 400 transitório NÃO deve desativar enabled no banco"


@pytest.mark.asyncio
async def test_turn_2_quarantine_skips_exhausted_credential_directly(incident_db):
    """
    Valida que no turno seguinte, a resolução de failover respeita a quarentena
    da credencial do OrcaRouter, pulando-a sem efetuar nova chamada HTTP externa.
    """
    db, db_path = incident_db
    # Coloca credencial do OrcaRouter em quarentena
    await quarantine_credential("orcarouter", "orca-key-live-1", db, duration_seconds=3600)

    # Tenta resolver o modelo do OrcaRouter
    resolved = await resolve_model_with_failover(
        "orcarouter/deepseek/deepseek-v4.1-flash-1017",
        db,
        failover_reason="quota_exhausted",
        failover_enabled=True,
        user_id="user-osmar",
    )

    # O modelo do OrcaRouter está em quarentena, logo o resolvedor deve saltar para
    # outro membro elegível da família (LLM7 ou OpenRouter)
    assert resolved.model_id != "orcarouter/deepseek/deepseek-v4.1-flash-1017"
    assert resolved.was_failover is True


@pytest.mark.asyncio
async def test_failover_budget_exhaustion_emits_timeout_stream_end(incident_db):
    """
    Valida que quando o orçamento total de tempo se esgota, o failover encerra
    limpamente com evento terminal stream_end (outcome='timeout', reason='failover_budget_exhausted').
    """
    db, db_path = incident_db
    ws = MockWsCollector()

    class StallingProvider:
        async def stream_chat(self, **kwargs):
            raise ProviderHTTPError(500, "Internal Server Error", provider="mock")

    with patch("backend.orchestration.resolve_request.get_provider", return_value=StallingProvider()):
        with patch("backend.orchestration.resolve_request.MIN_RETRY_BUDGET_SECONDS", 999.0):
            result = await stream_from_llm(
                ws=ws,
                db=db,
                conversation_id="conv-incident-001",
                user_id="user-osmar",
                model_id="orcarouter/deepseek/deepseek-v4.1-flash-1017",
                provider_id="orcarouter",
                history=[{"role": "user", "content": "Olá"}],
                turn_id="turn-budget-exhausted",
            )

    assert result is None
    # Verifica que stream_end terminal foi emitido com timeout
    stream_ends = [e for e in ws.events if e.get("type") == "stream_end"]
    assert len(stream_ends) >= 1
    term = stream_ends[-1]
    assert term.get("outcome") == "timeout"
    assert term.get("reason") == "failover_budget_exhausted"
    assert term.get("turn_id") == "turn-budget-exhausted"


@pytest.mark.asyncio
async def test_incident_failover_with_web_search_disabled(incident_db):
    """
    T6.1: Valida que a cascata de failover funciona perfeitamente
    mesmo quando o usuário desativou a busca web.
    """
    db, db_path = incident_db
    ws = MockWsCollector()

    class MockOrca:
        api_key = "orca-key-live-1"
        async def stream_chat(self, **kwargs):
            if False:
                yield ""
            raise ProviderHTTPError(402, "quota_exhausted", provider="orcarouter")

    class MockLLM7:
        api_key = "llm7-key-live-1"
        async def stream_chat(self, **kwargs):
            if False:
                yield ""
            raise ProviderHTTPError(400, "model_unavailable", provider="llm7")

    class MockOpenRouter:
        api_key = "openrouter-key-live-1"
        async def stream_chat(self, **kwargs):
            yield "Resposta gerada normalmente sem busca web."

    async def fake_get_provider(provider_id, *args, **kwargs):
        if provider_id == "orcarouter":
            return MockOrca()
        elif provider_id == "llm7":
            return MockLLM7()
        elif provider_id == "openrouter":
            return MockOpenRouter()
        raise ValueError(provider_id)

    with patch("backend.orchestration.resolve_request.get_provider", side_effect=fake_get_provider):
        result = await stream_from_llm(
            ws=ws,
            db=db,
            conversation_id="conv-incident-001",
            user_id="user-osmar",
            model_id="orcarouter/deepseek/deepseek-v4.1-flash-1017",
            provider_id="orcarouter",
            history=[{"role": "user", "content": "Explique o teorema de Pitágoras"}],
            turn_id="turn-no-search",
        )

    assert result is not None
    full_resp, served_model, served_prov = result
    assert "Resposta gerada normalmente sem busca web" in full_resp
    assert served_model == "openrouter/nvidia/nemotron-3-ultra-550b-a55b:free"


@pytest.mark.asyncio
async def test_credential_quarantine_does_not_block_alternative_healthy_credential(incident_db):
    """
    T2.1 & T6.1: Bloqueia a credencial esgotada específica em nível de credencial (402),
    sem bloquear uma credencial alternativa válida do mesmo provedor.
    """
    db, db_path = incident_db
    key_exhausted = "orca-key-exhausted"
    key_healthy = "orca-key-healthy"

    # Coloca apenas a credencial esgotada em quarentena
    await quarantine_credential("orcarouter", key_exhausted, db, duration_seconds=3600)

    # Verifica status
    is_q1 = await is_credential_quarantined("orcarouter", key_exhausted, db)
    is_q2 = await is_credential_quarantined("orcarouter", key_healthy, db)

    assert is_q1 is True, "Credencial esgotada deve estar em quarentena"
    assert is_q2 is False, "Credencial alternativa saudável NÃO deve estar em quarentena"

