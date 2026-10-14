"""F2.8 — pipeline do Assistente Proativo com detector/busca/síntese fakes.

Tudo roda no banco temporário do conftest.py. Nenhuma chamada de rede: o
classificador e a síntese usam ``FakeLLM`` (imita ``stream_chat``), a busca
usa ``search_fn``/``fetch_fn`` injetados e o socket é ``FakeSocket``.
"""
from __future__ import annotations

import asyncio
import json
import uuid
from dataclasses import replace

import pytest

from backend.database import get_db, init_db
from backend.proactive import config as pconfig
from backend.proactive import delivery, presence, researcher, service, synthesizer
from backend.proactive.detector import InterestSignal
from backend.routers import chat as chat_router

# ─────────────────────────────────────────────────────────────────────────────
# Fakes e helpers
# ─────────────────────────────────────────────────────────────────────────────

# Fakes compartilhados (F5.1.2) — re-exportados aqui porque os testes de F3/F4 os importam deste módulo
from backend.tests.fakes.proactive import (  # noqa: E402
    CLASSIFIER_JSON,
    SOURCES_RAW,
    SYNTH_JSON,
    USER_MESSAGE,
    FakeLLM,
    FakeSocket,
    fake_fetch,
    fake_search,
)

__all__ = ["CLASSIFIER_JSON", "SOURCES_RAW", "SYNTH_JSON", "USER_MESSAGE", "FakeLLM", "FakeSocket",
           "fake_fetch", "fake_search"]


async def seed_user_conv(db, *, enabled: bool = True):
    user_id = f"u-{uuid.uuid4()}"
    conv_id = str(uuid.uuid4())
    await db.execute(
        "INSERT INTO users (id, username, password_hash, role) VALUES (?, ?, 'x', 'user')", (user_id, user_id)
    )
    await db.execute(
        "INSERT INTO conversations (id, user_id, title, model_id, provider_id) VALUES (?, ?, 'Papo', 'm/x', 'p')",
        (conv_id, user_id),
    )
    msg_id = str(uuid.uuid4())
    await db.execute(
        "INSERT INTO messages (id, conversation_id, role, content) VALUES (?, ?, 'user', ?)",
        (msg_id, conv_id, USER_MESSAGE),
    )
    await db.commit()
    if enabled:
        await pconfig.upsert_user_settings(db, user_id, enabled=True)
    return user_id, conv_id, msg_id


async def insert_insight(db, user_id, conv_id, *, status="ready", topic_hash="abc", created_at=None,
                         sources_json=None, topic="t"):
    insight_id = str(uuid.uuid4())
    await db.execute(
        """INSERT INTO proactive_insights
               (id, user_id, conversation_id, topic, topic_hash, category, confidence, status, sources_json, created_at)
           VALUES (?, ?, ?, ?, ?, 'event', 0.9, ?, ?, COALESCE(?, datetime('now')))""",
        (insight_id, user_id, conv_id, topic, topic_hash, status, sources_json, created_at),
    )
    await db.commit()
    return insight_id


_CURRENT: dict = {"llm": None}  # LLM fake usado pelos resolvers monkeypatchados na fixture


async def run_full_pipeline(db, user_id, conv_id, msg_id, *, llm=None, config=None, **overrides):
    if llm is not None:
        _CURRENT["llm"] = llm
    elif _CURRENT["llm"] is None:
        _CURRENT["llm"] = FakeLLM()
    cfg = config or replace(pconfig.ProactiveConfig(), total_timeout_s=10, research_timeout_s=5, synth_timeout_s=5)
    result = await service.run_pipeline(
        user_id, conv_id, msg_id, overrides.pop("message", USER_MESSAGE),
        model_id="m/x", provider_id="p", config=cfg, db=db, **overrides,
    )
    return result, _CURRENT["llm"]


@pytest.fixture(autouse=True)
async def _isolation(monkeypatch):
    """Config limpa, presença/turnos zerados e fakes de modelo/busca por padrão."""
    await init_db()
    pconfig.invalidate_config_cache()
    presence.reset()
    service.reset_runtime_state()
    chat_router._user_sockets.clear()

    _CURRENT["llm"] = FakeLLM()

    async def _detector(db, user_id, prov, model):
        return _CURRENT["llm"], "fake-detector", "override"

    async def _synth(db, user_id, prov, model, cfg):
        return _CURRENT["llm"], "fake-synth", "override"

    async def _label(db, source, model_name, conv_model_id):
        return "fake/fake-synth"

    monkeypatch.setattr(service, "resolve_detector_model", _detector)
    monkeypatch.setattr(synthesizer, "resolve_synth_model", _synth)
    monkeypatch.setattr(synthesizer, "model_label", _label)

    real_research = researcher.research

    async def _research(signal, db, **kw):
        kw.setdefault("search_fn", fake_search)
        kw.setdefault("fetch_fn", fake_fetch)
        kw.setdefault("use_cache", False)  # o banco é compartilhado entre testes; cache só no teste dedicado
        return await real_research(signal, db, **kw)

    monkeypatch.setattr(researcher, "research", _research)
    yield _CURRENT
    presence.reset()
    service.reset_runtime_state()
    chat_router._user_sockets.clear()


def _connect(user_id: str, conv_id: str | None, state: str = "active") -> FakeSocket:
    ws = FakeSocket()
    chat_router.register_socket(user_id, ws)
    presence.update(user_id, ws, state=state, conversation_id=conv_id, view="chat")
    return ws


# ─────────────────────────────────────────────────────────────────────────────
# F2.8.1 — pipeline completo
# ─────────────────────────────────────────────────────────────────────────────

