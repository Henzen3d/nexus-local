"""F5.1 — regressão de segurança, "não interromper", carga leve e observabilidade.

Banco temporário do ``conftest.py``; fakes de ``backend/tests/fakes/proactive.py``.
A fixture ``_isolation`` (autouse, importada) zera config/presença/tasks e troca
modelo/busca por fakes — nenhuma chamada de rede.
"""
from __future__ import annotations

import asyncio
import json
import logging
import uuid
from dataclasses import replace

from backend.database import get_db
from backend.proactive import admin as padmin
from backend.proactive import config as pconfig
from backend.proactive import presence, researcher, service, synthesizer
from backend.proactive.detector import InterestSignal
from backend.tests.fakes.proactive import SYNTH_JSON, FakeProvider, FakeReader, FakeSearch, FakeSocket
from backend.tests.test_proactive_pipeline import (  # noqa: F401  (_isolation é autouse)
    _CURRENT,
    USER_MESSAGE,
    _auth,
    _client_with,
    _connect,
    _isolation,
    run_full_pipeline,
    seed_user_conv,
)
from backend.tests.test_proactive_return import TEXT as SYNTH_TEXT
from backend.tests.test_proactive_return import seed_ready_insight


def _routers():
    from backend.routers.proactive import router as proactive_router

    return _client_with(proactive_router)


async def _row(db, insight_id: str, *cols: str) -> tuple:
    async with db.execute(f"SELECT {', '.join(cols)} FROM proactive_insights WHERE id = ?", (insight_id,)) as cur:
        return tuple(await cur.fetchone())


# ─────────────────────────────────────────────────────────────────────────────
# F5.1.3 — IDOR: usuário B nunca vê/age sobre insight de A
# ─────────────────────────────────────────────────────────────────────────────

async def test_idor_ack_expand_pending_never_cross_users():
    db = await get_db()
    try:
        alice, conv_a, _ = await seed_user_conv(db)
        bob, conv_b, _ = await seed_user_conv(db)
        insight_a = await seed_ready_insight(db, alice, conv_a)
        insight_b = await seed_ready_insight(db, bob, conv_b, topic="outro assunto")
    finally:
        await db.close()
    client = _routers()
    ha, hb = _auth(alice), _auth(bob)

    # pending: só os próprios
    assert {i["id"] for i in client.get("/api/proactive/pending", headers=ha).json()["insights"]} == {insight_a}
    assert {i["id"] for i in client.get("/api/proactive/pending", headers=hb).json()["insights"]} == {insight_b}
    assert client.get("/api/proactive/pending").status_code in (401, 403)

    # ack/expand de B sobre o insight de A ⇒ 404 (não revela existência) e nada muda
    for action in ("seen", "dismissed", "blocked", "know_more"):
        r = client.post(f"/api/proactive/insights/{insight_a}/ack", json={"action": action}, headers=hb)
        assert r.status_code == 404, (action, r.status_code)
    for mode in ("same", "new_chat"):
        r = client.post(f"/api/proactive/insights/{insight_a}/expand", json={"mode": mode}, headers=hb)
        assert r.status_code == 404, (mode, r.status_code)
    r = client.post(f"/api/proactive/insights/{uuid.uuid4()}/ack", json={"action": "seen"}, headers=hb)
    assert r.status_code == 404
    db = await get_db()
    try:
        status, know_more_at, spawned = await _row(db, insight_a, "status", "know_more_at", "spawned_conversation_id")
        assert status == "ready" and know_more_at is None and spawned is None
        async with db.execute("SELECT COUNT(*) FROM proactive_topic_blocklist WHERE user_id = ?", (alice,)) as cur:
            assert (await cur.fetchone())[0] == 0
    finally:
        await db.close()

    # expand new_chat pelo dono cria a conversa **do dono**; B não consegue ler nem reexpandir
    r = client.post(f"/api/proactive/insights/{insight_a}/expand", json={"mode": "new_chat"}, headers=ha)
    assert r.status_code == 200
    new_conv = r.json()["conversation_id"]
    db = await get_db()
    try:
        async with db.execute("SELECT user_id FROM conversations WHERE id = ?", (new_conv,)) as cur:
            assert (await cur.fetchone())[0] == alice
        async with db.execute(
            "SELECT COUNT(*) FROM messages WHERE conversation_id = ? AND kind = 'proactive'", (new_conv,)
        ) as cur:
            assert (await cur.fetchone())[0] == 1
    finally:
        await db.close()
    assert client.post(f"/api/proactive/insights/{insight_a}/expand", json={"mode": "new_chat"}, headers=hb).status_code == 404
    # idempotente para o dono (mesma conversa)
    again = client.post(f"/api/proactive/insights/{insight_a}/expand", json={"mode": "new_chat"}, headers=ha).json()
    assert again["conversation_id"] == new_conv and again["created"] is False


