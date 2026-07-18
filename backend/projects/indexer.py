"""
Async indexing jobs for project files and sibling chat turns.
"""

from __future__ import annotations

import asyncio
import os
import uuid
from pathlib import Path
from typing import Optional

import aiosqlite

from backend.database import DB_PATH
from backend.projects.chunker import chunk_text, resolve_file_type
from backend.projects.embedder import embed_texts_async, embed_text_async
from backend.projects.vector_store import (
    DEFAULT_RETRIEVAL_THRESHOLD,
    DEFAULT_TOP_K,
    search_chat_chunks,
)

from backend.logging_config import get_logger

logger = get_logger(__name__)

_RAG_DEBUG = os.environ.get("PROJECTS_RAG_DEBUG", "").strip().lower() in (
    "1",
    "true",
    "yes",
    "on",
)


# Prevent concurrent double-index of the same file
_indexing_lock = asyncio.Lock()
_indexing_files: set[str] = set()


async def _set_file_status(file_id: str, status: str, error: Optional[str] = None) -> None:
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            """UPDATE project_files
               SET index_status = ?, index_error = ?, indexed_at = CASE WHEN ? = 'ready'
                   THEN datetime('now') ELSE indexed_at END
               WHERE id = ?""",
            (status, error, status, file_id),
        )
        await db.commit()


async def index_project_file(file_id: str) -> dict:
    """
    Chunk + embed a project file. Safe to call as asyncio.create_task.
    Status: pending → indexing → ready | error
    """
    async with _indexing_lock:
        if file_id in _indexing_files:
            return {"ok": False, "reason": "already_indexing"}
        _indexing_files.add(file_id)

    try:
        async with aiosqlite.connect(DB_PATH) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute(
                "SELECT id, project_id, filename, mime_type, raw_path, extracted_text FROM project_files WHERE id = ?",
                (file_id,),
            ) as cur:
                row = await cur.fetchone()
            if not row:
                return {"ok": False, "reason": "not_found"}

            text = row["extracted_text"] or ""
            if not text.strip() and row["raw_path"]:
                # Best-effort re-read from disk
                path = Path(row["raw_path"])
                if not path.is_absolute():
                    path = Path(__file__).resolve().parent.parent / path
                if path.exists():
                    try:
                        from backend.attachments.extractors import extract_text


                        text = await extract_text(str(path), row["mime_type"] or "text/plain")
                        await db.execute(
                            "UPDATE project_files SET extracted_text = ? WHERE id = ?",
                            (text, file_id),
                        )
                        await db.commit()
                    except Exception as e:
                        await _set_file_status(file_id, "error", str(e)[:500])
                        return {"ok": False, "reason": "extract_failed", "error": str(e)}

        if not text or not text.strip():
            await _set_file_status(file_id, "error", "Arquivo sem texto extraível")
            return {"ok": False, "reason": "empty_text"}

        await _set_file_status(file_id, "indexing")

        # Prefer extension when MIME is generic (browsers often send .md as text/plain)
        file_type = resolve_file_type(row["mime_type"], row["filename"])
        chunks = chunk_text(
            text,
            file_type=file_type,
            filename=row["filename"],
        )
        if not chunks:
            await _set_file_status(file_id, "error", "Nenhum chunk gerado")
            return {"ok": False, "reason": "no_chunks"}

        if _RAG_DEBUG:
            lens = [len(c) for c in chunks]
            logger.debug(
                "[projects-rag] index file=%r type=%s text_len=%s n_chunks=%s min=%s max=%s avg=%s",
                row["filename"], file_type, len(text), len(chunks),
                min(lens), max(lens), sum(lens) // len(lens),
            )
            for i, c in enumerate(chunks):
                logger.debug(
                    "[projects-rag]   chunk[%s] len=%s head=%r tail=%r",
                    i, len(c), c[:20], c[-20:],
                )

        blobs = await embed_texts_async(chunks)

        async with aiosqlite.connect(DB_PATH) as db:
            await db.execute("DELETE FROM file_chunks WHERE project_file_id = ?", (file_id,))
            for i, (chunk, blob) in enumerate(zip(chunks, blobs)):
                await db.execute(
                    """INSERT INTO file_chunks (id, project_file_id, chunk_text, chunk_index, embedding)
                       VALUES (?, ?, ?, ?, ?)""",
                    (str(uuid.uuid4()), file_id, chunk, i, blob),
                )
            await db.commit()

        await _set_file_status(file_id, "ready")
        logger.info(
            "[projects] indexed %r: %s chunks (~%s chars/chunk)",
            row["filename"], len(chunks),
            sum(len(c) for c in chunks) // max(1, len(chunks)),
        )
        return {"ok": True, "chunks": len(chunks)}
    except Exception as e:
        await _set_file_status(file_id, "error", str(e)[:500])
        return {"ok": False, "reason": "exception", "error": str(e)}
    finally:
        async with _indexing_lock:
            _indexing_files.discard(file_id)


async def index_chat_turn(
    conversation_id: str,
    project_id: str,
    user_text: str,
    assistant_text: str,
) -> Optional[str]:
    """
    After a completed chat turn inside a project, embed Q+A pair into chat_chunks.
    """
    if not project_id or not conversation_id:
        return None
    user_text = (user_text or "").strip()
    assistant_text = (assistant_text or "").strip()
    if not user_text and not assistant_text:
        return None

    pair = f"Pergunta: {user_text}\nResposta: {assistant_text}"
    # Cap stored text size
    if len(pair) > 4000:
        pair = pair[:4000] + "…"

    blob = await embed_text_async(pair)
    chunk_id = str(uuid.uuid4())
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            """INSERT INTO chat_chunks
               (id, chat_session_id, project_id, chunk_text, role, embedding)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (chunk_id, conversation_id, project_id, pair, "turn", blob),
        )
        await db.commit()
    return chunk_id


async def retrieve_related_chats(
    query: str,
    project_id: str,
    exclude_conversation_id: Optional[str] = None,
    top_k: int = DEFAULT_TOP_K,
    threshold: float = DEFAULT_RETRIEVAL_THRESHOLD,
) -> list[dict]:
    """Public API used by Context Builder — sibling chats only."""
    return await search_chat_chunks(
        project_id=project_id,
        query=query,
        exclude_conversation_id=exclude_conversation_id,
        top_k=top_k,
        threshold=threshold,
    )


def schedule_file_index(file_id: str) -> None:
    """Fire-and-forget background indexing."""
    try:
        loop = asyncio.get_running_loop()
        loop.create_task(index_project_file(file_id))
    except RuntimeError:
        asyncio.run(index_project_file(file_id))
