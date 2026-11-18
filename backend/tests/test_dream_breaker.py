import asyncio
import logging
import os
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

import aiosqlite
import pytest
from httpx import ASGITransport, AsyncClient

from backend import database as dbmod
from backend.auth import create_access_token, invalidate_user_state_cache
from backend.main import app, recover_interrupted_dreams, run_dream_consolidation_cycle
from backend.memory_dream import DreamSafetyError, run_dream_with_breaker


class FakeClock:
    def __init__(self, start: datetime):
        self.current = start

    def now(self) -> datetime:
        return self.current

    def advance(self, **kwargs) -> datetime:
        self.current = self.current + timedelta(**kwargs)
        return self.current


@pytest.fixture
async def isolated_db():
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    original_db = dbmod.DB_PATH
    dbmod.DB_PATH = Path(path)
    await dbmod.init_db()
    try:
        yield Path(path)
    finally:
        dbmod.DB_PATH = original_db
        try:
            os.remove(path)
        except OSError:
            pass


async def _seed_user(user_id: str, username: str, role: str = "user", active_facts: int = 6):
    async with aiosqlite.connect(dbmod.DB_PATH) as db:
        await db.execute(
            """INSERT OR IGNORE INTO users (id, username, password_hash, role)
               VALUES (?, ?, 'hash', ?)""",
            (user_id, username, role),
        )
        await db.commit()
    for i in range(active_facts):
        await dbmod.add_memory_fact(user_id, "tech", f"Fato tecnico de teste numero {i} para {user_id}")


@pytest.mark.asyncio
async def test_idempotent_migration_and_integrity_check(isolated_db):
    """init_db() is idempotent and database passes PRAGMA integrity_check."""
    await dbmod.init_db()
    async with aiosqlite.connect(isolated_db) as db:
        async with db.execute("PRAGMA integrity_check") as cur:
            row = await cur.fetchone()
        assert row and row[0] == "ok"
        async with db.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='dream_breaker_state'"
        ) as cur:
            tbl = await cur.fetchone()
        assert tbl is not None