# ─────────────────────────────────────────────────────────────────────────────
# F5.1.3 — SSRF: fontes privadas nunca são lidas nem listadas
# ─────────────────────────────────────────────────────────────────────────────

PRIVATE_URLS = [
    "http://127.0.0.1:8000/admin",
    "http://localhost/x",
    "http://10.0.0.5/painel",
    "http://172.16.3.4/",
    "http://192.168.0.1/",
    "http://169.254.169.254/latest/meta-data/",
    "http://[::1]/",
    "http://[::ffff:127.0.0.1]/",
    "http://0.0.0.0/",
    "http://nexus_backend.internal/",
    "http://impressora.local/",
    "file:///etc/passwd",
    "ftp://exemplo.com/arquivo",
    "javascript:alert(1)",
]


def test_is_public_looking_url_rejects_private_and_non_http():
    for url in PRIVATE_URLS:
        assert researcher.is_public_looking_url(url) is False, url
    for url in ("https://g1.globo.com/x", "http://exemplo.com.br/", "https://8.8.8.8/", "https://[2001:4860:4860::8888]/"):
        assert researcher.is_public_looking_url(url) is True, url


async def test_researcher_never_fetches_or_lists_private_sources():
    db = await get_db()
    try:
        results = [{"title": "interno", "url": url, "snippet": "segredo"} for url in PRIVATE_URLS]
        results.insert(2, {"title": "Público", "url": "https://g1.globo.com/pr/coldplay", "snippet": "ok"})
        results.append({"title": "Eventim", "url": "https://www.eventim.com.br/coldplay", "snippet": "ingressos"})
        search = FakeSearch(results)
        reader = FakeReader(fail_on=())
        signal = InterestSignal(interest=0.9, topic="show do Coldplay", entities=["Coldplay"], category="event",
                                suggested_query="Coldplay Curitiba", language="pt-BR")
        result = await researcher.research(
            signal, db, topic_hash="ssrf-" + uuid.uuid4().hex, search_fn=search, fetch_fn=reader, use_cache=False
        )
    finally:
        await db.close()
    assert result.ok
    urls = [s.url for s in result.sources]
    assert urls and all(u.startswith("https://") for u in urls)
    assert not any(any(p in u for p in ("127.0.0.1", "localhost", "10.0.0.5", "169.254", "::1", ".internal", ".local"))
                   for u in urls)
    assert reader.requested and all(researcher.is_public_looking_url(u) for u in reader.requested)
    assert "segredo" not in json.dumps([s.to_dict() for s in result.sources], ensure_ascii=False)


async def test_reader_blocks_private_targets_before_any_request():
    from backend.web_search.reader import fetch_page_content, is_safe_public_url

    for url in ("http://127.0.0.1:8000/", "http://localhost/", "http://10.1.2.3/", "http://169.254.169.254/",
                "http://[::1]/", "file:///etc/passwd"):
        assert await is_safe_public_url(url) is False, url
        assert await fetch_page_content(url, timeout=1.0) is None, url


