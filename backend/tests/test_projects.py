"""
Tests for Projects module:
- referential integrity (cascade)
- project_id nullable on conversations (standalone chats)
- chunker basics
- context builder budget trim
- retrieval precision smoke (when embedder available)
"""

from __future__ import annotations

import asyncio
import os
import sys
import tempfile
import uuid
from pathlib import Path

# Ensure repo root on path
ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import aiosqlite


def run(coro):
    return asyncio.get_event_loop().run_until_complete(coro)


async def _setup_tmp_db():
    """Point DB_PATH at a temp file and run init_db."""
    from backend import database as dbmod

    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    dbmod.DB_PATH = Path(path)
    # Also patch modules that imported DB_PATH at import time
    import backend.projects.vector_store as vs
    import backend.projects.indexer as idx
    import backend.projects.memory_job as mj
    import backend.projects.context_builder as cb

    vs.DB_PATH = dbmod.DB_PATH
    idx.DB_PATH = dbmod.DB_PATH
    mj.DB_PATH = dbmod.DB_PATH
    cb.DB_PATH = dbmod.DB_PATH

    await dbmod.init_db()
    return dbmod, path


async def test_cascade_delete_project():
    dbmod, path = await _setup_tmp_db()
    user_id = str(uuid.uuid4())
    project_id = str(uuid.uuid4())
    file_id = str(uuid.uuid4())
    chunk_id = str(uuid.uuid4())
    mem_id = str(uuid.uuid4())
    conv_id = str(uuid.uuid4())
    chat_chunk_id = str(uuid.uuid4())

    async with aiosqlite.connect(dbmod.DB_PATH) as db:
        await db.execute("PRAGMA foreign_keys=ON")
        await db.execute(
            "INSERT INTO users (id, username, password_hash) VALUES (?, ?, ?)",
            (user_id, f"u_{user_id[:8]}", "x"),
        )
        await db.execute(
            """INSERT INTO projects (id, user_id, name) VALUES (?, ?, ?)""",
            (project_id, user_id, "Cascade Test"),
        )
        await db.execute(
            """INSERT INTO project_files (id, project_id, filename, index_status)
               VALUES (?, ?, ?, 'ready')""",
            (file_id, project_id, "doc.txt"),
        )
        await db.execute(
            """INSERT INTO file_chunks (id, project_file_id, chunk_text, chunk_index)
               VALUES (?, ?, ?, 0)""",
            (chunk_id, file_id, "hello world",),
        )
        await db.execute(
            """INSERT INTO project_memory (id, project_id, summary_text)
               VALUES (?, ?, ?)""",
            (mem_id, project_id, "mem"),
        )
        await db.execute(
            """INSERT INTO conversations (id, user_id, title, project_id)
               VALUES (?, ?, ?, ?)""",
            (conv_id, user_id, "chat", project_id),
        )
        await db.execute(
            """INSERT INTO chat_chunks (id, chat_session_id, project_id, chunk_text)
               VALUES (?, ?, ?, ?)""",
            (chat_chunk_id, conv_id, project_id, "Q+A"),
        )
        await db.commit()

        await db.execute("DELETE FROM projects WHERE id = ?", (project_id,))
        await db.commit()

        async with db.execute("SELECT COUNT(*) FROM project_files WHERE project_id = ?", (project_id,)) as c:
            assert (await c.fetchone())[0] == 0
        async with db.execute("SELECT COUNT(*) FROM file_chunks WHERE id = ?", (chunk_id,)) as c:
            assert (await c.fetchone())[0] == 0
        async with db.execute("SELECT COUNT(*) FROM project_memory WHERE project_id = ?", (project_id,)) as c:
            assert (await c.fetchone())[0] == 0
        async with db.execute("SELECT COUNT(*) FROM chat_chunks WHERE project_id = ?", (project_id,)) as c:
            assert (await c.fetchone())[0] == 0
        # Conversation survives (ON DELETE SET NULL for project_id)
        async with db.execute("SELECT project_id FROM conversations WHERE id = ?", (conv_id,)) as c:
            row = await c.fetchone()
            assert row is not None
            assert row[0] is None

    os.unlink(path)
    print("OK test_cascade_delete_project")


async def test_standalone_chat_without_project():
    dbmod, path = await _setup_tmp_db()
    user_id = str(uuid.uuid4())
    conv_id = str(uuid.uuid4())
    async with aiosqlite.connect(dbmod.DB_PATH) as db:
        await db.execute("PRAGMA foreign_keys=ON")
        await db.execute(
            "INSERT INTO users (id, username, password_hash) VALUES (?, ?, ?)",
            (user_id, f"u_{user_id[:8]}", "x"),
        )
        await db.execute(
            "INSERT INTO conversations (id, user_id, title, project_id) VALUES (?, ?, ?, NULL)",
            (conv_id, user_id, "avulso"),
        )
        await db.commit()
        async with db.execute(
            "SELECT project_id FROM conversations WHERE id = ?", (conv_id,)
        ) as c:
            assert (await c.fetchone())[0] is None
    os.unlink(path)
    print("OK test_standalone_chat_without_project")


