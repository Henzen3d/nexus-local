"""Testes de regressão das correções da auditoria (docs/auditoria-sistema.md).

Cobrem: URLs assinadas de anexos, rate limit de login, poda de histórico,
guarda anti-SSRF do Deep Reader e verificação de dono de conversa/anexo.
Usam apenas o banco temporário definido em conftest.py.
"""
from __future__ import annotations

import uuid
from urllib.parse import parse_qs, urlparse

import pytest

from backend.database import get_db, init_db


# ── Anexos: URL assinada ─────────────────────────────────────────────────────

def test_attachment_url_signature_roundtrip():
    from backend.attachments.signing import attachment_url, verify_attachment_signature

    url = attachment_url("conv/att_1_file.png")
    parsed = urlparse(url)
    qs = parse_qs(parsed.query)
    assert parsed.path == "/attachments/conv/att_1_file.png"
    assert verify_attachment_signature("conv/att_1_file.png", qs["exp"][0], qs["sig"][0])
    # Outro caminho, assinatura adulterada ou expiração alterada → inválido
    assert not verify_attachment_signature("conv/att_2_file.png", qs["exp"][0], qs["sig"][0])
    assert not verify_attachment_signature("conv/att_1_file.png", qs["exp"][0], "0" * 32)
    assert not verify_attachment_signature("conv/att_1_file.png", str(int(qs["exp"][0]) + 1), qs["sig"][0])


def test_attachment_url_expired_is_rejected():
    from backend.attachments.signing import attachment_url, verify_attachment_signature

    url = attachment_url("conv/x.png", ttl_seconds=-10)
    qs = parse_qs(urlparse(url).query)
    assert not verify_attachment_signature("conv/x.png", qs["exp"][0], qs["sig"][0])


def test_serve_attachment_route_requires_valid_signature(tmp_path, monkeypatch):
    """Rota pública /attachments/<rel>: sem/má assinatura → 403; traversal → 403; ok → arquivo."""
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    import backend.routers.attachments as att_router
    from backend.attachments.signing import attachment_url

    storage = tmp_path / "attachments"
    (storage / "conv").mkdir(parents=True)
    (storage / "conv" / "att_1_doc.txt").write_text("conteudo privado", encoding="utf-8")
    monkeypatch.setattr(att_router, "STORAGE_DIR", storage)

    app = FastAPI()
    app.include_router(att_router.files_router)
    client = TestClient(app)

    good = attachment_url("conv/att_1_doc.txt")
    r = client.get(good)
    assert r.status_code == 200
    assert r.headers["cache-control"].startswith("private")
    assert r.headers["x-content-type-options"] == "nosniff"
    assert r.text == "conteudo privado"

    assert client.get("/attachments/conv/att_1_doc.txt").status_code == 403
    assert client.get(good.replace("sig=", "sig=00")).status_code == 403
    # Caminho assinado válido, mas apontando para fora do storage, nunca é servido
    outside = attachment_url("../../etc/passwd")
    assert client.get(outside).status_code in (400, 403, 404)


# ── Login: rate limit ────────────────────────────────────────────────────────

async def test_sliding_window_limiter_blocks_and_resets():
    from backend.rate_limit import SlidingWindowLimiter

    lim = SlidingWindowLimiter(max_hits=3, window_seconds=60)
    assert await lim.hit("k") == 0
    assert await lim.hit("k") == 0
    assert await lim.hit("k") == 0
    retry = await lim.hit("k")
    assert retry > 0  # 4ª tentativa dentro da janela → bloqueado
    await lim.reset("k")
    assert await lim.hit("k") == 0
    assert await lim.hit("outra") == 0  # chaves independentes


# ── Histórico: poda ao orçamento ─────────────────────────────────────────────

def test_trim_history_keeps_recent_and_last_user_message():
    from backend.orchestration.handle_attachments import (
        estimate_message_tokens,
        trim_history_to_budget,
    )

    history = [
        {"role": "user", "content": "a" * 4000},
        {"role": "assistant", "content": "b" * 4000},
        {"role": "user", "content": "c" * 4000},
        {"role": "assistant", "content": "d" * 4000},
        {"role": "user", "content": "pergunta final"},
    ]
    trimmed, removed = trim_history_to_budget(history, budget_tokens=2500, reserved_tokens=300)
    assert removed == 2
    assert trimmed[-1]["content"] == "pergunta final"
    assert trimmed[0]["role"] == "user"  # nunca começa com resposta órfã do assistente
    assert sum(estimate_message_tokens(m) for m in trimmed) <= 2200

    # Cabe tudo → nada removido
    same, removed = trim_history_to_budget(history, budget_tokens=100_000)
    assert removed == 0 and same == history

    # Última mensagem sozinha maior que o orçamento → ainda assim é mantida
    only, removed = trim_history_to_budget([{"role": "user", "content": "x" * 10_000}], budget_tokens=100)
    assert len(only) == 1 and removed == 0