@pytest.mark.asyncio
async def test_three_failures_open_once_no_warn_spam_and_probe_lifecycle(isolated_db, caplog):
    """3 operational failures open once; OPEN cycles don't spam WARN; probe after cooldown closes or reopens."""
    uid = "u_breaker_main"
    await _seed_user(uid, "breaker_main", active_facts=6)

    clock = FakeClock(datetime(2026, 11, 18, 12, 0, 0, tzinfo=timezone.utc))
    async with aiosqlite.connect(isolated_db) as db:
        await db.execute(
            "INSERT OR REPLACE INTO meta (key, value) VALUES ('dream_breaker_cooldown_minutes', '60')"
        )
        await db.commit()

    calls = 0

    async def failing_consolidator(**kwargs):
        nonlocal calls
        calls += 1
        raise RuntimeError("503 service unavailable")

    with caplog.at_level(logging.WARNING):
        # 1st and 2nd failures keep breaker closed
        await run_dream_consolidation_cycle(
            consolidator=failing_consolidator, now_fn=clock.now, inter_user_delay_s=0
        )
        st = await dbmod.get_dream_breaker_status(uid, now=clock.now())
        assert st["state"] == "closed"
        assert st["consecutive_failures"] == 1

        clock.advance(minutes=5)
        await run_dream_consolidation_cycle(
            consolidator=failing_consolidator, now_fn=clock.now, inter_user_delay_s=0
        )
        st = await dbmod.get_dream_breaker_status(uid, now=clock.now())
        assert st["state"] == "closed"
        assert st["consecutive_failures"] == 2
        assert len([r for r in caplog.records if "Dream Circuit Breaker" in r.message]) == 0

        # 3rd failure opens the breaker and logs WARN exactly once
        clock.advance(minutes=5)
        await run_dream_consolidation_cycle(
            consolidator=failing_consolidator, now_fn=clock.now, inter_user_delay_s=0
        )
        st = await dbmod.get_dream_breaker_status(uid, now=clock.now())
        assert st["state"] == "open"
        assert st["consecutive_failures"] == 3
        assert st["retry_at"] is not None
        open_warns = [r for r in caplog.records if "Dream Circuit Breaker" in r.message]
        assert len(open_warns) == 1
        assert calls == 3

        # Multiple OPEN cycles before cooldown do NOT call consolidator and do NOT repeat WARN
        for _ in range(3):
            clock.advance(minutes=15)
            res = await run_dream_consolidation_cycle(
                consolidator=failing_consolidator, now_fn=clock.now, inter_user_delay_s=0
            )
            assert res["skipped_breaker"] == 1
        assert calls == 3
        assert len([r for r in caplog.records if "Dream Circuit Breaker" in r.message]) == 1

        # Advance past 60m cooldown -> half_open probe executes; if it fails, reopens with new retry_at
        clock.advance(minutes=20)  # total 65m since 3rd failure
        st_half = await dbmod.get_dream_breaker_status(uid, now=clock.now())
        assert st_half["state"] == "half_open"

        old_retry_at = st["retry_at"]
        await run_dream_consolidation_cycle(
            consolidator=failing_consolidator, now_fn=clock.now, inter_user_delay_s=0
        )
        assert calls == 4
        st_reopened = await dbmod.get_dream_breaker_status(uid, now=clock.now())
        assert st_reopened["state"] == "open"
        assert st_reopened["consecutive_failures"] == 4
        assert st_reopened["retry_at"] != old_retry_at
        assert len([r for r in caplog.records if "Dream Circuit Breaker" in r.message]) == 2

    # Advance past new cooldown -> probe succeeds -> closes and resets counter to 0
    clock.advance(minutes=61)

    async def succeeding_consolidator(**kwargs):
        nonlocal calls
        calls += 1
        return {"status": "success", "dream_id": "d-ok"}

    res = await run_dream_consolidation_cycle(
        consolidator=succeeding_consolidator, now_fn=clock.now, inter_user_delay_s=0
    )
    assert res["executed"] == 1
    assert calls == 5
    st_closed = await dbmod.get_dream_breaker_status(uid, now=clock.now())
    assert st_closed["state"] == "closed"
    assert st_closed["consecutive_failures"] == 0
    assert st_closed["retry_at"] is None


@pytest.mark.asyncio
async def test_parallel_probe_acquires_at_most_one(isolated_db):
    """Two concurrent probe acquisitions after cooldown allow at most one probe."""
    uid = "u_parallel_probe"
    await _seed_user(uid, "parallel_probe", active_facts=6)
    t0 = datetime(2026, 11, 18, 12, 0, 0, tzinfo=timezone.utc)

    for i in range(3):
        await dbmod.record_dream_attempt(uid, 0, "failure", now=t0 + timedelta(minutes=i), cooldown_minutes=30)

    t_probe = t0 + timedelta(minutes=40)
    r1, r2 = await asyncio.gather(
        dbmod.try_acquire_dream_probe(uid, now=t_probe, cooldown_minutes=30),
        dbmod.try_acquire_dream_probe(uid, now=t_probe, cooldown_minutes=30),
    )
    allowed_count = int(bool(r1["allowed"])) + int(bool(r2["allowed"]))
    assert allowed_count == 1
    modes = {r1["mode"], r2["mode"]}
    assert modes == {"probe", "probe_busy"}


