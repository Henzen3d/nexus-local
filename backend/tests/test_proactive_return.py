"""F3.6 — presença completa, fila ``pending``, entrega no retorno e "Me conta aqui".

Tudo no banco temporário do ``conftest.py`` (usuários/conversas únicos por
teste, porque o arquivo é compartilhado). Sockets são ``FakeSocket``; nenhuma
chamada de rede.
"""
from __future__ import annotations

import time
import uuid

from backend.database import get_db
from backend.proactive import delivery, presence, service
from backend.proactive.delivery import PresenceContext
from backend.tests.test_proactive_pipeline import (  # noqa: F401  (_isolation é autouse: vale para este módulo)
    _auth,
    _client_with,
    _connect,
    _isolation,
    seed_user_conv,
)

TOPIC = "show do Coldplay em Curitiba"
TEXT = "O show está marcado para 21 de março no Couto Pereira. Quer que eu fique de olho nos ingressos?"


async def seed_ready_insight(
    db,
    user_id: str,
    conv_id: str,
    *,
    status: str = "ready",
    topic: str = TOPIC,
    language: str = "pt-BR",
    expires_in: str = "+7 days",
    created_offset: str = "+0 seconds",
    category: str = "event",
    follow_ups=("Quanto custam os ingressos?", "Tem setor pista?"),
) -> str:
    import json

    insight_id = str(uuid.uuid4())
    await db.execute(
        """INSERT INTO proactive_insights
               (id, user_id, conversation_id, topic, topic_hash, category, confidence, status,
                synthesized_text, reason_line, sources_json, follow_ups_json, language, synth_model,
                created_at, ready_at, expires_at)
           VALUES (?, ?, ?, ?, ?, ?, 0.9, ?, ?, ?, ?, ?, ?, 'fake/fake-synth',
                   datetime('now', ?), datetime('now', ?), datetime('now', ?))""",
        (
            insight_id, user_id, conv_id, topic, service.compute_topic_hash(topic + insight_id), category, status,
            TEXT, "Pesquisei porque você pareceu animado com o show.",
            json.dumps([{"title": "Eventim", "url": "https://www.eventim.com.br/coldplay", "domain": "eventim.com.br"}]),
            json.dumps(list(follow_ups)), language,
            created_offset, created_offset, expires_in,
        ),
    )
    await db.commit()
    return insight_id


async def _insight_row(db, insight_id: str) -> dict:
    row = await delivery.load_insight(db, insight_id)
    assert row is not None
    return row


async def _proactive_messages(db, conv_id: str) -> list[tuple]:
    async with db.execute(
        "SELECT id, content, kind, proactive_insight_id FROM messages WHERE conversation_id = ? AND kind = 'proactive' ORDER BY created_at, rowid",
        (conv_id,),
    ) as cur:
        return list(await cur.fetchall())


# ─────────────────────────────────────────────────────────────────────────────
# F3.1.6 — máquina de presença
# ─────────────────────────────────────────────────────────────────────────────

def test_presence_effective_state_multi_socket_and_stale():
    presence.reset()
    ws1, ws2 = object(), object()
    assert presence.effective_state("u") == "offline"

    tr = presence.register("u", ws1)
    assert tr.kind == "connect" and presence.effective_state("u") == "active"  # ainda não reportou ⇒ ativo

    presence.update("u", ws1, state="hidden", view="chat")
    assert presence.effective_state("u") == "hidden"
    presence.register("u", ws2)
    presence.update("u", ws2, state="idle", conversation_id="c1", view="chat")
    assert presence.effective_state("u") == "idle"            # melhor entre hidden/idle
    presence.update("u", ws2, state="active", conversation_id="c1", view="chat")
    assert presence.effective_state("u") == "active" and presence.is_active_in_conversation("u", "c1")

    # F3.1.3 — socket sem sinal de vida há > 2× ping ⇒ hidden
    sock2 = presence.get_socket("u", ws2)
    sock2.last_seen_at -= presence.STALE_AFTER_S + 1
    assert sock2.effective_state() == "hidden" and not sock2.is_active
    assert presence.effective_state("u") == "hidden" and not presence.has_active_socket("u")
    assert not presence.is_active_in_conversation("u", "c1")

    # ping volta ⇒ retorno
    tr = presence.touch("u", ws2)
    assert tr is not None and tr.returned and tr.kind == "return" and presence.has_active_socket("u")
    assert presence.touch("u", ws2) is None  # sem transição
    assert presence.touch("u", object()) is None

    presence.remove("u", ws1)
    presence.remove("u", ws2)
    assert presence.effective_state("u") == "offline" and presence.snapshot("u") == []
    presence.reset()


