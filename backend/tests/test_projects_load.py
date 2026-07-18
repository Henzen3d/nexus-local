"""
Fase 8 — smoke de carga do Context Builder.
Projeto sintético com N file chunks + M chat chunks; mede latência de build.
"""

from __future__ import annotations

import asyncio
import os
import sys
import tempfile
import time
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import aiosqlite


async def main(n_files: int = 50, n_chats: int = 30):
    from backend import database as dbmod
    import backend.projects.vector_store as vs
    import backend.projects.indexer as idx
    import backend.projects.context_builder as cb
    import backend.projects.memory_job as mj

    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    dbmod.DB_PATH = Path(path)
    for mod in (vs, idx, cb, mj):
        mod.DB_PATH = dbmod.DB_PATH
    await dbmod.init_db()

    from backend.projects.embedder import init_embedder, is_embedder_ready, embed_text
    from backend.projects.context_builder import build_project_context

    init_embedder()
    if not is_embedder_ready():
        print("SKIP load test — embedder unavailable")
        os.unlink(path)
        return

    user_id = str(uuid.uuid4())
    project_id = str(uuid.uuid4())

    async with aiosqlite.connect(dbmod.DB_PATH) as db:
        await db.execute(
            "INSERT INTO users (id, username, password_hash) VALUES (?, ?, ?)",
            (user_id, f"load_{user_id[:8]}", "x"),
        )
        await db.execute(
            "INSERT INTO projects (id, user_id, name, instructions) VALUES (?, ?, ?, ?)",
            (project_id, user_id, "Load", "Instruções de carga."),
        )
        await db.execute(
            "INSERT INTO project_memory (id, project_id, summary_text) VALUES (?, ?, ?)",
            (str(uuid.uuid4()), project_id, "Memória sintética do projeto de carga."),
        )

        for i in range(n_files):
            fid = str(uuid.uuid4())
            text = f"Documento {i}: conteúdo genérico sobre tópico {i % 7}."
            if i == 17:
                text = "O número mágico da vistoria é 918273."
            await db.execute(
                """INSERT INTO project_files
                   (id, project_id, filename, mime_type, extracted_text, index_status)
                   VALUES (?, ?, ?, 'text/plain', ?, 'ready')""",
                (fid, project_id, f"doc_{i}.txt", text),
            )
            blob = embed_text(text)
            await db.execute(
                """INSERT INTO file_chunks (id, project_file_id, chunk_text, chunk_index, embedding)
                   VALUES (?, ?, ?, 0, ?)""",
                (str(uuid.uuid4()), fid, text, blob),
            )

        for i in range(n_chats):
            cid = str(uuid.uuid4())
            await db.execute(
                "INSERT INTO conversations (id, user_id, title, project_id) VALUES (?, ?, ?, ?)",
                (cid, user_id, f"chat {i}", project_id),
            )
            pair = f"Pergunta: assunto {i}\nResposta: detalhe {i}"
            if i == 11:
                pair = "Pergunta: qual o prazo?\nResposta: O prazo acordado é 15 dias úteis."
            blob = embed_text(pair)
            await db.execute(
                """INSERT INTO chat_chunks
                   (id, chat_session_id, project_id, chunk_text, role, embedding)
                   VALUES (?, ?, ?, ?, 'turn', ?)""",
                (str(uuid.uuid4()), cid, project_id, pair, blob),
            )
        await db.commit()

    t0 = time.perf_counter()
    ctx = await build_project_context(
        project_id,
        "qual o número mágico da vistoria?",
        exclude_conversation_id="none",
        context_window=8192,
        include_debug=True,
    )
    ms = (time.perf_counter() - t0) * 1000
    print(f"Context Builder latency: {ms:.1f} ms")
    print(f"tokens_est={ctx.tokens_est} files={len(ctx.file_chunks)} chats={len(ctx.chat_chunks)}")
    print(f"file scores: {ctx.debug.get('file_scores')}")
    assert ms < 15000, f"too slow: {ms}ms"
    joined = " ".join(c["chunk_text"] for c in ctx.file_chunks)
    hit = "918273" in joined
    print(f"needle recall: {'HIT' if hit else 'MISS'}")
    os.unlink(path)
    print("OK load smoke")


if __name__ == "__main__":
    try:
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())  # type: ignore
    except Exception:
        pass
    asyncio.run(main())
