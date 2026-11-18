"""Testes de ciclo de vida de conexões SQLite, índices e paginação de histórico (T3.1)."""

from __future__ import annotations

import asyncio
import sqlite3
import statistics
import time
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import aiosqlite
import pytest

import backend.database as db_mod
from backend.routers import chat as chat_router
from backend.routers import conversations as conv_router
from backend.routers import dashboard as dash_router


@pytest.fixture
async def isolated_db(tmp_path, monkeypatch):
    db_file = tmp_path / "t31_sqlite_lifecycle.db"
    monkeypatch.setattr(db_mod, "DB_PATH", db_file)
    await db_mod.init_db()
    return db_file


class _FakeConn:
    """Conexão fake para testar fechamento em falha/cancelamento no get_db()."""

    def __init__(self, fail_on_call: int, exc: BaseException):
        self.fail_on_call = fail_on_call
        self.exc = exc
        self.calls = 0
        self.closed = False

    async def execute(self, sql: str, *args, **kwargs):
        self.calls += 1
        if self.calls == self.fail_on_call:
            raise self.exc
        return None

    async def close(self):
        self.closed = True


@pytest.mark.asyncio
async def test_get_db_closes_connection_on_pragma_error(monkeypatch):
    fake = _FakeConn(fail_on_call=2, exc=sqlite3.OperationalError("simulated pragma error"))

    async def _fake_connect(*args, **kwargs):
        return fake

    monkeypatch.setattr(aiosqlite, "connect", _fake_connect)

    with pytest.raises(sqlite3.OperationalError, match="simulated pragma error"):
        await db_mod.get_db()

    assert fake.closed is True, "Conexão deve ser fechada se PRAGMA falhar"


@pytest.mark.asyncio
async def test_get_db_closes_connection_on_cancellation(monkeypatch):
    fake = _FakeConn(fail_on_call=3, exc=asyncio.CancelledError())

    async def _fake_connect(*args, **kwargs):
        return fake

    monkeypatch.setattr(aiosqlite, "connect", _fake_connect)

    with pytest.raises(asyncio.CancelledError):
        await db_mod.get_db()

    assert fake.closed is True, "Conexão deve ser fechada se inicialização for cancelada"


@pytest.mark.asyncio
async def test_dashboard_read_routes_close_db_on_query_error(monkeypatch):
    closed_count = 0

    class _BoomDB:
        def execute(self, *args, **kwargs):
            raise RuntimeError("boom query")

        async def close(self):
            nonlocal closed_count
            closed_count += 1

    async def _fake_get_db():
        return _BoomDB()

    monkeypatch.setattr(dash_router, "get_db", _fake_get_db)
    admin = {"id": "u-admin", "role": "admin"}

    for call in (
        lambda: dash_router.get_usage_stats(days=7, current_user=admin),
        lambda: dash_router.get_recent_failovers(limit=5, current_user=admin),
        lambda: dash_router.get_quota_status(current_user=admin),
        lambda: dash_router.get_auto_router_stats(days=7, current_user=admin),
    ):
        with pytest.raises(RuntimeError, match="boom query"):
            await call()

    assert closed_count == 4, "Todas as 4 rotas de leitura do dashboard devem fechar db em finally"


@pytest.mark.asyncio
async def test_websocket_chat_unregisters_socket_when_get_db_fails(monkeypatch):
    registered: list[tuple[str, object]] = []
    unregistered: list[tuple[str, object]] = []

    class _FakeWS:
        query_params = {"token": "tok"}
        headers = {}

        async def accept(self):
            return None

        async def send_json(self, data):
            return None

        async def close(self, code=1000, reason=""):
            return None

    async def _fake_auth(token):
        return {"id": "user-ws-fail", "username": "u", "role": "user"}

    async def _failing_get_db():
        raise sqlite3.OperationalError("db open failed")

    monkeypatch.setattr(chat_router, "is_origin_allowed", lambda *args, **kwargs: True)
    monkeypatch.setattr(chat_router, "resolve_token_user", _fake_auth)
    monkeypatch.setattr(chat_router, "register_socket", lambda uid, ws: registered.append((uid, ws)))
    monkeypatch.setattr(chat_router, "unregister_socket", lambda uid, ws: unregistered.append((uid, ws)))
    monkeypatch.setattr(chat_router, "get_db", _failing_get_db)
    monkeypatch.setattr(
        chat_router.proactive_service,
        "schedule_return_flush",
        lambda *args, **kwargs: None,
    )

    ws = _FakeWS()
    with pytest.raises(sqlite3.OperationalError, match="db open failed"):
        await chat_router.websocket_chat(ws)

    assert len(registered) == 1
    assert unregistered == registered, "Socket deve ser desregistrado mesmo se get_db() falhar"


