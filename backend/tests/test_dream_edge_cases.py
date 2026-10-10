import json
import os
import tempfile
from pathlib import Path
import pytest
from unittest.mock import AsyncMock, patch

from backend import database as dbmod
from backend.memory_dream import (
    execute_dream_consolidation,
    simulate_dream_consolidation,
    verify_dream_safety,
    DreamSafetyError,
    DreamOperation,
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
async def test_zero_facts_dream_noop(temp_db):
    """When a user has zero active facts, consolidation is a graceful no-op."""
    user_id = "user_zero_facts"
    res = await execute_dream_consolidation(user_id)
    assert res["status"] in ("no_op", "noop", "success")


@pytest.mark.asyncio
async def test_single_fact_consolidation_preservation(temp_db):
    """Excessive archival (>60%) raises DreamSafetyError to prevent mass deletion."""
    facts = [{"id": f"fact_{i}", "is_pinned": 0} for i in range(10)]
    # Propose archiving 7 out of 10 facts (70% > 60%)
    ops = [
        DreamOperation(
            action="archive",
            fact_id=f"fact_{i}",
            reason="teste excesso remocao",
        )
        for i in range(7)
    ]
    with pytest.raises(DreamSafetyError) as exc_info:
        verify_dream_safety(facts, ops)
    assert "Taxa de arquivamento perigosa" in str(exc_info.value)


@pytest.mark.asyncio
async def test_all_pinned_facts_protected(temp_db):
    """Pinned facts can never be archived, even if proposed by LLM."""
    user_id = "user_pinned"
    fid1 = await dbmod.add_memory_fact(user_id, "identity", "Nome: Osmar", "identity.name")
    fid2 = await dbmod.add_memory_fact(user_id, "preference", "Prefere respostas diretas", "prefs.style")
    await dbmod.set_memory_fact_pinned(user_id, fid1, True)
    await dbmod.set_memory_fact_pinned(user_id, fid2, True)

    facts = await dbmod.get_user_memory(user_id)
    assert len(facts) == 2
    assert all(f.get("is_pinned") == 1 for f in facts)

    # Attempt to archive a pinned fact must raise DreamSafetyError
    ops = [
        DreamOperation(
            action="archive",
            fact_id=fid1,
            reason="Tentativa ilegal",
        )
    ]
    with pytest.raises(DreamSafetyError) as exc_info:
        verify_dream_safety(facts, ops)
    assert "Tentativa ilegal de arquivar fato fixado" in str(exc_info.value)


@pytest.mark.asyncio
async def test_dry_run_preview_zero_mutations(temp_db):
    """Simulating consolidation returns projected changes without mutating the database."""
    user_id = "user_preview_nomut"
    fid1 = await dbmod.add_memory_fact(user_id, "tech", "Usa React", "tech.fe")
    fid2 = await dbmod.add_memory_fact(user_id, "tech", "Usa TypeScript", "tech.fe_lang")

    facts_before = await dbmod.get_user_memory(user_id)
    assert len(facts_before) == 2

    # Mock LLM call to simulate a merge proposal as JSON string
    mock_llm_response = {
        "summary_of_changes": "Merge React e TypeScript",
        "operations": [
            {
                "action": "merge",
                "source_fact_ids": [fid1, fid2],
                "new_fact": {
                    "category": "tech",
                    "fact_key": "tech.stack",
                    "fact": "Stack frontend: React + TypeScript",
                    "confidence": 0.95,
                    "is_pinned": False,
                },
                "reason": "Unificar stack",
            }
        ],
    }

    with patch(
        "backend.memory_dream.call_dream_llm",
        new=AsyncMock(return_value=json.dumps(mock_llm_response)),
    ):
        preview = await simulate_dream_consolidation(user_id)

    assert preview["facts_before"] == 2
    assert preview["actions_breakdown"]["merge"] == 1

    # Verify that database was NOT touched at all
    facts_after = await dbmod.get_user_memory(user_id)
    assert len(facts_after) == 2
    assert {f["id"] for f in facts_after} == {fid1, fid2}
    logs = await dbmod.list_dream_logs(user_id)
    assert len(logs) == 0