async def test_pipeline_delivers_inline_when_user_present(_isolation):
    db = await get_db()
    try:
        user_id, conv_id, msg_id = await seed_user_conv(db)
        ws = _connect(user_id, conv_id)
        llm = _isolation["llm"]

        result, _ = await run_full_pipeline(db, user_id, conv_id, msg_id, llm=llm)
        assert result.stage == "delivered" and result.channel == "inline", result

        async with db.execute(
            "SELECT status, channel, synthesized_text, reason_line, sources_json, follow_ups_json, expires_at, "
            "delivered_message_id, synth_model, detector_model, language FROM proactive_insights WHERE id = ?",
            (result.insight_id,),
        ) as cur:
            row = await cur.fetchone()
        status, channel, text, reason, sources_json, follow_ups_json, expires_at, delivered_msg, synth_model, det, lang = row
        assert status == "delivered" and channel == "inline" and delivered_msg == result.message_id
        assert text.startswith("O show do Coldplay") and reason.startswith("Pesquisei porque")
        assert synth_model == "fake/fake-synth" and det == "override:fake-detector" and lang == "pt-BR"
        assert json.loads(follow_ups_json) == SYNTH_JSON["follow_ups"]
        sources = json.loads(sources_json)
        assert 1 <= len(sources) <= 3
        assert sources[0]["url"].startswith("https://www.eventim.com.br")  # fonte usada vem primeiro
        assert all("instagram" not in s["url"] for s in sources)           # rede social fica de fora do top 3
        assert expires_at.startswith("2027-03-21")                          # event → data detectada

        # Mensagem persistida como bolha proativa, com prefixo "ao vivo" (§3.4) e sem mexer no título
        async with db.execute(
            "SELECT role, content, kind, proactive_insight_id, model_id FROM messages WHERE id = ?",
            (result.message_id,),
        ) as cur:
            role, content, kind, pid, model_id = await cur.fetchone()
        assert role == "assistant" and kind == "proactive" and pid == result.insight_id
        assert content.startswith("Fiquei curioso com **show do Coldplay em Curitiba** e fui pesquisar: ")
        assert model_id == "fake/fake-synth"
        async with db.execute("SELECT title FROM conversations WHERE id = ?", (conv_id,)) as cur:
            assert (await cur.fetchone())[0] == "Papo"

        # Eventos no socket: status (researching, synthesizing) antes do insight
        stages = [m["stage"] for m in ws.of_type("proactive_status")]
        assert stages == ["researching", "synthesizing"]
        insights = ws.of_type("proactive_insight")
        assert len(insights) == 1
        evt = insights[0]
        assert evt["channel_hint"] == "inline"
        ins = evt["insight"]
        assert ins["id"] == result.insight_id and ins["message_id"] == result.message_id
        assert ins["conversation_id"] == conv_id and ins["category"] == "event"
        assert ins["text"] == text and ins["reason_line"] == reason
        assert ins["sources"] and set(ins["sources"][0]) == {"title", "url", "domain"}
        assert ins["follow_ups"] == SYNTH_JSON["follow_ups"] and ins["expires_at"] == expires_at
        assert ws.sent.index(insights[0]) > ws.sent.index(ws.of_type("proactive_status")[-1])

        # O classificador recebeu contexto curto e a síntese recebeu as fontes
        kinds = [c["kind"] for c in llm.calls]
        assert kinds == ["classifier", "synth"]
        synth_prompt = llm.calls[1]["messages"][1]["content"]
        assert "eventim.com.br" in synth_prompt and "Language: Brazilian Portuguese" in synth_prompt
    finally:
        await db.close()


async def test_pipeline_uses_toast_when_user_is_elsewhere(_isolation):
    db = await get_db()
    try:
        user_id, conv_id, msg_id = await seed_user_conv(db)
        ws = _connect(user_id, str(uuid.uuid4()))  # ativo, mas em outra conversa
        result, _ = await run_full_pipeline(db, user_id, conv_id, msg_id, llm=_isolation["llm"])
        assert result.stage == "delivered" and result.channel == "toast"
        assert ws.of_type("proactive_insight")[0]["channel_hint"] == "toast"
        async with db.execute(
            "SELECT COUNT(*) FROM messages WHERE conversation_id = ? AND kind = 'proactive'", (conv_id,)
        ) as cur:
            assert (await cur.fetchone())[0] == 1
    finally:
        await db.close()


@pytest.mark.parametrize("state", ["hidden", "idle"])
async def test_pipeline_keeps_ready_without_active_socket(_isolation, state):
    """F2.5.5: sem socket ativo ⇒ ``ready`` sem mensagem (F3 cuida do retorno)."""
    db = await get_db()
    try:
        user_id, conv_id, msg_id = await seed_user_conv(db)
        ws = _connect(user_id, conv_id, state=state)
        result, _ = await run_full_pipeline(db, user_id, conv_id, msg_id, llm=_isolation["llm"])
        assert result.stage == "ready" and result.status == "ready" and result.reason == "absent"
        async with db.execute("SELECT status, delivered_message_id FROM proactive_insights WHERE id = ?",
                              (result.insight_id,)) as cur:
            assert tuple(await cur.fetchone()) == ("ready", None)
        async with db.execute("SELECT COUNT(*) FROM messages WHERE kind = 'proactive' AND conversation_id = ?",
                              (conv_id,)) as cur:
            assert (await cur.fetchone())[0] == 0
        assert ws.of_type("proactive_insight") == []
    finally:
        await db.close()


async def test_pipeline_with_no_socket_at_all_keeps_ready(_isolation):
    db = await get_db()
    try:
        user_id, conv_id, msg_id = await seed_user_conv(db)
        result, _ = await run_full_pipeline(db, user_id, conv_id, msg_id, llm=_isolation["llm"])
        assert result.stage == "ready" and result.reason == "absent"
    finally:
        await db.close()


async def test_delivery_waits_for_active_turn(_isolation):
    """F2.5.4: nunca entregar no meio de uma resposta — aguarda ``mark_turn_finished``."""
    db = await get_db()
    try:
        user_id, conv_id, msg_id = await seed_user_conv(db)
        ws = _connect(user_id, conv_id)
        guard = service.TurnGuard()
        guard.start(conv_id)
        assert service.is_turn_active(conv_id)

        task = asyncio.create_task(run_full_pipeline(db, user_id, conv_id, msg_id, llm=_isolation["llm"]))
        await asyncio.sleep(0.3)
        assert not task.done()
        assert ws.of_type("proactive_insight") == []
        async with db.execute("SELECT status FROM proactive_insights WHERE conversation_id = ?", (conv_id,)) as cur:
            assert (await cur.fetchone())[0] == "ready"  # pronto, mas segurado

        guard.finish()
        result, _ = await asyncio.wait_for(task, timeout=5)
        assert result.stage == "delivered" and result.channel == "inline"
        assert len(ws.of_type("proactive_insight")) == 1
    finally:
        await db.close()


