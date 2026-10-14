"""F4.5 — controles do usuário, onboarding opt-in e painel admin.

Banco temporário do ``conftest.py`` (usuários únicos por teste). A fixture
``_isolation`` (autouse, importada) zera config/presença/tasks e troca
modelo/busca por fakes — nenhuma chamada de rede.
"""
from __future__ import annotations

import asyncio
import uuid

from backend.database import get_db
from backend.proactive import admin as padmin
from backend.proactive import config as pconfig
from backend.proactive import service
from backend.tests.test_proactive_pipeline import (  # noqa: F401  (_isolation é autouse: vale para este módulo)
    _CURRENT,
    USER_MESSAGE,
    FakeLLM,
    _auth,
    _client_with,
    _isolation,
    run_full_pipeline,
    seed_user_conv,
)
from backend.tests.test_proactive_return import TEXT as SYNTH_TEXT
from backend.tests.test_proactive_return import seed_ready_insight


async def seed_admin(db) -> str:
    user_id = f"adm-{uuid.uuid4()}"
    await db.execute(
        "INSERT INTO users (id, username, password_hash, role) VALUES (?, ?, 'x', 'admin')", (user_id, user_id)
    )
    await db.commit()
    return user_id


async def _status(db, insight_id: str) -> tuple:
    async with db.execute(
        "SELECT status, error_code, know_more_at FROM proactive_insights WHERE id = ?", (insight_id,)
    ) as cur:
        return tuple(await cur.fetchone())


def _routers():
    from backend.routers.proactive import router as proactive_router

    return _client_with(proactive_router)


# ─────────────────────────────────────────────────────────────────────────────
# F4.5.1 — autorização
# ─────────────────────────────────────────────────────────────────────────────

async def test_admin_endpoints_require_admin():
    db = await get_db()
    try:
        user, _, _ = await seed_user_conv(db)
        admin = await seed_admin(db)
    finally:
        await db.close()
    client = _routers()

    for method, path, body in [
        ("GET", "/api/proactive/admin-config", None),
        ("PUT", "/api/proactive/admin-config", {"max_pending": 3}),  # valor default: não altera os demais testes
        ("GET", "/api/proactive/logs", None),
        ("GET", "/api/proactive/admin-stats", None),
    ]:
        anon = client.request(method, path, json=body)
        assert anon.status_code in (401, 403), (path, anon.status_code)
        denied = client.request(method, path, json=body, headers=_auth(user))
        assert denied.status_code == 403, (path, denied.status_code)
        ok = client.request(method, path, json=body, headers=_auth(admin))
        assert ok.status_code == 200, (path, ok.status_code, ok.text)

    # settings continua por usuário: o que um faz não aparece para o outro
    client.put("/api/proactive/settings", json={"enabled": True, "sensitivity": "high"}, headers=_auth(user))
    other = client.get("/api/proactive/settings", headers=_auth(admin)).json()
    assert other["enabled"] is False and other["sensitivity"] == "medium"
    # desbloquear tópico só mexe na própria blocklist (idempotente, sem vazar existência)
    r = client.delete("/api/proactive/blocklist/naoexiste", headers=_auth(user))
    assert r.status_code == 200 and r.json()["removed"] is False


# ─────────────────────────────────────────────────────────────────────────────
# F4.5.2 — settings: payload completo, PUT parcial, quiet_hours, onboarding
# ─────────────────────────────────────────────────────────────────────────────