def test_presence_transitions_drive_return_flush():
    presence.reset()
    ws = object()
    presence.register("u", ws)
    # 1º relato do socket = chegada (equivale a offline → active), mesmo na tela inicial
    tr = presence.update("u", ws, state="active", conversation_id=None, view="chat")
    assert tr.previous_state == "offline" and tr.returned and tr.should_flush and tr.kind == "connect"
    # mesmo estado/conversa ⇒ nada
    tr = presence.update("u", ws, state="active", conversation_id=None, view="chat")
    assert not tr.should_flush and tr.kind == "none"
    # abriu uma conversa ⇒ flush com contexto (F3.2.5)
    tr = presence.update("u", ws, state="active", conversation_id="c1", view="chat")
    assert tr.conversation_changed and not tr.returned and tr.kind == "conversation"
    assert tr.socket.conversation_id == "c1" and tr.socket.view == "chat"
    # saiu (hidden) ⇒ não dispara; voltou ⇒ dispara
    tr = presence.update("u", ws, state="hidden", conversation_id="c1", view="chat")
    assert not tr.should_flush and tr.user_state == "hidden"
    tr = presence.update("u", ws, state="active", conversation_id="c1", view="chat")
    assert tr.returned and tr.kind == "return" and tr.user_previous_state == "hidden" and tr.user_state == "active"
    # idle ⇒ active também é retorno
    presence.update("u", ws, state="idle", conversation_id="c1", view="chat")
    assert presence.update("u", ws, state="active", conversation_id="c1", view="chat").returned
    # trocar de tela sem conversa (view admin) ⇒ conversation None ⇒ muda
    tr = presence.update("u", ws, state="active", conversation_id=None, view="admin")
    assert tr.conversation_changed

    stats = presence.stats()
    assert stats["users_online"] == 1 and stats["users_active"] == 1 and stats["sockets"] == 1
    assert stats["transitions_last_hour"] >= 5 and stats["transitions_by_kind"]["return"] >= 2
    presence.reset()


def test_decide_follows_presence_matrix():
    presence.reset()
    insight = {"user_id": "u", "conversation_id": "c1"}
    assert delivery.decide(insight) == "pending"                      # offline
    ws = object()
    presence.register("u", ws)
    presence.update("u", ws, state="hidden", conversation_id="c1")
    assert delivery.decide(insight) == "pending"                      # hidden
    presence.update("u", ws, state="idle", conversation_id="c1")
    assert delivery.decide(insight) == "pending"                      # idle = ausente
    presence.update("u", ws, state="active", conversation_id="c2")
    assert delivery.decide(insight) == "toast"                        # ativo em outra conversa
    presence.update("u", ws, state="active", conversation_id="c1")
    assert delivery.decide(insight) == "inline"                       # ativo na origem
    presence.reset()


# ─────────────────────────────────────────────────────────────────────────────
# F3.6.1 — retorno: origem ⇒ pending_inline; tela inicial/outra ⇒ proactive_pending
# ─────────────────────────────────────────────────────────────────────────────