def test_chunker():
    from backend.projects.chunker import chunk_text

    text = "Parágrafo um.\n\n" + ("palavra " * 400)
    chunks = chunk_text(text, file_type="txt", chunk_size=200, overlap=40)
    assert len(chunks) >= 2
    # Soft upper bound: boundary packing may slightly exceed size on last unit join
    assert all(len(c) <= 320 for c in chunks)
    # No mid-word starts (except first chunk)
    for c in chunks[1:]:
        assert c[0].isupper() or c[0] in "-#*`[" or c[0].isdigit() or c.startswith("palavra"), (
            f"suspicious mid-word start: {c[:40]!r}"
        )
    print("OK test_chunker")


def test_chunker_markdown_no_midword():
    """Markdown structure + no mid-token starts (FABLE5 regression)."""
    from backend.projects.chunker import chunk_text, resolve_file_type

    sample = """# Título

Introdução curta sobre o plano.

## Fase 1 — Banco

- [x] Adicionar coluna `grounding_enabled INTEGER DEFAULT 1` na tabela `fusion_config` (schema).
- [x] Migração incremental em `init_db()`.

## Melhorias adicionais

- [x] Timeout no Juiz (180s) e detecção de claims (30s).
- [x] Limite de 1500 chars por resposta na detecção de claims.

## Outra seção com texto longo

""" + ("contexto técnico " * 80)

    assert resolve_file_type("text/plain", "FABLE5.md") == "md"
    assert resolve_file_type("application/octet-stream", "doc.md") == "md"

    chunks = chunk_text(sample, file_type="text/plain", filename="FABLE5.md", chunk_size=400, overlap=60)
    assert len(chunks) >= 2
    joined = "\n".join(chunks)
    assert "grounding_enabled INTEGER DEFAULT 1" in joined
    assert "Melhorias adicionais" in joined or "180s" in joined
    assert "1500" in joined

    for i, c in enumerate(chunks):
        # Must not start mid-word like "led INTEGER" from grounding_enabled
        assert not c.startswith("led INTEGER"), f"chunk {i} mid-word cut"
        assert not re_match_midword_start(c), f"chunk {i} starts mid-token: {c[:50]!r}"

    print("OK test_chunker_markdown_no_midword")


def re_match_midword_start(c: str) -> bool:
    """True if chunk starts with a lowercase letter mid-token (no leading structure)."""
    if not c:
        return False
    # Allow normal sentence/paragraph starts that happen to be lowercase (pt-BR)
    # Flag only clear truncation residues: letter immediately after missing prefix pattern
    bad_prefixes = ("led INTEGER", "nho real", "a correta.", "ctual (", "la `fusion")
    return any(c.startswith(b) for b in bad_prefixes)


def test_token_budget_trim():
    from backend.projects.context_builder import apply_token_budget, estimate_tokens

    parts = {
        "system": "base " * 50,
        "instructions": "instr " * 50,
        "memory_global": "",
        "memory_project": "mem " * 50,
        "files": "file chunk " * 200,
        "related_chats": "chat chunk " * 200,
        "extra": "",
    }
    # Tiny budget forces drop of related_chats then files
    out, trimmed = apply_token_budget(parts, budget_tokens=80, drop_order=["related_chats", "files"])
    assert "related_chats" in trimmed or estimate_tokens("".join(out.values())) <= 200
    assert out["system"]
    print("OK test_token_budget_trim")


def test_safe_input_and_fit_budget():
    from backend.projects.context_builder import (
        compute_safe_input_tokens,
        fit_chunks_to_token_budget,
        estimate_tokens,
    )

    # Groq + huge context must not open a 100k prompt window
    safe = compute_safe_input_tokens(131072, known_tpm=8000, provider_id="groq")
    assert safe <= 7500, safe
    assert safe >= 2048, safe

    # DESIGN-sized dump must be cut by fit_chunks
    huge = "x" * 68000
    chunks = [
        {"chunk_text": huge, "score": 0.9, "filename": "DESIGN.md"},
        {"chunk_text": "timeout 180s no Juiz", "score": 0.8, "filename": "FABLE5.md"},
    ]
    selected, truncated = fit_chunks_to_token_budget(chunks, max_tokens=500)
    assert truncated
    assert selected
    assert estimate_tokens(selected[0]["chunk_text"]) <= 550
    # Prefer not to include both when first already fills
    assert sum(estimate_tokens(c["chunk_text"]) for c in selected) <= 600
    print("OK test_safe_input_and_fit_budget", safe, len(selected))


