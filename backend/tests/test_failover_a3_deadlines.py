"""
backend/tests/test_failover_a3_deadlines.py
Testes unitários da Etapa A3 do Golden Prompt v3.0:
- Orçamento de tempo total único (padrão 45s, configurável via meta/env).
- Deadlines distintos (TTFT clamped ao orçamento restante).
- Cascata lenta com relógio controlado: 4 candidatos lentos não excedem o orçamento
  total e emitem um único erro terminal claro ("Tempo limite de resposta esgotado após tentativas de failover.").
"""

import asyncio
import time
import pytest
import aiosqlite
from unittest.mock import AsyncMock, patch

from backend.orchestration.resolve_request import (
    stream_from_llm,
    get_failover_total_budget,
    DEFAULT_FAILOVER_TOTAL_BUDGET_SECONDS,
    MIN_RETRY_BUDGET_SECONDS,
)


@pytest.fixture
async def setup_a3_db():
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
            CREATE TABLE meta (
                key TEXT PRIMARY KEY,
                value TEXT
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
                route_policy TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

        # Configura 4 provedores e 4 modelos da mesma família
        await db.execute("INSERT INTO providers (id, name, enabled) VALUES ('p1', 'Prov 1', 1)")
        await db.execute("INSERT INTO providers (id, name, enabled) VALUES ('p2', 'Prov 2', 1)")
        await db.execute("INSERT INTO providers (id, name, enabled) VALUES ('p3', 'Prov 3', 1)")
        await db.execute("INSERT INTO providers (id, name, enabled) VALUES ('p4', 'Prov 4', 1)")

        for i in range(1, 5):
            mid = f"m{i}"
            pid = f"p{i}"
            await db.execute(
                "INSERT INTO models (id, name, display_name, provider_id, enabled) VALUES (?, ?, ?, ?, 1)",
                (mid, f"name_{mid}", f"Display {mid}", pid),
            )
            await db.execute(
                "INSERT INTO user_api_keys (user_id, provider_id, api_key) VALUES ('user_a3', ?, 'sk-test')",
                (pid,),
            )

        await db.execute("INSERT INTO model_families (id, display_name) VALUES ('slow_fam', 'Slow Family')")
        for i in range(1, 5):
            await db.execute(
                "INSERT INTO model_family_members (family_id, model_id, fallback_order) VALUES ('slow_fam', ?, ?)",
                (f"m{i}", i),
            )

        await db.commit()
        yield db


@pytest.mark.asyncio
async def test_get_failover_total_budget(setup_a3_db):
    db = setup_a3_db
    # Padrão
    budget = await get_failover_total_budget(db)
    assert budget == DEFAULT_FAILOVER_TOTAL_BUDGET_SECONDS

    # Via tabela meta
    await db.execute("INSERT INTO meta (key, value) VALUES ('failover_total_budget_sec', '30.0')")
    await db.commit()
    budget = await get_failover_total_budget(db)
    assert budget == 30.0

    # Via variável de ambiente (precedência sobre meta)
    with patch.dict("os.environ", {"FAILOVER_TOTAL_BUDGET_SECONDS": "20.5"}):
        budget = await get_failover_total_budget(db)
        assert budget == 20.5


@pytest.mark.asyncio
async def test_controlled_clock_stops_four_slow_candidates_at_budget(setup_a3_db):
    """
    Risco #12 / A3: 4 candidatos lentos com relógio controlado.
    Garante que não excede o orçamento total e emite exatamente um único erro terminal.
    """
    db = setup_a3_db
    mock_ws = AsyncMock()

    # Define orçamento total de 12 segundos
    await db.execute("INSERT OR REPLACE INTO meta (key, value) VALUES ('failover_total_budget_sec', '12.0')")
    await db.commit()

    # Relógio virtual simulado
    current_virtual_time = 100.0

    def virtual_monotonic():
        return current_virtual_time

    # Provedor lento que consome 4.0s virtuais e gera 0 tokens
    class SlowEmptyProvider:
        async def stream_chat(self, **kwargs):
            nonlocal current_virtual_time
            # Avança 4 segundos virtuais em cada chamada
            current_virtual_time += 4.0
            if False:
                yield "never"

    async def mock_get_provider(pid, database, user_id=None):
        return SlowEmptyProvider()

    with patch("time.monotonic", side_effect=virtual_monotonic), \
         patch("backend.orchestration.resolve_request.get_provider", side_effect=mock_get_provider):

        res = await stream_from_llm(
            ws=mock_ws,
            db=db,
            conversation_id="conv_a3_budget",
            user_id="user_a3",
            model_id="m1",
            provider_id="p1",
            history=[{"role": "user", "content": "teste de timeout"}],
        )

        assert res is None, "A chamada deveria retornar None após estourar orçamento."

        # Verifica chamadas enviadas pelo WebSocket
        sent_messages = [call.args[0] for call in mock_ws.send_json.call_args_list]
        error_messages = [m for m in sent_messages if m.get("type") == "error"]

        # Deve haver exatamente UM erro terminal
        assert len(error_messages) == 1, f"Deveria haver exatamente 1 erro terminal, mas houve: {error_messages}"
        assert "Tempo limite de resposta esgotado após tentativas de failover." in error_messages[0]["message"]

        # O tempo virtual decorrido total deve ter sido respeitado
        total_elapsed = current_virtual_time - 100.0
        # 12.0s de orçamento:
        # Tentativa 1: avança para 104.0 (+4s), elapsed=4s, remaining=8s >= 3s.
        # Tentativa 2: avança para 108.0 (+4s), elapsed=8s, remaining=4s >= 3s.
        # Tentativa 3: avança para 112.0 (+4s), elapsed=12s, remaining=0s < 3s -> para!
        # Candidato 4 nem foi tentado.
        assert total_elapsed <= 12.0 + 1.0


@pytest.mark.asyncio
async def test_ttft_timeout_stops_early_when_budget_depleted(setup_a3_db):
    """
    Testa estouro de orçamento provocado por TTFT Timeout precoce.
    """
    db = setup_a3_db
    mock_ws = AsyncMock()

    await db.execute("INSERT OR REPLACE INTO meta (key, value) VALUES ('failover_total_budget_sec', '10.0')")
    await db.commit()

    current_virtual_time = 50.0

    def virtual_monotonic():
        return current_virtual_time

    class TimeoutProvider:
        def stream_chat(self, **kwargs):
            class TimeoutStream:
                def __aiter__(self):
                    return self
                async def __anext__(self):
                    nonlocal current_virtual_time
                    current_virtual_time += 4.5
                    raise asyncio.TimeoutError()
                async def aclose(self):
                    pass
            return TimeoutStream()

    async def mock_get_provider(pid, database, user_id=None):
        return TimeoutProvider()

    with patch("time.monotonic", side_effect=virtual_monotonic), \
         patch("backend.orchestration.resolve_request.get_provider", side_effect=mock_get_provider):

        res = await stream_from_llm(
            ws=mock_ws,
            db=db,
            conversation_id="conv_a3_ttft",
            user_id="user_a3",
            model_id="m1",
            provider_id="p1",
            history=[{"role": "user", "content": "teste ttft"}],
        )

        assert res is None
        sent_messages = [call.args[0] for call in mock_ws.send_json.call_args_list]
        error_messages = [m for m in sent_messages if m.get("type") == "error"]

        assert len(error_messages) == 1
        assert "Tempo limite de resposta esgotado após tentativas de failover." in error_messages[0]["message"]