async def test_settings_payload_partial_update_and_onboarding():
    db = await get_db()
    try:
        user, conv_id, _ = await seed_user_conv(db, enabled=False)
        delivered = await seed_ready_insight(db, user, conv_id, status="delivered")
        await db.execute(
            "UPDATE proactive_insights SET delivered_at = datetime('now'), know_more_at = datetime('now') WHERE id = ?",
            (delivered,),
        )
        await db.commit()
    finally:
        await db.close()
    client = _routers()
    h = _auth(user)

    r = client.get("/api/proactive/settings", headers=h)
    assert r.status_code == 200
    data = r.json()
    assert data["enabled"] is False and data["blocked_topics"] == []
    assert data["stats"] == {"insights_30d": 1, "delivered_30d": 1, "know_more_30d": 1, "blocked_30d": 0}
    assert data["conversation_count"] == 1 and data["onboarding_eligible"] is False  # < 3 conversas

    # PUT parcial: só sensitivity ⇒ enabled/categories/quiet_hours intocados
    client.put("/api/proactive/settings", json={"enabled": True, "categories": ["event", "news"]}, headers=h)
    r = client.put("/api/proactive/settings", json={"sensitivity": "low"}, headers=h)
    assert r.status_code == 200
    data = r.json()
    assert data["enabled"] is True and data["sensitivity"] == "low" and data["categories"] == ["event", "news"]
    assert data["quiet_hours"] is None and "disabled" not in data

    # quiet_hours validado
    assert client.put("/api/proactive/settings", json={"quiet_hours": {"start": "25:00", "end": "08:00"}}, headers=h).status_code == 422
    assert client.put("/api/proactive/settings", json={"quiet_hours": {"start": "22:00"}}, headers=h).status_code == 422
    assert client.put("/api/proactive/settings", json={"quiet_hours": {"start": "22:00", "end": "22:00"}}, headers=h).status_code == 422
    assert client.put("/api/proactive/settings", json={"sensitivity": "extreme"}, headers=h).status_code == 422
    assert client.put("/api/proactive/settings", json={"categories": ["gossip"]}, headers=h).status_code == 422
    r = client.put("/api/proactive/settings", json={"quiet_hours": {"start": "22:00", "end": "08:00"}}, headers=h)
    assert r.status_code == 200 and r.json()["quiet_hours"] == {"start": "22:00", "end": "08:00"}
    r = client.put("/api/proactive/settings", json={"clear_quiet_hours": True}, headers=h)
    assert r.json()["quiet_hours"] is None and r.json()["sensitivity"] == "low"

    # onboarding-seen não mexe em enabled; elegibilidade exige ≥ 3 conversas e onboarding nunca visto
    db = await get_db()
    try:
        for _ in range(2):
            await db.execute(
                "INSERT INTO conversations (id, user_id, title) VALUES (?, ?, 'x')", (str(uuid.uuid4()), user)
            )
        await db.commit()
        await pconfig.upsert_user_settings(db, user, enabled=False)
    finally:
        await db.close()
    data = client.get("/api/proactive/settings", headers=h).json()
    assert data["conversation_count"] == 3 and data["onboarding_eligible"] is True
    r = client.post("/api/proactive/settings/onboarding-seen", headers=h)
    assert r.status_code == 200 and r.json()["onboarding_seen_at"] and r.json()["enabled"] is False
    data = client.get("/api/proactive/settings", headers=h).json()
    assert data["onboarding_seen_at"] and data["onboarding_eligible"] is False and data["enabled"] is False


# ─────────────────────────────────────────────────────────────────────────────
# F4.5.3 — desligar cancela pipeline em voo e expira pendentes
# ─────────────────────────────────────────────────────────────────────────────

async def test_disable_cancels_inflight_pipeline_and_expires_pending():
    db = await get_db()
    try:
        user, conv_id, msg_id = await seed_user_conv(db)
        pending = await seed_ready_insight(db, user, conv_id)
        kept = await seed_ready_insight(db, user, conv_id, topic="entregue", status="delivered")
        researching = await seed_ready_insight(db, user, conv_id, topic="pesquisando", status="researching")

        # Pipeline real com modelo lento (classificador dorme 5 s) — rastreado por usuário
        _CURRENT["llm"] = FakeLLM(delay=5)
        task = service.track_task(
            run_full_pipeline(db, user, conv_id, msg_id), name="proactive:test", user_id=user,
        )
        await asyncio.sleep(0.05)
        assert service.user_task_count(user) == 1

        result = await service.disable_user(db, user)
        assert result["cancelled"] == 1 and result["expired"] == 2
        try:
            await task
        except asyncio.CancelledError:
            pass
        assert task.cancelled() or task.done()
        assert service.user_task_count(user) == 0

        assert (await _status(db, pending))[:2] == ("expired", "user_disabled")
        assert (await _status(db, researching))[:2] == ("expired", "user_disabled")
        assert (await _status(db, kept))[0] == "delivered"              # histórico preservado
        # Novo agendamento não roda enquanto o usuário está desligado
        await pconfig.upsert_user_settings(db, user, enabled=False)
        assert await service.schedule_proactive_check(db, user, conv_id, msg_id, USER_MESSAGE) is None
    finally:
        await db.close()


