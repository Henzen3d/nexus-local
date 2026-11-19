"""Testes de ciclo de vida e isolamento de contexto do chat (T3.2)."""

from __future__ import annotations

import asyncio
import os
import tempfile
import time
from pathlib import Path
from unittest.mock import AsyncMock, patch

import aiosqlite
import pytest

from backend import database as dbmod
from backend.context import RequestContext
from backend.orchestration import build_context as bc
from backend.projects import context_assembler as ca
from backend.routers import chat as chat_router


@pytest.fixture
async def isolated_chat_db(tmp_path, monkeypatch):
    db_file = tmp_path / "chat_context_lifecycle.db"
    monkeypatch.setattr(dbmod, "DB_PATH", db_file)
    monkeypatch.setattr(ca, "DB_PATH", str(db_file))
    await dbmod.init_db()
    return db_file


@pytest.mark.asyncio
async def test_request_context_embedding_reuse_and_timing():
    req_ctx = RequestContext(user_id="u1", conversation_id="c1")
    blob1 = b"fake-embedding-bytes-12345"

    with patch("backend.projects.embedder.embed_text_async", new_callable=AsyncMock) as mock_embed:
        mock_embed.return_value = blob1

        res1 = await req_ctx.get_embedding("Como integrar API?")
        assert res1 == blob1
        assert mock_embed.call_count == 1
        assert "fastembed_compute" in req_ctx.phase_latencies

        # Segunda chamada para mesmo texto deve retornar da RAM imediatamente sem nova chamada de embedding
        res2 = await req_ctx.get_embedding(" Como integrar API? ")
        assert res2 == blob1
        assert mock_embed.call_count == 1


@pytest.mark.asyncio
async def test_build_memory_context_partial_failure_survival(isolated_chat_db, monkeypatch):
    """Se uma das buscas de memória falhar com Exception, os dados úteis da outra devem ser preservados."""
    user = {"id": "u_test_mem"}
    async with aiosqlite.connect(isolated_chat_db) as db:
        await db.execute(
            "INSERT INTO users (id, username, password_hash) VALUES (?, ?, ?)",
            (user["id"], "alice", "hash"),
        )
        await db.execute(
            """INSERT INTO user_memory_summaries (id, user_id, scope, scope_ref, summary_md)
               VALUES (?, ?, 'global', '', 'Resumo Global: Usuário prefere TypeScript.')""",
            ("sum-1", user["id"]),
        )
        await db.commit()

    # Cenário 1: get_relevant_memory falha -> resumo global é preservado no prompt
    async def _failing_relevant(*args, **kwargs):
        raise RuntimeError("Vector search down")

    monkeypatch.setattr(bc, "get_relevant_memory", _failing_relevant)
    mem_text, fingerprint = await bc.build_memory_context(
        user=user,
        conversation_id="conv-1",
        user_message="Olá",
        use_memory=True,
        provider_id="local",
        model_id="local-test",
    )
    assert "Usuário prefere TypeScript" in mem_text
    assert fingerprint != ""

    external_text, external_fingerprint = await bc.build_memory_context(
        user, "conv-1", "Olá", True, "openai", "gpt-4o",
    )
    assert "Usuário prefere TypeScript" not in external_text
    assert external_fingerprint != fingerprint
    failover_text, _ = await bc.build_memory_context(
        user, "conv-1", "Olá", True, "local", "local-test", may_use_external_fallback=True,
    )
    assert "Usuário prefere TypeScript" not in failover_text

    # Cenário 2: get_memory_context_metadata falha -> fatos relevantes são preservados
    fake_fact = {
        "id": "f1",
        "fact": "Trabalha com backend em Python",
        "category": "professional",
        "source_confidence": 0.9,
    }

    async def _good_relevant(*args, **kwargs):
        return [fake_fact]

    async def _failing_metadata(*args, **kwargs):
        raise RuntimeError("Metadata sqlite error")

    monkeypatch.setattr(bc, "get_relevant_memory", _good_relevant)
    monkeypatch.setattr(bc, "get_memory_context_metadata", _failing_metadata)

    mem_text2, fingerprint2 = await bc.build_memory_context(
        user=user,
        conversation_id="conv-1",
        user_message="Olá",
        use_memory=True,
        provider_id="openai",
        model_id="gpt-4o",
    )
    assert "Trabalha com backend em Python" in mem_text2
    assert fingerprint2 != ""

    # Cenário 3: CancelledError NÃO é engolido, propaga para cima
    async def _cancelled_relevant(*args, **kwargs):
        raise asyncio.CancelledError()

    monkeypatch.setattr(bc, "get_relevant_memory", _cancelled_relevant)
    with pytest.raises(asyncio.CancelledError):
        await bc.build_memory_context(
            user=user,
            conversation_id="conv-1",
            user_message="Olá",
            use_memory=True,
            provider_id="openai",
            model_id="gpt-4o",
        )


