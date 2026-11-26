import os
import tempfile
import uuid
import aiosqlite
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

import backend.database as db_mod
import backend.attachments.storage as storage_mod
import backend.orchestration.persist_turn as persist_mod
import backend.routers.conversations as conv_router
import backend.routers.chat as chat_router
import backend.tools.dispatcher as disp_mod
from backend.auth import create_access_token
from backend.tools.base import ToolResult


@pytest.fixture
async def turn_db(monkeypatch, tmp_path):
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    monkeypatch.setattr(db_mod, "DB_PATH", path)
    monkeypatch.setattr(storage_mod, "STORAGE_DIR", tmp_path / "attachments")
    (tmp_path / "attachments" / "pending").mkdir(parents=True, exist_ok=True)
    await db_mod.init_db()

    async with aiosqlite.connect(path) as db:
        await db.execute(
            "INSERT INTO users (id, username, password_hash, email, role) VALUES (?, ?, ?, ?, ?)",
            ("u1", "alice", "hash", "alice@example.com", "user"),
        )
        await db.execute(
            "INSERT INTO users (id, username, password_hash, email, role) VALUES (?, ?, ?, ?, ?)",
            ("u2", "bob", "hash", "bob@example.com", "user"),
        )
        conv_id = str(uuid.uuid4())
        await db.execute(
            "INSERT INTO conversations (id, user_id, title) VALUES (?, ?, ?)",
            (conv_id, "u1", "Conversa Resiliencia"),
        )
        await db.commit()

    yield path, conv_id, tmp_path

    for ext in ("", "-wal", "-shm"):
        p = path + ext
        if os.path.exists(p):
            try:
                os.remove(p)
            except OSError:
                pass


@pytest.mark.asyncio
async def test_move_attachments_idempotent_on_retry(turn_db):
    path, conv_id, tmp_path = turn_db
    att_id = f"att_{uuid.uuid4().hex}"
    pending_rel = f"pending/{att_id}_nota.txt"
    abs_pending = tmp_path / "attachments" / pending_rel
    abs_pending.write_text("conteudo importante", encoding="utf-8")

    user_msg_id = str(uuid.uuid4())
    other_msg_id = str(uuid.uuid4())
    async with aiosqlite.connect(path) as db:
        await db.execute(
            "INSERT INTO messages (id, conversation_id, role, content) VALUES (?, ?, 'user', ?)",
            (user_msg_id, conv_id, "oi"),
        )
        await db.execute(
            """INSERT INTO attachments (id, user_id, filename, mime_type, file_type, size_bytes, file_hash, storage_path, message_id)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, NULL)""",
            (att_id, "u1", "nota.txt", "text/plain", "document", 19, "deadbeef1234", pending_rel),
        )
        await db.commit()

        # 1ª tentativa vincula à mensagem do usuário
        await storage_mod.move_attachments_to_conversation([att_id], conv_id, user_msg_id, db, user_id="u1")
        # 2ª tentativa com o MESMO (conv_id, user_msg_id) é idempotente
        await storage_mod.move_attachments_to_conversation([att_id], conv_id, user_msg_id, db, user_id="u1")
        # Tentativa com OUTRA mensagem NÃO sobrescreve nem rouba
        await storage_mod.move_attachments_to_conversation([att_id], conv_id, other_msg_id, db, user_id="u1")

        async with db.execute("SELECT message_id, storage_path FROM attachments WHERE id = ?", (att_id,)) as cur:
            row = await cur.fetchone()
        assert row is not None
        assert row[0] == user_msg_id
        assert row[1].startswith(f"{conv_id}/")