# ─────────────────────────────────────────────────────────────────────────────
# F5.1.3 — tamanho máximo do texto sintetizado
# ─────────────────────────────────────────────────────────────────────────────

async def test_synthesized_text_is_clipped_to_max_chars():
    huge = {**SYNTH_JSON, "text": ("Frase bem comprida sobre o show. " * 200).strip(),
            "reason_line": "motivo " * 100, "follow_ups": [f"pergunta {i} " * 30 for i in range(10)]}
    provider = FakeProvider(synth=huge)
    signal = InterestSignal(interest=0.9, topic="show do Coldplay", entities=["Coldplay"], category="event",
                            suggested_query="Coldplay Curitiba", language="pt-BR", emotion="excited")
    sources = researcher.merge_results([[{"title": "Eventim", "url": "https://www.eventim.com.br/coldplay",
                                          "snippet": "ingressos"}]], ["coldplay"])
    synthesis = await synthesizer.synthesize(signal, sources, provider=provider, model_name="fake", timeout=5)
    assert synthesis.ok
    assert len(synthesis.text) <= synthesizer.MAX_TEXT_CHARS
    assert len(synthesis.reason_line) <= synthesizer.MAX_REASON_CHARS
    assert len(synthesis.follow_ups) <= synthesizer.MAX_FOLLOW_UPS
    assert all(len(f) <= synthesizer.MAX_FOLLOW_UP_CHARS for f in synthesis.follow_ups)
    assert synthesis.prompt_chars > 0 and synthesis.response_chars > 0

    # a mesma garantia vale no fim do pipeline (coluna synthesized_text)
    db = await get_db()
    try:
        user, conv_id, msg_id = await seed_user_conv(db)
        result, _ = await run_full_pipeline(db, user, conv_id, msg_id, llm=provider)
        assert result.insight_id
        (text,) = await _row(db, result.insight_id, "synthesized_text")
        assert text and len(text) <= synthesizer.MAX_TEXT_CHARS
    finally:
        await db.close()


# ─────────────────────────────────────────────────────────────────────────────
# F5.1.4 — "não interromper": insight pronto durante o turno sai depois do stream_end
# ─────────────────────────────────────────────────────────────────────────────

async def test_ready_during_active_turn_is_delivered_only_after_turn_ends():
    db = await get_db()
    try:
        user, conv_id, msg_id = await seed_user_conv(db)
        ws = _connect(user, conv_id, state="active")
        service.mark_turn_started(conv_id)  # turno em andamento (resposta sendo transmitida)
        task = service.track_task(run_full_pipeline(db, user, conv_id, msg_id), name="proactive:t", user_id=user)
        await asyncio.sleep(0.6)  # pipeline (fakes) já chegou em ready e está esperando o turno
        assert not ws.of_type("proactive_insight")
        (status,) = await _row(db, (await _latest_insight(db, user)), "status")
        assert status == "ready"
        ws.sent.append({"type": "stream_end"})  # marcador do fim do turno no socket fake
        service.mark_turn_finished(conv_id)
        result, _ = await asyncio.wait_for(task, timeout=5)
        assert result.status == "delivered"
        types = ws.types()
        assert types.index("stream_end") < types.index("proactive_insight")
    finally:
        await db.close()


async def _latest_insight(db, user_id: str) -> str:
    async with db.execute(
        "SELECT id FROM proactive_insights WHERE user_id = ? ORDER BY created_at DESC LIMIT 1", (user_id,)
    ) as cur:
        return (await cur.fetchone())[0]


# ─────────────────────────────────────────────────────────────────────────────
# F5.1.5 — carga leve: 20 detecções ⇒ ≤ concurrency em voo; nenhuma task vaza
# ─────────────────────────────────────────────────────────────────────────────