async def test_flush_in_origin_persists_return_prefix_for_all_tabs():
    db = await get_db()
    try:
        user_id, conv_id, _ = await seed_user_conv(db)
        insight_id = await seed_ready_insight(db, user_id, conv_id)
        tab_a = _connect(user_id, conv_id)          # aba na conversa de origem
        tab_b = _connect(user_id, None)             # aba na tela inicial

        result = await delivery.flush_pending(user_id, tab_a, PresenceContext("chat", conv_id), db=db)
        assert result.delivered == [insight_id] and result.pending == [] and result.expired == 0

        # Multi-aba: as duas recebem o MESMO message_id (F3.6.6)
        a_events, b_events = tab_a.of_type("proactive_insight"), tab_b.of_type("proactive_insight")
        assert len(a_events) == 1 and len(b_events) == 1
        assert a_events[0]["channel_hint"] == "inline"
        assert a_events[0]["insight"]["message_id"] == b_events[0]["insight"]["message_id"]
        assert a_events[0]["insight"]["channel"] == "pending_inline"
        assert not tab_a.of_type("proactive_pending") and not tab_b.of_type("proactive_pending")

        rows = await _proactive_messages(db, conv_id)
        assert len(rows) == 1 and rows[0][0] == a_events[0]["insight"]["message_id"]
        assert rows[0][1].startswith(f"Enquanto você estava fora, pesquisei sobre **{TOPIC}**: ")
        row = await _insight_row(db, insight_id)
        assert row["status"] == "delivered" and row["channel"] == "pending_inline"
        assert row["delivered_message_id"] == rows[0][0] and row["delivered_at"]

        # Idempotência: novo retorno não duplica nada
        again = await delivery.flush_pending(user_id, tab_a, PresenceContext("chat", conv_id), db=db)
        assert again.total == 0 and len(await _proactive_messages(db, conv_id)) == 1
        assert len(tab_a.of_type("proactive_insight")) == 1
    finally:
        await db.close()


async def test_flush_at_home_announces_pending_without_persisting():
    db = await get_db()
    try:
        user_id, conv_id, _ = await seed_user_conv(db)
        insight_id = await seed_ready_insight(db, user_id, conv_id)
        tab_a = _connect(user_id, None)
        tab_b = _connect(user_id, None)

        result = await delivery.flush_pending(user_id, tab_a, PresenceContext("chat", None), db=db)
        assert result.delivered == [] and result.pending == [insight_id]

        pend = tab_a.of_type("proactive_pending")
        assert len(pend) == 1 and not tab_b.sent                       # só o socket que voltou
        item = pend[0]["insights"][0]
        assert item["id"] == insight_id and item["status"] == "ready" and item["message_id"] is None
        assert item["origin"] == {"conversation_id": conv_id, "title": "Papo"}
        assert item["sources"][0]["domain"] == "eventim.com.br" and item["follow_ups"]
        assert item["text"] == TEXT and item["ready_at"] and item["expires_at"]

        assert await _proactive_messages(db, conv_id) == []
        row = await _insight_row(db, insight_id)
        assert row["status"] == "ready" and row["channel"] is None and row["delivered_message_id"] is None

        # Em outra conversa/tela: idem (o cliente decide toast + badge)
        tab_a.sent.clear()
        other_conv = str(uuid.uuid4())
        await delivery.flush_pending(user_id, tab_a, PresenceContext("chat", other_conv), db=db)
        assert len(tab_a.of_type("proactive_pending")) == 1
        tab_a.sent.clear()
        await delivery.flush_pending(user_id, tab_a, PresenceContext("admin", conv_id), db=db)  # view ≠ chat
        assert len(tab_a.of_type("proactive_pending")) == 1 and await _proactive_messages(db, conv_id) == []

        # Sem socket específico ⇒ todos recebem
        tab_a.sent.clear()
        await delivery.flush_pending(user_id, None, None, db=db)
        assert tab_a.of_type("proactive_pending") and tab_b.of_type("proactive_pending")
    finally:
        await db.close()


async def test_flush_waits_for_active_turn_in_origin():
    import asyncio

    db = await get_db()
    try:
        user_id, conv_id, _ = await seed_user_conv(db)
        insight_id = await seed_ready_insight(db, user_id, conv_id)
        tab = _connect(user_id, conv_id)
        guard = service.TurnGuard()
        guard.start(conv_id)

        async def _finish_turn():
            await asyncio.sleep(0.2)
            guard.finish()

        asyncio.get_event_loop().create_task(_finish_turn())
        started = time.monotonic()
        result = await delivery.flush_pending(user_id, tab, PresenceContext("chat", conv_id), db=db)
        assert result.delivered == [insight_id] and time.monotonic() - started >= 0.15
    finally:
        await db.close()


# ─────────────────────────────────────────────────────────────────────────────
# F3.6.2 — expiração / housekeeping · F3.6.3 — máx. 3 pendentes
# ─────────────────────────────────────────────────────────────────────────────

