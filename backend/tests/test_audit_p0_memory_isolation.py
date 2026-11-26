import logging
import os
import sqlite3
import tempfile
import aiosqlite
import pytest

import backend.database as db_mod
import backend.memory as mem_mod
import backend.cache.manager as cache_mod
import backend.orchestration.build_context as ctx_mod
from backend.context.request_context import RequestContext


@pytest.fixture
async def isolated_db(monkeypatch):
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    for mod in (db_mod, mem_mod, cache_mod, ctx_mod):
        monkeypatch.setattr(mod, "DB_PATH", path)
    await db_mod.init_db()

    # Evita carregamento pesado do FastEmbed neste teste unitário
    monkeypatch.setattr(db_mod, "_try_embed_fact", lambda _text: None)
    monkeypatch.setattr(
        mem_mod,
        "build_memory_fingerprint",
        mem_mod.build_memory_fingerprint,
    )

    async with aiosqlite.connect(path) as db:
        await db.execute(
            "INSERT INTO users (id, username, password_hash, email, role) VALUES (?, ?, ?, ?, ?)",
            ("u1", "alice", "hash", "alice@example.com", "user"),
        )
        await db.execute(
            "INSERT INTO users (id, username, password_hash, email, role) VALUES (?, ?, ?, ?, ?)",
            ("u2", "bob", "hash", "bob@example.com", "user"),
        )
        await db.execute(
            "INSERT INTO projects (id, user_id, name, instructions) VALUES (?, ?, ?, ?)",
            ("proj-alfa", "u1", "Projeto ALFA", "Use sempre contexto exclusivo do Alfa."),
        )
        await db.execute(
            "INSERT INTO projects (id, user_id, name, instructions) VALUES (?, ?, ?, ?)",
            ("proj-beta", "u1", "Projeto BETA", "Use sempre contexto exclusivo do Beta."),
        )
        await db.execute(
            "INSERT INTO conversations (id, user_id, title, project_id, project_tag) VALUES (?, ?, ?, ?, ?)",
            ("conv-alfa", "u1", "Chat Alfa", "proj-alfa", None),
        )
        await db.execute(
            "INSERT INTO conversations (id, user_id, title, project_id, project_tag) VALUES (?, ?, ?, ?, ?)",
            ("conv-beta", "u1", "Chat Beta", "proj-beta", None),
        )
        await db.execute(
            "INSERT INTO conversations (id, user_id, title, project_id, project_tag) VALUES (?, ?, ?, ?, ?)",
            ("conv-avulso", "u1", "Chat Avulso", None, None),
        )
        await db.commit()

    yield path

    for ext in ("", "-wal", "-shm"):
        p = path + ext
        if os.path.exists(p):
            try:
                os.remove(p)
            except OSError:
                pass


@pytest.mark.asyncio
async def test_project_memory_isolation_and_same_fact_key(isolated_db):
    alfa_id = await db_mod.add_memory_fact(
        "u1",
        "tech",
        "Banco de dados oficial PostgreSQL 16 exclusivo do projeto",
        "tech.db",
        source_conv_id="conv-alfa",
        scope="project",
        project_id="proj-alfa",
    )
    beta_id = await db_mod.add_memory_fact(
        "u1",
        "tech",
        "Banco de dados analitico DuckDB em memoria",
        "tech.db",
        source_conv_id="conv-beta",
        scope="project",
        project_id="proj-beta",
    )
    global_id = await db_mod.add_memory_fact(
        "u1",
        "preference",
        "Prefiro respostas diretas em portugues",
        "pref.language",
        source_conv_id="conv-avulso",
        scope="global",
    )

    assert alfa_id and beta_id and global_id
    assert alfa_id != beta_id

    # Mesmo fact_key em projetos diferentes coexistindo ativos ao mesmo tempo
    active_all = await db_mod.get_user_memory("u1", active_only=True)
    active_ids = {f["id"] for f in active_all}
    assert {alfa_id, beta_id, global_id}.issubset(active_ids)

    # Atualiza fact_key apenas em ALFA; BETA não é sobrescrito
    await db_mod.add_memory_fact(
        "u1",
        "tech",
        "Banco de dados oficial PostgreSQL 17 exclusivo do projeto",
        "tech.db",
        source_conv_id="conv-alfa",
        scope="project",
        project_id="proj-alfa",
    )
    beta_rows = await db_mod.get_user_memory("u1", active_only=True, scope="project", project_id="proj-beta")
    assert len(beta_rows) == 1
    assert "DuckDB" in beta_rows[0]["fact"]

    # Recuperação no projeto BETA (testando provedores openrouter e ollama)
    for provider in ("openrouter", "ollama"):
        ctx_beta = RequestContext(user_id="u1", conversation_id="conv-beta")
        mem_beta, fp_beta = await ctx_mod.build_memory_context(
            {"id": "u1"},
            "conv-beta",
            "Qual banco de dados usar e como prefiro respostas?",
            True,
            provider,
            "test-model",
            request_context=ctx_beta,
            active_project_id="proj-beta",
        )
        assert "DuckDB" in mem_beta
        assert "Prefiro respostas diretas" in mem_beta
        assert "PostgreSQL" not in mem_beta
        used = ctx_beta.get_memo("memory_used", [])
        used_facts = " ".join(u.get("fact", "") for u in used)
        assert "DuckDB" in used_facts
        assert "PostgreSQL" not in used_facts

    # Recuperação em conversa avulsa: apenas global, zero vazamento de ALFA ou BETA
    ctx_avulso = RequestContext(user_id="u1", conversation_id="conv-avulso")
    mem_avulso, fp_avulso = await ctx_mod.build_memory_context(
        {"id": "u1"},
        "conv-avulso",
        "Qual banco de dados usar e como prefiro respostas?",
        True,
        "openrouter",
        "test-model",
        request_context=ctx_avulso,
        active_project_id=None,
    )
    assert "Prefiro respostas diretas" in mem_avulso
    assert "PostgreSQL" not in mem_avulso
    assert "DuckDB" not in mem_avulso

    # Fingerprints distintos entre ALFA, BETA e avulso
    ctx_alfa = RequestContext(user_id="u1", conversation_id="conv-alfa")
    _, fp_alfa = await ctx_mod.build_memory_context(
        {"id": "u1"},
        "conv-alfa",
        "Qual banco de dados usar e como prefiro respostas?",
        True,
        "openrouter",
        "test-model",
        request_context=ctx_alfa,
        active_project_id="proj-alfa",
    )
    assert len({fp_alfa, fp_beta, fp_avulso}) == 3