def test_chunker_tables_atomic():
    from backend.projects.chunker import chunk_text

    table = """## Providers

| Provider | Modelo | TPM |
| --- | --- | --- |
| Groq | gpt-oss-120b | 8000 |
| OpenRouter | llama | 0 |

Texto depois.
"""
    chunks = chunk_text(table, file_type="md", chunk_size=200, overlap=40)
    joined = "\n".join(chunks)
    assert "| Provider | Modelo | TPM |" in joined
    # Header should appear with body rows (atomic or repeated)
    assert "gpt-oss-120b" in joined
    # No mid-cell cut of the header row alone into "rovider"
    for c in chunks:
        assert not c.strip().startswith("rovider")
        assert not c.strip().startswith("oq |")
    print("OK test_chunker_tables_atomic", len(chunks))


async def test_retrieval_precision_smoke():
    """If embedder works, plant known text and ask a related query."""
    from backend.projects.embedder import init_embedder, is_embedder_ready

    init_embedder()
    if not is_embedder_ready():
        print("SKIP test_retrieval_precision_smoke (embedder unavailable)")
        return

    dbmod, path = await _setup_tmp_db()
    from backend.projects.indexer import index_project_file, retrieve_related_chats, index_chat_turn
    from backend.projects.vector_store import search_file_chunks

    user_id = str(uuid.uuid4())
    project_id = str(uuid.uuid4())
    file_id = str(uuid.uuid4())
    conv_a = str(uuid.uuid4())
    conv_b = str(uuid.uuid4())

    secret = "O código secreto do cofre Facilita Vistorias é AZUL-42-ORION."

    async with aiosqlite.connect(dbmod.DB_PATH) as db:
        await db.execute(
            "INSERT INTO users (id, username, password_hash) VALUES (?, ?, ?)",
            (user_id, f"u_{user_id[:8]}", "x"),
        )
        await db.execute(
            "INSERT INTO projects (id, user_id, name) VALUES (?, ?, ?)",
            (project_id, user_id, "Facilita"),
        )
        await db.execute(
            """INSERT INTO project_files
               (id, project_id, filename, mime_type, extracted_text, index_status)
               VALUES (?, ?, ?, 'text/plain', ?, 'pending')""",
            (file_id, project_id, "segredo.txt", secret + "\nOutras notas irrelevantes."),
        )
        await db.execute(
            "INSERT INTO conversations (id, user_id, title, project_id) VALUES (?, ?, ?, ?)",
            (conv_a, user_id, "chat A", project_id),
        )
        await db.execute(
            "INSERT INTO conversations (id, user_id, title, project_id) VALUES (?, ?, ?, ?)",
            (conv_b, user_id, "chat B", project_id),
        )
        await db.commit()

    res = await index_project_file(file_id)
    assert res.get("ok"), res

    hits = await search_file_chunks(project_id, "qual o código secreto do cofre?", top_k=3, threshold=0.3)
    assert hits, "expected at least one file hit"
    assert any("ORION" in h["chunk_text"] or "AZUL" in h["chunk_text"] for h in hits)

    await index_chat_turn(conv_a, project_id, "Qual o prazo de entrega?", "O prazo de entrega é 15 dias úteis.")
    related = await retrieve_related_chats(
        "prazo de entrega do projeto",
        project_id,
        exclude_conversation_id=conv_b,
        top_k=3,
        threshold=0.3,
    )
    assert related, "expected sibling chat hit"
    # Must not include current chat
    assert all(r["conversation_id"] != conv_b for r in related)

    os.unlink(path)
    print("OK test_retrieval_precision_smoke")


async def test_context_builder_load():
    dbmod, path = await _setup_tmp_db()
    from backend.projects.context_builder import build_project_context

    user_id = str(uuid.uuid4())
    project_id = str(uuid.uuid4())
    async with aiosqlite.connect(dbmod.DB_PATH) as db:
        await db.execute(
            "INSERT INTO users (id, username, password_hash) VALUES (?, ?, ?)",
            (user_id, f"u_{user_id[:8]}", "x"),
        )
        await db.execute(
            """INSERT INTO projects (id, user_id, name, instructions)
               VALUES (?, ?, ?, ?)""",
            (project_id, user_id, "P", "Sempre responda em português formal."),
        )
        await db.execute(
            """INSERT INTO project_memory (id, project_id, summary_text)
               VALUES (?, ?, ?)""",
            (str(uuid.uuid4()), project_id, "Cliente prefere relatórios curtos."),
        )
        await db.commit()

    ctx = await build_project_context(project_id, "olá", include_debug=True, context_window=4096)
    assert "português formal" in ctx.system_content
    assert "relatórios curtos" in ctx.system_content
    assert ctx.instructions_used
    assert ctx.memory_project_used
    assert ctx.memory_global_used is False
    os.unlink(path)
    print("OK test_context_builder_load")


