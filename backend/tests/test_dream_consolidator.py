import os
import tempfile
from pathlib import Path
import pytest
import aiosqlite

from backend import database as dbmod
from backend.memory_dream import (
    DreamOperation,
    NewFactPayload,
    DreamSafetyError,
    verify_dream_safety,
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


def test_verify_safety_preserves_pinned():
    """Pinned facts cannot be archived; if merged, is_pinned is inherited."""
    facts = [
        {"id": "fact_1", "fact": "Gosta de Python", "is_pinned": 1, "category": "tech"},
        {"id": "fact_2", "fact": "Gosta de FastAPI", "is_pinned": 0, "category": "tech"},
    ]

    # Attempting to archive a pinned fact must fail
    bad_op = [
        DreamOperation(action="archive", fact_id="fact_1", reason="Antigo"),
        DreamOperation(action="keep", fact_id="fact_2"),
    ]
    with pytest.raises(DreamSafetyError, match="PINNED"):
        verify_dream_safety(facts, bad_op)

    # Merging a pinned fact must set is_pinned = True on the new fact
    merge_op = [
        DreamOperation(
            action="merge",
            source_fact_ids=["fact_1", "fact_2"],
            new_fact=NewFactPayload(
                category="tech",
                fact="Especialista em Python e FastAPI",
                is_pinned=False,  # validator should auto-promote this!
            ),
        )
    ]
    verify_dream_safety(facts, merge_op)
    assert merge_op[0].new_fact.is_pinned is True


def test_verify_safety_aborts_excessive_deletion():
    """If > 60% of facts are archived for a bank with >= 8 facts, DreamSafetyError is raised."""
    facts = [{"id": f"f_{i}", "fact": f"Fato número {i}", "is_pinned": 0, "category": "general"} for i in range(10)]

    # 7 archives out of 10 = 70%
    ops = [DreamOperation(action="archive", fact_id=f"f_{i}", reason="ruido") for i in range(7)]
    ops.extend([DreamOperation(action="keep", fact_id=f"f_{i}") for i in range(7, 10)])

    with pytest.raises(DreamSafetyError, match="Taxa de arquivamento perigosa"):
        verify_dream_safety(facts, ops)


def test_verify_safety_aborts_unknown_id():
    """Referencing an ID that does not exist in facts_before must raise DreamSafetyError."""
    facts = [{"id": "fact_1", "fact": "Usa Linux", "is_pinned": 0, "category": "tech"}]
    ops = [DreamOperation(action="keep", fact_id="non_existent_id")]

    with pytest.raises(DreamSafetyError, match="ID inexistente"):
        verify_dream_safety(facts, ops)


@pytest.mark.asyncio
async def test_apply_dream_operations_merge_and_supersede(temp_db):
    """Applying merge and supersede operations updates statuses and lineages correctly."""
    user_id = "user_apply_test"
    id1 = await dbmod.add_memory_fact(user_id, "tech", "Usa React", "tech.react")
    id2 = await dbmod.add_memory_fact(user_id, "tech", "Usa NextJS", "tech.next")
    id3 = await dbmod.add_memory_fact(user_id, "personal", "Mora em SP", "location.city")
    id4 = await dbmod.add_memory_fact(user_id, "personal", "Trabalha remoto", "work.type")

    facts_before = await dbmod.get_user_memory(user_id, active_only=True)
    assert len(facts_before) == 4

    dream_id = "dream_123"

    operations = [
        # Merge id1 and id2
        DreamOperation(
            action="merge",
            source_fact_ids=[id1, id2],
            new_fact=NewFactPayload(
                category="tech",
                fact_key="tech.frontend_stack",
                fact="Stack frontend: React com NextJS",
                confidence=0.98,
                is_pinned=False,
            ),
        ),
        # Supersede id3 (moved to Curitiba)
        DreamOperation(
            action="supersede",
            old_fact_id=id3,
            new_fact=NewFactPayload(
                category="personal",
                fact_key="location.city",
                fact="Reside atualmente em Curitiba",
                confidence=0.95,
                is_pinned=False,
            ),
        ),
        # Keep id4
        DreamOperation(action="keep", fact_id=id4),
    ]

    stats = await apply_dream_operations(user_id, dream_id, operations, facts_before)
    assert stats["facts_merged"] == 2
    assert stats["facts_superseded"] == 1
    assert stats["facts_created"] == 2
    assert stats["facts_kept"] == 1

    # Check active facts
    active = await dbmod.get_user_memory(user_id, active_only=True)
    assert len(active) == 3  # 1 merged result + 1 supersede result + 1 kept

    active_texts = {f["fact"] for f in active}
    assert "Stack frontend: React com NextJS" in active_texts
    assert "Reside atualmente em Curitiba" in active_texts
    assert "Trabalha remoto" in active_texts

    # Check historical facts lineage
    all_facts = await dbmod.get_user_memory(user_id, active_only=False)
    id_map = {f["id"]: f for f in all_facts}

    assert id_map[id1]["status"] == "merged"
    assert id_map[id1]["is_active"] == 0
    assert id_map[id1]["superseded_by_id"] is not None

    assert id_map[id2]["status"] == "merged"
    assert id_map[id2]["is_active"] == 0
    assert id_map[id2]["superseded_by_id"] == id_map[id1]["superseded_by_id"]

    assert id_map[id3]["status"] == "superseded"
    assert id_map[id3]["is_active"] == 0
    assert id_map[id3]["superseded_by_id"] is not None