async def test_put_enabled_false_reports_disable_summary():
    db = await get_db()
    try:
        user, conv_id, _ = await seed_user_conv(db)
        await seed_ready_insight(db, user, conv_id)
    finally:
        await db.close()
    client = _routers()
    r = client.put("/api/proactive/settings", json={"enabled": False}, headers=_auth(user))
    assert r.status_code == 200
    body = r.json()
    assert body["enabled"] is False and body["disabled"] == {"cancelled": 0, "expired": 1}
    assert client.get("/api/proactive/pending", headers=_auth(user)).json() == {"insights": []}
    # Religar não ressuscita o que expirou
    r = client.put("/api/proactive/settings", json={"enabled": True}, headers=_auth(user))
    assert r.json()["enabled"] is True and "disabled" not in r.json()
    assert client.get("/api/proactive/pending", headers=_auth(user)).json() == {"insights": []}


# ─────────────────────────────────────────────────────────────────────────────
# F4.5.4 — logs anonimizados · admin-stats
# ─────────────────────────────────────────────────────────────────────────────

async def test_logs_are_anonymized_and_filterable():
    db = await get_db()
    try:
        user, conv_id, _ = await seed_user_conv(db)
        admin = await seed_admin(db)
        long_topic = "tópico " + "x" * 100
        ready = await seed_ready_insight(db, user, conv_id, topic=long_topic)
        failed = await seed_ready_insight(db, user, conv_id, topic="falhou", status="failed")
        await db.execute(
            "UPDATE proactive_insights SET error_code = 'timeout', latency_detect_ms = 120, "
            "latency_research_ms = 3000, latency_synth_ms = 900 WHERE id = ?",
            (failed,),
        )
        await db.commit()
    finally:
        await db.close()
    client = _routers()

    r = client.get("/api/proactive/logs?limit=5", headers=_auth(admin))
    assert r.status_code == 200
    body = r.text
    # Nunca o texto da mensagem do usuário nem o texto sintetizado
    assert USER_MESSAGE not in body and SYNTH_TEXT not in body
    assert "Couto Pereira" not in body
    data = r.json()
    assert data["limit"] == 5 and data["total"] >= 2
    rows = {row["id"]: row for row in data["rows"]}
    assert set(rows[failed].keys()) == set(padmin.LOG_COLUMNS)
    assert rows[failed]["username"] == user and rows[failed]["error_code"] == "timeout"
    assert rows[failed]["latency_research_ms"] == 3000 and rows[failed]["status"] == "failed"
    assert len(rows[ready]["topic"]) <= padmin.TOPIC_LABEL_MAX and rows[ready]["topic"].endswith("…")

    # Filtro por status e paginação
    r = client.get("/api/proactive/logs?status=failed&limit=200", headers=_auth(admin))
    assert all(row["status"] == "failed" for row in r.json()["rows"]) and failed in {x["id"] for x in r.json()["rows"]}
    assert client.get("/api/proactive/logs?status=weird", headers=_auth(admin)).json()["rows"] == []
    assert client.get("/api/proactive/logs?limit=0", headers=_auth(admin)).status_code == 422
    assert client.get("/api/proactive/logs?limit=999", headers=_auth(admin)).status_code == 422
    page2 = client.get("/api/proactive/logs?limit=1&offset=1", headers=_auth(admin)).json()
    assert page2["offset"] == 1 and len(page2["rows"]) == 1


async def test_admin_stats_rates_and_percentiles():
    db = await get_db()
    try:
        user, conv_id, _ = await seed_user_conv(db)
        admin = await seed_admin(db)
        ids = [await seed_ready_insight(db, user, conv_id, topic=f"s{i}", status="delivered") for i in range(4)]
        for i, insight_id in enumerate(ids):
            await db.execute(
                "UPDATE proactive_insights SET delivered_at = datetime('now'), latency_detect_ms = ?, "
                "latency_research_ms = ?, latency_synth_ms = ? WHERE id = ?",
                (100 * (i + 1), 1000 * (i + 1), 500, insight_id),
            )
        await db.execute("UPDATE proactive_insights SET know_more_at = datetime('now') WHERE id = ?", (ids[0],))
        await db.execute("UPDATE proactive_insights SET status = 'blocked' WHERE id = ?", (ids[1],))
        await db.commit()
    finally:
        await db.close()

    assert padmin.percentile([], 95) is None
    assert padmin.percentile([10], 95) == 10
    assert padmin.percentile([100, 200, 300, 400], 50) == 250
    assert padmin.percentile([100, 200, 300, 400], 95) == 385

    client = _routers()
    r = client.get("/api/proactive/admin-stats", headers=_auth(admin))
    assert r.status_code == 200
    data = r.json()
    day = data["windows"]["24h"]
    assert day["delivered"] >= 4 and day["know_more"] >= 1 and day["blocked"] >= 1
    assert day["know_more_rate"] is not None and 0 < day["know_more_rate"] <= 1
    assert day["blocked_rate"] is not None and 0 < day["blocked_rate"] <= 1
    assert set(day["by_status"].keys()) == set(padmin.ALL_STATUSES)
    assert data["windows"]["7d"]["total"] >= day["total"]
    lat = data["latency"]
    assert lat["samples"] >= 4 and lat["research_p95_ms"] >= lat["research_p50_ms"] > 0
    assert lat["total_p95_ms"] >= lat["research_p95_ms"]
    assert data["users_enabled"] >= 1 and "pending_now" in data and "blocklist_size" in data
    assert "tasks_in_flight" in data["runtime"] and "users_active" in data["runtime"]["presence"]


