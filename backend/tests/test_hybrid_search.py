"""Testes para o motor de busca híbrida FTS5 BM25 + Vetores + Recência."""

import pytest
from backend.database import add_memory_fact, get_relevant_memory, get_memory_stats


@pytest.mark.asyncio
async def test_hybrid_search_exact_keyword_match():
    user_id = "test_hybrid_user"
    await add_memory_fact(user_id, "tech", "Servidor VPS configurado na porta 9090", "tech.server")
    await add_memory_fact(user_id, "personal", "Gosta de café colombiano pela manhã", "pref.coffee")

    # Busca por termo exato que FTS5 BM25 captura perfeitamente
    results = await get_relevant_memory(user_id, "porta 9090", limit=5)
    assert len(results) >= 1
    assert any("porta 9090" in r.get("fact", "") for r in results)


@pytest.mark.asyncio
async def test_memory_stats_includes_kb_and_clusters():
    user_id = "test_hybrid_user"
    stats = await get_memory_stats(user_id)
    assert "kb_estimate" in stats
    assert isinstance(stats["kb_estimate"], float)
    assert stats["active_facts"] >= 2
