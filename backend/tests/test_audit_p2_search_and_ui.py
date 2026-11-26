import os
import tempfile
import aiosqlite
import pytest
from httpx import ASGITransport, AsyncClient

import backend.database as db_mod
import backend.routers.conversations as conv_router
from backend.auth import create_access_token
from backend.main import app
from backend.ui_blocks.validate import validate_envelope


@pytest.fixture
async def search_db(monkeypatch):
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    monkeypatch.setattr(db_mod, "DB_PATH", path)
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
        await db.execute(
            "INSERT INTO projects (id, user_id, name, instructions) VALUES (?, ?, ?, ?)",
            ("proj-fin", "u1", "Financeiro", "Contexto financeiro"),
        )
        await db.execute(
            "INSERT INTO conversations (id, user_id, title, project_id, updated_at) VALUES (?, ?, ?, ?, ?)",
            ("c-match", "u1", "Conversa Generica", "proj-fin", "2026-11-25 10:00:00"),
        )
        await db.execute(
            "INSERT INTO conversations (id, user_id, title, project_id, updated_at) VALUES (?, ?, ?, ?, ?)",
            ("c-other", "u1", "Outra Conversa", None, "2026-11-25 09:00:00"),
        )
        await db.execute(
            "INSERT INTO conversations (id, user_id, title, project_id, updated_at) VALUES (?, ?, ?, ?, ?)",
            ("c-bob", "u2", "Segredo Bob", None, "2026-11-25 11:00:00"),
        )
        await db.execute(
            """INSERT INTO messages (id, conversation_id, role, content, created_at)
               VALUES (?, ?, 'user', ?, ?)""",
            ("m-hit", "c-match", "Precisamos revisar o orçamento trimestral de infraestrutura cloud.", "2026-11-25 10:01:00"),
        )
        await db.execute(
            """INSERT INTO messages (id, conversation_id, role, content, created_at)
               VALUES (?, ?, 'assistant', ?, ?)""",
            ("m-bob", "c-bob", "Segredo trimestral exclusivo do outro usuário.", "2026-11-25 11:01:00"),
        )
        await db.commit()

    yield path

    for ext in ("", "-wal", "-shm"):
        p = path + ext
        if os.path.exists(p):
            os.remove(p)


@pytest.mark.asyncio
async def test_search_conversations_matches_message_content_and_isolates_users(search_db):
    token = create_access_token("u1", "alice", "user")
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        res = await client.get(
            "/api/conversations",
            params={"search": "trimestral"},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert res.status_code == 200
        rows = res.json()
        assert len(rows) == 1
        hit = rows[0]
        assert hit["id"] == "c-match"
        assert hit["matched_message_id"] == "m-hit"
        assert "trimestral" in (hit["matched_snippet"] or "").lower()
        assert hit["project_id"] == "proj-fin"
        assert hit["project_name"] == "Financeiro"

        # Filtro por project_id exclui avulsas
        res_proj = await client.get(
            "/api/conversations",
            params={"project_id": "proj-fin"},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert res_proj.status_code == 200
        assert [r["id"] for r in res_proj.json()] == ["c-match"]

        # Detalhe da conversa retorna project_name
        detail = await client.get(
            "/api/conversations/c-match",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert detail.status_code == 200
        assert detail.json()["project_name"] == "Financeiro"


def test_continuity_block_precedence_clarification_gt_options_gt_follow_up():
    env_all = validate_envelope({
        "v": 1,
        "blocks": [
            {"id": "m1", "type": "metric", "items": [{"label": "Total", "value": "10"}]},
            {
                "id": "cl1",
                "type": "clarification",
                "questions": [
                    {
                        "id": "q1",
                        "label": "Qual objetivo?",
                        "options": [{"id": "o1", "label": "Crescer"}, {"id": "o2", "label": "Reduzir"}],
                    }
                ],
            },
                {
                    "id": "opt1",
                    "type": "options",
                    "question": "Escolha formato",
                    "options": [{"value": "pdf", "label": "PDF"}, {"value": "html", "label": "HTML"}],
                    "action": {"name": "send_message", "template": "Formato: {choice}"},
                },
                {"id": "fu1", "type": "follow_up", "items": ["Passo 1", "Passo 2"]},
            ],
        })
    assert env_all is not None
    assert [b["type"] for b in env_all["blocks"]] == ["metric", "clarification"]

    env_opt = validate_envelope({
        "v": 1,
        "blocks": [
            {
                "id": "opt1",
                "type": "options",
                "question": "Escolha formato",
                "options": [{"value": "pdf", "label": "PDF"}, {"value": "html", "label": "HTML"}],
                "action": {"name": "send_message", "template": "Formato: {choice}"},
            },
            {"id": "fu1", "type": "follow_up", "items": ["Passo 1", "Passo 2"]},
        ],
    })
    assert env_opt is not None
    assert [b["type"] for b in env_opt["blocks"]] == ["options"]

    # options inválido não suprime follow_up válido
    env_fallback = validate_envelope({
        "v": 1,
        "blocks": [
            {"id": "opt_bad", "type": "options", "question": "Q", "options": []},
            {"id": "fu1", "type": "follow_up", "items": ["Sugestão válida 1", "Sugestão válida 2"]},
        ],
    })
    assert env_fallback is not None
    assert [b["type"] for b in env_fallback["blocks"]] == ["follow_up"]
