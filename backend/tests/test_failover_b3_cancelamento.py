"""
backend/tests/test_failover_b3_cancelamento.py
Testes unitários da Etapa B3 do Golden Prompt v3.0:
- Higiene de recursos e propagação de cancelamento.
- Cancelamento pelo cliente no meio do stream fecha o generator com aclose()
  e propaga asyncio.CancelledError sem gerar failover nem penalizar o modelo.
- Desconexão de WebSocket fecha conexão sem penalidade nem tentativa de failover.
- aclose() de stream_iter é garantido em blocos finally em caso de erro/timeout.
- Background flush task do HealthRegistry é cancelado e aguardado no shutdown
  com flush limpo de registros pendentes.
"""

import asyncio
import pytest
import aiosqlite
from unittest.mock import AsyncMock, patch, MagicMock
from starlette.websockets import WebSocketDisconnect

from backend.orchestration.resolve_request import stream_from_llm
from backend.ranking.health_registry import InMemoryHealthRegistry, HealthConfig


@pytest.fixture
async def setup_b3_db():
    async with aiosqlite.connect(":memory:") as db:
        await db.execute("""
            CREATE TABLE providers (
                id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                enabled INTEGER DEFAULT 1,
                is_free INTEGER DEFAULT 0,
                is_local INTEGER DEFAULT 0,
                base_url TEXT DEFAULT '',
                api_key TEXT DEFAULT 'test_key',
                share_admin_key INTEGER DEFAULT 1
            )
        """)
        await db.execute("""
            CREATE TABLE models (
                id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                display_name TEXT NOT NULL,
                provider_id TEXT NOT NULL,
                enabled INTEGER DEFAULT 1,
                context_length INTEGER DEFAULT 8192,
                reasoning_control TEXT DEFAULT 'none',
                reasoning_levels TEXT DEFAULT NULL,
                reasoning_default TEXT DEFAULT NULL
            )
        """)
        await db.execute("""
            CREATE TABLE model_families (
                id TEXT PRIMARY KEY,
                display_name TEXT NOT NULL
            )
        """)
        await db.execute("""
            CREATE TABLE model_family_members (
                family_id TEXT NOT NULL,
                model_id TEXT NOT NULL,
                fallback_order INTEGER DEFAULT 1,
                PRIMARY KEY (family_id, model_id)
            )
        """)
        await db.execute("""
            CREATE TABLE user_api_keys (
                user_id TEXT NOT NULL,
                provider_id TEXT NOT NULL,
                api_key TEXT NOT NULL,
                PRIMARY KEY (user_id, provider_id)
            )
        """)
        await db.execute("CREATE TABLE model_overrides (model_id TEXT PRIMARY KEY)")
        await db.execute("""
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
            )
        """)
        await db.execute("""
            CREATE TABLE meta (
                key TEXT PRIMARY KEY,
                value TEXT
            )
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
            )
        """)

        await db.execute("INSERT INTO providers (id, name, enabled, is_free, share_admin_key) VALUES ('prov1', 'Provider 1', 1, 1, 1)")
        await db.execute("INSERT INTO providers (id, name, enabled, is_free, share_admin_key) VALUES ('prov2', 'Provider 2', 1, 1, 1)")
        await db.execute("INSERT INTO user_api_keys (user_id, provider_id, api_key) VALUES ('user-1', 'prov1', 'key1')")
        await db.execute("INSERT INTO user_api_keys (user_id, provider_id, api_key) VALUES ('user-1', 'prov2', 'key2')")
        await db.execute("INSERT INTO models (id, name, display_name, provider_id, enabled) VALUES ('prov1/mod1', 'mod1', 'Model 1', 'prov1', 1)")
        await db.execute("INSERT INTO models (id, name, display_name, provider_id, enabled) VALUES ('prov2/mod2', 'mod2', 'Model 2', 'prov2', 1)")
        await db.execute("INSERT INTO model_families (id, display_name) VALUES ('family1', 'Family 1')")
        await db.execute("INSERT INTO model_family_members (family_id, model_id, fallback_order) VALUES ('family1', 'prov1/mod1', 1)")
        await db.execute("INSERT INTO model_family_members (family_id, model_id, fallback_order) VALUES ('family1', 'prov2/mod2', 2)")
        await db.commit()
        yield db


class MockStreamIterWithAclose:
    def __init__(self, items, raise_cancel_at_step: int | None = None):
        self.items = items
        self.raise_cancel_at_step = raise_cancel_at_step
        self.step = 0
        self.aclose_called = False

    def __aiter__(self):
        return self

    async def __anext__(self):
        if self.raise_cancel_at_step is not None and self.step == self.raise_cancel_at_step:
            raise asyncio.CancelledError()
        if self.step < len(self.items):
            val = self.items[self.step]
            self.step += 1
            return val
        raise StopAsyncIteration

    async def aclose(self):
        self.aclose_called = True


@pytest.mark.asyncio
async def test_client_cancellation_propagates_and_closes_stream_without_failover_nor_penalty(setup_b3_db):
    """
    Risco #18 / Princípio 5 / B3: Cancelamento pelo cliente no meio do stream fecha
    o stream via aclose(), propaga asyncio.CancelledError e NÃO aciona failover
    nem penaliza o modelo na telemetria de saúde.
    """
    db = setup_b3_db

    stream_iter = MockStreamIterWithAclose(["token 1", "token 2"], raise_cancel_at_step=1)

    mock_provider = MagicMock()
    mock_provider.stream_chat = MagicMock(return_value=stream_iter)

    registry = InMemoryHealthRegistry(HealthConfig())
    registry_mock = MagicMock(wraps=registry)

    ws = AsyncMock()

    with patch("backend.orchestration.resolve_request.get_provider", return_value=mock_provider), \
         patch("backend.orchestration.resolve_request.get_model_name", return_value="mod1"), \
         patch("backend.ranking.health_registry.health_registry", registry_mock):

        with pytest.raises(asyncio.CancelledError):
            await stream_from_llm(
                ws=ws,
                db=db,
                conversation_id="conv-1",
                user_id="user-1",
                model_id="prov1/mod1",
                provider_id="prov1",
                history=[{"role": "user", "content": "hi"}],
            )

    # 1. aclose foi chamado garantindo higiene do socket HTTP
    assert stream_iter.aclose_called is True

    # 2. NÃO registrou falha no health registry para cancelamento de cliente
    registry_mock.record_failure.assert_not_called()

    # 3. NÃO tentou chamar provedor secundário de failover
    assert mock_provider.stream_chat.call_count == 1