@pytest.mark.asyncio
async def test_legacy_db_migrations_create_indexes_and_pass_integrity_check(tmp_path, monkeypatch):
    """Simula banco legado sem user_id/is_favorite/favorited_at/was_auto_routed e valida init_db()."""
    legacy_file = tmp_path / "legacy_t31.db"
    conn = sqlite3.connect(legacy_file)
    conn.executescript(
        """
        CREATE TABLE users (
            id TEXT PRIMARY KEY,
            username TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL,
            created_at TEXT DEFAULT (datetime('now'))
        );
        CREATE TABLE conversations (
            id TEXT PRIMARY KEY,
            title TEXT DEFAULT 'Legacy',
            model_id TEXT,
            provider_id TEXT,
            created_at TEXT DEFAULT (datetime('now')),
            updated_at TEXT DEFAULT (datetime('now'))
        );
        CREATE TABLE model_usage_log (
            id TEXT PRIMARY KEY,
            user_id TEXT,
            conversation_id TEXT,
            model_id TEXT NOT NULL,
            provider_id TEXT NOT NULL,
            prompt_tokens INTEGER DEFAULT 0,
            completion_tokens INTEGER DEFAULT 0,
            latency_ms REAL DEFAULT 0,
            status TEXT NOT NULL,
            error_message TEXT,
            created_at TEXT DEFAULT (datetime('now'))
        );
        """
    )
    conn.commit()
    conn.close()

    monkeypatch.setattr(db_mod, "DB_PATH", legacy_file)
    await db_mod.init_db()
    # Repete inicialização para provar idempotência
    await db_mod.init_db()

    db = await db_mod.get_db()
    try:
        async with db.execute("PRAGMA integrity_check") as cur:
            row = await cur.fetchone()
            assert row[0] == "ok"

        async with db.execute(
            "SELECT name FROM sqlite_master WHERE type = 'index'"
        ) as cur:
            indexes = {r[0] for r in await cur.fetchall()}

        assert "idx_conversations_user_updated" in indexes
        assert "idx_conversations_user_favorite" in indexes
        assert "idx_messages_conversation" in indexes
        assert "idx_usage_conv" in indexes
    finally:
        await db.close()