async def test_expired_insight_is_never_delivered_on_return():
    db = await get_db()
    try:
        user_id, conv_id, _ = await seed_user_conv(db)
        stale_id = await seed_ready_insight(db, user_id, conv_id, expires_in="-1 hours")
        fresh_id = await seed_ready_insight(db, user_id, conv_id, topic="Kindle Scribe", category="product")
        tab = _connect(user_id, None)

        api_items = await delivery.pending_for_api(db, user_id)
        assert [i["id"] for i in api_items] == [fresh_id]
        assert (await _insight_row(db, stale_id))["status"] == "expired"

        # Vencido no retorno à origem: nada é persistido
        tab.sent.clear()
        presence.update(user_id, tab, state="active", conversation_id=conv_id, view="chat")
        other_stale = await seed_ready_insight(db, user_id, conv_id, topic="festival", expires_in="-1 minutes")
        result = await delivery.flush_pending(user_id, tab, PresenceContext("chat", conv_id), db=db)
        assert result.expired == 1 and result.delivered == [fresh_id]
        assert (await _insight_row(db, other_stale))["status"] == "expired"
        rows = await _proactive_messages(db, conv_id)
        assert len(rows) == 1 and "Kindle Scribe" in rows[0][1]

        # deliver() ao vivo também recusa vencidos
        late = await seed_ready_insight(db, user_id, conv_id, topic="late", expires_in="-2 days")
        outcome = await delivery.deliver(await _insight_row(db, late), db)
        assert outcome.channel is None and outcome.reason == "expired"
        assert (await _insight_row(db, late))["status"] == "expired"
    finally:
        await db.close()


async def test_housekeeping_expires_fails_stuck_and_purges_old():
    db = await get_db()
    try:
        user_id, conv_id, _ = await seed_user_conv(db)
        overdue = await seed_ready_insight(db, user_id, conv_id, expires_in="-1 hours")
        stuck = await seed_ready_insight(db, user_id, conv_id, status="researching", created_offset="-10 minutes")
        young = await seed_ready_insight(db, user_id, conv_id, status="researching", created_offset="-1 minutes")
        old_seen = await seed_ready_insight(db, user_id, conv_id, status="seen", created_offset="-40 days")
        old_failed = await seed_ready_insight(db, user_id, conv_id, status="failed", created_offset="-31 days")
        old_delivered = await seed_ready_insight(db, user_id, conv_id, status="delivered", created_offset="-40 days")
        recent_seen = await seed_ready_insight(db, user_id, conv_id, status="seen", created_offset="-2 days")

        counts = await service.run_housekeeping(db)
        assert counts["expired"] >= 1 and counts["stuck"] >= 1 and counts["purged"] >= 2

        assert (await _insight_row(db, overdue))["status"] == "expired"
        row = await _insight_row(db, stuck)
        assert row["status"] == "failed" and row["error_code"] == "stuck"
        assert (await _insight_row(db, young))["status"] == "researching"
        assert await delivery.load_insight(db, old_seen) is None
        assert await delivery.load_insight(db, old_failed) is None
        assert (await _insight_row(db, old_delivered))["status"] == "delivered"
        assert (await _insight_row(db, recent_seen))["status"] == "seen"
    finally:
        await db.close()


async def test_flush_and_api_respect_max_pending():
    db = await get_db()
    try:
        user_id, conv_id, _ = await seed_user_conv(db)
        ids = []
        for i in range(5):
            ids.append(await seed_ready_insight(db, user_id, conv_id, topic=f"tópico {i}", created_offset=f"-{50 - i} minutes"))
        tab = _connect(user_id, None)
        result = await delivery.flush_pending(user_id, tab, PresenceContext("chat", None), db=db, max_pending=3)
        assert result.pending == ids[:3]                                  # os 3 mais antigos, em ordem
        payload = tab.of_type("proactive_pending")[0]
        assert [i["id"] for i in payload["insights"]] == ids[:3]
        assert len(await delivery.pending_for_api(db, user_id, max_pending=3)) == 3

        # A regra do pipeline (4º pendente expira o mais antigo) continua valendo
        expired = await service.enforce_pending_limit(db, user_id, 3)
        assert expired == ids[:2]
        assert [i["id"] for i in await delivery.pending_for_api(db, user_id, max_pending=3)] == ids[2:]
    finally:
        await db.close()