async def test_twenty_concurrent_detections_respect_concurrency_and_leak_nothing():
    provider = FakeProvider(delay=0.05)
    _CURRENT["llm"] = provider
    cfg = replace(pconfig.ProactiveConfig(), concurrency=2, total_timeout_s=20, research_timeout_s=5, synth_timeout_s=5)
    db = await get_db()
    try:
        seeds = [await seed_user_conv(db) for _ in range(20)]
        tasks = [
            service.track_task(
                service.run_pipeline(user, conv, msg, USER_MESSAGE, model_id="m/x", provider_id="p", config=cfg, db=db),
                name=f"proactive:load{i}", user_id=user,
            )
            for i, (user, conv, msg) in enumerate(seeds)
        ]
        assert service.pending_tasks() == 20
        results = await asyncio.gather(*tasks)
    finally:
        await db.close()
    assert provider.max_active <= cfg.concurrency, provider.max_active
    assert len(provider.calls_of("classifier")) == 20
    assert all(r.insight_id for r in results) and {r.status for r in results} <= {"ready", "delivered"}
    await asyncio.sleep(0)  # callbacks de done rodam no próximo passo do loop
    assert service.pending_tasks() == 0
    assert all(service.user_task_count(user) == 0 for user, _, _ in seeds)


# ─────────────────────────────────────────────────────────────────────────────
# F5.2.1 / F5.2.2 — housekeeping compacta dismissed; boot recupera interrompidos
# ─────────────────────────────────────────────────────────────────────────────

async def test_housekeeping_compacts_dismissed_sources_and_recovery_marks_restart():
    db = await get_db()
    try:
        user, conv_id, _ = await seed_user_conv(db)
        dismissed = await seed_ready_insight(db, user, conv_id, status="dismissed", created_offset="-2 hours")
        fresh = await seed_ready_insight(db, user, conv_id, status="dismissed", topic="recente")
        kept = await seed_ready_insight(db, user, conv_id, status="delivered", topic="entregue", created_offset="-2 hours")
        detected = await seed_ready_insight(db, user, conv_id, status="detected", topic="d")
        researching = await seed_ready_insight(db, user, conv_id, status="researching", topic="r")

        summary = await service.run_housekeeping(db)
        assert summary["compacted"] == 1
        (sources,) = await _row(db, dismissed, "sources_json")
        assert json.loads(sources) == [{"url": "https://www.eventim.com.br/coldplay"}]
        assert "Eventim" in (await _row(db, fresh, "sources_json"))[0]      # recente: ainda não compacta
        assert "Eventim" in (await _row(db, kept, "sources_json"))[0]       # entregue: intocado
        assert (await service.run_housekeeping(db))["compacted"] == 0       # idempotente

        # F5.2.2 — "restart": detected|researching ⇒ failed:restart; o resto fica
        # (o banco é compartilhado entre arquivos de teste: outros testes podem ter deixado linhas em andamento)
        assert await service.recover_interrupted(db) >= 2
        assert (await _row(db, detected, "status", "error_code")) == ("failed", "restart")
        assert (await _row(db, researching, "status", "error_code")) == ("failed", "restart")
        assert (await _row(db, kept, "status"))[0] == "delivered"
        assert await service.recover_interrupted(db) == 0
    finally:
        await db.close()


# ─────────────────────────────────────────────────────────────────────────────
# F5.2.3 — logs estruturados: id/etapa/latência, nunca o texto do usuário
# ─────────────────────────────────────────────────────────────────────────────

