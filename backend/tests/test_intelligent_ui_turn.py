"""Intelligent UI — turno de chat com a flag desligada e ligada (plano 01, Task 4).

O LLM é substituído por um ``resolve_and_stream`` fake que devolve prosa + fence
``nexus-ui``. Com a flag **desligada** o chat tem de ser idêntico ao de antes do
recurso: texto persistido intacto (fence incluído), nenhuma linha em
``message_ui_blocks`` e ``stream_end`` sem ``ui_blocks``. Com a flag **ligada**
o fence sai de ``messages.content``, o envelope é gravado com ``source='model'``
e vai no ``stream_end``; a releitura da conversa devolve o mesmo envelope.

Também cobre: catálogo só com flag ligada + heurístico (e nunca em modo voz),
``GET/POST /api/intelligent-ui/config`` (POST só admin) e a lista de hosts do
painel chegando ao filtro de imagem do turno.
"""
from __future__ import annotations

import asyncio
import time
import uuid

import pytest

from backend.database import get_db, init_db
from backend.routers import chat as chat_router
from backend.routers import intelligent_ui as iui_router
from backend.ui_blocks.config import update_intelligent_ui_config

PROSE = "Sete de dez verificações já foram concluídas."
FENCE = (
    "```nexus-ui\n"
    '{"v":1,"blocks":[{"id":"seo","type":"progress","label":"Auditoria SEO","value":7,"max":10},'
    '{"id":"foto","type":"card","title":"Placa","image":{"url":"https://img.casa.lan/esp32.jpg","alt":"ESP32"}}]}\n'
    "```"
)
MODEL_REPLY = f"{PROSE}\n\n{FENCE}"


@pytest.fixture
async def turn_env(monkeypatch):
    await init_db()
    chat_router._user_sockets.clear()
    for name in ("INTELLIGENT_UI_ENABLED", "INTELLIGENT_UI_IMAGE_HOSTS", "INTELLIGENT_UI_ALLOW_PRIVATE_HTTP"):
        monkeypatch.delenv(name, raising=False)

    db = await get_db()
    try:
        # Tabela singleton zerada: o estado efetivo vem do .env (ou do que o teste salvar)
        await db.execute("DELETE FROM intelligent_ui_config")
        await db.commit()
        user_id = f"u-{uuid.uuid4()}"
        admin_id = f"a-{uuid.uuid4()}"
        await db.execute(
            "INSERT INTO users (id, username, password_hash, role) VALUES (?, ?, 'x', 'user')", (user_id, user_id)
        )
        await db.execute(
            "INSERT INTO users (id, username, password_hash, role) VALUES (?, ?, 'x', 'admin')", (admin_id, admin_id)
        )
        await db.commit()
    finally:
        await db.close()

    captured: dict = {}

    async def fake_resolve_and_stream(ws, db_, conversation_id, uid, model_id, provider_id, history, *args, **kwargs):
        captured["system_prompt"] = history[0]["content"] if history and history[0].get("role") == "system" else ""
        await ws.send_json({"type": "stream_start", "conversation_id": conversation_id})
        await ws.send_json({"type": "token", "content": MODEL_REPLY})
        return MODEL_REPLY, None, model_id, provider_id

    monkeypatch.setattr(chat_router, "resolve_and_stream", fake_resolve_and_stream)

    yield {"user_id": user_id, "admin_id": admin_id, "captured": captured}

    chat_router._user_sockets.clear()


def _collect_until(ws, wanted: str, limit: int = 40) -> list[dict]:
    frames: list[dict] = []
    for _ in range(limit):
        frame = ws.receive_json()
        frames.append(frame)
        if frame.get("type") == wanted:
            return frames
    raise AssertionError(f"frame {wanted!r} não chegou; recebidos: {[f.get('type') for f in frames]}")


def _run_turn(user_id: str, message: str, *, voice_mode: bool = False) -> dict:
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    from backend.auth import create_access_token

    token = create_access_token(user_id, user_id, "user")
    app = FastAPI()
    app.include_router(chat_router.router)
    with TestClient(app) as client:
        with client.websocket_connect(f"/ws/chat?token={token}") as ws:
            assert ws.receive_json() == {"type": "ready"}
            payload = {
                "conversation_id": None,
                "message": message,
                "model_id": "m/x",
                "provider_id": "p",
                "use_memory": False,
                "fusion": False,
            }
            if voice_mode:
                payload["voice_mode"] = True
            ws.send_json(payload)
            frames = _collect_until(ws, "stream_end")
        time.sleep(0.2)
    return {"conversation_id": frames[0]["conversation_id"], "stream_end": frames[-1]}