def test_estimate_message_tokens_counts_images_as_fixed_cost():
    from backend.orchestration.handle_attachments import estimate_message_tokens

    msg = {
        "role": "user",
        "content": [
            {"type": "text", "text": "veja"},
            {"type": "image_url", "image_url": {"url": "data:image/png;base64," + "A" * 2_000_000}},
        ],
    }
    # 2 MB de base64 NÃO viram 500k tokens
    assert estimate_message_tokens(msg) < 2000


# ── Web search: anti-SSRF ────────────────────────────────────────────────────

@pytest.mark.parametrize(
    "url",
    [
        "http://127.0.0.1:8000/health",
        "http://localhost/",
        "http://[::1]/",
        "http://169.254.169.254/latest/meta-data/",
        "http://10.0.0.5/",
        "http://192.168.1.1/",
        "http://backend.internal/",
        "ftp://example.com/",
        "file:///etc/passwd",
    ],
)
async def test_reader_blocks_private_and_non_http_targets(url):
    from backend.web_search.reader import is_safe_public_url

    assert await is_safe_public_url(url) is False


def test_private_ip_detection_covers_mapped_ipv6():
    from backend.web_search.reader import _is_private_ip

    assert _is_private_ip("::ffff:127.0.0.1")
    assert _is_private_ip("::ffff:10.1.2.3")
    assert _is_private_ip("fe80::1")
    assert not _is_private_ip("1.1.1.1")
    assert not _is_private_ip("2606:4700:4700::1111")


# ── Conversas e anexos: dono ─────────────────────────────────────────────────

async def test_verify_conversation_owner_rejects_other_user_and_bad_ids():
    from backend.orchestration.persist_turn import (
        ConversationAccessError,
        is_valid_conversation_id,
        verify_conversation_owner,
    )

    await init_db()
    db = await get_db()
    try:
        owner, intruder = f"u-{uuid.uuid4()}", f"u-{uuid.uuid4()}"
        for uid in (owner, intruder):
            await db.execute(
                "INSERT INTO users (id, username, password_hash, role) VALUES (?, ?, 'x', 'user')",
                (uid, uid),
            )
        conv_id = str(uuid.uuid4())
        await db.execute(
            "INSERT INTO conversations (id, user_id, title) VALUES (?, ?, 'privada')",
            (conv_id, owner),
        )
        await db.commit()

        await verify_conversation_owner(db, conv_id, owner)  # dono: ok
        with pytest.raises(ConversationAccessError):
            await verify_conversation_owner(db, conv_id, intruder)
        with pytest.raises(ConversationAccessError):
            await verify_conversation_owner(db, str(uuid.uuid4()), owner)  # inexistente
        with pytest.raises(ConversationAccessError):
            await verify_conversation_owner(db, "../../etc", owner)  # malformado
        assert is_valid_conversation_id(conv_id)
        assert not is_valid_conversation_id("x; DROP TABLE conversations")
    finally:
        await db.close()


async def test_move_attachments_only_moves_callers_unsent_attachments(tmp_path, monkeypatch):
    import backend.attachments.storage as storage_mod
    from backend.attachments.storage import move_attachments_to_conversation

    await init_db()
    db = await get_db()
    try:
        alice, bob = f"u-{uuid.uuid4()}", f"u-{uuid.uuid4()}"
        for uid in (alice, bob):
            await db.execute(
                "INSERT INTO users (id, username, password_hash, role) VALUES (?, ?, 'x', 'user')",
                (uid, uid),
            )
        conv_bob = str(uuid.uuid4())
        await db.execute(
            "INSERT INTO conversations (id, user_id, title) VALUES (?, ?, 't')", (conv_bob, bob)
        )
        msg_bob = str(uuid.uuid4())
        await db.execute(
            "INSERT INTO messages (id, conversation_id, role, content) VALUES (?, ?, 'user', 'oi')",
            (msg_bob, conv_bob),
        )
        att_alice = f"att_{uuid.uuid4().hex[:12]}"
        await db.execute(
            """INSERT INTO attachments (id, message_id, filename, mime_type, file_type, size_bytes,
                                        file_hash, storage_path, user_id)
               VALUES (?, NULL, 'segredo.txt', 'text/plain', 'document', 10, 'h', 'tmp/segredo.txt', ?)""",
            (att_alice, alice),
        )
        await db.commit()

        # Bob tenta "roubar" o anexo da Alice referenciando o ID dela
        monkeypatch.setattr(storage_mod, "STORAGE_DIR", tmp_path / "attachments")
        await move_attachments_to_conversation(
            [att_alice, "../../x", "att_inexistente"], conv_bob, msg_bob, db, user_id=bob
        )
        async with db.execute(
            "SELECT message_id, user_id FROM attachments WHERE id = ?", (att_alice,)
        ) as cur:
            row = await cur.fetchone()
        assert row[0] is None and row[1] == alice
    finally:
        await db.close()