# ─────────────────────────────────────────────────────────────────────────────
# F3.6.4 — "Me conta aqui" (expand) e REST de pendentes
# ─────────────────────────────────────────────────────────────────────────────

async def test_expand_new_chat_creates_owned_conversation_with_origin():
    from backend.routers.conversations import router as conversations_router
    from backend.routers.proactive import router as proactive_router

    db = await get_db()
    try:
        owner, origin_conv, _ = await seed_user_conv(db)
        intruder, _, _ = await seed_user_conv(db)
        insight_id = await seed_ready_insight(db, owner, origin_conv)
    finally:
        await db.close()

    client = _client_with(proactive_router, conversations_router)

    # Intruso: 404 (não revela existência); sem token: 401/403; modo inválido: 422
    assert client.post(f"/api/proactive/insights/{insight_id}/expand", json={"mode": "new_chat"}, headers=_auth(intruder)).status_code == 404
    assert client.post(f"/api/proactive/insights/{insight_id}/expand", json={"mode": "new_chat"}).status_code in (401, 403)
    assert client.post(f"/api/proactive/insights/{insight_id}/expand", json={"mode": "later"}, headers=_auth(owner)).status_code == 422

    # same ⇒ só prefill (nada é escrito em nome do usuário)
    r = client.post(f"/api/proactive/insights/{insight_id}/expand", json={"mode": "same"}, headers=_auth(owner))
    assert r.status_code == 200
    assert r.json() == {"ok": True, "mode": "same", "conversation_id": origin_conv,
                        "prefill": "Quanto custam os ingressos?", "topic": TOPIC}

    # new_chat ⇒ conversa do dono com origin_insight_id + 1ª mensagem do assistente
    r = client.post(f"/api/proactive/insights/{insight_id}/expand", json={"mode": "new_chat"}, headers=_auth(owner))
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["ok"] and body["mode"] == "new_chat" and body["created"] is True
    new_conv, message_id = body["conversation_id"], body["message_id"]
    assert new_conv != origin_conv and message_id and body["title"] == "Show do Coldplay em Curitiba"

    db = await get_db()
    try:
        async with db.execute(
            "SELECT user_id, title, model_id, provider_id, origin_insight_id FROM conversations WHERE id = ?", (new_conv,)
        ) as cur:
            conv = await cur.fetchone()
        assert conv == (owner, "Show do Coldplay em Curitiba", "m/x", "p", insight_id)
        rows = await _proactive_messages(db, new_conv)
        assert len(rows) == 1 and rows[0][0] == message_id and rows[0][3] == insight_id
        assert rows[0][1].startswith(f"Oi! Na nossa conversa **«Papo»** você demonstrou interesse por **{TOPIC}**, então fui pesquisar: ")
        assert rows[0][1].endswith(TEXT)
        assert await _proactive_messages(db, origin_conv) == []           # nada na origem
        row = await _insight_row(db, insight_id)
        assert row["spawned_conversation_id"] == new_conv and row["status"] == "delivered"
        assert row["channel"] == "new_chat" and row["delivered_message_id"] == message_id
        # Some da fila de pendentes
        assert await delivery.pending_for_api(db, owner) == []
    finally:
        await db.close()

    # Idempotente: 2ª chamada devolve a mesma conversa, sem criar outra
    r2 = client.post(f"/api/proactive/insights/{insight_id}/expand", json={"mode": "new_chat"}, headers=_auth(owner))
    assert r2.status_code == 200 and r2.json()["conversation_id"] == new_conv and r2.json()["created"] is False
    assert r2.json()["message_id"] == message_id

    # GET da conversa nova: bolha com insight.origin = conversa de origem (F3.3.2)
    r = client.get(f"/api/conversations/{new_conv}", headers=_auth(owner))
    assert r.status_code == 200
    data = r.json()
    assert data["origin_insight_id"] == insight_id
    first = data["messages"][0]
    assert first["kind"] == "proactive" and first["role"] == "assistant" and first["proactive_insight_id"] == insight_id
    assert first["insight"]["origin"] == {"conversation_id": origin_conv, "title": "Papo"}
    assert first["insight"]["sources"] and first["insight"]["reason_line"]
    # Intruso não enxerga a conversa gerada
    assert client.get(f"/api/conversations/{new_conv}", headers=_auth(intruder)).status_code == 403
    # Lista expõe origin_insight_id (F3.3.4)
    listing = client.get("/api/conversations", headers=_auth(owner)).json()
    by_id = {c["id"]: c for c in listing}
    assert by_id[new_conv]["origin_insight_id"] == insight_id and by_id[origin_conv]["origin_insight_id"] is None

    # Insight vencido/expirado ⇒ 409
    db = await get_db()
    try:
        gone = await seed_ready_insight(db, owner, origin_conv, status="expired")
    finally:
        await db.close()
    assert client.post(f"/api/proactive/insights/{gone}/expand", json={"mode": "new_chat"}, headers=_auth(owner)).status_code == 409