async def test_turn_guard_is_reentrant_per_conversation():
    service.reset_runtime_state()
    a, b = service.TurnGuard(), service.TurnGuard()
    a.start("c1")
    b.start("c1")
    a.finish()
    assert service.is_turn_active("c1")
    b.finish()
    assert not service.is_turn_active("c1")
    assert await service.wait_turn_end("c1", timeout=0.1)


# ─────────────────────────────────────────────────────────────────────────────
# Gate / opt-in / agendamento
# ─────────────────────────────────────────────────────────────────────────────

async def test_gate_rejection_never_calls_models_or_db(_isolation):
    db = await get_db()
    try:
        user_id, conv_id, msg_id = await seed_user_conv(db)
        llm = _isolation["llm"]
        result, _ = await run_full_pipeline(
            db, user_id, conv_id, msg_id, llm=llm, message="Quando é o show do Coldplay em Curitiba?"
        )
        assert result.stage == "gate" and not result.created
        assert llm.calls == []
        async with db.execute("SELECT COUNT(*) FROM proactive_insights WHERE user_id = ?", (user_id,)) as cur:
            assert (await cur.fetchone())[0] == 0
    finally:
        await db.close()


async def test_classifier_rejection_creates_no_row(_isolation):
    db = await get_db()
    try:
        user_id, conv_id, msg_id = await seed_user_conv(db)
        llm = FakeLLM(classifier={**CLASSIFIER_JSON, "interest": 0.4})
        result, _ = await run_full_pipeline(db, user_id, conv_id, msg_id, llm=llm)
        assert result.stage == "classify" and result.reason == "below_threshold"
        llm2 = FakeLLM(classifier={**CLASSIFIER_JSON, "entity_type": "private_person"})
        result2, _ = await run_full_pipeline(db, user_id, conv_id, msg_id, llm=llm2)
        assert result2.reason == "private_person" and not result2.created
    finally:
        await db.close()


async def test_disabled_user_and_global_kill_switch(_isolation):
    db = await get_db()
    try:
        user_id, conv_id, msg_id = await seed_user_conv(db, enabled=False)
        assert await service.schedule_proactive_check(db, user_id, conv_id, msg_id, USER_MESSAGE) is None
        result, _ = await run_full_pipeline(db, user_id, conv_id, msg_id)
        assert result.stage == "skipped" and result.reason == "disabled_user"

        await pconfig.upsert_user_settings(db, user_id, enabled=True)
        cfg = replace(pconfig.ProactiveConfig(), enabled_global=False)
        result, _ = await run_full_pipeline(db, user_id, conv_id, msg_id, config=cfg)
        assert result.reason == "disabled_global"

        # Kill-switch via meta também é respeitado pelo agendador
        await db.execute("UPDATE meta SET value = 'false' WHERE key = 'proactive_enabled_global'")
        await db.commit()
        pconfig.invalidate_config_cache()
        assert await service.schedule_proactive_check(db, user_id, conv_id, msg_id, USER_MESSAGE) is None
        await db.execute("UPDATE meta SET value = 'true' WHERE key = 'proactive_enabled_global'")
        await db.commit()
        pconfig.invalidate_config_cache()
    finally:
        await db.close()


async def test_schedule_creates_tracked_task_and_runs_pipeline(_isolation):
    db = await get_db()
    try:
        user_id, conv_id, msg_id = await seed_user_conv(db)
        _connect(user_id, conv_id)
        task = await service.schedule_proactive_check(
            db, user_id, conv_id, msg_id, USER_MESSAGE, model_id="m/x", provider_id="p"
        )
        assert task is not None and task in service._tasks
        result = await asyncio.wait_for(task, timeout=10)
        assert result.stage == "delivered"
        await asyncio.sleep(0)  # done_callback descarta a referência
        assert task not in service._tasks
        # web_search_used ⇒ porteiro recusa ⇒ nada agendado
        assert await service.schedule_proactive_check(
            db, user_id, conv_id, msg_id, USER_MESSAGE, web_search_used=True
        ) is None
    finally:
        await db.close()


async def test_category_disabled_by_user_is_skipped(_isolation):
    db = await get_db()
    try:
        user_id, conv_id, msg_id = await seed_user_conv(db)
        await pconfig.upsert_user_settings(db, user_id, categories=["news", "product"])
        result, _ = await run_full_pipeline(db, user_id, conv_id, msg_id, llm=_isolation["llm"])
        assert result.stage == "classify" and result.reason == "category_disabled"
    finally:
        await db.close()


# ─────────────────────────────────────────────────────────────────────────────
# F2.8.2 — limites (created_at injetável)
# ─────────────────────────────────────────────────────────────────────────────

def _topic_hash() -> str:
    return service.compute_topic_hash(CLASSIFIER_JSON["topic"], CLASSIFIER_JSON["entities"])


def test_topic_hash_is_stable_and_normalized():
    h1 = service.compute_topic_hash("Show do Coldplay", ["Coldplay", "Curitiba"])
    h2 = service.compute_topic_hash("  show DO coldplay ", ["curitiba", "COLDPLAY", "Coldplay"])
    assert h1 == h2 and len(h1) == 16
    assert service.compute_topic_hash("outro", []) != h1


async def test_limit_three_per_conversation_per_hour(_isolation):
    db = await get_db()
    try:
        user_id, conv_id, msg_id = await seed_user_conv(db)
        _connect(user_id, conv_id)
        for i in range(3):
            await insert_insight(db, user_id, conv_id, topic_hash=f"h{i}", created_at=None)
        result, llm = await run_full_pipeline(db, user_id, conv_id, msg_id)
        assert result.stage == "limits" and result.reason == "limit_conv_hour" and not result.created
        # Classificador rodou (limites vêm depois dele), mas nada de pesquisa/síntese
        assert [c["kind"] for c in llm.calls] == ["classifier"]

        # Insights antigos (> 1 h) e falhos não contam
        await db.execute("UPDATE proactive_insights SET created_at = datetime('now', '-2 hours') WHERE user_id = ?",
                         (user_id,))
        await db.commit()
        result, _ = await run_full_pipeline(db, user_id, conv_id, msg_id)
        assert result.stage == "delivered"
    finally:
        await db.close()


