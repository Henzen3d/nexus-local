"""
backend/tests/test_failover_ttft_sqlite.py
Testes unitários para instrumentação de TTFT, configuração de timeout e otimizações SQLite (Pontos 3 e 4).
"""

import asyncio
import os
import pytest
import aiosqlite
from unittest.mock import AsyncMock, patch

from backend.orchestration.resolve_request import (
    get_failover_stream_ttft_timeout,
    DEFAULT_STREAM_TTFT_TIMEOUT_SECONDS,
    stream_from_llm,
)
from backend.database import (
    get_memory_context_metadata,
    get_db,
    init_db,
    SCHEMA,
)
from backend.context.request_context import RequestContext


@pytest.mark.asyncio
async def test_get_failover_stream_ttft_timeout():
    async with aiosqlite.connect(":memory:") as db:
        await db.execute("CREATE TABLE meta (key TEXT PRIMARY KEY, value TEXT)")
        await db.commit()

        # 1. Padrão sem env nem meta
        timeout = await get_failover_stream_ttft_timeout(db)
        assert timeout == DEFAULT_STREAM_TTFT_TIMEOUT_SECONDS

        # 2. Configurado via meta no banco
        await db.execute("INSERT INTO meta (key, value) VALUES ('stream_ttft_timeout_sec', '18.5')")
        await db.commit()
        timeout = await get_failover_stream_ttft_timeout(db)
        assert timeout == 18.5

        # 3. Env var tem precedência sobre meta
        with patch.dict(os.environ, {"FAILOVER_STREAM_TTFT_TIMEOUT_SECONDS": "12.0"}):
            timeout = await get_failover_stream_ttft_timeout(db)
            assert timeout == 12.0


@pytest.mark.asyncio
async def test_get_memory_context_metadata(tmp_path, monkeypatch):
    test_db = tmp_path / "test_memory_meta.db"
    monkeypatch.setattr("backend.database.DB_PATH", test_db)

    async with aiosqlite.connect(str(test_db)) as db:
        await db.execute("""
            CREATE TABLE conversations (
                id TEXT PRIMARY KEY,
                project_tag TEXT
            )
        """)
        await db.execute("""
            CREATE TABLE user_memory_summaries (
                id TEXT PRIMARY KEY,
                user_id TEXT NOT NULL,
                scope TEXT NOT NULL,
                scope_ref TEXT DEFAULT '',
                summary_md TEXT NOT NULL,
                updated_at TEXT DEFAULT (datetime('now'))
            )
        """)
        await db.execute("INSERT INTO conversations (id, project_tag) VALUES ('conv-1', 'meu-projeto')")
        await db.execute("""
            INSERT INTO user_memory_summaries (id, user_id, scope, scope_ref, summary_md)
            VALUES ('s1', 'u1', 'global', '', '# Global Summary')
        """)
        await db.execute("""
            INSERT INTO user_memory_summaries (id, user_id, scope, scope_ref, summary_md)
            VALUES ('s2', 'u1', 'project', 'meu-projeto', '# Project Summary')
        """)
        await db.commit()

    global_sum, proj_tag, proj_sum = await get_memory_context_metadata("u1", "conv-1")
    assert global_sum is not None
    assert global_sum["summary_md"] == "# Global Summary"
    assert proj_tag == "meu-projeto"
    assert proj_sum is not None
    assert proj_sum["summary_md"] == "# Project Summary"


@pytest.mark.asyncio
async def test_model_usage_log_conv_index():
    async with aiosqlite.connect(":memory:") as db:
        await db.executescript(SCHEMA)
        await db.commit()

        # Verifica que o índice idx_usage_conv existe
        async with db.execute(
            "SELECT name FROM sqlite_master WHERE type='index' AND name='idx_usage_conv'"
        ) as cur:
            row = await cur.fetchone()
        assert row is not None
        assert row[0] == "idx_usage_conv"

        # Verifica que a query de último route_intent da conversa usa o índice
        async with db.execute(
            "EXPLAIN QUERY PLAN SELECT route_intent FROM model_usage_log "
            "WHERE conversation_id = 'c1' AND was_auto_routed = 1 ORDER BY created_at DESC LIMIT 1"
        ) as cur:
            plan = await cur.fetchall()
        plan_str = " ".join(str(step) for step in plan)
        assert "idx_usage_conv" in plan_str


@pytest.mark.asyncio
async def test_stream_ttft_telemetry_and_failover_meta():
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
        await db.execute("INSERT INTO providers (id, name) VALUES ('p_test', 'Provider Test')")
        await db.execute("INSERT INTO models (id, name, display_name, provider_id) VALUES ('m_test', 'model-test', 'Model Test', 'p_test')")
        await db.executescript("""
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
            CREATE TABLE model_usage_log (
                id TEXT PRIMARY KEY,
                model_id TEXT,
                provider_id TEXT,
                conversation_id TEXT,
                user_id TEXT,
                was_fallback INTEGER DEFAULT 0,
                fallback_from_model_id TEXT,
                fallback_reason TEXT,
                was_auto_routed INTEGER DEFAULT 0,
                route_intent TEXT,
                route_confidence REAL,
                route_latency_ms REAL,
                route_policy TEXT,
                created_at TEXT DEFAULT (datetime('now'))
            );
            INSERT INTO user_api_keys (user_id, provider_id, api_key) VALUES ('user-ttft-1', 'p_test', 'key-123');
        """)
        await db.commit()

        class FastProvider:
            async def stream_chat(self, **kwargs):
                yield "Olá"
                yield " mundo!"

        sent_ws = []
        class MockWs:
            async def send_json(self, payload):
                sent_ws.append(payload)

        req_ctx = RequestContext(request_id="req-ttft-1")

        with patch("backend.orchestration.resolve_request.get_provider", return_value=FastProvider()):
            result = await stream_from_llm(
                ws=MockWs(),
                db=db,
                conversation_id="conv-ttft-1",
                user_id="user-ttft-1",
                model_id="m_test",
                provider_id="p_test",
                history=[{"role": "user", "content": "olá"}],
                request_context=req_ctx,
            )

        assert result is not None
        assert result[0] == "Olá mundo!"
        assert hasattr(result, "failover_meta")
        meta = result.failover_meta
        assert meta["outcome"] == "success"
        assert meta["attempt_count"] == 1
        assert "ttft_ms" in meta
        assert meta["ttft_ms"] is not None

        # Confirma que as fases de TTFT foram registradas no RequestContext
        assert "llm_ttfb" in req_ctx.phase_latencies
        assert "llm_ttft_attempt_1" in req_ctx.phase_latencies
        assert "client_ttft" in req_ctx.phase_latencies


@pytest.mark.asyncio
async def test_get_db_pragmas(tmp_path, monkeypatch):
    test_db = tmp_path / "test_pragmas.db"
    monkeypatch.setattr("backend.database.DB_PATH", test_db)

    db = await get_db()
    try:
        async with db.execute("PRAGMA foreign_keys") as cur:
            row = await cur.fetchone()
            assert row[0] == 1

        async with db.execute("PRAGMA synchronous") as cur:
            row = await cur.fetchone()
            # 1 = NORMAL
            assert row[0] == 1

        async with db.execute("PRAGMA cache_size") as cur:
            row = await cur.fetchone()
            assert row[0] == -64000

        async with db.execute("PRAGMA temp_store") as cur:
            row = await cur.fetchone()
            # 2 = MEMORY
            assert row[0] == 2
    finally:
        await db.close()