@pytest.mark.asyncio
async def test_build_memory_context_concurrent_overlap(isolated_chat_db, monkeypatch):
    """Verifica que relevant_memory e memory_metadata rodam com barreira concorrente sobreposta."""
    user = {"id": "u_overlap"}
    barrier = asyncio.Barrier(2)
    phases_entered = []

    async def _slow_relevant(*args, **kwargs):
        phases_entered.append("relevant")
        await barrier.wait()
        return []

    async def _slow_metadata(*args, **kwargs):
        phases_entered.append("metadata")
        await barrier.wait()
        return None, None, None

    monkeypatch.setattr(bc, "get_relevant_memory", _slow_relevant)
    monkeypatch.setattr(bc, "get_memory_context_metadata", _slow_metadata)

    req_ctx = RequestContext(user_id=user["id"], conversation_id="c_overlap")
    await bc.build_memory_context(
        user=user,
        conversation_id="c_overlap",
        user_message="mensagem",
        use_memory=True,
        provider_id="openai",
        model_id="gpt-4o",
        request_context=req_ctx,
    )

    assert set(phases_entered) == {"relevant", "metadata"}
    assert "memory_relevance" in req_ctx.phase_latencies
    assert "db_memory_metadata" in req_ctx.phase_latencies


@pytest.mark.asyncio
async def test_project_context_ownership_isolation(isolated_chat_db):
    """Garante que projeto pertencente a outro usuário ou arquivado nunca é injetado e preserva prompt base com memória."""
    user_a = {"id": "user-a"}
    user_b = {"id": "user-b"}

    async with aiosqlite.connect(isolated_chat_db) as db:
        await db.execute("INSERT INTO users (id, username, password_hash) VALUES (?, ?, ?)", (user_a["id"], "ua", "p"))
        await db.execute("INSERT INTO users (id, username, password_hash) VALUES (?, ?, ?)", (user_b["id"], "ub", "p"))

        # Projeto do Usuário B (privado/ativo)
        await db.execute(
            """INSERT INTO projects (id, user_id, name, description, instructions, archived)
               VALUES (?, ?, ?, ?, ?, 0)""",
            ("proj-b-secret", user_b["id"], "Segredo B", "Confidencial", "Instruções ultra secretas"),
        )
        # Projeto do Usuário A, porém arquivado
        await db.execute(
            """INSERT INTO projects (id, user_id, name, description, instructions, archived)
               VALUES (?, ?, ?, ?, ?, 1)""",
            ("proj-a-archived", user_a["id"], "Projeto Antigo", "Desc", "Instrução antiga"),
        )
        # Conversa do Usuário A tentando apontar para projeto do Usuário B
        await db.execute(
            """INSERT INTO conversations (id, user_id, title, project_id)
               VALUES (?, ?, 'Chat A', 'proj-b-secret')""",
            ("conv-a", user_a["id"]),
        )
        await db.commit()

        # 1. Usuário A resolvendo contexto na conversa 'conv-a' NÃO deve carregar 'proj-b-secret'
        mock_ws = AsyncMock()
        resolved_pid, instruction = await bc.resolve_project_context(
            db=db,
            ws=mock_ws,
            conversation_id="conv-a",
            request_project_id="proj-b-secret",
            user=user_a,
            model_id="gpt-4o",
            provider_id="openai",
            user_message="Qual o segredo?",
            history=[],
            project_context_debug=False,
            base_system="Base Prompt.",
            user_mem_text="Memória do Usuário A elegível.",
        )
        assert resolved_pid is None, "Projeto de outro usuário não pode ser associado"
        assert "Instruções ultra secretas" not in instruction
        assert "Memória do Usuário A elegível." in instruction

        # 2. Usuário A tentando passar projeto arquivado
        resolved_pid_arch, instruction_arch = await bc.resolve_project_context(
            db=db,
            ws=mock_ws,
            conversation_id="conv-a",
            request_project_id="proj-a-archived",
            user=user_a,
            model_id="gpt-4o",
            provider_id="openai",
            user_message="teste",
            history=[],
            project_context_debug=False,
            base_system="Base Prompt.",
            user_mem_text="Memória elegível.",
        )
        assert resolved_pid_arch is None, "Projeto arquivado não pode ser associado"
        assert "Instrução antiga" not in instruction_arch
        assert "Memória elegível." in instruction_arch


@pytest.mark.asyncio
async def test_web_search_task_cancellation_and_telemetry_isolation(isolated_chat_db):
    """Verifica que _cancel_pending_task aguarda e cancela sem vazamentos e telemetria usa conexão dedicada."""
    started = asyncio.Event()

    async def _long_search():
        started.set()
        await asyncio.sleep(10)

    task = asyncio.create_task(_long_search())
    await started.wait()

    t0 = time.perf_counter()
    await chat_router._cancel_pending_task(task)
    assert task.cancelled() or task.done()
    assert (time.perf_counter() - t0) < 0.5, "Cancelamento deve ser rápido e imediato"

    # Telemetria com conexão curta própria
    await chat_router._record_web_search_telemetry(
        conversation_id="c_tel",
        message_id="m_tel",
        query="query teste",
        trigger_type="manual",
        results_count=4,
        user_id="u_tel",
    )

    db = await dbmod.get_db()
    try:
        async with db.execute(
            "SELECT query, trigger_type, results_count, user_id FROM web_search_log WHERE conversation_id = 'c_tel'"
        ) as cur:
            row = await cur.fetchone()
        assert row is not None
        assert row[0] == "query teste"
        assert row[1] == "manual"
        assert row[2] == 4
        assert row[3] == "u_tel"
    finally:
        await db.close()