@pytest.mark.asyncio
async def test_neutral_outcomes_do_not_trip_breaker_and_release_probe(isolated_db):
    """no_op, DreamSafetyError, and CancelledError never count as operational failure and release probes."""
    uid = "u_neutral"
    await _seed_user(uid, "neutral_user", active_facts=6)
    clock = FakeClock(datetime(2026, 11, 18, 14, 0, 0, tzinfo=timezone.utc))

    # no_op
    async def noop_fn(**kwargs):
        return {"status": "no_op"}

    res = await run_dream_with_breaker(uid, consolidator=noop_fn, now_fn=clock.now, respect_breaker=True)
    assert res["status"] == "no_op"
    st = await dbmod.get_dream_breaker_status(uid, now=clock.now())
    assert st["consecutive_failures"] == 0

    # safety abort
    async def safety_fn(**kwargs):
        raise DreamSafetyError("too aggressive")

    with pytest.raises(DreamSafetyError):
        await run_dream_with_breaker(uid, consolidator=safety_fn, now_fn=clock.now, respect_breaker=True)
    st = await dbmod.get_dream_breaker_status(uid, now=clock.now())
    assert st["consecutive_failures"] == 0

    # cancelled during half-open probe releases lease without incrementing failures
    for _ in range(3):
        await dbmod.record_dream_attempt(uid, 0, "failure", now=clock.now(), cooldown_minutes=10)
    clock.advance(minutes=15)

    async def cancel_fn(**kwargs):
        raise asyncio.CancelledError()

    with pytest.raises(asyncio.CancelledError):
        await run_dream_with_breaker(
            uid, consolidator=cancel_fn, now_fn=clock.now, respect_breaker=True, cooldown_minutes=10
        )
    st = await dbmod.get_dream_breaker_status(uid, now=clock.now(), cooldown_minutes=10)
    assert st["state"] == "half_open"
    assert st["consecutive_failures"] == 3
    assert st["probe_until"] is None


@pytest.mark.asyncio
async def test_reset_generation_fencing_isolation_and_no_rebootstrap(isolated_db):
    """Reset isolates users, survives reload, preserves history/snapshots, fences stale probes, and never re-bootstraps."""
    u1, u2 = "u_iso_1", "u_iso_2"
    await _seed_user(u1, "iso1", active_facts=6)
    await _seed_user(u2, "iso2", active_facts=6)
    t0 = datetime(2026, 11, 18, 10, 0, 0, tzinfo=timezone.utc)

    # Seed historical 3 failed logs + snapshot for u1 (legacy naive SQLite timestamps)
    snap_id, _ = await dbmod.create_memory_snapshot(u1, "dream_test")
    async with aiosqlite.connect(isolated_db) as db:
        for idx in range(3):
            ts = (t0 + timedelta(minutes=idx)).strftime("%Y-%m-%d %H:%M:%S")
            await db.execute(
                """INSERT INTO dream_logs
                   (id, user_id, snapshot_id, provider_id, model_id,
                    facts_before, facts_after, facts_merged, facts_superseded,
                    facts_created, facts_total_active, duration_ms, status, created_at)
                   VALUES (?, ?, ?, 'p', 'm', 6, 6, 0, 0, 0, 6, 100, 'failed', ?)""",
                (f"legacy_fail_{idx}", u1, snap_id, ts),
            )
        await db.commit()

    # First access bootstraps u1 as OPEN from historical failures
    st1 = await dbmod.get_dream_breaker_status(u1, now=t0 + timedelta(minutes=10), cooldown_minutes=60)
    assert st1["state"] == "open"
    assert st1["consecutive_failures"] == 3

    # Open u2 as well
    for idx in range(3):
        await dbmod.record_dream_attempt(u2, 0, "failure", now=t0 + timedelta(minutes=idx), cooldown_minutes=60)
    st2 = await dbmod.get_dream_breaker_status(u2, now=t0 + timedelta(minutes=10), cooldown_minutes=60)
    assert st2["state"] == "open"

    # Acquire a probe on u1 after cooldown, then reset u1 BEFORE the probe finishes
    t_probe = t0 + timedelta(minutes=70)
    probe = await dbmod.try_acquire_dream_probe(u1, now=t_probe, cooldown_minutes=60)
    assert probe["allowed"] is True
    stale_gen = probe["generation"]

    reset_res = await dbmod.reset_dream_breaker(u1, now=t_probe + timedelta(seconds=5))
    assert reset_res["state"] == "closed"
    assert reset_res["consecutive_failures"] == 0
    assert reset_res["generation"] == stale_gen + 1

    # Stale probe fails -> ignored because generation changed!
    stale_record = await dbmod.record_dream_attempt(
        u1, stale_gen, "failure", now=t_probe + timedelta(seconds=10), cooldown_minutes=60
    )
    assert stale_record["ignored_stale_generation"] is True
    assert stale_record["state"] == "closed"

    # Reloading status does NOT re-bootstrap from the 3 historical failed logs
    st1_after = await dbmod.get_dream_breaker_status(u1, now=t_probe + timedelta(seconds=20), cooldown_minutes=60)
    assert st1_after["state"] == "closed"
    assert st1_after["consecutive_failures"] == 0

    # Snapshots & dream_logs preserved
    assert len(await dbmod.list_memory_snapshots(u1)) == 1
    assert len(await dbmod.list_dream_logs(u1)) == 3

    # User 2 remains unaffected (still open)
    st2_after = await dbmod.get_dream_breaker_status(u2, now=t0 + timedelta(minutes=15), cooldown_minutes=60)
    assert st2_after["state"] == "open"