async def test_structured_logs_never_contain_user_text(caplog):
    caplog.set_level(logging.DEBUG, logger="nexuslocal")
    db = await get_db()
    try:
        user, conv_id, msg_id = await seed_user_conv(db)
        _connect(user, conv_id, state="active")
        result, _ = await run_full_pipeline(db, user, conv_id, msg_id)
        assert result.status == "delivered"
        # falha também loga (warning) sem vazar texto
        failing = FakeProvider(fail_with=("synth", RuntimeError("provider down")))
        user2, conv2, msg2 = await seed_user_conv(db)
        failed, _ = await run_full_pipeline(db, user2, conv2, msg2, llm=failing)
        assert failed.status == "failed"
    finally:
        await db.close()
    records = [r for r in caplog.records if "[Proactive]" in r.getMessage()]
    assert records
    text = "\n".join(r.getMessage() for r in records)
    for forbidden in (USER_MESSAGE, "Coldplay", SYNTH_JSON["text"][:40], SYNTH_TEXT[:30]):
        assert forbidden not in text, forbidden
    stages = {getattr(r, "proactive", {}).get("stage") for r in records if hasattr(r, "proactive")}
    assert {"detect", "research", "synth", "deliver"} <= stages
    ready = [r for r in records if hasattr(r, "proactive") and "ready" in r.getMessage()]
    assert ready and ready[0].proactive["insight_id"] == result.insight_id
    assert ready[0].proactive["latency_ms"] is not None
    warnings = [r for r in records if r.levelno == logging.WARNING and "synth_failed" in r.getMessage()]
    assert warnings and warnings[0].proactive["insight_id"] == failed.insight_id


# ─────────────────────────────────────────────────────────────────────────────
# F5.2.4 / F5.2.5 — tokens estimados, série diária e alarme de falhas
# ─────────────────────────────────────────────────────────────────────────────

async def test_tokens_daily_series_and_failure_alert():
    from backend.metrics import task_benchmark_manager

    db = await get_db()
    try:
        user, conv_id, msg_id = await seed_user_conv(db)
        result, _ = await run_full_pipeline(db, user, conv_id, msg_id)
        tokens_in, tokens_out = await _row(db, result.insight_id, "tokens_in", "tokens_out")
        assert tokens_in > 0 and tokens_out > 0
        bench = task_benchmark_manager.get_aggregated_stats("proactive")
        assert bench.get("proactive", {}).get("count", 0) >= 1

        series = await padmin.daily_series(db, 3)
        assert len(series) == 3 and series[-1]["total"] >= 1 and series[-1]["tokens_in"] >= tokens_in
        assert series[0]["day"] < series[-1]["day"]

        assert padmin.failure_alert({"total": 4, "by_status": {"failed": 4}})["active"] is False   # amostra pequena
        assert padmin.failure_alert({"total": 10, "by_status": {"failed": 6}})["active"] is True
        assert padmin.failure_alert({"total": 10, "by_status": {"failed": 5}})["active"] is False  # 50 % não dispara
        assert padmin.failure_alert({"total": 0, "by_status": {}})["ratio"] is None

        stats = await padmin.admin_stats(db, days=2)
        assert len(stats["daily"]) == 2 and set(stats["tokens"]) == {"24h", "7d"}
        assert stats["tokens"]["24h"]["tokens_in"] >= tokens_in
        assert set(stats["alert"]) >= {"active", "failed", "total", "ratio", "threshold"}
    finally:
        await db.close()

    # endpoint: ?days validado e admin-only
    db = await get_db()
    try:
        admin = f"adm-{uuid.uuid4()}"
        await db.execute("INSERT INTO users (id, username, password_hash, role) VALUES (?, ?, 'x', 'admin')", (admin, admin))
        await db.commit()
    finally:
        await db.close()
    client = _routers()
    assert client.get("/api/proactive/admin-stats?days=3", headers=_auth(user)).status_code == 403
    r = client.get("/api/proactive/admin-stats?days=3", headers=_auth(admin))
    assert r.status_code == 200 and len(r.json()["daily"]) == 3
    assert client.get("/api/proactive/admin-stats?days=0", headers=_auth(admin)).status_code == 422
    assert client.get("/api/proactive/admin-stats?days=91", headers=_auth(admin)).status_code == 422


