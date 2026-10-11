"""Testes para o clustering semântico e empacotamento inteligente de lotes."""

import pytest
from backend.memory_dream import (
    cluster_facts_semantically,
    split_facts_for_budget,
    _fact_scope,
)


def test_fact_scope_segregation():
    facts = [
        {"id": "1", "category": "tech", "fact_key": "tech.python", "fact": "Usa Python"},
        {"id": "2", "category": "personal", "fact_key": "family.son", "fact": "Filho estuda matemática"},
        {"id": "3", "category": "project", "fact_key": "project.nexus.arch", "fact": "Projeto nexus usa SQLite"},
        {"id": "4", "category": "project", "fact_key": "project.crm.db", "fact": "Projeto CRM usa PostgreSQL"},
    ]
    scopes = [_fact_scope(f) for f in facts]
    assert scopes[0] == "tech"
    assert scopes[1] == "family"
    assert scopes[2] == "project:nexus"
    assert scopes[3] == "project:crm"


def test_cluster_facts_semantically_scopes():
    facts = [
        {"id": "1", "category": "tech", "fact_key": "tech.python", "fact": "Usa Python"},
        {"id": "2", "category": "personal", "fact_key": "family.son", "fact": "Filho estuda matemática"},
        {"id": "3", "category": "project", "fact_key": "project.nexus.arch", "fact": "Projeto nexus usa SQLite"},
    ]
    clusters = cluster_facts_semantically(facts)
    # Deve criar clusters separados por escopo rígido
    assert len(clusters) == 3


def test_split_facts_for_budget_preserves_clusters():
    facts = [
        {"id": f"id_{i}", "category": "tech", "fact_key": f"tech.{i}", "fact": f"Fato técnico número {i}"}
        for i in range(10)
    ]
    chunks = split_facts_for_budget(facts, system_prompt="System Prompt", max_tokens=6000)
    assert len(chunks) >= 1
    # Todos os 10 fatos devem estar presentes nos chunks
    all_ids = [f["id"] for chunk in chunks for f in chunk]
    assert len(all_ids) == 10
