import io
import json
import logging
import os
import tempfile
import uuid
import aiosqlite
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

import backend.database as db_mod
import backend.memory as mem_mod
import backend.orchestration.build_context as ctx_mod
import backend.orchestration.persist_turn as persist_mod
import backend.routers.conversations as conv_router
from backend.auth import create_access_token
from backend.context.request_context import RequestContext
from backend.logging_config import configure_logging, redact_sensitive_text, _SecretRedactionFilter
from backend.orchestration.ws_protocol import build_stream_end_success


@pytest.fixture
async def mem_precision_db(monkeypatch):
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    for mod in (db_mod, mem_mod, ctx_mod):
        monkeypatch.setattr(mod, "DB_PATH", path)
    await db_mod.init_db()
    monkeypatch.setattr(db_mod, "_try_embed_fact", lambda _text: None)

    async with aiosqlite.connect(path) as db:
        await db.execute(
            "INSERT INTO users (id, username, password_hash, email, role) VALUES (?, ?, ?, ?, ?)",
            ("u1", "alice", "hash", "alice@example.com", "user"),
        )
        conv_id = str(uuid.uuid4())
        await db.execute(
            "INSERT INTO conversations (id, user_id, title) VALUES (?, ?, ?)",
            (conv_id, "u1", "Preferencia Tecnica"),
        )
        await db.commit()

    yield path, conv_id

    for ext in ("", "-wal", "-shm"):
        p = path + ext
        if os.path.exists(p):
            try:
                os.remove(p)
            except OSError:
                pass


@pytest.mark.asyncio
async def test_memory_precision_excludes_40_distractors(mem_precision_db):
    _, conv_id = mem_precision_db
    # 40 memórias distratoras (cores/hobbies aleatórios)
    for idx in range(40):
        await db_mod.add_memory_fact(
            "u1",
            "personal",
            f"Cor favorita numero {idx} e tonalidade pastel {idx}",
            f"personal.color_{idx}",
            source_conv_id=conv_id,
            scope="global",
        )

    rel_id = await db_mod.add_memory_fact(
        "u1",
        "preference",
        "Prefiro respostas tecnicas sempre organizadas em tabelas comparativas",
        "pref.tables",
        source_conv_id=conv_id,
        scope="global",
    )

    # Pergunta relevante ao formato tabular -> 1/1 pertinente, 0/40 distratores
    ctx_rel = RequestContext(user_id="u1", conversation_id=conv_id)
    block, _ = await ctx_mod.build_memory_context(
        {"id": "u1"},
        conv_id,
        "Organize a comparacao em tabelas comparativas",
        True,
        "openrouter",
        "m1",
        request_context=ctx_rel,
        active_project_id=None,
    )
    used = ctx_rel.get_memo("memory_used", [])
    assert [u["id"] for u in used] == [rel_id]
    assert "tabelas comparativas" in block
    assert "Cor favorita" not in block
    assert ctx_rel.get_memo("memory_none_relevant") is False

    # Pergunta totalmente não relacionada -> 0 memórias injetadas + memory_none_relevant=True
    ctx_none = RequestContext(user_id="u1", conversation_id=conv_id)
    empty_block, _ = await ctx_mod.build_memory_context(
        {"id": "u1"},
        conv_id,
        "Que horas sao agora no aeroporto de Heathrow?",
        True,
        "openrouter",
        "m1",
        request_context=ctx_none,
        active_project_id=None,
    )
    assert ctx_none.get_memo("memory_used", []) == []
    assert ctx_none.get_memo("memory_none_relevant") is True
    assert "Cor favorita" not in empty_block
    assert "tabelas" not in empty_block


def test_memory_used_persisted_on_message_and_stream_end_and_get_conv(mem_precision_db):
    import asyncio
    path, conv_id = mem_precision_db
    used_meta = [
        {
            "id": "fact-1",
            "category": "preference",
            "fact": "Prefiro respostas curtas",
            "fact_key": "pref.short",
            "scope": "global",
            "project_id": None,
            "source_conv_id": conv_id,
            "version": 3,
        }
    ]

    # Frame terminal aceita memory_used e memory_none_relevant
    frame = build_stream_end_success(
        message_id="msg-asst-1",
        conversation_id=conv_id,
        memory_used=used_meta,
        memory_none_relevant=False,
    )
    assert frame["memory_used"][0]["version"] == 3

    async def _save():
        async with aiosqlite.connect(path) as db:
            await persist_mod.save_assistant_message(
                db,
                conv_id,
                "Resposta curta!",
                "m1",
                "openrouter",
                message_id="msg-asst-1",
                memory_used_json=json.dumps(used_meta, ensure_ascii=False),
                turn_status="completed",
            )

    asyncio.run(_save())

    app = FastAPI()
    app.include_router(conv_router.router)
    token = create_access_token("u1", "alice", "user")
    with TestClient(app) as client:
        res = client.get(f"/api/conversations/{conv_id}", headers={"Authorization": f"Bearer {token}"})
        assert res.status_code == 200
        msgs = res.json()["messages"]
        assert len(msgs) == 1
        assert msgs[0]["memory_used"][0]["id"] == "fact-1"
        assert msgs[0]["memory_used"][0]["source_conv_id"] == conv_id
        assert msgs[0]["memory_used"][0]["version"] == 3


def test_logging_redacts_api_keys_and_bearer_tokens():
    sample = "Authorization: Bearer super_secret_token_999 api_key=gsk_abcdef1234567890 other=sk-proj-secret1234567890"
    redacted = redact_sensitive_text(sample)
    assert "super_secret_token_999" not in redacted
    assert "gsk_abcdef1234567890" not in redacted
    assert "sk-proj-secret1234567890" not in redacted
    assert "***REDACTED***" in redacted

    buf = io.StringIO()
    handler = logging.StreamHandler(buf)
    handler.addFilter(_SecretRedactionFilter())
    test_logger = logging.getLogger("nexuslocal.audit_redact_test")
    test_logger.setLevel(logging.INFO)
    test_logger.propagate = False
    test_logger.addHandler(handler)
    try:
        test_logger.info("Request falhou para Bearer abcdef123456789 e AIzaSyDummySecretKey1234567890")
    finally:
        test_logger.removeHandler(handler)
    logged = buf.getvalue()
    assert "abcdef123456789" not in logged
    assert "AIzaSyDummySecretKey1234567890" not in logged
    assert "***REDACTED***" in logged