# ─────────────────────────────────────────────────────────────────────────────
# F4.5.5 — admin-config: validação, persistência sem reiniciar, kill-switch
# ─────────────────────────────────────────────────────────────────────────────

ADMIN_DEFAULTS = {
    "enabled_global": True, "max_pending": 3, "expiry_news_hours": 48, "total_timeout_s": 45.0,
    "allow_chat_model_fallback": False, "detector_provider_id": "", "detector_model_id": "",
}


async def test_admin_config_roundtrip_validation_and_kill_switch():
    db = await get_db()
    try:
        user, conv_id, msg_id = await seed_user_conv(db)
        admin = await seed_admin(db)
        pending = await seed_ready_insight(db, user, conv_id)
        await pconfig.save_admin_config(db, ADMIN_DEFAULTS)  # o banco é compartilhado entre os testes
    finally:
        await db.close()
    client = _routers()
    h = _auth(admin)

    base = client.get("/api/proactive/admin-config", headers=h).json()
    assert base["enabled_global"] is True and base["max_pending"] == 3 and base["expiry_news_hours"] == 48
    assert base["limits"]["max_pending"] == [1, 10]

    # Validação de limites/tipos
    assert client.put("/api/proactive/admin-config", json={"max_pending": 0}, headers=h).status_code == 422
    assert client.put("/api/proactive/admin-config", json={"concurrency": 99}, headers=h).status_code == 422
    assert client.put("/api/proactive/admin-config", json={"total_timeout_s": 1}, headers=h).status_code == 422
    assert client.put("/api/proactive/admin-config", json={}, headers=h).status_code == 422

    # Persistência em meta + efeito imediato (cache invalidado) sem reiniciar
    r = client.put(
        "/api/proactive/admin-config",
        json={"max_pending": 2, "detector_provider_id": "p", "detector_model_id": "m/x",
              "expiry_news_hours": 12, "total_timeout_s": 30.5, "allow_chat_model_fallback": True},
        headers=h,
    )
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["max_pending"] == 2 and data["detector_model_id"] == "m/x" and data["expiry_news_hours"] == 12
    assert data["total_timeout_s"] == 30.5 and data["allow_chat_model_fallback"] is True
    db = await get_db()
    try:
        async with db.execute("SELECT value FROM meta WHERE key = 'proactive_max_pending'") as cur:
            assert (await cur.fetchone())[0] == "2"
        cfg = await pconfig.load_config(db)
        assert cfg.max_pending == 2 and cfg.total_timeout_s == 30.5 and cfg.expiry_news_hours == 12
        # Limpar um campo de texto volta ao default/env
        client.put("/api/proactive/admin-config", json={"detector_model_id": ""}, headers=h)
        assert (await pconfig.load_config(db)).detector_model_id is None
    finally:
        await db.close()

    # Kill-switch: cancela em voo + expira pendentes de todos + bloqueia novas detecções na hora
    db = await get_db()
    try:
        _CURRENT["llm"] = FakeLLM(delay=5)
        task = service.track_task(run_full_pipeline(db, user, conv_id, msg_id), name="proactive:ks", user_id=user)
        await asyncio.sleep(0.05)
        r = client.put("/api/proactive/admin-config", json={"enabled_global": False}, headers=h)
        assert r.status_code == 200 and r.json()["enabled_global"] is False
        assert r.json()["kill_switch"]["expired"] >= 1
        # a task vive no loop deste teste: o cancelamento vem pelo mesmo registro, aqui
        service.cancel_all()
        try:
            await task
        except asyncio.CancelledError:
            pass
        assert (await _status(db, pending))[:2] == ("expired", "global_disabled")
        assert await service.schedule_proactive_check(db, user, conv_id, msg_id, USER_MESSAGE) is None
        # Religar: volta a agendar
        r = client.put("/api/proactive/admin-config", json={"enabled_global": True}, headers=h)
        assert r.json()["enabled_global"] is True and "kill_switch" not in r.json()
        _CURRENT["llm"] = FakeLLM()
        task = await service.schedule_proactive_check(db, user, conv_id, msg_id, USER_MESSAGE)
        assert task is not None
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass
    finally:
        try:
            await pconfig.save_admin_config(db, ADMIN_DEFAULTS)
        finally:
            await db.close()


