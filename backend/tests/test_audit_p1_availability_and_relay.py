import os
import tempfile
import uuid
import aiosqlite
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

import backend.database as db_mod
import backend.routers.admin as admin_router
import backend.routers.conversations as conv_router
import backend.orchestration.handle_attachments as ha_mod
from backend.auth import create_access_token
from backend.context.request_context import RequestContext


@pytest.fixture
async def avail_db(monkeypatch):
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    monkeypatch.setattr(db_mod, "DB_PATH", path)
    await db_mod.init_db()

    async with aiosqlite.connect(path) as db:
        await db.execute(
            "INSERT INTO users (id, username, password_hash, email, role) VALUES (?, ?, ?, ?, ?)",
            ("u1", "admin", "hash", "admin@example.com", "admin"),
        )
        await db.commit()
    yield path
    for ext in ("", "-wal", "-shm"):
        p = path + ext
        if os.path.exists(p):
            try:
                os.remove(p)
            except OSError:
                pass


@pytest.mark.asyncio
async def test_openrouter_sync_records_structured_delta_and_exclusions(avail_db, monkeypatch):
    async def _fake_fetch_openrouter(api_key: str, *, stats_out: dict | None = None):
        if stats_out is not None:
            stats_out.update({
                "remote_total": 100,
                "chat_eligible_count": 2,
                "excluded_non_chat": 18,
                "free_count": 1,
                "paid_count": 1,
            })
        return [
            {
                "model_name": "google/gemini-free:free",
                "display_name": "Gemini Free",
                "context_length": 128000,
                "supports_vision": True,
                "confirmed_free": True,
            },
            {
                "model_name": "anthropic/claude-paid",
                "display_name": "Claude Paid",
                "context_length": 200000,
                "supports_vision": True,
                "confirmed_free": False,
            },
        ]

    monkeypatch.setattr(admin_router.ModelFetcher, "fetch_openrouter", staticmethod(_fake_fetch_openrouter))

    async with aiosqlite.connect(avail_db) as db:
        # Modelo legado que foi removido do remoto deve entrar na contagem removed_from_remote
        await db.execute(
            """INSERT INTO models (id, provider_id, name, display_name, context_length, enabled, confirmed_free)
               VALUES ('openrouter/legacy-removed:free', 'openrouter', 'legacy-removed:free', 'Legacy', 8192, 1, 1)"""
        )
        await db.execute(
            "INSERT OR IGNORE INTO providers (id, name, base_url, api_key, enabled, is_free) VALUES ('openrouter', 'OpenRouter', 'https://openrouter.ai/api/v1', 'sk-test', 1, 1)"
        )
        await db.commit()

        res = await admin_router.sync_provider_models("openrouter", db, custom_api_key="sk-test", recompute_scores=False)

    assert res["errors"] == []
    report = res["sync_report"]
    assert report["remote_total"] == 100
    assert report["chat_eligible_count"] == 2
    assert report["excluded"]["non_chat_endpoint"] == 18
    assert report["excluded"]["paid_or_not_free"] == 1
    assert report["excluded"]["removed_from_remote"] >= 1
    assert report["active_enabled_count"] >= 1

    # GET /admin/providers expõe last_sync_report estruturado
    app = FastAPI()
    app.include_router(admin_router.router)
    token = create_access_token("u1", "admin", "admin")
    with TestClient(app) as client:
        resp = client.get("/api/admin/providers", headers={"Authorization": f"Bearer {token}"})
        assert resp.status_code == 200
        openrouter_entry = next(p for p in resp.json() if p["id"] == "openrouter")
        assert openrouter_entry["last_sync_report"]["remote_total"] == 100


@pytest.mark.asyncio
async def test_load_history_propagates_relay_status_direct_relay_and_placeholder(avail_db, monkeypatch):
    conv_id = str(uuid.uuid4())
    user_msg_id = str(uuid.uuid4())
    att_id = f"att_{uuid.uuid4().hex}"
    async with aiosqlite.connect(avail_db) as db:
        await db.execute("INSERT INTO conversations (id, user_id, title) VALUES (?, ?, ?)", (conv_id, "u1", "Imagem"))
        await db.execute("INSERT INTO messages (id, conversation_id, role, content) VALUES (?, ?, 'user', ?)", (user_msg_id, conv_id, "Veja esta imagem"))
        await db.commit()

        msg_atts = {
            user_msg_id: [
                {
                    "id": att_id,
                    "filename": "foto.png",
                    "mime_type": "image/png",
                    "file_type": "image",
                    "storage_path": f"{conv_id}/{att_id}_foto.png",
                    "file_hash": "hash123",
                }
            ]
        }

        # Caso 1: Relay indisponível -> placeholder_only registrado no RequestContext
        async def _relay_down(*args, **kwargs):
            raise RuntimeError("relay unavailable")

        monkeypatch.setattr("backend.vision_relay.relay.describe_image_via_relay", _relay_down)
        ctx_ph = RequestContext(user_id="u1", conversation_id=conv_id)
        _, relay_used_ph, relay_model_ph = await ha_mod.load_history(
            db, conv_id, user_msg_id, msg_atts, {}, False, False, [], "", None, None, "u1",
            request_context=ctx_ph,
        )
        assert relay_used_ph == 0
        assert relay_model_ph is None
        assert ctx_ph.get_memo("relay_status") == "placeholder_only"

        # Caso 2: Relay bem-sucedido -> relay_used=1, relay_model_id e relay_status='relay'
        async def _relay_ok(*args, **kwargs):
            return {"description": "Um grafico de barras azul", "relay_model": "gemini-flash-vision"}

        monkeypatch.setattr("backend.vision_relay.relay.describe_image_via_relay", _relay_ok)
        ctx_rel = RequestContext(user_id="u1", conversation_id=conv_id)
        _, relay_used_ok, relay_model_ok = await ha_mod.load_history(
            db, conv_id, user_msg_id, msg_atts, {}, False, False, [], "", None, None, "u1",
            request_context=ctx_rel,
        )
        assert relay_used_ok == 1
        assert relay_model_ok == "gemini-flash-vision"
        assert ctx_rel.get_memo("relay_status") == "relay"