def test_turn_state_lifecycle_and_turn_status_endpoint(turn_db):
    import asyncio
    path, conv_id, _ = turn_db
    req_id = "turn-" + uuid.uuid4().hex[:10]
    user_msg_id = persist_mod.chat_request_message_id("u1", req_id, "user")
    asst_msg_id = persist_mod.chat_request_message_id("u1", req_id, "assistant")

    async def _seed_incomplete():
        async with aiosqlite.connect(path) as db:
            await persist_mod.save_user_message(
                db, conv_id, "Resuma o contrato", "m1", "groq", message_id=user_msg_id
            )
            await db_mod.upsert_chat_turn_state(
                db,
                user_id="u1",
                request_id=req_id,
                conversation_id=conv_id,
                user_message_id=user_msg_id,
                status="streaming",
                partial_content="Resumo parcial 1",
                model_id="m1",
                provider_id="groq",
                tool_effects=[{"family": "weather", "provider_id": "open-meteo", "data": {"temp": 25}}],
            )
        await db_mod.save_chat_turn_partial("u1", req_id, "Resumo parcial 1 + continuação", status="incomplete")

    asyncio.run(_seed_incomplete())

    app = FastAPI()
    app.include_router(conv_router.router)
    t_u1 = create_access_token("u1", "alice", "user")
    t_u2 = create_access_token("u2", "bob", "user")

    with TestClient(app) as client:
        # Outro usuário não enxerga estado de u1 (IDOR bloqueado)
        res_other = client.get(
            f"/api/conversations/turn-status?request_id={req_id}",
            headers={"Authorization": f"Bearer {t_u2}"},
        )
        assert res_other.status_code == 200
        assert res_other.json()["found"] is False

        res_status = client.get(
            f"/api/conversations/turn-status?request_id={req_id}",
            headers={"Authorization": f"Bearer {t_u1}"},
        )
        assert res_status.status_code == 200
        data = res_status.json()
        assert data["found"] is True
        assert data["status"] == "incomplete"
        assert data["conversation_id"] == conv_id
        assert data["partial_content"] == "Resumo parcial 1 + continuação"

        res_conv = client.get(
            f"/api/conversations/{conv_id}",
            headers={"Authorization": f"Bearer {t_u1}"},
        )
        assert res_conv.status_code == 200
        conv_data = res_conv.json()
        assert conv_data["pending_turn"] is not None
        assert conv_data["pending_turn"]["request_id"] == req_id
        assert conv_data["pending_turn"]["partial_content"] == "Resumo parcial 1 + continuação"

        # Conclui o turno e verifica que pending_turn some
        async def _complete():
            async with aiosqlite.connect(path) as db:
                await persist_mod.save_assistant_message(
                    db, conv_id, "Resposta final completa.", "m1", "groq", message_id=asst_msg_id
                )
                await db_mod.upsert_chat_turn_state(
                    db,
                    user_id="u1",
                    request_id=req_id,
                    conversation_id=conv_id,
                    user_message_id=user_msg_id,
                    assistant_message_id=asst_msg_id,
                    status="completed",
                    partial_content="Resposta final completa.",
                )

        asyncio.run(_complete())

        res_done = client.get(
            f"/api/conversations/turn-status?request_id={req_id}",
            headers={"Authorization": f"Bearer {t_u1}"},
        )
        assert res_done.status_code == 200
        assert res_done.json()["status"] == "completed"

        res_conv_after = client.get(
            f"/api/conversations/{conv_id}",
            headers={"Authorization": f"Bearer {t_u1}"},
        )
        assert res_conv_after.status_code == 200
        assert res_conv_after.json()["pending_turn"] is None


@pytest.mark.asyncio
async def test_retry_same_request_id_does_not_duplicate_tool_effects(turn_db, monkeypatch):
    _, conv_id, _ = turn_db
    calls = []

    class _DummyWS:
        async def send_json(self, _payload):
            pass

    async def _fake_dispatch(family, params, user_id=None, db=None, conversation_id=None):
        calls.append((family, dict(params)))
        return ToolResult(success=True, data={"temp": 24, "city": "Curitiba"}, provider_id="fake", family=family)

    async def _fake_search(*args, **kwargs):
        return False, "", [], [], None, []

    monkeypatch.setattr(disp_mod, "dispatch_tool", _fake_dispatch)
    monkeypatch.setattr(chat_router, "_resolve_web_search", _fake_search)

    web1, res1, attempted1, _ = await chat_router._resolve_turn_evidence(
        _DummyWS(),
        {"web_search": False},
        "previsão do tempo em Curitiba",
        "u1",
        conv_id,
        intent_res=None,
        history=[],
        intent_routing=None,
        turn_ref={"conversation_id": conv_id},
        existing_tool_effects=None,
    )
    assert attempted1 is True
    assert len(res1) == 1
    assert len(calls) == 1

    saved_effects = [
        {"family": r.family, "provider_id": r.provider_id, "data": r.data, "cached": r.cached, "metadata": r.metadata}
        for r in res1
    ]

    # Retry do mesmo request_id reutiliza o efeito gravado sem re-executar a tool
    web2, res2, attempted2, _ = await chat_router._resolve_turn_evidence(
        _DummyWS(),
        {"web_search": False},
        "previsão do tempo em Curitiba",
        "u1",
        conv_id,
        intent_res=None,
        history=[],
        intent_routing=None,
        turn_ref={"conversation_id": conv_id},
        existing_tool_effects=saved_effects,
    )
    assert attempted2 is True
    assert len(res2) == 1
    assert res2[0].data == {"temp": 24, "city": "Curitiba"}
    assert res2[0].metadata.get("reconciled") is True
    assert len(calls) == 1