@pytest.mark.asyncio
async def test_legacy_and_unknown_origin_conservative_isolation(isolated_db):
    async with aiosqlite.connect(isolated_db) as db:
        await db.execute(
            """INSERT INTO user_memory
               (id, user_id, category, fact, fact_key, source_conv_id, is_active, scope, project_id, scope_verified)
               VALUES (?, ?, ?, ?, ?, ?, 1, 'global', NULL, 0)""",
            ("leg-alfa", "u1", "work", "Segredo legado da conversa Alfa", "work.alfa", "conv-alfa"),
        )
        await db.execute(
            """INSERT INTO user_memory
               (id, user_id, category, fact, fact_key, source_conv_id, is_active, scope, project_id, scope_verified)
               VALUES (?, ?, ?, ?, ?, ?, 1, 'global', NULL, 0)""",
            ("leg-orphan", "u1", "work", "Dado antigo de origem removida", "work.orphan", "conv-apagada"),
        )
        # Permite reexecutar backfill idempotente no próximo init_db
        await db.execute("DELETE FROM meta WHERE key = 'memory_scope_backfilled_v1'")
        await db.commit()

    # Mesmo antes do backfill, a busca no BETA não pode receber nenhum dos dois
    pre_beta = await db_mod.get_relevant_memory(
        "u1",
        "Segredo legado dado antigo",
        project_id="proj-beta",
    )
    pre_ids = {r["id"] for r in pre_beta}
    assert "leg-alfa" not in pre_ids
    assert "leg-orphan" not in pre_ids

    await db_mod.init_db()

    rows = {r["id"]: r for r in await db_mod.get_user_memory("u1", active_only=True)}
    assert rows["leg-alfa"]["scope"] == "project"
    assert rows["leg-alfa"]["project_id"] == "proj-alfa"
    assert rows["leg-alfa"]["scope_verified"] == 1
    assert rows["leg-orphan"]["scope"] == "unknown"
    assert rows["leg-orphan"]["scope_verified"] == 0

    post_beta = await db_mod.get_relevant_memory(
        "u1",
        "Segredo legado dado antigo",
        project_id="proj-beta",
    )
    post_ids = {r["id"] for r in post_beta}
    assert "leg-alfa" not in post_ids
    assert "leg-orphan" not in post_ids