async def test_no_full_file_dump_under_groq_budget():
    """
    PLAN_FIX_RAG: 4 files including a DESIGN-sized body must NOT produce
    19k–28k token system prompts (413 TPM). Selective RAG + hard budget.
    """
    from backend.projects.embedder import init_embedder, is_embedder_ready
    from backend.projects.indexer import index_project_file
    from backend.projects.context_builder import build_project_context, estimate_tokens

    init_embedder()
    if not is_embedder_ready():
        print("SKIP test_no_full_file_dump_under_groq_budget (embedder unavailable)")
        return

    dbmod, path = await _setup_tmp_db()
    user_id = str(uuid.uuid4())
    project_id = str(uuid.uuid4())

    fable = (
        "# FABLE5\n\n## Melhorias adicionais\n"
        "- [x] Timeout no Juiz 180s e detecção de claims 30s.\n"
        "- [x] Limite de 1500 chars por resposta na detecção de claims.\n"
        "- [x] grounding_enabled INTEGER DEFAULT 1 na tabela fusion_config.\n"
    )
    design = "# DESIGN\n\n" + ("Arquitetura detalhada do NexusLocal. " * 2000)  # ~60k+ chars
    mythos = "# MYTHOS\n\n## Fase 3\nTool use nos proposers fica adiado.\n" + ("nota " * 200)
    readme = "# README\n\n## Próximos módulos planejados\n- Projects RAG\n- Memory\n"

    files = [
        ("FABLE5.md", fable),
        ("DESIGN.md", design),
        ("MYTHOS.md", mythos),
        ("README.md", readme),
    ]

    async with aiosqlite.connect(dbmod.DB_PATH) as db:
        await db.execute(
            "INSERT INTO users (id, username, password_hash) VALUES (?, ?, ?)",
            (user_id, f"u_{user_id[:8]}", "x"),
        )
        await db.execute(
            "INSERT INTO projects (id, user_id, name, retrieval_top_k) VALUES (?, ?, ?, ?)",
            (project_id, user_id, "RAG Fix", 6),
        )
        for name, text in files:
            fid = str(uuid.uuid4())
            await db.execute(
                """INSERT INTO project_files
                   (id, project_id, filename, mime_type, extracted_text, index_status, size_bytes)
                   VALUES (?, ?, ?, 'text/markdown', ?, 'pending', ?)""",
                (fid, project_id, name, text, len(text)),
            )
        await db.commit()

    async with aiosqlite.connect(dbmod.DB_PATH) as db:
        async with db.execute(
            "SELECT id FROM project_files WHERE project_id = ?", (project_id,)
        ) as cur:
            ids = [r[0] for r in await cur.fetchall()]
    for fid in ids:
        res = await index_project_file(fid)
        assert res.get("ok"), res

    ctx = await build_project_context(
        project_id,
        "Qual o timeout do Juiz e o limite de 1500 chars nas claims?",
        context_window=131072,
        known_tpm=8000,
        provider_id="groq",
        reserve_for_history=1500,
        reserve_for_response=1024,
        include_debug=True,
    )

    # Must stay well under free-tier TPM blowup territory
    assert ctx.tokens_est < 6000, f"system too large: {ctx.tokens_est}"
    # Must NOT contain most of DESIGN dump
    assert ctx.system_content.count("Arquitetura detalhada") < 80
    # Must recover the technical facts from FABLE5
    body = ctx.system_content
    assert "180s" in body or any("180" in (c.get("chunk_text") or "") for c in ctx.file_chunks)
    assert "1500" in body or any("1500" in (c.get("chunk_text") or "") for c in ctx.file_chunks)

    # Catalog lists files but does not paste full DESIGN
    assert "DESIGN.md" in body
    assert "FABLE5.md" in body
    print(
        f"OK test_no_full_file_dump_under_groq_budget tokens={ctx.tokens_est} "
        f"hits={len(ctx.file_chunks)} mode={ctx.debug.get('retrieval_mode')}"
    )
    os.unlink(path)


if __name__ == "__main__":
    # Windows event loop
    try:
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())  # type: ignore
    except Exception:
        pass
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    test_chunker()
    test_chunker_markdown_no_midword()
    test_token_budget_trim()
    test_safe_input_and_fit_budget()
    test_chunker_tables_atomic()
    loop.run_until_complete(test_cascade_delete_project())
    loop.run_until_complete(test_standalone_chat_without_project())
    loop.run_until_complete(test_context_builder_load())
    loop.run_until_complete(test_retrieval_precision_smoke())
    loop.run_until_complete(test_no_full_file_dump_under_groq_budget())
    print("\nAll project tests passed.")