async def test_limit_ten_per_user_per_day(_isolation):
    db = await get_db()
    try:
        user_id, conv_id, msg_id = await seed_user_conv(db)
        _connect(user_id, conv_id)
        for i in range(10):
            other_conv = str(uuid.uuid4())
            await db.execute("INSERT INTO conversations (id, user_id, title) VALUES (?, ?, 'c')", (other_conv, user_id))
            await db.commit()
            await insert_insight(db, user_id, other_conv, topic_hash=f"d{i}",
                                 created_at="datetime('now', '-5 hours')" and None)
            await db.execute("UPDATE proactive_insights SET created_at = datetime('now', '-5 hours') "
                             "WHERE conversation_id = ?", (other_conv,))
            await db.commit()
        result, _ = await run_full_pipeline(db, user_id, conv_id, msg_id)
        assert result.stage == "limits" and result.reason == "limit_user_day"

        # Com 9 no dia (um falhou), a 10ª passa
        await db.execute("UPDATE proactive_insights SET status = 'failed' WHERE user_id = ? "
                         "AND id = (SELECT id FROM proactive_insights WHERE user_id = ? LIMIT 1)", (user_id, user_id))
        await db.commit()
        result, _ = await run_full_pipeline(db, user_id, conv_id, msg_id)
        assert result.stage == "delivered"
    finally:
        await db.close()


async def test_topic_cooldown_24h_same_user(_isolation):
    db = await get_db()
    try:
        user_id, conv_id, msg_id = await seed_user_conv(db)
        _connect(user_id, conv_id)
        other_conv = str(uuid.uuid4())
        await db.execute("INSERT INTO conversations (id, user_id, title) VALUES (?, ?, 'c')", (other_conv, user_id))
        await db.commit()
        await insert_insight(db, user_id, other_conv, topic_hash=_topic_hash(), status="seen")
        await db.execute("UPDATE proactive_insights SET created_at = datetime('now', '-20 hours') WHERE user_id = ?",
                         (user_id,))
        await db.commit()
        result, _ = await run_full_pipeline(db, user_id, conv_id, msg_id)
        assert result.stage == "limits" and result.reason == "topic_cooldown"

        await db.execute("UPDATE proactive_insights SET created_at = datetime('now', '-25 hours') WHERE user_id = ?",
                         (user_id,))
        await db.commit()
        result, _ = await run_full_pipeline(db, user_id, conv_id, msg_id)
        assert result.stage == "delivered"
    finally:
        await db.close()


async def test_blocked_topic_is_never_researched(_isolation):
    db = await get_db()
    try:
        user_id, conv_id, msg_id = await seed_user_conv(db)
        _connect(user_id, conv_id)
        await db.execute(
            "INSERT INTO proactive_topic_blocklist (user_id, topic_hash, topic_label) VALUES (?, ?, 'x')",
            (user_id, _topic_hash()),
        )
        await db.commit()
        result, _ = await run_full_pipeline(db, user_id, conv_id, msg_id)
        assert result.stage == "limits" and result.reason == "topic_blocked"
    finally:
        await db.close()


async def test_research_cache_reuses_sources_from_other_user(_isolation, monkeypatch):
    """F2.3.6: mesmo topic_hash de OUTRO usuário em < 24 h ⇒ reaproveita fontes (sem buscar)."""
    db = await get_db()
    try:
        other_user, other_conv, _ = await seed_user_conv(db)
        unique_topic = f"show único {uuid.uuid4().hex[:6]}"
        unique_hash = service.compute_topic_hash(unique_topic, ["Curitiba"])
        cached_sources = json.dumps([{"title": "Cache", "url": "https://cache.example/x", "domain": "cache.example",
                                      "snippet": "s", "content_excerpt": "e", "published_at": None}])
        await insert_insight(db, other_user, other_conv, topic_hash=unique_hash, status="delivered",
                             sources_json=cached_sources)

        user_id, conv_id, msg_id = await seed_user_conv(db)
        _connect(user_id, conv_id)
        _CURRENT["llm"] = FakeLLM(classifier={**CLASSIFIER_JSON, "topic": unique_topic, "entities": ["Curitiba"]})
        calls = {"search": 0}

        async def counting_search(query, db_):
            calls["search"] += 1
            return list(SOURCES_RAW)

        async def _research(signal, db_, **kw):
            kw["search_fn"] = counting_search
            kw["fetch_fn"] = fake_fetch
            return await _original_research(signal, db_, **kw)

        monkeypatch.setattr(researcher, "research", _research)

        result, _ = await run_full_pipeline(db, user_id, conv_id, msg_id)
        assert result.stage == "delivered"
        assert calls["search"] == 0
        async with db.execute("SELECT sources_json FROM proactive_insights WHERE id = ?", (result.insight_id,)) as cur:
            assert json.loads((await cur.fetchone())[0])[0]["url"] == "https://cache.example/x"
    finally:
        await db.close()


_original_research = researcher.research


async def test_pending_limit_expires_oldest(_isolation):
    """4º pendente ⇒ o mais antigo vira ``expired``; o recém-pronto nunca é expirado."""
    db = await get_db()
    try:
        user_id, conv_id, msg_id = await seed_user_conv(db)
        olds = []
        for i in range(3):
            other_conv = str(uuid.uuid4())
            await db.execute("INSERT INTO conversations (id, user_id, title) VALUES (?, ?, 'c')", (other_conv, user_id))
            await db.commit()
            olds.append(await insert_insight(db, user_id, other_conv, topic_hash=f"p{i}"))
            await db.execute("UPDATE proactive_insights SET created_at = datetime('now', ?) WHERE id = ?",
                             (f"-{30 - i} minutes", olds[-1]))
            await db.commit()
        # Sem socket ⇒ o novo fica 'ready' (4º pendente)
        result, _ = await run_full_pipeline(db, user_id, conv_id, msg_id)
        assert result.stage == "ready"
        async with db.execute("SELECT id, status FROM proactive_insights WHERE user_id = ?", (user_id,)) as cur:
            statuses = dict(await cur.fetchall())
        assert statuses[olds[0]] == "expired"
        assert statuses[olds[1]] == "ready" and statuses[olds[2]] == "ready"
        assert statuses[result.insight_id] == "ready"
        assert sum(1 for s in statuses.values() if s == "ready") == 3
    finally:
        await db.close()