# ─────────────────────────────────────────────────────────────────────────────
# F5.4.3 — flag de onboarding (rollout gradual) e F5.1.6 — banco temporário
# ─────────────────────────────────────────────────────────────────────────────

async def test_onboarding_flag_is_admin_controlled():
    db = await get_db()
    try:
        admin = f"adm-{uuid.uuid4()}"
        await db.execute("INSERT INTO users (id, username, password_hash, role) VALUES (?, ?, 'x', 'admin')", (admin, admin))
        await db.commit()
        user, _, _ = await seed_user_conv(db, enabled=False)
        for _ in range(3):
            await db.execute("INSERT INTO conversations (id, user_id, title) VALUES (?, ?, 'x')", (str(uuid.uuid4()), user))
        await db.commit()
    finally:
        await db.close()
    client = _routers()
    h = _auth(admin)
    try:
        assert client.get("/api/proactive/admin-config", headers=h).json()["onboarding_enabled"] is False
        assert client.get("/api/proactive/settings", headers=_auth(user)).json()["onboarding_eligible"] is False
        r = client.put("/api/proactive/admin-config", json={"onboarding_enabled": True}, headers=h)
        assert r.status_code == 200 and r.json()["onboarding_enabled"] is True
        assert client.get("/api/proactive/settings", headers=_auth(user)).json()["onboarding_eligible"] is True
        # kill-switch global também segura o modal
        client.put("/api/proactive/admin-config", json={"enabled_global": False}, headers=h)
        assert client.get("/api/proactive/settings", headers=_auth(user)).json()["onboarding_eligible"] is False
    finally:
        client.put("/api/proactive/admin-config", json={"enabled_global": True, "onboarding_enabled": False}, headers=h)


def test_suite_never_touches_live_database():
    import os
    from pathlib import Path

    from backend import database as dbmod

    live = Path(dbmod.__file__).resolve().parent / "nexuslocal.db"
    assert Path(dbmod.DB_PATH).resolve() != live.resolve()
    assert "nexuslocal-tests-" in str(dbmod.DB_PATH)
    assert os.environ["DB_PATH"] == str(dbmod.DB_PATH)


async def test_fake_socket_and_presence_helpers():
    ws = FakeSocket()
    presence.reset()
    presence.update("u", ws, state="active", conversation_id="c", view="chat")
    assert presence.effective_state("u") == "active"
    await ws.send_json({"type": "x"})
    assert ws.types() == ["x"]
    ws.closed = True
    try:
        await ws.send_json({"type": "y"})
    except RuntimeError:
        pass
    else:  # pragma: no cover
        raise AssertionError("socket fechado deveria falhar")
    presence.reset()


async def test_proactive_companion_chat_endpoint(_isolation, monkeypatch):
    """Testa o endpoint POST /api/proactive/companion/chat com proteção IDOR e atualização de artefato."""
    db = await get_db()
    try:
        owner, conv_id, msg_id = await seed_user_conv(db)
        stranger, _, _ = await seed_user_conv(db)
        result, _ = await run_full_pipeline(db, owner, conv_id, msg_id)
        insight_id = result.insight_id
    finally:
        await db.close()

    client = _routers()

    # IDOR: stranger não pode conversar no companion de outro usuário
    res_idor = client.post(
        "/api/proactive/companion/chat",
        json={"insight_id": insight_id, "message": "Quais os horários?", "history": []},
        headers=_auth(stranger),
    )
    assert res_idor.status_code == 404

    # Owner tem acesso e recebe resposta amigável e artefato
    res_owner = client.post(
        "/api/proactive/companion/chat",
        json={
            "insight_id": insight_id,
            "message": "Pode me resumir os melhores setores?",
            "history": [],
        },
        headers=_auth(owner),
    )
    assert res_owner.status_code == 200
    data = res_owner.json()
    assert data["ok"] is True
    assert data["reply"]
    assert data["artifact"] is not None
    assert data["artifact"]["id"]
    assert data["artifact"]["title"]

