"""Testes das Rotas REST de Bots, Rotinas, Memórias e Mascotes (F8 & F9)."""
from __future__ import annotations

import pytest
from backend.database import get_db
from backend.tests.test_proactive_pipeline import (  # noqa: F401
    _auth,
    _client_with,
    _isolation,
    seed_user_conv,
)


def _routers():
    from backend.routers.proactive import router as proactive_router

    return _client_with(proactive_router)


@pytest.mark.asyncio
async def test_pet_settings_update():
    db = await get_db()
    try:
        user_id, conv_id, _ = await seed_user_conv(db)
    finally:
        await db.close()

    client = _routers()
    headers = _auth(user_id)

    # Atualiza selected_pet para 'zed' e desativa widget
    resp = client.put(
        "/api/proactive/settings",
        json={"selected_pet": "zed", "pet_widget_enabled": False},
        headers=headers,
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["ok"] is True
    assert data["selected_pet"] == "zed"
    assert data["pet_widget_enabled"] is False

    # Leitura confirma persistência
    resp2 = client.get("/api/proactive/settings", headers=headers)
    assert resp2.status_code == 200
    assert resp2.json()["selected_pet"] == "zed"
    assert resp2.json()["pet_widget_enabled"] is False


@pytest.mark.asyncio
async def test_companion_pair_endpoint():
    db = await get_db()
    try:
        user_id, _, _ = await seed_user_conv(db)
    finally:
        await db.close()

    client = _routers()
    headers = _auth(user_id)

    resp = client.get("/api/proactive/companion/pair", headers=headers)
    assert resp.status_code == 200
    data = resp.json()
    assert data["ok"] is True
    assert "pair_code" in data
    assert "companion_url" in data
    assert data["expires_in_seconds"] == 300


@pytest.mark.asyncio
async def test_bots_crud_flow():
    db = await get_db()
    try:
        user_id, _, _ = await seed_user_conv(db)
    finally:
        await db.close()

    client = _routers()
    headers = _auth(user_id)

    # 1. Listagem inicial semeia os templates padrões
    resp = client.get("/api/proactive/bots", headers=headers)
    assert resp.status_code == 200
    bots = resp.json()["bots"]
    assert len(bots) >= 3

    # 2. Criação de um bot customizado
    create_payload = {
        "name": "Bot Financeiro",
        "title": "Cripto & Ações",
        "description": "Monitora oscilações e notícias do mercado.",
        "system_instructions": "Você é analista quantitativo sênior.",
        "color_hex": "#10B981",
        "avatar_shape": "sprout",
        "mascot_id": "neko",
        "computer_mode": "sandbox",
        "ambient_enabled": True,
        "ambient_rules": {"topics": ["bitcoin", "dolar"]},
    }
    create_resp = client.post("/api/proactive/bots", json=create_payload, headers=headers)
    assert create_resp.status_code == 200
    bot = create_resp.json()["bot"]
    bot_id = bot["id"]
    assert bot["name"] == "Bot Financeiro"

    # 3. Atualização do bot
    update_resp = client.put(
        f"/api/proactive/bots/{bot_id}",
        json={"name": "Bot Financeiro Pro", "color_hex": "#059669"},
        headers=headers,
    )
    assert update_resp.status_code == 200

    # 4. Exclusão do bot
    del_resp = client.delete(f"/api/proactive/bots/{bot_id}", headers=headers)
    assert del_resp.status_code == 200

    # 5. Excluir novamente retorna 404
    del_resp2 = client.delete(f"/api/proactive/bots/{bot_id}", headers=headers)
    assert del_resp2.status_code == 404


@pytest.mark.asyncio
async def test_routines_crud_flow():
    db = await get_db()
    try:
        user_id, _, _ = await seed_user_conv(db)
    finally:
        await db.close()

    client = _routers()
    headers = _auth(user_id)

    # Obtém bots existentes
    bots_resp = client.get("/api/proactive/bots", headers=headers)
    bot_id = bots_resp.json()["bots"][0]["id"]

    # 1. Cria rotina
    routine_payload = {
        "bot_id": bot_id,
        "name": "Varredura Matinal",
        "prompt": "Resuma as principais notícias tech",
        "timing_type": "interval",
        "timing_value": "4h",
        "is_active": True,
    }
    resp = client.post("/api/proactive/routines", json=routine_payload, headers=headers)
    assert resp.status_code == 200
    routine_id = resp.json()["routine"]["id"]

    # 2. Listagem
    list_resp = client.get("/api/proactive/routines", headers=headers)
    assert list_resp.status_code == 200
    routines = list_resp.json()["routines"]
    assert any(r["id"] == routine_id for r in routines)

    # 3. Atualização
    up_resp = client.put(
        f"/api/proactive/routines/{routine_id}",
        json={"name": "Varredura Matinal Atualizada", "timing_value": "6h"},
        headers=headers,
    )
    assert up_resp.status_code == 200

    # 4. Exclusão
    del_resp = client.delete(f"/api/proactive/routines/{routine_id}", headers=headers)
    assert del_resp.status_code == 200


@pytest.mark.asyncio
async def test_memories_flow():
    db = await get_db()
    try:
        user_id, _, _ = await seed_user_conv(db)
    finally:
        await db.close()

    client = _routers()
    headers = _auth(user_id)

    # 1. Envia sinal de tópico
    signal_payload = {
        "category": "place",
        "topic_key": "viagem toquio japao",
        "snippet": "Quero visitar Shinjuku e Akihabara na primavera",
        "weight": 1.5,
    }
    post_resp = client.post("/api/proactive/memories/signal", json=signal_payload, headers=headers)
    assert post_resp.status_code == 200
    memory = post_resp.json()["memory"]
    assert memory["topic_key"] == "place:viagem_toquio_japao"
    assert memory["signal_count"] >= 1

    # 2. Listagem de memórias
    list_resp = client.get("/api/proactive/memories", headers=headers)
    assert list_resp.status_code == 200
    mems = list_resp.json()["memories"]
    assert len(mems) >= 1
    assert any(m["topic_key"] == "place:viagem_toquio_japao" for m in mems)