async def test_enforce_pending_limit_helper():
    db = await get_db()
    try:
        user_id, conv_id, _ = await seed_user_conv(db)
        ids = [await insert_insight(db, user_id, conv_id, topic_hash=f"e{i}") for i in range(5)]
        for i, iid in enumerate(ids):
            await db.execute("UPDATE proactive_insights SET created_at = datetime('now', ?) WHERE id = ?",
                             (f"-{50 - i} minutes", iid))
        await db.commit()
        expired = await service.enforce_pending_limit(db, user_id, 3, keep_id=ids[0])
        # 5 ready, máx. 3 ⇒ 2 expirados; ids[0] é preservado ⇒ expiram ids[1] e ids[2]
        assert expired == [ids[1], ids[2]]
    finally:
        await db.close()


# ─────────────────────────────────────────────────────────────────────────────
# Falhas silenciosas
# ─────────────────────────────────────────────────────────────────────────────

async def test_no_results_marks_failed_without_message(_isolation, monkeypatch):
    db = await get_db()
    try:
        user_id, conv_id, msg_id = await seed_user_conv(db)
        ws = _connect(user_id, conv_id)

        async def empty_search(query, db_):
            return []

        async def _research(signal, db_, **kw):
            kw["search_fn"] = empty_search
            kw["fetch_fn"] = fake_fetch
            kw["use_cache"] = False
            return await _original_research(signal, db_, **kw)

        monkeypatch.setattr(researcher, "research", _research)
        result, llm = await run_full_pipeline(db, user_id, conv_id, msg_id)
        assert result.stage == "research" and result.reason == "no_results" and result.status == "failed"
        async with db.execute("SELECT status, error_code, latency_research_ms FROM proactive_insights WHERE id = ?",
                              (result.insight_id,)) as cur:
            status, code, lat = await cur.fetchone()
        assert status == "failed" and code == "no_results" and lat is not None
        assert ws.of_type("proactive_insight") == []
        assert [c["kind"] for c in llm.calls] == ["classifier"]  # síntese nunca roda
    finally:
        await db.close()


async def test_web_search_disabled_fails_silently(_isolation):
    db = await get_db()
    try:
        await db.execute("UPDATE web_search_config SET enabled = 0 WHERE id = 1")
        await db.commit()
        user_id, conv_id, msg_id = await seed_user_conv(db)
        _connect(user_id, conv_id)
        result, _ = await run_full_pipeline(db, user_id, conv_id, msg_id)
        assert result.reason == "web_search_disabled" and result.status == "failed"
    finally:
        await db.execute("UPDATE web_search_config SET enabled = 1 WHERE id = 1")
        await db.commit()
        await db.close()


async def test_synth_parse_failure_marks_failed(_isolation):
    db = await get_db()
    try:
        user_id, conv_id, msg_id = await seed_user_conv(db)
        ws = _connect(user_id, conv_id)
        llm = FakeLLM(synth_raw="Desculpe, não consegui gerar o JSON.")
        result, _ = await run_full_pipeline(db, user_id, conv_id, msg_id, llm=llm)
        assert result.stage == "synth" and result.reason == "synth_parse"
        async with db.execute("SELECT status, error_code, synth_model FROM proactive_insights WHERE id = ?",
                              (result.insight_id,)) as cur:
            assert tuple(await cur.fetchone()) == ("failed", "synth_parse", "fake/fake-synth")
        assert ws.of_type("proactive_insight") == []
    finally:
        await db.close()


async def test_no_synth_model_without_chat_fallback(_isolation, monkeypatch):
    db = await get_db()
    try:
        user_id, conv_id, msg_id = await seed_user_conv(db)
        _connect(user_id, conv_id)

        async def _no_model(db_, user_id_, prov, model, cfg):
            raise synthesizer.NoSynthModel("fallback desligado")

        monkeypatch.setattr(synthesizer, "resolve_synth_model", _no_model)
        result, _ = await run_full_pipeline(db, user_id, conv_id, msg_id)
        assert result.reason == "no_synth_model" and result.status == "failed"
    finally:
        await db.close()


async def test_total_timeout_marks_failed(_isolation):
    db = await get_db()
    try:
        user_id, conv_id, msg_id = await seed_user_conv(db)
        _connect(user_id, conv_id)
        llm = FakeLLM(delay=0.4)
        cfg = replace(pconfig.ProactiveConfig(), total_timeout_s=0.6, research_timeout_s=0.5, synth_timeout_s=0.5)
        result, _ = await run_full_pipeline(db, user_id, conv_id, msg_id, llm=llm, config=cfg)
        assert result.stage == "failed" and result.reason == "timeout"
        if result.insight_id:
            async with db.execute("SELECT status, error_code FROM proactive_insights WHERE id = ?",
                                  (result.insight_id,)) as cur:
                assert tuple(await cur.fetchone()) == ("failed", "timeout")
    finally:
        await db.close()


async def test_unexpected_exception_is_contained(_isolation, monkeypatch):
    db = await get_db()
    try:
        user_id, conv_id, msg_id = await seed_user_conv(db)
        _connect(user_id, conv_id)

        async def boom(signal, db_, **kw):
            raise RuntimeError("explodiu")

        monkeypatch.setattr(researcher, "research", boom)
        result, _ = await run_full_pipeline(db, user_id, conv_id, msg_id)
        assert result.stage == "failed" and result.reason == "error:RuntimeError"
        async with db.execute("SELECT status, error_code FROM proactive_insights WHERE id = ?",
                              (result.insight_id,)) as cur:
            assert tuple(await cur.fetchone()) == ("failed", "error:RuntimeError")
    finally:
        await db.close()


# ─────────────────────────────────────────────────────────────────────────────
# F2.3 — researcher isolado
# ─────────────────────────────────────────────────────────────────────────────

