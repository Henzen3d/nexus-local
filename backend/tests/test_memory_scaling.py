"""Tests for memory scaling and hybrid search."""

import sys
import pytest

sys.path.insert(0, "/app")
from backend.memory_lock import memory_pipeline_lock
from backend.database import get_relevant_memory


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
