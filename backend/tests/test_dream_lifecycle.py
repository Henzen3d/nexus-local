import os
import tempfile
import time
from pathlib import Path
import pytest
import aiosqlite

from backend import database as dbmod
from backend.main import recover_interrupted_dreams
from backend.memory_dream import (
    DreamOperation,
    NewFactPayload,
    apply_dream_operations,
)


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
async def test_interrupted_dream_startup_recovery(temp_db):
    """An interrupted dream marked 'running' at server restart is safely recovered and marked 'failed'."""
    user_id = "user_crash_test"
    fid = await dbmod.add_memory_fact(user_id, "tech", "Usa Docker", "tech.docker")
    snap_id, _ = await dbmod.create_memory_snapshot(user_id, "dream_test")

    dream_id = await dbmod.record_dream_log({
        "user_id": user_id,
        "snapshot_id": snap_id,
        "status": "running",
    })

    # Simulate server crash and restart
    await recover_interrupted_dreams()

    logs = await dbmod.list_dream_logs(user_id)
    assert len(logs) == 1
    assert logs[0]["id"] == dream_id
    assert logs[0]["status"] == "failed"
    assert logs[0]["interrupted_fixed"] == 1


@pytest.mark.asyncio
async def test_project_memory_slug_isolation(temp_db):
    """Facts with project.<slug> are partitioned and their scopes stay separated."""
    user_id = "user_proj_iso"
    await dbmod.add_memory_fact(user_id, "project", "Usa Vite no frontend", "project.web_app.frontend")
    await dbmod.add_memory_fact(user_id, "project", "Usa PyTorch no worker", "project.ai_worker.backend")

    facts = await dbmod.get_user_memory(user_id, active_only=True)
    slugs = set()
    for f in facts:
        key = f.get("fact_key") or ""
        if key.startswith("project."):
            slugs.add(key.split(".")[1])

    assert "web_app" in slugs
    assert "ai_worker" in slugs
    assert len(slugs) == 2


@pytest.mark.asyncio
async def test_flash_transaction_speed(temp_db):
    """Flash transaction apply_dream_operations must complete under 200ms."""
    user_id = "user_speed_test"
    ids = []
    for i in range(10):
        fid = await dbmod.add_memory_fact(user_id, "general", f"Fato de teste rápido {i}")
        ids.append(fid)

    facts_before = await dbmod.get_user_memory(user_id, active_only=True)
    dream_id = "dream_fast"

    operations = [
        DreamOperation(
            action="merge",
            source_fact_ids=[ids[0], ids[1]],
            new_fact=NewFactPayload(category="general", fact="Fatos fundidos 0 e 1"),
        ),
        DreamOperation(action="keep", fact_id=ids[2]),
        DreamOperation(action="archive", fact_id=ids[3], reason="teste"),
    ]

    t0 = time.time()
    await apply_dream_operations(user_id, dream_id, operations, facts_before)
    duration_ms = (time.time() - t0) * 1000

    assert duration_ms < 200
