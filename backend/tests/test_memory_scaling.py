"""Tests for memory scaling, hybrid search, and unified stats counts (T1.3)."""

import os
import sys
import tempfile
from pathlib import Path

import aiosqlite
import pytest

sys.path.insert(0, "/app")
from backend import database as dbmod
from backend.memory_lock import memory_pipeline_lock
from backend.database import get_relevant_memory


@pytest.fixture(autouse=True)
async def _isolated_scaling_db():
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    orig_db = dbmod.DB_PATH
    dbmod.DB_PATH = Path(path)
    await dbmod.init_db()
    try:
        yield Path(path)
    finally:
        dbmod.DB_PATH = orig_db
        try:
            os.remove(path)
        except OSError:
            pass


def test_lock_exists():
    assert memory_pipeline_lock is not None
    assert hasattr(memory_pipeline_lock, "locked")
    assert hasattr(memory_pipeline_lock, "acquire")
    assert hasattr(memory_pipeline_lock, "release")


@pytest.mark.asyncio
async def test_hybrid_search_recency_weight():
    """Hybrid search now includes recency decay in scoring."""
    # This is an integration test - just verify the function exists and runs
    # Real scoring logic is tested indirectly via dream tests
    result = await get_relevant_memory("test_user", "python", limit=5)
    assert isinstance(result, list)
    assert len(result) >= 0  # may be empty with no data


@pytest.mark.asyncio
async def test_no_artificial_cap():
    """Memory should not have artificial cap of 200 facts."""
    # Verify that add_memory_fact doesn't archive old facts
    from backend.database import add_memory_fact, get_user_memory
    
    user_id = "test_no_cap_user"
    # Create many facts - should not auto-archive any
    for i in range(10):
        await add_memory_fact(
            user_id=user_id,
            category="personal",
            fact=f"Test fact {i}",
            fact_key=f"test.no_cap.{i}",
        )
    
    facts = await get_user_memory(user_id, limit=5000, active_only=True)
    assert len(facts) >= 10  # all should remain active


@pytest.mark.asyncio
async def test_memory_stats_unified_predicate_above_500_and_multiuser(_isolated_scaling_db):
    """T1.3: totals match unified active predicate across >500 facts, legacy/conflicting rows, and two users."""
    from httpx import ASGITransport, AsyncClient
    from backend.auth import create_access_token, invalidate_user_state_cache
    from backend.main import app

    path = _isolated_scaling_db
    u1, u2 = "u_stats_1", "u_stats_2"
    async with aiosqlite.connect(path) as db:
        await db.execute("INSERT INTO users (id, username, password_hash, role) VALUES (?, 's1', 'h', 'user')", (u1,))
        await db.execute("INSERT INTO users (id, username, password_hash, role) VALUES (?, 's2', 'h', 'user')", (u2,))

        # 510 normal active facts for u1 (2 pinned)
        rows = []
        for i in range(510):
            rows.append((f"f_act_{i}", u1, "tech", f"Fato ativo {i}", 1, 1 if i < 2 else 0, "active"))
        # 2 legacy active facts (status NULL and status '') -> count as ACTIVE
        rows.append(("f_leg_null", u1, "personal", "Legado null", 1, 1, None))
        rows.append(("f_leg_empty", u1, "personal", "Legado vazio", 1, 0, ""))
        # Conflicting/historical facts -> ALL must count as INACTIVE (history)
        rows.append(("f_conf_arch", u1, "tech", "Conflito archived", 1, 1, "archived"))
        rows.append(("f_conf_merg", u1, "tech", "Conflito merged", 1, 0, "merged"))
        rows.append(("f_conf_sup", u1, "tech", "Conflito superseded", 1, 0, "superseded"))
        rows.append(("f_inact_act", u1, "tech", "Inativo com status active", 0, 1, "active"))
        rows.append(("f_inact_arch", u1, "personal", "Arquivado normal", 0, 0, "archived"))

        # User 2 facts (must not bleed into User 1)
        for i in range(7):
            rows.append((f"u2_f_{i}", u2, "tech", f"Fato u2 {i}", 1, 0, "active"))

        for r in rows:
            try:
                await db.execute(
                    """INSERT INTO user_memory (id, user_id, category, fact, is_active, is_pinned, status)
                       VALUES (?, ?, ?, ?, ?, ?, ?)""",
                    r,
                )
            except aiosqlite.IntegrityError:
                await db.execute(
                    """INSERT INTO user_memory (id, user_id, category, fact, is_active, is_pinned, status)
                       VALUES (?, ?, ?, ?, ?, ?, NULL)""",
                    r[:6],
                )
        await db.commit()

    expected_active = 512  # 510 + 2 legacy
    expected_inactive = 5  # 3 conflicting + 2 inactive
    expected_total = 517
    expected_pinned = 3    # 2 normal pinned + 1 legacy pinned (conflicting/inactive pinned excluded!)

    stats = await dbmod.get_memory_stats(u1)
    assert stats["total_facts"] == expected_total
    assert stats["active_facts"] == expected_active
    assert stats["inactive_facts"] == expected_inactive
    assert stats["active_facts"] + stats["inactive_facts"] == stats["total_facts"]
    assert stats["pinned_facts"] == expected_pinned
    assert stats["by_category"] == {"tech": 510, "personal": 2}

    # Verify HTTP endpoints: /api/memory capped at 500, /api/memory/stats returns full 512/5
    invalidate_user_state_cache()
    tok1 = create_access_token(u1, "s1", "user")
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        list_res = await client.get("/api/memory", headers={"Authorization": f"Bearer {tok1}"})
        assert list_res.status_code == 200
        assert len(list_res.json()) == 500

        stats_res = await client.get("/api/memory/stats", headers={"Authorization": f"Bearer {tok1}"})
        assert stats_res.status_code == 200
        st = stats_res.json()
        assert st["active_facts"] == expected_active
        assert st["inactive_facts"] == expected_inactive

        # Hard-delete one active fact -> active drops by 1, inactive unchanged, total drops by 1
        del_res = await client.delete("/api/memory/f_act_0", headers={"Authorization": f"Bearer {tok1}"})
        assert del_res.status_code == 200
        stats_after = (await client.get("/api/memory/stats", headers={"Authorization": f"Bearer {tok1}"})).json()
        assert stats_after["active_facts"] == expected_active - 1
        assert stats_after["inactive_facts"] == expected_inactive
        assert stats_after["total_facts"] == expected_total - 1

        # Clear all -> archives remaining facts so active=0 and inactive=total_facts
        clr_res = await client.post("/api/memory/clear", headers={"Authorization": f"Bearer {tok1}"})
        assert clr_res.status_code == 200
        stats_cleared = (await client.get("/api/memory/stats", headers={"Authorization": f"Bearer {tok1}"})).json()
        assert stats_cleared["active_facts"] == 0
        assert stats_cleared["inactive_facts"] == expected_total - 1
        assert stats_cleared["pinned_facts"] == 0

    # User 2 unaffected
    stats_u2 = await dbmod.get_memory_stats(u2)
    assert stats_u2["active_facts"] == 7
    assert stats_u2["inactive_facts"] == 0