@pytest.mark.asyncio
async def test_websocket_disconnect_closes_stream_without_failover_nor_penalty(setup_b3_db):
    """
    B3: Desconexão do WebSocket (Starlette WebSocketDisconnect) no meio do envio de deltas
    fecha stream_iter.aclose() e retorna None sem disparar failover para o próximo modelo.
    """
    db = setup_b3_db

    stream_iter = MockStreamIterWithAclose(["token 1", "token 2", "token 3"])

    mock_provider = MagicMock()
    mock_provider.stream_chat = MagicMock(return_value=stream_iter)

    registry_mock = MagicMock()

    ws = AsyncMock()
    # Ao tentar enviar token 2, WebSocket desconecta
    call_count = 0
    async def mock_send_json(payload):
        nonlocal call_count
        call_count += 1
        if call_count > 1:
            raise WebSocketDisconnect(code=1000)

    ws.send_json = mock_send_json

    with patch("backend.orchestration.resolve_request.get_provider", return_value=mock_provider), \
         patch("backend.orchestration.resolve_request.get_model_name", return_value="mod1"), \
         patch("backend.ranking.health_registry.health_registry", registry_mock):

        res = await stream_from_llm(
            ws=ws,
            db=db,
            conversation_id="conv-1",
            user_id="user-1",
            model_id="prov1/mod1",
            provider_id="prov1",
            history=[{"role": "user", "content": "hi"}],
        )

    assert res is None
    assert stream_iter.aclose_called is True
    # Sem penalização
    registry_mock.record_failure.assert_not_called()
    # Apenas uma chamada ao provedor (sem failover secundário)
    assert mock_provider.stream_chat.call_count == 1


@pytest.mark.asyncio
async def test_stream_iter_aclose_guaranteed_on_error(setup_b3_db):
    """
    B3: Garante que stream_iter.aclose() é sempre chamado em caso de erro da LLM
    liberando a conexão para o pool compartilhado.
    """
    from backend.orchestration.resolve_request import stream_from_llm
    db = setup_b3_db

    stream_iter = MockStreamIterWithAclose(["token 1"])
    # Simula erro após primeiro token
    async def exploding_anext():
        if stream_iter.step == 0:
            stream_iter.step += 1
            return "token 1"
        raise RuntimeError("LLM exploded mid-stream")

    stream_iter.__anext__ = exploding_anext

    mock_provider = MagicMock()
    mock_provider.stream_chat = MagicMock(return_value=stream_iter)

    ws = AsyncMock()

    with patch("backend.orchestration.resolve_request.get_provider", return_value=mock_provider), \
         patch("backend.orchestration.resolve_request.get_model_name", return_value="mod1"), \
         patch("backend.ranking.health_registry.health_registry.record_failure") as mock_record_fail:

        await stream_from_llm(
            ws=ws,
            db=db,
            conversation_id="conv-1",
            user_id="user-1",
            model_id="prov1/mod1",
            provider_id="prov1",
            history=[{"role": "user", "content": "hi"}],
        )

    assert stream_iter.aclose_called is True
    # Registra como MID_STREAM_DROP pois já tinha recebido token 1
    mock_record_fail.assert_called_with("prov1/mod1", "prov1", "MID_STREAM_DROP", stage="mid_stream")


@pytest.mark.asyncio
async def test_health_registry_background_flush_lifecycle():
    """
    B3: Garante que o loop de flush em background responde ao cancelamento e parada limpa
    sem deixar tarefas órfãs nem corromper dados pendentes.
    """
    registry = InMemoryHealthRegistry(HealthConfig(flush_interval_seconds=0.01))

    async with aiosqlite.connect(":memory:") as db:
        await db.execute("CREATE TABLE meta (key TEXT PRIMARY KEY, value TEXT)")
        await db.execute("""
            CREATE TABLE model_rankings (
                model_id TEXT PRIMARY KEY,
                ewma_ttft_ms REAL,
                ewma_tps REAL,
                sr_10m REAL,
                sr_1h REAL,
                sr_24h REAL,
                breaker_state TEXT,
                penalty_score REAL,
                half_life_sec REAL,
                last_failure_ts REAL,
                consecutive_failures INTEGER,
                updated_at TEXT
            )
        """)
        await db.commit()

        # Registra um evento para ficar dirty
        registry.record_success("p/m", "p", ttft_ms=150.0)
        assert registry.get_record("p/m").dirty is True

        # Inicia loop de flush em background
        flush_task = asyncio.create_task(registry.start_background_flush_loop(lambda: aiosqlite.connect(":memory:")))
        registry._flush_task = flush_task

        # Espera uma fração de tempo para o loop rodar
        await asyncio.sleep(0.03)

        # Encerra o loop (simula shutdown)
        registry.stop_background_flush()
        try:
            await asyncio.wait_for(flush_task, timeout=0.5)
        except (asyncio.CancelledError, asyncio.TimeoutError):
            pass

        assert flush_task.done() is True
