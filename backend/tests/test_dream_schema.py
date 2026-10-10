import os
import tempfile
import json
import hashlib
from pathlib import Path
import pytest
import aiosqlite

from backend import database as dbmod


@pytest.fixture
async def temp_db():
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


@pytest.mark.asyncio
async def test_schema_migration_idempotent(temp_db):
    """Multiple init_db calls must be idempotent and preserve columns and tables."""
    await dbmod.init_db()
    await dbmod.init_db()

    async with aiosqlite.connect(temp_db) as db:
        # Check user_memory columns
        async with db.execute("PRAGMA table_info(user_memory)") as cur:
            columns = {row[1] for row in await cur.fetchall()}
            assert "status" in columns
            assert "superseded_by_id" in columns
            assert "source_dream_id" in columns
            assert "consolidated_at" in columns
            assert "version" in columns

        # Check memory_snapshots table
        async with db.execute("PRAGMA table_info(memory_snapshots)") as cur:
            snap_cols = {row[1] for row in await cur.fetchall()}
            assert "snapshot_hash" in snap_cols
            assert "snapshot_json" in snap_cols

        # Check dream_logs table
        async with db.execute("PRAGMA table_info(dream_logs)") as cur:
            log_cols = {row[1] for row in await cur.fetchall()}
            assert "status" in log_cols
            assert "facts_merged" in log_cols


@pytest.mark.asyncio
async def test_status_and_is_active_sync(temp_db):
    """Adding facts sets status='active' and is_active=1; deactivating sets status='archived' and is_active=0."""
    user_id = "user_test_1"
    fact_id = await dbmod.add_memory_fact(
        user_id=user_id,
        category="tech",
        fact="Prefere Python e FastAPI",
        fact_key="tech.backend",
    )

    facts = await dbmod.get_user_memory(user_id=user_id, active_only=True)
    assert len(facts) == 1
    assert facts[0]["id"] == fact_id
    assert facts[0]["is_active"] == 1
    assert facts[0]["status"] == "active"

    # Deactivate by key
    await dbmod.deactivate_memory_by_key(user_id=user_id, fact_key="tech.backend")

    all_facts = await dbmod.get_user_memory(user_id=user_id, active_only=False)
    assert len(all_facts) == 1
    assert all_facts[0]["is_active"] == 0
    assert all_facts[0]["status"] == "archived"


@pytest.mark.asyncio
async def test_create_snapshot_integrity(temp_db):
    """Snapshot saves accurate JSON and correct SHA-256 hash."""
    user_id = "user_snap_test"
    await dbmod.add_memory_fact(user_id, "tech", "Usa Docker", "tech.docker")
    await dbmod.add_memory_fact(user_id, "personal", "Mora em Curitiba", "location.city")

    snap_id, snap_hash = await dbmod.create_memory_snapshot(user_id, "dream_nightly")
    assert snap_id is not None
    assert len(snap_hash) == 64

    async with aiosqlite.connect(temp_db) as db:
        async with db.execute(
            "SELECT facts_count, snapshot_json, snapshot_hash FROM memory_snapshots WHERE id = ?",
            (snap_id,),
        ) as cur:
            row = await cur.fetchone()
            assert row is not None
            count, raw_json, saved_hash = row
            assert count == 2
            assert saved_hash == snap_hash
            calculated = hashlib.sha256(raw_json.encode("utf-8")).hexdigest()
            assert calculated == snap_hash


@pytest.mark.asyncio
async def test_surgical_rollback_preserves_new_user_facts(temp_db):
    """Rollback restores consolidated facts without deleting new manual facts created by the user."""
    user_id = "user_rollback_test"
    id1 = await dbmod.add_memory_fact(user_id, "tech", "Usa React", "tech.react")
    id2 = await dbmod.add_memory_fact(user_id, "tech", "Usa TypeScript", "tech.ts")

    # 1. Take snapshot before consolidation
    snap_id, _ = await dbmod.create_memory_snapshot(user_id, "dream_test")

    # 2. Simulate Dream consolidation creating log and consolidated fact
    dream_id = await dbmod.record_dream_log({
        "user_id": user_id,
        "snapshot_id": snap_id,
        "provider_id": "test",
        "model_id": "test-model",
        "facts_before": 2,
        "facts_after": 1,
        "facts_merged": 2,
        "status": "success",
    })

    # Consolidate id1 and id2 into new fact
    async with aiosqlite.connect(temp_db) as db:
        await db.execute(
            "UPDATE user_memory SET is_active = 0, status = 'merged', superseded_by_id = 'fact_merged_123' WHERE id IN (?, ?)",
            (id1, id2),
        )
        await db.execute(
            """INSERT INTO user_memory
               (id, user_id, category, fact, fact_key, is_active, status, source_dream_id)
               VALUES ('fact_merged_123', ?, 'tech', 'Stack: React com TypeScript', 'tech.frontend', 1, 'active', ?)""",
            (user_id, dream_id),
        )
        await db.commit()

    # 3. User adds a brand new fact AFTER the dream
    id_new = await dbmod.add_memory_fact(user_id, "personal", "Gosta de café expresso", "prefs.coffee")

    # Verify state before rollback: merged fact + user new fact active
    active_before = await dbmod.get_user_memory(user_id, active_only=True)
    active_ids_before = {f["id"] for f in active_before}
    assert "fact_merged_123" in active_ids_before
    assert id_new in active_ids_before
    assert id1 not in active_ids_before
    assert id2 not in active_ids_before

    # 4. Perform surgical rollback
    success = await dbmod.rollback_memory_snapshot(user_id, snap_id)
    assert success is True

    # 5. Verify state after rollback:
    # id1 and id2 are restored to active
    # fact_merged_123 is deactivated
    # id_new remains untouched and active!
    active_after = await dbmod.get_user_memory(user_id, active_only=True)
    active_ids_after = {f["id"] for f in active_after}
    assert id1 in active_ids_after
    assert id2 in active_ids_after
    assert id_new in active_ids_after
    assert "fact_merged_123" not in active_ids_after


@pytest.mark.asyncio
async def test_clear_all_memory_purges_snapshots(temp_db):
    """clear_all_memory (LGPD) archives facts, deletes snapshots, and marks dream_logs as purged_by_user."""
    user_id = "user_clear_test"
    await dbmod.add_memory_fact(user_id, "tech", "Usa Python", "tech.py")
    snap_id, _ = await dbmod.create_memory_snapshot(user_id, "test")
    await dbmod.record_dream_log({
        "user_id": user_id,
        "snapshot_id": snap_id,
        "status": "success",
    })

    await dbmod.clear_all_memory(user_id)

    # Active facts must be 0
    active = await dbmod.get_user_memory(user_id, active_only=True)
    assert len(active) == 0

    # Snapshots must be empty
    async with aiosqlite.connect(temp_db) as db:
        async with db.execute("SELECT COUNT(*) FROM memory_snapshots WHERE user_id = ?", (user_id,)) as cur:
            (snap_count,) = await cur.fetchone()
            assert snap_count == 0

        async with db.execute("SELECT status FROM dream_logs WHERE user_id = ?", (user_id,)) as cur:
            row = await cur.fetchone()
            assert row[0] == "purged_by_user"