@pytest.mark.asyncio
async def test_legacy_naive_timestamps_and_last_success_outside_top3(isolated_db):
    """Last success outside top-3 logs is found accurately, even with legacy naive SQLite timestamps."""
    uid = "u_legacy_ts"
    await _seed_user(uid, "legacy_ts", active_facts=6)
    base = datetime(2026, 11, 18, 12, 0, 0, tzinfo=timezone.utc)

    async with aiosqlite.connect(isolated_db) as db:
        # 1 success 2 hours ago (naive SQLite format), followed by 2 failed + 2 aborted_safety
        # So the success is at position #5 (outside top 3!)
        entries = [
            ("d_succ", "success", (base - timedelta(hours=2)).strftime("%Y-%m-%d %H:%M:%S")),
            ("d_ab1", "aborted_safety", (base - timedelta(minutes=90)).strftime("%Y-%m-%d %H:%M:%S")),
            ("d_f1", "failed", (base - timedelta(minutes=60)).strftime("%Y-%m-%d %H:%M:%S")),
            ("d_ab2", "aborted_safety", (base - timedelta(minutes=40)).strftime("%Y-%m-%d %H:%M:%S")),
            ("d_f2", "failed", (base - timedelta(minutes=20)).strftime("%Y-%m-%d %H:%M:%S")),
        ]
        for lid, status, ts in entries:
            await db.execute(
                """INSERT INTO dream_logs
                   (id, user_id, provider_id, model_id,
                    facts_before, facts_after, facts_merged, facts_superseded,
                    facts_created, facts_total_active, duration_ms, status, created_at)
                   VALUES (?, ?, 'p', 'm', 6, 6, 0, 0, 0, 6, 50, ?, ?)""",
                (lid, uid, status, ts),
            )
        await db.commit()

    # get_last_dream_success_at finds d_succ even though top 3 has no 'success'
    last_succ = await dbmod.get_last_dream_success_at(uid)
    assert last_succ is not None

    # Because min_hours defaults to 24h and last success was 2h ago, cycle must NOT run
    called = 0

    async def should_not_run(**kwargs):
        nonlocal called
        called += 1
        return {"status": "success"}

    await run_dream_consolidation_cycle(
        consolidator=should_not_run, now_fn=lambda: base, inter_user_delay_s=0
    )
    assert called == 0


