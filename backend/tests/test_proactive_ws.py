"""F2.8.5 — integração WebSocket: turno normal + pipeline proativo fake.

O cliente recebe ``proactive_insight`` **depois** do ``stream_end`` (nunca
antes), a mensagem ``presence`` é honrada (bolha inline na conversa ativa) e
``ping``/``pong`` continuam funcionando. O LLM do turno é substituído por um
``resolve_and_stream`` fake; detector/pesquisa/síntese usam os mesmos fakes do
``test_proactive_pipeline``.
"""
from __future__ import annotations

import asyncio
import json
import time
import uuid

import pytest

from backend.database import get_db, init_db
from backend.proactive import config as pconfig
from backend.proactive import presence, researcher, service, synthesizer
from backend.routers import chat as chat_router
from backend.tests.test_proactive_pipeline import (
    SOURCES_RAW,
    USER_MESSAGE,
    FakeLLM,
    fake_fetch,
)


@pytest.fixture
async def ws_env(monkeypatch):
    await init_db()
    pconfig.invalidate_config_cache()
    presence.reset()
    service.reset_runtime_state()
    chat_router._user_sockets.clear()

    db = await get_db()
    try:
        user_id = f"u-{uuid.uuid4()}"
        await db.execute(
            "INSERT INTO users (id, username, password_hash, role) VALUES (?, ?, 'x', 'user')", (user_id, user_id)
        )
        await db.commit()
        await pconfig.upsert_user_settings(db, user_id, enabled=True)
    finally:
        await db.close()

    llm = FakeLLM()

    async def _detector(db_, uid, prov, model):
        return llm, "fake-detector", "override"

    async def _synth(db_, uid, prov, model, cfg):
        return llm, "fake-synth", "override"

    async def _label(db_, source, model_name, conv_model_id):
        return "fake/fake-synth"

    async def _search(query, db_):
        await asyncio.sleep(0.4)  # dá tempo de o cliente enviar a presença da conversa criada
        return list(SOURCES_RAW)

    real_research = researcher.research

    async def _research(signal, db_, **kw):
        kw["search_fn"] = _search
        kw["fetch_fn"] = fake_fetch
        kw["use_cache"] = False
        return await real_research(signal, db_, **kw)

    async def fake_resolve_and_stream(ws, db_, conversation_id, uid, model_id, provider_id, history, *args, **kwargs):
        await ws.send_json({"type": "stream_start", "conversation_id": conversation_id})
        await ws.send_json({"type": "token", "content": "Que legal, "})
        await ws.send_json({"type": "token", "content": "aproveite o show!"})
        return "Que legal, aproveite o show!", None, model_id, provider_id

    monkeypatch.setattr(service, "resolve_detector_model", _detector)
    monkeypatch.setattr(synthesizer, "resolve_synth_model", _synth)
    monkeypatch.setattr(synthesizer, "model_label", _label)
    monkeypatch.setattr(researcher, "research", _research)
    monkeypatch.setattr(chat_router, "resolve_and_stream", fake_resolve_and_stream)

    yield {"user_id": user_id, "llm": llm}

    presence.reset()
    service.reset_runtime_state()
    chat_router._user_sockets.clear()


def _collect_until(ws, wanted: str, limit: int = 40) -> list[dict]:
    frames: list[dict] = []
    for _ in range(limit):
        frame = ws.receive_json()
        frames.append(frame)
        if frame.get("type") == wanted:
            return frames
    raise AssertionError(f"frame {wanted!r} não chegou; recebidos: {[f.get('type') for f in frames]}")