@pytest.mark.asyncio
async def test_promote_fact_to_global_and_invalidate_summaries_and_cache(isolated_db):
    alfa_id = await db_mod.add_memory_fact(
        "u1",
        "tech",
        "Stack obrigatoria em Rust com Tokio no servico Alfa",
        "tech.stack",
        source_conv_id="conv-alfa",
        scope="project",
        project_id="proj-alfa",
    )
    await mem_mod.refresh_memory_summaries("u1", use_llm=False)

    global_sum_before = await db_mod.get_memory_summary("u1", "global", "")
    alfa_sum_before = await db_mod.get_memory_summary("u1", "project", "proj-alfa")
    assert alfa_sum_before and "Rust" in alfa_sum_before["summary_md"]
    assert not global_sum_before or "Rust" not in global_sum_before.get("summary_md", "")

    async with aiosqlite.connect(isolated_db) as db:
        await db.execute(
            "INSERT INTO cache_exact (id, hash, model_id, response, user_id) VALUES (?, ?, ?, ?, ?)",
            ("c1", "h1", "m1", "resp u1", "u1"),
        )
        await db.execute(
            "INSERT INTO cache_exact (id, hash, model_id, response, user_id) VALUES (?, ?, ?, ?, ?)",
            ("c2", "h2", "m1", "resp u2", "u2"),
        )
        await db.commit()

    updated = await db_mod.update_memory_fact_scope("u1", alfa_id, "global")
    assert updated["scope"] == "global"
    assert updated["project_id"] is None
    assert updated["scope_verified"] == 1
    assert updated["version"] >= 2

    # Cache exato de u1 foi limpo; o de u2 foi preservado
    async with aiosqlite.connect(isolated_db) as db:
        async with db.execute("SELECT id FROM cache_exact") as cur:
            remaining = [r[0] for r in await cur.fetchall()]
    assert remaining == ["c2"]

    # Agora BETA consegue acessar o fato promovido a global
    ctx_beta = RequestContext(user_id="u1", conversation_id="conv-beta")
    mem_beta, _ = await ctx_mod.build_memory_context(
        {"id": "u1"},
        "conv-beta",
        "Qual stack em Rust usamos?",
        True,
        "openrouter",
        "m1",
        request_context=ctx_beta,
        active_project_id="proj-beta",
    )
    assert "Rust" in mem_beta


@pytest.mark.asyncio
async def test_auto_extractor_scoping_and_parse_error_no_leak(isolated_db, monkeypatch, caplog):
    async with aiosqlite.connect(isolated_db) as db:
        await db.execute(
            "INSERT INTO messages (id, conversation_id, role, content) VALUES (?, ?, ?, ?)",
            ("m1", "conv-alfa", "user", "Neste projeto usamos FastAPI e prefiro TypeScript limpo."),
        )
        await db.execute(
            "INSERT INTO messages (id, conversation_id, role, content) VALUES (?, ?, ?, ?)",
            ("m2", "conv-alfa", "assistant", "Entendido!"),
        )
        await db.commit()

    class _FakeProvider:
        def __init__(self, payload: str):
            self.payload = payload

        async def stream_chat(self, **_kwargs):
            yield self.payload

    async def _always_enabled(_db):
        return True

    monkeypatch.setattr(mem_mod, "is_memory_extractor_enabled", _always_enabled)

    # Caso 1: extração separa fato de projeto (inclusive mal rotulado como global) de preferência global
    good_json = (
        '[{"action":"upsert","category":"tech","fact":"Usa FastAPI como API principal","fact_key":"tech.api","scope":"project","confidence":0.9},'
        '{"action":"upsert","category":"preference","fact":"Prefere codigo TypeScript limpo","fact_key":"pref.ts","scope":"global","confidence":0.9},'
        '{"action":"upsert","category":"work","fact":"Nesse projeto o deploy roda em container Docker","fact_key":"work.deploy","scope":"global","confidence":0.8}]'
    )

    async def _good_provider(_db, _pid, _mid, _uid):
        return _FakeProvider(good_json), "fake-model", "test"

    monkeypatch.setattr(mem_mod, "_get_extractor_provider_and_model", _good_provider)
    await mem_mod.extract_user_memory_background("u1", "conv-alfa", "fake-model", "fake")

    facts = {f["fact_key"]: f for f in await db_mod.get_user_memory("u1", active_only=True)}
    assert facts["tech.api"]["scope"] == "project"
    assert facts["tech.api"]["project_id"] == "proj-alfa"
    assert facts["work.deploy"]["scope"] == "project"
    assert facts["work.deploy"]["project_id"] == "proj-alfa"
    assert facts["pref.ts"]["scope"] == "global"
    assert facts["pref.ts"]["project_id"] is None

    # Caso 2: resposta inválida do extrator não pode vazar payload bruto nos logs
    async def _bad_provider(_db, _pid, _mid, _uid):
        return _FakeProvider("RAW_SECRET_PAYLOAD_DO_NOT_LOG {{{invalid json"), "fake-model", "test"

    monkeypatch.setattr(mem_mod, "_get_extractor_provider_and_model", _bad_provider)
    caplog.set_level(logging.WARNING)
    await mem_mod.extract_user_memory_background("u1", "conv-alfa", "fake-model", "fake")

    joined_logs = "\n".join(rec.getMessage() for rec in caplog.records)
    assert "memory_extract_parse_error" in joined_logs
    assert "RAW_SECRET_PAYLOAD_DO_NOT_LOG" not in joined_logs