def _signal(**over) -> InterestSignal:
    data = {k: v for k, v in CLASSIFIER_JSON.items()}
    data.update(over)
    return InterestSignal(**data)


async def test_researcher_success_dedupe_ranking_and_partial_fetch_failure():
    db = await get_db()
    try:
        async def search(query, db_):
            dup = dict(SOURCES_RAW[0], url="http://eventim.com.br/coldplay/?utm_medium=y#top")
            return list(SOURCES_RAW) + [dup]

        res = await researcher.research(_signal(), db, topic_hash="zzz-none", search_fn=search, fetch_fn=fake_fetch,
                                        use_cache=False)
        assert res.ok and not res.cache_hit and res.error == ""
        urls = [s.url for s in res.sources]
        assert len(urls) == 3 and len(set(researcher.canonical_url(u) for u in urls)) == 3
        assert "instagram" not in " ".join(urls)
        top = res.sources[0]
        assert "eventim" in top.domain and top.content_excerpt.startswith("Coldplay Music") and top.published_at
        assert res.queries and res.queries[0].endswith(str(__import__("datetime").datetime.now().year))
        assert len(res.queries) <= 2
    finally:
        await db.close()


async def test_researcher_no_results_and_disabled_and_timeout():
    db = await get_db()
    try:
        async def nothing(query, db_):
            return []

        res = await researcher.research(_signal(), db, search_fn=nothing, fetch_fn=fake_fetch, use_cache=False)
        assert res.error == "no_results" and not res.ok

        async def slow(query, db_):
            await asyncio.sleep(0.5)
            return list(SOURCES_RAW)

        res = await researcher.research(_signal(), db, search_fn=slow, fetch_fn=fake_fetch, use_cache=False,
                                        timeout=0.1)
        assert res.error == "timeout"

        await db.execute("UPDATE web_search_config SET enabled = 0 WHERE id = 1")
        await db.commit()
        try:
            res = await researcher.research(_signal(), db, search_fn=fake_search, fetch_fn=fake_fetch, use_cache=False)
            assert res.error == "web_search_disabled"
        finally:
            await db.execute("UPDATE web_search_config SET enabled = 1 WHERE id = 1")
            await db.commit()
    finally:
        await db.close()


def test_canonical_url_and_scoring():
    assert researcher.canonical_url("https://www.Site.com/a/?utm_source=x&b=1#frag") == "https://site.com/a?b=1"
    assert researcher.canonical_url("http://site.com/a/") == researcher.canonical_url("https://www.site.com/a")
    assert researcher.score_source("https://www.coldplay.com/tour", ["coldplay"]) > researcher.score_source(
        "https://www.instagram.com/coldplay", ["coldplay"])
    assert researcher.score_source("https://g1.globo.com/x", []) > researcher.score_source("https://blog.random.net/x", [])


# ─────────────────────────────────────────────────────────────────────────────
# F2.4 — synthesizer isolado
# ─────────────────────────────────────────────────────────────────────────────

def _sources() -> list[researcher.Source]:
    return [researcher.Source.from_dict({"title": s["title"], "url": s["url"], "snippet": s["snippet"]})
            for s in SOURCES_RAW[:3]]


def test_parse_synthesis_tolerant_and_postprocessed():
    raw = "```json\n" + json.dumps({
        **SYNTH_JSON,
        "text": "Veja em [Eventim](https://www.eventim.com.br/coldplay) ou https://g1.globo.com/x " + ("muito texto " * 80),
        "used_source_urls": ["https://eventim.com.br/coldplay/", "https://nao-esta-nas-fontes.com/"],
        "follow_ups": ["a", "a", "b", "c", "d"],
    }) + "\n```"
    syn = synthesizer.parse_synthesis(raw, _sources())
    assert syn.ok
    assert "http" not in syn.text and "[" not in syn.text and syn.text.startswith("Veja em Eventim ou")
    assert len(syn.text) <= 600
    assert syn.used_source_urls == ["https://www.eventim.com.br/coldplay?utm_source=x"]  # ⊆ fontes, URL original
    assert syn.follow_ups == ["a", "b", "c"]
    assert syn.event_date == "2027-03-21"

    bad = synthesizer.parse_synthesis("nada de json aqui", _sources())
    assert bad.error == "synth_parse" and not bad.ok
    empty = synthesizer.parse_synthesis('{"text": "", "reason_line": "x"}', _sources())
    assert empty.error == "synth_parse"


def test_expires_at_by_category():
    from datetime import datetime, timezone

    now = datetime(2026, 10, 13, 12, 0, tzinfo=timezone.utc)
    assert synthesizer.compute_expires_at("news", now=now) == "2026-10-15 12:00:00"
    assert synthesizer.compute_expires_at("product", now=now) == "2026-10-20 12:00:00"
    assert synthesizer.compute_expires_at("place", now=now) == "2026-10-20 12:00:00"
    assert synthesizer.compute_expires_at("event", now=now) == "2026-10-20 12:00:00"
    assert synthesizer.compute_expires_at("event", event_date="2026-11-15", now=now) == "2026-11-15 23:59:59"
    # Data de evento no passado não serve ⇒ +7 d
    assert synthesizer.compute_expires_at("event", event_date="2026-01-01", now=now) == "2026-10-20 12:00:00"


async def test_synthesize_with_fake_provider_language_and_defaults():
    llm = FakeLLM(synth={**SYNTH_JSON, "reason_line": ""})
    syn = await synthesizer.synthesize(_signal(language="en-US", emotion="curious"), _sources(),
                                       provider=llm, model_name="fake", user_message=USER_MESSAGE)
    assert syn.ok and syn.model_label == "fake"
    assert syn.reason_line == "I looked it up because you seemed curious about show do Coldplay em Curitiba."
    prompt = llm.calls[0]["messages"][1]["content"]
    assert "Language: English (en-US)" in prompt and "[1]" in prompt and "[3]" in prompt
    assert llm.calls[0]["temperature"] == 0.3 if "temperature" in llm.calls[0] else True

    slow = FakeLLM(delay=0.5)
    syn = await synthesizer.synthesize(_signal(), _sources(), provider=slow, model_name="fake", timeout=0.1)
    assert syn.error == "synth_timeout"