def test_ws_turn_then_proactive_insight_after_stream_end(ws_env):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    from backend.auth import create_access_token

    user_id = ws_env["user_id"]
    token = create_access_token(user_id, user_id, "user")
    app = FastAPI()
    app.include_router(chat_router.router)

    with TestClient(app) as client:
        with client.websocket_connect(f"/ws/chat?token={token}") as ws:
            assert ws.receive_json() == {"type": "ready"}

            # Heartbeat e presença inicial (tela de chat novo)
            ws.send_json({"type": "ping"})
            assert ws.receive_json() == {"type": "pong"}
            ws.send_json({"type": "presence", "state": "active", "conversation_id": None, "view": "chat"})

            ws.send_json({
                "conversation_id": None,
                "message": USER_MESSAGE,
                "model_id": "m/x",
                "provider_id": "p",
                "use_memory": False,
                "fusion": False,
            })
            frames = _collect_until(ws, "stream_end")
            types = [f["type"] for f in frames]
            assert "proactive_insight" not in types and "proactive_status" not in types
            assert types[0] == "conversation_created" and "stream_start" in types and "token" in types
            conv_id = frames[0]["conversation_id"]
            assert frames[-1]["conversation_id"] == conv_id

            # Cliente passa a estar "na conversa" (F2.7.4) ⇒ entrega inline
            ws.send_json({"type": "presence", "state": "active", "conversation_id": conv_id, "view": "chat"})

            after = _collect_until(ws, "proactive_insight")
            after_types = [f["type"] for f in after]
            assert after_types[:2] == ["proactive_status", "proactive_status"]
            assert [f["stage"] for f in after[:2]] == ["researching", "synthesizing"]
            insight_frame = after[-1]
            assert insight_frame["channel_hint"] == "inline"
            insight = insight_frame["insight"]
            assert insight["conversation_id"] == conv_id and insight["message_id"]
            assert insight["sources"] and insight["follow_ups"] and insight["expires_at"]
        time.sleep(0.2)  # deixa o handler fechar a conexão do banco antes de derrubar o loop do TestClient

    # Persistência: bolha proativa depois da resposta normal, com fontes/motivo no GET
    async def _check():
        db = await get_db()
        try:
            async with db.execute(
                "SELECT role, kind, content FROM messages WHERE conversation_id = ? ORDER BY created_at, rowid",
                (conv_id,),
            ) as cur:
                rows = await cur.fetchall()
            assert [(r[0], r[1]) for r in rows] == [("user", "normal"), ("assistant", "normal"), ("assistant", "proactive")]
            assert rows[2][2].startswith("Fiquei curioso com **")
            async with db.execute(
                "SELECT status, channel, delivered_message_id FROM proactive_insights WHERE conversation_id = ?",
                (conv_id,),
            ) as cur:
                status, channel, delivered = await cur.fetchone()
            assert status == "delivered" and channel == "inline" and delivered == insight["message_id"]
        finally:
            await db.close()

    asyncio.get_event_loop().run_until_complete(_check())
    # Socket fechado ⇒ presença/registro limpos
    assert presence.snapshot(user_id) == []
    assert user_id not in chat_router._user_sockets


def test_ws_presence_frame_is_ignored_when_malformed(ws_env):
    """Campos inválidos não derrubam o socket nem alteram o estado."""
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    from backend.auth import create_access_token

    user_id = ws_env["user_id"]
    token = create_access_token(user_id, user_id, "user")
    app = FastAPI()
    app.include_router(chat_router.router)
    with TestClient(app) as client:
        with client.websocket_connect(f"/ws/chat?token={token}") as ws:
            assert ws.receive_json() == {"type": "ready"}
            ws.send_json({"type": "presence", "state": 42, "conversation_id": {"x": 1}, "view": ["chat"]})
            ws.send_json({"type": "presence", "state": "hidden", "conversation_id": "c-1", "view": "chat"})
            ws.send_json({"type": "ping"})
            assert ws.receive_json() == {"type": "pong"}
            snap = presence.snapshot(user_id)
            assert len(snap) == 1 and snap[0].state == "hidden" and snap[0].conversation_id == "c-1"
            assert not presence.has_active_socket(user_id)
            ws.send_text("isso não é json")
            assert ws.receive_json()["type"] == "error"
            assert json.dumps(snap[0].to_dict())  # serializável
        time.sleep(0.2)