# ─────────────────────────────────────────────────────────────────────────────
# F4.3.2 — ligações da bolha: know_more, bloquear + desfazer
# ─────────────────────────────────────────────────────────────────────────────

async def test_know_more_and_unblock_restore():
    db = await get_db()
    try:
        user, conv_id, _ = await seed_user_conv(db)
        insight = await seed_ready_insight(db, user, conv_id, status="delivered")
        async with db.execute("SELECT topic_hash FROM proactive_insights WHERE id = ?", (insight,)) as cur:
            topic_hash = (await cur.fetchone())[0]
    finally:
        await db.close()
    client = _routers()
    h = _auth(user)

    # know_more: registra a métrica sem mudar o status
    r = client.post(f"/api/proactive/insights/{insight}/ack", json={"action": "know_more"}, headers=h)
    assert r.status_code == 200 and r.json()["status"] == "delivered" and r.json()["topic_hash"] == topic_hash
    db = await get_db()
    try:
        status, _, know_more_at = await _status(db, insight)
        assert status == "delivered" and know_more_at
    finally:
        await db.close()
    assert client.get("/api/proactive/settings", headers=h).json()["stats"]["know_more_30d"] == 1

    # bloquear ⇒ blocklist + status blocked; desfazer ⇒ remove da blocklist e reabre a bolha (seen)
    r = client.post(f"/api/proactive/insights/{insight}/ack", json={"action": "blocked"}, headers=h)
    assert r.status_code == 200 and r.json()["status"] == "blocked"
    settings = client.get("/api/proactive/settings", headers=h).json()
    assert [b["topic_hash"] for b in settings["blocked_topics"]] == [topic_hash]
    assert settings["blocked_topics"][0]["topic_label"].startswith("show do Coldplay")

    r = client.delete(f"/api/proactive/blocklist/{topic_hash}", headers=h)
    assert r.status_code == 200
    assert r.json()["removed"] is True and r.json()["restored_insight_ids"] == [insight]
    assert client.get("/api/proactive/settings", headers=h).json()["blocked_topics"] == []
    db = await get_db()
    try:
        assert (await _status(db, insight))[0] == "seen"
    finally:
        await db.close()
    # Outro usuário não consegue desbloquear por você
    db = await get_db()
    try:
        intruder, _, _ = await seed_user_conv(db)
        client.post(f"/api/proactive/insights/{insight}/ack", json={"action": "blocked"}, headers=h)
    finally:
        await db.close()
    r = client.delete(f"/api/proactive/blocklist/{topic_hash}", headers=_auth(intruder))
    assert r.json()["removed"] is False
    assert len(client.get("/api/proactive/settings", headers=h).json()["blocked_topics"]) == 1


def test_quiet_hours_and_admin_validators():
    assert pconfig.validate_quiet_hours(None) is None
    assert pconfig.validate_quiet_hours({"start": "22:00", "end": "08:00"}) == {"start": "22:00", "end": "08:00"}
    for bad in ("x", {"start": "22:00"}, {"start": "22:60", "end": "08:00"}, {"start": "9:00", "end": "10:00"}):
        try:
            pconfig.validate_quiet_hours(bad)
        except ValueError:
            pass
        else:
            raise AssertionError(f"deveria rejeitar {bad!r}")
    clean = pconfig.validate_admin_updates({"max_pending": "4", "enabled_global": "off", "synth_model_id": " m ", "concurrency": None})
    assert clean == {"max_pending": 4, "enabled_global": False, "synth_model_id": "m"}
    for bad in ({"max_pending": 11}, {"concurrency": "abc"}, {"unknown": 1}, {"enabled_global": "talvez"}):
        try:
            pconfig.validate_admin_updates(bad)
        except ValueError:
            pass
        else:
            raise AssertionError(f"deveria rejeitar {bad!r}")
    cfg = pconfig.build_config({"proactive_expiry_news_hours": "0", "proactive_expiry_default_days": "14"}, env={})
    assert cfg.expiry_news_hours == 48 and cfg.expiry_default_days == 14