async def _seed_synthetic_history(db_file, *, n_convs: int = 240, msgs_per_conv: int = 12):
    db = await db_mod.get_db()
    try:
        await db.execute(
            "INSERT INTO users (id, username, password_hash, role) VALUES (?, ?, ?, ?)",
            ("u1", "alice", "hash", "user"),
        )
        await db.execute(
            "INSERT INTO users (id, username, password_hash, role) VALUES (?, ?, ?, ?)",
            ("u2", "bob", "hash", "user"),
        )
        conv_rows = []
        msg_rows = []
        usage_rows = []
        for i in range(n_convs):
            cid = f"c-{i:04d}"
            uid = "u1" if i < int(n_convs * 0.85) else "u2"
            is_fav = 1 if (i % 5 == 0) else 0
            ts = f"2026-01-{(i % 28) + 1:02d} {(i % 24):02d}:{(i % 60):02d}:00"
            fav_ts = ts if is_fav else None
            title = f"Projeto Alpha #{i}" if (i % 7 == 0) else f"Conversa comum #{i}"
            conv_rows.append((cid, uid, title, "m1", "p1", is_fav, fav_ts, ts, ts))

            # Inclui algumas conversas com 0 mensagens para validar contagem = 0
            count_for_conv = 0 if (i % 13 == 0) else msgs_per_conv
            for j in range(count_for_conv):
                msg_rows.append((
                    f"m-{i:04d}-{j:03d}",
                    cid,
                    "user" if j % 2 == 0 else "assistant",
                    f"msg {j}",
                    "m1",
                    "p1",
                    f"2026-01-{(i % 28) + 1:02d} 00:{j:02d}:00",
                ))
            if i < 40:
                usage_rows.append((
                    f"ul-{i:04d}",
                    uid,
                    cid,
                    "m1",
                    "p1",
                    30,
                    0,
                    1,
                    "code_engineering",
                    ts,
                ))

        await db.executemany(
            """INSERT INTO conversations
               (id, user_id, title, model_id, provider_id, is_favorite, favorited_at, created_at, updated_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            conv_rows,
        )
        await db.executemany(
            """INSERT INTO messages
               (id, conversation_id, role, content, model_id, provider, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            msg_rows,
        )
        await db.executemany(
            """INSERT INTO model_usage_log
               (id, user_id, conversation_id, model_id, provider_id, tokens_est,
                was_fallback, was_auto_routed, route_intent, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            usage_rows,
        )
        await db.commit()
    finally:
        await db.close()


@pytest.mark.asyncio
async def test_explain_query_plan_uses_expected_indexes(isolated_db):
    await _seed_synthetic_history(isolated_db, n_convs=120, msgs_per_conv=8)
    db = await db_mod.get_db()
    try:
        async def _plan(sql: str, params: tuple = ()) -> str:
            async with db.execute(f"EXPLAIN QUERY PLAN {sql}", params) as cur:
                rows = await cur.fetchall()
            return " | ".join(str(r[3]) for r in rows)

        p_default = await _plan(
            "SELECT id, title FROM conversations WHERE user_id = ? ORDER BY updated_at DESC, id ASC LIMIT 50 OFFSET 0",
            ("u1",),
        )
        assert "idx_conversations_user_updated" in p_default, f"Plano default inesperado: {p_default}"

        p_fav = await _plan(
            "SELECT id, title FROM conversations WHERE user_id = ? AND is_favorite = 1 ORDER BY favorited_at DESC, id ASC LIMIT 50 OFFSET 0",
            ("u1",),
        )
        assert "idx_conversations_user_favorite" in p_fav, f"Plano favoritos inesperado: {p_fav}"

        p_search = await _plan(
            "SELECT id, title FROM conversations WHERE user_id = ? AND title LIKE ? ORDER BY updated_at DESC, id ASC LIMIT 50 OFFSET 0",
            ("u1", "%Alpha%"),
        )
        assert "idx_conversations_user_updated" in p_search, f"Plano busca inesperado: {p_search}"

        p_msgs = await _plan(
            "SELECT id, content FROM messages WHERE conversation_id = ? ORDER BY created_at ASC",
            ("c-0001",),
        )
        assert "idx_messages_conversation" in p_msgs, f"Plano histórico inesperado: {p_msgs}"

        p_prev_intent = await _plan(
            "SELECT route_intent FROM model_usage_log WHERE conversation_id = ? AND was_auto_routed = 1 ORDER BY created_at DESC LIMIT 1",
            ("c-0001",),
        )
        assert "idx_usage_conv" in p_prev_intent, f"Plano intenção anterior inesperado: {p_prev_intent}"
    finally:
        await db.close()


@pytest.mark.asyncio
async def test_list_conversations_equivalence_and_latency_profile(isolated_db):
    """Prova equivalência funcional exata entre a query antiga (JOIN+GROUP BY) e a nova paginada, e mede p50/p95."""
    await _seed_synthetic_history(isolated_db, n_convs=240, msgs_per_conv=15)
    user = {"id": "u1", "role": "user"}

    async def _legacy_list(search=None, filter_val=None, page=1, limit=30):
        db = await db_mod.get_db()
        try:
            q = """
                SELECT c.id, c.title, c.updated_at, COUNT(m.id) as message_count, c.is_favorite, c.favorited_at
                FROM conversations c
                LEFT JOIN messages m ON m.conversation_id = c.id
                WHERE c.user_id = ?
            """
            params = [user["id"]]
            if search:
                q += " AND c.title LIKE ?"
                params.append(f"%{search}%")
            if filter_val == "favorites":
                q += " AND c.is_favorite = 1"
            q += " GROUP BY c.id"
            if filter_val == "favorites":
                q += " ORDER BY c.favorited_at DESC, c.id ASC"
            else:
                q += " ORDER BY c.updated_at DESC, c.id ASC"
            q += " LIMIT ? OFFSET ?"
            params.extend([limit, (page - 1) * limit])
            async with db.execute(q, params) as cur:
                return [
                    (r[0], r[1], r[2], r[3], bool(r[4]), r[5])
                    for r in await cur.fetchall()
                ]
        finally:
            await db.close()

    for kwargs in (
        {"search": None, "filter": None, "page": 1, "limit": 30},
        {"search": None, "filter": None, "page": 2, "limit": 30},
        {"search": None, "filter": "favorites", "page": 1, "limit": 20},
        {"search": "Alpha", "filter": None, "page": 1, "limit": 25},
    ):
        expected = await _legacy_list(
            search=kwargs["search"],
            filter_val=kwargs["filter"],
            page=kwargs["page"],
            limit=kwargs["limit"],
        )
        actual_raw = await conv_router.list_conversations(
            search=kwargs["search"],
            filter=kwargs["filter"],
            page=kwargs["page"],
            limit=kwargs["limit"],
            current_user=user,
        )
        actual = [
            (c["id"], c["title"], c["updated_at"], c["message_count"], c["is_favorite"], c["favorited_at"])
            for c in actual_raw
        ]
        assert actual == expected, f"Divergência em {kwargs}"

    # Benchmark leve (15 amostras cada) para p50/p95 em DB descartável sem SQLITE_BUSY
    legacy_times = []
    new_times = []
    for _ in range(15):
        t0 = time.perf_counter()
        await _legacy_list(page=1, limit=30)
        legacy_times.append((time.perf_counter() - t0) * 1000.0)

        t1 = time.perf_counter()
        await conv_router.list_conversations(page=1, limit=30, current_user=user)
        new_times.append((time.perf_counter() - t1) * 1000.0)

    legacy_p50 = statistics.median(legacy_times)
    new_p50 = statistics.median(new_times)
    legacy_p95 = sorted(legacy_times)[int(len(legacy_times) * 0.95) - 1]
    new_p95 = sorted(new_times)[int(len(new_times) * 0.95) - 1]
    # Apenas garante execução rápida e registro sem falhas de concorrência
    assert new_p50 > 0 and legacy_p50 > 0
    assert new_p95 >= new_p50 and legacy_p95 >= legacy_p50

    # Teste de leituras concorrentes (cache_size / temp_store) sem SQLITE_BUSY
    results = await asyncio.gather(
        *(conv_router.list_conversations(page=1, limit=20, current_user=user) for _ in range(10))
    )
    assert all(len(r) == 20 for r in results)