async def _assistant_row(conversation_id: str):
    db = await get_db()
    try:
        async with db.execute(
            "SELECT id, content FROM messages WHERE conversation_id = ? AND role = 'assistant' ORDER BY created_at, rowid",
            (conversation_id,),
        ) as cur:
            rows = await cur.fetchall()
        assert len(rows) == 1
        msg_id, content = rows[0]
        async with db.execute(
            "SELECT payload, source FROM message_ui_blocks WHERE message_id = ?", (msg_id,)
        ) as cur:
            ui_row = await cur.fetchone()
        return msg_id, content, ui_row
    finally:
        await db.close()


def test_flag_desligada_turno_identico_ao_chat_sem_o_recurso(turn_env):
    result = _run_turn(turn_env["user_id"], "compare os custos dos modelos")
    end = result["stream_end"]
    assert "ui_blocks" not in end

    msg_id, content, ui_row = asyncio.get_event_loop().run_until_complete(_assistant_row(result["conversation_id"]))
    assert content == MODEL_REPLY  # fence permanece no texto, como antes do recurso
    assert ui_row is None
    # Catálogo não foi oferecido, mesmo com a frase casando no heurístico
    assert "nexus-ui" not in turn_env["captured"]["system_prompt"]


def test_flag_ligada_extrai_grava_e_devolve_no_stream_end(turn_env, monkeypatch):
    monkeypatch.setenv("INTELLIGENT_UI_ENABLED", "true")
    result = _run_turn(turn_env["user_id"], "compare os custos dos modelos")
    end = result["stream_end"]

    assert end.get("ui_blocks") and end["ui_blocks"]["v"] == 1
    ids = [b["id"] for b in end["ui_blocks"]["blocks"]]
    assert ids == ["seo", "foto"]
    # Host não confiável (sem lista): a imagem sai, o cartão fica
    card = end["ui_blocks"]["blocks"][1]
    assert card["type"] == "card" and "image" not in card

    msg_id, content, ui_row = asyncio.get_event_loop().run_until_complete(_assistant_row(result["conversation_id"]))
    assert content == PROSE
    assert "nexus-ui" not in content and "{" not in content
    assert ui_row is not None and ui_row[1] == "model"
    assert '"id": "seo"' in ui_row[0] or '"id":"seo"' in ui_row[0]

    # Catálogo oferecido (flag + heurístico)
    assert "nexus-ui" in turn_env["captured"]["system_prompt"]
    assert "chart: kind" in turn_env["captured"]["system_prompt"]
    assert "follow_up: items" in turn_env["captured"]["system_prompt"]
    assert "controls: title" not in turn_env["captured"]["system_prompt"]

    # Releitura da conversa devolve o envelope junto da mensagem
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    from backend.auth import create_access_token
    from backend.routers.conversations import router as conv_router

    app = FastAPI()
    app.include_router(conv_router)
    token = create_access_token(turn_env["user_id"], turn_env["user_id"], "user")
    with TestClient(app) as client:
        r = client.get(f"/api/conversations/{result['conversation_id']}", headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 200, r.text
    assistant = [m for m in r.json()["messages"] if m["role"] == "assistant"]
    assert assistant and assistant[0]["ui_blocks"]["blocks"][0]["id"] == "seo"
    assert assistant[0]["content"] == PROSE


def test_flag_ligada_nao_oferece_catalogo_em_modo_voz_nem_sem_gatilho(turn_env, monkeypatch):
    monkeypatch.setenv("INTELLIGENT_UI_ENABLED", "true")
    _run_turn(turn_env["user_id"], "compare os custos dos modelos", voice_mode=True)
    assert "nexus-ui" not in turn_env["captured"]["system_prompt"]

    _run_turn(turn_env["user_id"], "bom dia, tudo bem?")
    assert "nexus-ui" not in turn_env["captured"]["system_prompt"]


def test_painel_manda_sobre_env_e_lista_de_hosts_chega_ao_filtro(turn_env, monkeypatch):
    # .env desligado, painel liga e confia em img.casa.lan
    async def _save():
        db = await get_db()
        try:
            await update_intelligent_ui_config(db, {"enabled": True, "image_hosts": "img.casa.lan"})
        finally:
            await db.close()

    asyncio.get_event_loop().run_until_complete(_save())
    result = _run_turn(turn_env["user_id"], "compare os custos dos modelos")
    end = result["stream_end"]
    assert end.get("ui_blocks")
    card = end["ui_blocks"]["blocks"][1]
    assert card["image"]["url"] == "https://img.casa.lan/esp32.jpg"


def test_endpoint_config_get_para_usuario_e_post_so_admin(turn_env):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    from backend.auth import create_access_token

    app = FastAPI()
    app.include_router(iui_router.router)
    user_tok = create_access_token(turn_env["user_id"], turn_env["user_id"], "user")
    admin_tok = create_access_token(turn_env["admin_id"], turn_env["admin_id"], "admin")

    with TestClient(app) as client:
        r = client.get("/api/intelligent-ui/config", headers={"Authorization": f"Bearer {user_tok}"})
        assert r.status_code == 200
        assert r.json()["enabled"] is False and r.json()["image_hosts"] == []

        r = client.post(
            "/api/intelligent-ui/config",
            json={"enabled": True, "image_hosts": "https://CDN.Exemplo.com/x, img.casa.lan"},
            headers={"Authorization": f"Bearer {user_tok}"},
        )
        assert r.status_code in (401, 403)

        r = client.post(
            "/api/intelligent-ui/config",
            json={"enabled": True, "image_hosts": "https://CDN.Exemplo.com/x, img.casa.lan"},
            headers={"Authorization": f"Bearer {admin_tok}"},
        )
        assert r.status_code == 200, r.text
        cfg = r.json()["config"]
        assert cfg["enabled"] is True and cfg["image_hosts"] == ["cdn.exemplo.com", "img.casa.lan"] and cfg["source"] == "db"

        r = client.get("/api/intelligent-ui/config", headers={"Authorization": f"Bearer {user_tok}"})
        assert r.json()["enabled"] is True and r.json()["allow_private_http"] is False


def test_telemetria_conta_oferta_producao_validade_e_descartes(turn_env, monkeypatch):
    from backend.ui_blocks.telemetry import intelligent_ui_telemetry

    intelligent_ui_telemetry.reset()
    monkeypatch.setenv("INTELLIGENT_UI_ENABLED", "true")

    # Turno 1: oferta + fence válido (2 blocos: um fica, a imagem do card sai mas o card fica)
    _run_turn(turn_env["user_id"], "compare os custos dos modelos")
    # Turno 2: sem gatilho (não oferecido), modelo manda fence mesmo assim
    _run_turn(turn_env["user_id"], "bom dia, tudo bem?")

    snap = intelligent_ui_telemetry.snapshot()
    assert snap["turns"] == 2
    assert snap["offered"] == 1
    assert snap["produced"] == 2
    assert snap["produced_without_offer"] == 1
    assert snap["valid"] == 2
    assert snap["blocks_in"] == 4 and snap["blocks_out"] == 4
    assert snap["discarded"] == {"no_fence": 0, "invalid_json": 0, "rejected_envelope": 0, "empty_after_validation": 0}
    assert snap["block_types"] == {"progress": 2, "card": 2}
    assert snap["rates"]["produced_given_offered"] == 1.0

    # Endpoint só para admin
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    from backend.auth import create_access_token

    app = FastAPI()
    app.include_router(iui_router.router)
    with TestClient(app) as client:
        user_tok = create_access_token(turn_env["user_id"], turn_env["user_id"], "user")
        admin_tok = create_access_token(turn_env["admin_id"], turn_env["admin_id"], "admin")
        assert client.get("/api/intelligent-ui/stats", headers={"Authorization": f"Bearer {user_tok}"}).status_code in (401, 403)
        r = client.get("/api/intelligent-ui/stats", headers={"Authorization": f"Bearer {admin_tok}"})
        assert r.status_code == 200 and r.json()["turns"] == 2