# ─────────────────────────────────────────────────────────────────────────────
# F2.2.1 — config
# ─────────────────────────────────────────────────────────────────────────────

def test_build_config_precedence_meta_env_defaults():
    cfg = pconfig.build_config({}, env={})
    assert cfg.max_per_hour_conv == 3 and cfg.enabled_global is True and cfg.total_timeout_s == 45
    cfg = pconfig.build_config({}, env={"PROACTIVE_MAX_PER_HOUR_CONV": "5", "PROACTIVE_ENABLED_GLOBAL": "0"})
    assert cfg.max_per_hour_conv == 5 and cfg.enabled_global is False
    cfg = pconfig.build_config({"proactive_max_per_hour_conv": "2", "proactive_enabled_global": "true"},
                               env={"PROACTIVE_MAX_PER_HOUR_CONV": "5", "PROACTIVE_ENABLED_GLOBAL": "0"})
    assert cfg.max_per_hour_conv == 2 and cfg.enabled_global is True
    # Valores inválidos caem no default; concorrência mínima 1
    cfg = pconfig.build_config({"proactive_concurrency": "0", "proactive_total_timeout_s": "abc"}, env={})
    assert cfg.concurrency == 1 and cfg.total_timeout_s == 45


async def test_load_config_caches_and_invalidates():
    db = await get_db()
    try:
        pconfig.invalidate_config_cache()
        cfg = await pconfig.load_config(db)
        assert cfg.max_pending == 3
        await db.execute("UPDATE meta SET value = '7' WHERE key = 'proactive_max_pending'")
        await db.commit()
        assert (await pconfig.load_config(db)).max_pending == 3  # cache de 60 s
        pconfig.invalidate_config_cache()
        assert (await pconfig.load_config(db)).max_pending == 7
        await db.execute("UPDATE meta SET value = '3' WHERE key = 'proactive_max_pending'")
        await db.commit()
        pconfig.invalidate_config_cache()
    finally:
        await db.close()


async def test_user_settings_roundtrip():
    db = await get_db()
    try:
        user_id, _, _ = await seed_user_conv(db, enabled=False)
        s = await pconfig.get_user_settings(db, user_id)
        assert s.enabled is False and s.sensitivity == "medium" and s.categories == ["event", "news", "product", "place"]
        s = await pconfig.upsert_user_settings(db, user_id, enabled=True, sensitivity="high",
                                               categories=["place", "event", "bogus"], onboarding_seen=True)
        assert s.enabled and s.sensitivity == "high" and s.categories == ["event", "place"] and s.onboarding_seen_at
        s = await pconfig.upsert_user_settings(db, user_id, sensitivity="weird")
        assert s.sensitivity == "medium" and s.enabled is True
    finally:
        await db.close()


# ─────────────────────────────────────────────────────────────────────────────
# F2.8.3 — segurança (ack de outro usuário, GET da conversa)
# ─────────────────────────────────────────────────────────────────────────────

def _client_with(*routers):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    app = FastAPI()
    for r in routers:
        app.include_router(r)
    return TestClient(app)


def _auth(user_id: str) -> dict:
    from backend.auth import create_access_token

    return {"Authorization": f"Bearer {create_access_token(user_id, user_id, 'user')}"}


async def test_ack_only_by_owner_and_blocked_writes_blocklist(_isolation):
    from backend.routers.proactive import router as proactive_router

    db = await get_db()
    try:
        owner, conv_id, msg_id = await seed_user_conv(db)
        intruder, _, _ = await seed_user_conv(db)
        _connect(owner, conv_id)
        result, _ = await run_full_pipeline(db, owner, conv_id, msg_id)
        assert result.stage == "delivered"
        insight_id = result.insight_id
    finally:
        await db.close()

    client = _client_with(proactive_router)
    # Intruso: 404 (não revela existência)
    r = client.post(f"/api/proactive/insights/{insight_id}/ack", json={"action": "seen"}, headers=_auth(intruder))
    assert r.status_code == 404
    r = client.post(f"/api/proactive/insights/{uuid.uuid4()}/ack", json={"action": "seen"}, headers=_auth(owner))
    assert r.status_code == 404
    r = client.post(f"/api/proactive/insights/{insight_id}/ack", json={"action": "explode"}, headers=_auth(owner))
    assert r.status_code == 422
    r = client.post(f"/api/proactive/insights/{insight_id}/ack", json={"action": "seen"})
    assert r.status_code in (401, 403)

    r = client.post(f"/api/proactive/insights/{insight_id}/ack", json={"action": "seen"}, headers=_auth(owner))
    assert r.status_code == 200 and r.json()["status"] == "seen"
    r = client.post(f"/api/proactive/insights/{insight_id}/ack", json={"action": "blocked"}, headers=_auth(owner))
    assert r.status_code == 200 and r.json()["status"] == "blocked"

    db = await get_db()
    try:
        async with db.execute("SELECT status, seen_at FROM proactive_insights WHERE id = ?", (insight_id,)) as cur:
            status, seen_at = await cur.fetchone()
        assert status == "blocked" and seen_at
        async with db.execute("SELECT topic_hash FROM proactive_topic_blocklist WHERE user_id = ?", (owner,)) as cur:
            rows = await cur.fetchall()
        assert rows and rows[0][0] == _topic_hash()
        async with db.execute("SELECT COUNT(*) FROM proactive_topic_blocklist WHERE user_id = ?", (intruder,)) as cur:
            assert (await cur.fetchone())[0] == 0
    finally:
        await db.close()


async def test_settings_endpoints_are_per_user(_isolation):
    from backend.routers.proactive import router as proactive_router

    db = await get_db()
    try:
        alice, _, _ = await seed_user_conv(db, enabled=False)
        bob, _, _ = await seed_user_conv(db, enabled=False)
    finally:
        await db.close()
    client = _client_with(proactive_router)
    r = client.get("/api/proactive/settings", headers=_auth(alice))
    assert r.status_code == 200 and r.json()["enabled"] is False  # opt-in
    assert r.json()["allowed_categories"] == ["event", "news", "product", "place"]
    r = client.put("/api/proactive/settings", json={"enabled": True, "categories": ["event"]}, headers=_auth(alice))
    assert r.status_code == 200 and r.json()["enabled"] is True and r.json()["categories"] == ["event"]
    r = client.put("/api/proactive/settings", json={"categories": ["nope"]}, headers=_auth(alice))
    assert r.status_code == 422
    r = client.put("/api/proactive/settings", json={"sensitivity": "ultra"}, headers=_auth(alice))
    assert r.status_code == 422
    r = client.get("/api/proactive/settings", headers=_auth(bob))
    assert r.json()["enabled"] is False and r.json()["categories"] == ["event", "news", "product", "place"]