@pytest.mark.asyncio
async def test_startup_recovery_clears_orphan_probes(isolated_db):
    """recover_interrupted_dreams clears orphan probe_until leases left after process restart."""
    uid = "u_orphan"
    await _seed_user(uid, "orphan", active_facts=6)
    t0 = datetime(2026, 11, 18, 12, 0, 0, tzinfo=timezone.utc)
    for i in range(3):
        await dbmod.record_dream_attempt(uid, 0, "failure", now=t0 + timedelta(minutes=i), cooldown_minutes=10)

    probe = await dbmod.try_acquire_dream_probe(uid, now=t0 + timedelta(minutes=20), cooldown_minutes=10)
    assert probe["allowed"] is True
    assert probe["probe_until"] is not None

    await recover_interrupted_dreams()

    st = await dbmod.get_dream_breaker_status(uid, now=t0 + timedelta(minutes=21), cooldown_minutes=10)
    assert st["state"] == "half_open"
    assert st["probe_until"] is None


@pytest.mark.asyncio
async def test_http_endpoints_auth_isolation_and_config_validation(isolated_db):
    """GET/POST dream-breaker enforce 401, scope to authenticated user, and dream-config validates cooldown."""
    u1, u2 = "u_api_1", "u_api_2"
    await _seed_user(u1, "api1", role="admin", active_facts=6)
    await _seed_user(u2, "api2", role="user", active_facts=6)

    invalidate_user_state_cache()
    tok1 = create_access_token(u1, "api1", "admin")
    tok2 = create_access_token(u2, "api2", "user")
    now = datetime.now(timezone.utc)
    for _ in range(3):
        await dbmod.record_dream_attempt(u1, 0, "failure", now=now, cooldown_minutes=60)
        await dbmod.record_dream_attempt(u2, 0, "failure", now=now, cooldown_minutes=60)

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # Unauthenticated / invalid bearer token -> 401 (or 403 when Authorization header omitted)
        r = await client.get("/api/memory/dream-breaker")
        assert r.status_code in (401, 403)
        r = await client.get("/api/memory/dream-breaker", headers={"Authorization": "Bearer invalid-token"})
        assert r.status_code == 401
        r = await client.post("/api/memory/dream-breaker/reset", headers={"Authorization": "Bearer invalid-token"})
        assert r.status_code == 401

        # Authenticated u1 sees open state
        r = await client.get("/api/memory/dream-breaker", headers={"Authorization": f"Bearer {tok1}"})
        assert r.status_code == 200
        body = r.json()
        assert body["state"] == "open"
        assert body["consecutive_failures"] == 3
        assert body["retry_at"] is not None

        # u1 resets -> only u1 closes, u2 remains open
        r = await client.post("/api/memory/dream-breaker/reset", headers={"Authorization": f"Bearer {tok1}"})
        assert r.status_code == 200
        assert r.json() == {"state": "closed", "consecutive_failures": 0, "retry_at": None}

        r2 = await client.get("/api/memory/dream-breaker", headers={"Authorization": f"Bearer {tok2}"})
        assert r2.status_code == 200
        assert r2.json()["state"] == "open"

        # Config validation for dream_breaker_cooldown_minutes (1..1440)
        bad_low = await client.put(
            "/api/memory/dream-config",
            json={"dream_breaker_cooldown_minutes": 0},
            headers={"Authorization": f"Bearer {tok1}"},
        )
        assert bad_low.status_code == 422

        bad_high = await client.put(
            "/api/memory/dream-config",
            json={"dream_breaker_cooldown_minutes": 1441},
            headers={"Authorization": f"Bearer {tok1}"},
        )
        assert bad_high.status_code == 422

        ok_cfg = await client.put(
            "/api/memory/dream-config",
            json={"dream_breaker_cooldown_minutes": 45},
            headers={"Authorization": f"Bearer {tok1}"},
        )
        assert ok_cfg.status_code == 200

        got_cfg = await client.get("/api/memory/dream-config", headers={"Authorization": f"Bearer {tok1}"})
        assert got_cfg.status_code == 200
        assert got_cfg.json()["dream_breaker_cooldown_minutes"] == 45