async def test_pending_endpoint_is_per_user_and_capped():
    from backend.routers.proactive import router as proactive_router

    db = await get_db()
    try:
        owner, conv_id, _ = await seed_user_conv(db)
        intruder, _, _ = await seed_user_conv(db)
        ids = [await seed_ready_insight(db, owner, conv_id, topic=f"t{i}", created_offset=f"-{9 - i} minutes") for i in range(4)]
        await seed_ready_insight(db, owner, conv_id, topic="vencido", expires_in="-1 hours")
        dismissed = await seed_ready_insight(db, owner, conv_id, topic="dispensado")
    finally:
        await db.close()

    client = _client_with(proactive_router)
    assert client.get("/api/proactive/pending").status_code in (401, 403)
    assert client.get("/api/proactive/pending", headers=_auth(intruder)).json() == {"insights": []}

    # Dispensar no cartão não apaga: status='dismissed', some das listas (F3.2.6)
    r = client.post(f"/api/proactive/insights/{dismissed}/ack", json={"action": "dismissed"}, headers=_auth(owner))
    assert r.status_code == 200 and r.json()["status"] == "dismissed"

    r = client.get("/api/proactive/pending", headers=_auth(owner))
    assert r.status_code == 200
    items = r.json()["insights"]
    assert [i["id"] for i in items] == ids[:3]
    assert all(i["status"] == "ready" and i["origin"]["title"] == "Papo" for i in items)
    assert all("vencido" != i["topic"] for i in items)


# ─────────────────────────────────────────────────────────────────────────────
# Textos (§3.4) e título do chat novo
# ─────────────────────────────────────────────────────────────────────────────

def test_new_chat_prefix_and_title():
    base = {"topic": "Kindle Scribe", "synthesized_text": "It ships in May."}
    assert delivery.build_message_content({**base, "language": "en-US"}, mode="new_chat", origin_title="Gadgets") == (
        "Hi! In our chat **«Gadgets»** you seemed interested in **Kindle Scribe**, so I looked it up: It ships in May.")
    assert delivery.build_message_content({**base, "language": "es-ES"}, mode="new_chat", origin_title="Gadgets").startswith(
        "¡Hola! En nuestra conversación **«Gadgets»**")
    assert delivery.build_message_content(base, mode="new_chat").startswith("Oi! Na nossa conversa **«…»**")
    assert delivery.new_chat_title("  show   do coldplay em curitiba ") == "Show do coldplay em curitiba"
    assert delivery.new_chat_title("x" * 80).endswith("…") and len(delivery.new_chat_title("x" * 80)) == 60
    assert delivery.new_chat_title("") == "✦"


def test_insight_public_dict_origin_only_when_known():
    base = {"id": "i", "conversation_id": "c", "topic": "t", "status": "ready"}
    assert delivery.insight_public_dict(base)["origin"] is None
    assert delivery.insight_public_dict({**base, "origin_title": "Papo"})["origin"] == {"conversation_id": "c", "title": "Papo"}
    assert delivery.insight_public_dict({**base, "spawned_conversation_id": "n"})["origin"] == {"conversation_id": "c", "title": ""}
    assert delivery.build_pending_payload([base])["type"] == "proactive_pending"
