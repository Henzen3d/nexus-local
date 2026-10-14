"""Origin no handshake do WebSocket (plano 12 §6 do Intelligent UI).

Regra em ``backend/ws_origin.py``: sem Origin passa; Origin do mesmo host passa;
Origin de ``ALLOWED_ORIGINS`` passa; o resto é recusado antes do ``accept``
(o navegador recebe 403, nunca o frame ``ready``).
"""
from __future__ import annotations

import pytest

from backend.ws_origin import allowed_origins_from_env, is_origin_allowed


def test_sem_origin_passa():
    assert is_origin_allowed(None, "multi.exemplo.br", []) is True
    assert is_origin_allowed("", "multi.exemplo.br", []) is True


def test_mesmo_host_passa_com_e_sem_porta_padrao():
    assert is_origin_allowed("https://multi.exemplo.br", "multi.exemplo.br", []) is True
    assert is_origin_allowed("https://multi.exemplo.br:443", "multi.exemplo.br", []) is True
    assert is_origin_allowed("http://localhost:5173", "localhost:5173", []) is True
    assert is_origin_allowed("HTTP://LocalHost:5173", "localhost:5173", []) is True


def test_porta_diferente_nao_e_mesmo_host():
    # Dev direto no backend (Vite 5173 → ws://localhost:8000): só passa pela lista.
    assert is_origin_allowed("http://localhost:5173", "localhost:8000", []) is False
    assert is_origin_allowed("http://localhost:5173", "localhost:8000", ["http://localhost:5173"]) is True


def test_lista_allowed_origins_compara_sem_barra_final_e_sem_caixa():
    allowed = ["https://App.Exemplo.br/"]
    assert is_origin_allowed("https://app.exemplo.br", "api.exemplo.br", allowed) is True
    assert is_origin_allowed("https://app.exemplo.br.evil.tld", "api.exemplo.br", allowed) is False


def test_origin_null_ou_lixo_e_recusada():
    assert is_origin_allowed("null", "multi.exemplo.br", ["https://multi.exemplo.br"]) is False
    assert is_origin_allowed("evil", "multi.exemplo.br", []) is False
    assert is_origin_allowed("https://evil.tld", "multi.exemplo.br", ["https://multi.exemplo.br"]) is False


def test_allowed_origins_from_env(monkeypatch):
    monkeypatch.delenv("ALLOWED_ORIGINS", raising=False)
    assert allowed_origins_from_env() == ["http://localhost:5173", "http://127.0.0.1:5173"]
    monkeypatch.setenv("ALLOWED_ORIGINS", " https://a.tld/ , https://b.tld ,, ")
    assert allowed_origins_from_env() == ["https://a.tld", "https://b.tld"]


@pytest.mark.asyncio
async def test_handshake_recusa_origin_de_outro_site_e_aceita_o_proprio(monkeypatch):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from starlette.websockets import WebSocketDisconnect

    from backend.auth import create_access_token
    from backend.database import get_db, init_db
    from backend.routers import chat as chat_router

    await init_db()
    monkeypatch.delenv("ALLOWED_ORIGINS", raising=False)
    user_id = "ws-origin-user"
    db = await get_db()
    try:
        await db.execute(
            "INSERT OR IGNORE INTO users (id, username, password_hash, role) VALUES (?, ?, 'x', 'user')",
            (user_id, user_id),
        )
        await db.commit()
    finally:
        await db.close()

    token = create_access_token(user_id, user_id, "user")
    app = FastAPI()
    app.include_router(chat_router.router)
    url = f"/ws/chat?token={token}"

    with TestClient(app) as client:
        # Outro site: recusado no handshake, antes de qualquer frame.
        with pytest.raises(WebSocketDisconnect) as exc:
            with client.websocket_connect(url, headers={"Origin": "https://evil.example"}):
                pass
        assert exc.value.code == 4003

        # Mesmo host do TestClient ("testserver"): passa e recebe o ready.
        with client.websocket_connect(url, headers={"Origin": "http://testserver"}) as ws:
            assert ws.receive_json() == {"type": "ready"}

        # Sem Origin (cliente que não é navegador): passa.
        with client.websocket_connect(url) as ws:
            assert ws.receive_json() == {"type": "ready"}

    chat_router._user_sockets.clear()