async def test_conversation_get_exposes_insight_only_to_owner(_isolation):
    from backend.routers.conversations import router as conv_router

    db = await get_db()
    try:
        owner, conv_id, msg_id = await seed_user_conv(db)
        intruder, _, _ = await seed_user_conv(db)
        _connect(owner, conv_id)
        result, _ = await run_full_pipeline(db, owner, conv_id, msg_id)
        assert result.stage == "delivered"
    finally:
        await db.close()

    client = _client_with(conv_router)
    r = client.get(f"/api/conversations/{conv_id}", headers=_auth(intruder))
    assert r.status_code == 403
    r = client.get(f"/api/conversations/{conv_id}", headers=_auth(owner))
    assert r.status_code == 200
    msgs = r.json()["messages"]
    assert [m["kind"] for m in msgs] == ["normal", "proactive"]
    bubble = msgs[1]
    assert bubble["role"] == "assistant" and bubble["proactive_insight_id"] == result.insight_id
    ins = bubble["insight"]
    assert ins["id"] == result.insight_id and ins["status"] == "delivered"
    assert ins["reason_line"].startswith("Pesquisei porque") and ins["sources"] and ins["follow_ups"]
    assert ins["topic"] == CLASSIFIER_JSON["topic"] and ins["message_id"] == result.message_id
    assert "insight" not in msgs[0]


# ─────────────────────────────────────────────────────────────────────────────
# F2.8.4 — memória ignora mensagens proativas
# ─────────────────────────────────────────────────────────────────────────────

async def test_memory_extractor_ignores_proactive_messages(_isolation, monkeypatch):
    from backend import memory as memory_mod

    db = await get_db()
    try:
        user_id, conv_id, msg_id = await seed_user_conv(db)
        _connect(user_id, conv_id)
        result, _ = await run_full_pipeline(db, user_id, conv_id, msg_id)
        assert result.stage == "delivered"
        await db.execute(
            "INSERT INTO messages (id, conversation_id, role, content) VALUES (?, ?, 'assistant', 'Que legal!')",
            (str(uuid.uuid4()), conv_id),
        )
        await db.commit()
    finally:
        await db.close()

    captured: dict = {}

    class Extractor:
        async def stream_chat(self, model, messages, temperature=0.7, max_tokens=4096, **kw):
            captured["prompt"] = messages[1]["content"]
            yield "[]"

    async def _provider(db_, prov, model, uid):
        return Extractor(), "fake-extractor", "override"

    async def _not_dead(db_, model_name):
        return False

    monkeypatch.setattr(memory_mod, "_get_extractor_provider_and_model", _provider)
    monkeypatch.setattr(memory_mod, "extractor_model_is_dead", _not_dead)
    await memory_mod.extract_user_memory_background(user_id, conv_id, "m/x", "p")
    assert "prompt" in captured, "extrator não rodou"
    assert USER_MESSAGE in captured["prompt"] and "Que legal!" in captured["prompt"]
    assert "Fiquei curioso" not in captured["prompt"]
    assert "Coldplay em Curitiba está marcado" not in captured["prompt"]


# ─────────────────────────────────────────────────────────────────────────────
# Presença / entrega isoladas
# ─────────────────────────────────────────────────────────────────────────────

def test_presence_rules():
    presence.reset()
    ws1, ws2 = object(), object()
    presence.register("u", ws1)
    assert presence.has_active_socket("u") and not presence.is_active_in_conversation("u", "c1")
    presence.update("u", ws1, state="active", conversation_id="c1", view="chat")
    assert presence.is_active_in_conversation("u", "c1")
    presence.update("u", ws1, state="hidden")
    assert not presence.has_active_socket("u")
    presence.update("u", ws2, state="active", conversation_id=None)
    assert presence.has_active_socket("u") and not presence.is_active_in_conversation("u", "c1")
    presence.update("u", ws2, state="bogus", conversation_id="x" * 100)  # ignorados
    assert presence.snapshot("u")[1].state == "active" and presence.snapshot("u")[1].conversation_id is None
    presence.remove("u", ws1)
    presence.remove("u", ws2)
    assert presence.snapshot("u") == []
    presence.reset()


async def test_deliver_is_idempotent(_isolation):
    db = await get_db()
    try:
        user_id, conv_id, msg_id = await seed_user_conv(db)
        ws = _connect(user_id, conv_id)
        result, _ = await run_full_pipeline(db, user_id, conv_id, msg_id)
        row = await delivery.load_insight(db, result.insight_id)
        again = await delivery.deliver(row, db)
        assert again.reason == "already_delivered" and again.message_id == result.message_id
        assert len(ws.of_type("proactive_insight")) == 1
        async with db.execute("SELECT COUNT(*) FROM messages WHERE kind = 'proactive' AND conversation_id = ?",
                              (conv_id,)) as cur:
            assert (await cur.fetchone())[0] == 1
    finally:
        await db.close()


def test_message_content_prefix_by_language():
    base = {"topic": "Kindle Scribe", "synthesized_text": "It ships in May."}
    assert delivery.build_message_content({**base, "language": "en-US"}) == (
        "I got curious about **Kindle Scribe** and looked it up: It ships in May.")
    assert delivery.build_message_content({**base, "language": "es-ES"}).startswith("Me dio curiosidad **Kindle Scribe**")
    assert delivery.build_message_content({**base, "language": None}).startswith("Fiquei curioso com **Kindle Scribe**")
    assert delivery.build_message_content({**base, "language": "pt-BR"}, mode="return").startswith(
        "Enquanto você estava fora, pesquisei sobre **Kindle Scribe**")
