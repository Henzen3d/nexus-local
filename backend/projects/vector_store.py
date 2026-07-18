"""
Vector store for Projects RAG.

Uses BLOB float32 embeddings in SQLite + cosine similarity (same proven approach
as the semantic cache). Hybrid retrieval blends dense (embedding) scores with a
lightweight lexical score so exact technical terms (timeout, 1500, column names)
surface even when pure semantic similarity is weak.

Namespaces:
  - project_id:file  → file_chunks
  - project_id:chat  → chat_chunks
"""

from __future__ import annotations

import math
import re
from collections import Counter
from typing import Optional

import aiosqlite

from backend.database import DB_PATH
from backend.projects.embedder import (
    blob_to_embedding,
    cosine_similarity,
    embed_text_async,
)

from backend.logging_config import get_logger

logger = get_logger(__name__)

# Projects RAG threshold — 0.75 era rígido demais para queries curtas
# ("comente os arquivos anexos") e modelos multilingual; 0.38 recupera
# trechos úteis sem poluir demais (hybrid lexical recovers exact terms).
DEFAULT_RETRIEVAL_THRESHOLD = 0.38
# 4–6 chunks: enough recall without blowing free-tier TPM (budget still hard-caps)
DEFAULT_TOP_K = 6

# Hybrid blend: final = α * dense + (1-α) * lexical
_DENSE_WEIGHT = 0.65
_LEXICAL_WEIGHT = 0.35
# Soft floor so strong keyword hits can enter even with modest cosine
_LEXICAL_BOOST_THRESHOLD = 0.55

_TOKEN_RE = re.compile(r"[a-zA-ZÀ-ÿ0-9_]{2,}")
_SQLITE_VEC_TRIED = False
_SQLITE_VEC_OK = False


def try_load_sqlite_vec(conn) -> bool:
    """Best-effort load of sqlite-vec extension. Returns True if available."""
    global _SQLITE_VEC_TRIED, _SQLITE_VEC_OK
    if _SQLITE_VEC_TRIED:
        return _SQLITE_VEC_OK
    _SQLITE_VEC_TRIED = True
    try:
        import sqlite_vec  # type: ignore


        conn.enable_load_extension(True)
        sqlite_vec.load(conn)
        conn.enable_load_extension(False)
        _SQLITE_VEC_OK = True
        logger.info("✅ sqlite-vec carregado")
    except Exception:
        _SQLITE_VEC_OK = False
    return _SQLITE_VEC_OK


def _tokenize(text: str) -> list[str]:
    if not text:
        return []
    return [t.lower() for t in _TOKEN_RE.findall(text)]


def _lexical_score(query_tokens: list[str], doc_text: str) -> float:
    """
    Lightweight BM25-ish / coverage score in [0, 1].
    Rewards exact term hits and multi-term coverage without external deps.
    """
    if not query_tokens or not doc_text:
        return 0.0
    doc_tokens = _tokenize(doc_text)
    if not doc_tokens:
        return 0.0

    doc_tf = Counter(doc_tokens)
    doc_len = len(doc_tokens)
    # Unique query terms (preserve multi-hit weight lightly via tf)
    q_unique = list(dict.fromkeys(query_tokens))
    if not q_unique:
        return 0.0

    hit = 0.0
    covered = 0
    for t in q_unique:
        tf = doc_tf.get(t, 0)
        if tf <= 0:
            continue
        covered += 1
        # log tf saturation
        hit += 1.0 + math.log(1.0 + tf)

    coverage = covered / len(q_unique)
    # Length-normalized density of hits
    density = hit / (1.0 + math.log(1.0 + doc_len / 40.0))
    # Blend coverage (main) with density, clamp
    score = 0.7 * coverage + 0.3 * min(1.0, density / max(1.0, len(q_unique)))
    return max(0.0, min(1.0, score))


def _hybrid_score(dense: float, lexical: float) -> float:
    return _DENSE_WEIGHT * dense + _LEXICAL_WEIGHT * lexical


def _passes_threshold(dense: float, lexical: float, hybrid: float, threshold: float) -> bool:
    if hybrid >= threshold:
        return True
    # Strong exact-term match can admit a chunk with weaker embedding score
    if lexical >= _LEXICAL_BOOST_THRESHOLD and dense >= max(0.15, threshold * 0.4):
        return True
    return False


async def search_file_chunks(
    project_id: str,
    query: str,
    top_k: int = DEFAULT_TOP_K,
    threshold: float = DEFAULT_RETRIEVAL_THRESHOLD,
) -> list[dict]:
    """Retrieve top-K file chunks for a project (hybrid dense + lexical)."""
    if not is_embedder_ready() and not (await embed_text_async("x")):
        return []
    q_blob = await embed_text_async(query)
    if not q_blob:
        return []
    q_vec = blob_to_embedding(q_blob)
    q_tokens = _tokenize(query)

    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            """
            SELECT fc.id, fc.chunk_text, fc.chunk_index, fc.embedding,
                   pf.filename, pf.id AS file_id
            FROM file_chunks fc
            JOIN project_files pf ON pf.id = fc.project_file_id
            WHERE pf.project_id = ? AND pf.index_status = 'ready' AND fc.embedding IS NOT NULL
            """,
            (project_id,),
        ) as cur:
            rows = await cur.fetchall()

    scored: list[dict] = []
    for r in rows:
        emb = r["embedding"]
        if not emb:
            continue
        dense = cosine_similarity(q_vec, blob_to_embedding(emb))
        lexical = _lexical_score(q_tokens, r["chunk_text"] or "")
        hybrid = _hybrid_score(dense, lexical)
        if _passes_threshold(dense, lexical, hybrid, threshold):
            scored.append(
                {
                    "id": r["id"],
                    "chunk_text": r["chunk_text"],
                    "chunk_index": r["chunk_index"],
                    "filename": r["filename"],
                    "file_id": r["file_id"],
                    "score": hybrid,
                    "score_dense": dense,
                    "score_lexical": lexical,
                    "source": "file",
                }
            )
    scored.sort(key=lambda x: x["score"], reverse=True)
    return scored[: max(1, top_k)]


async def search_chat_chunks(
    project_id: str,
    query: str,
    exclude_conversation_id: Optional[str] = None,
    top_k: int = DEFAULT_TOP_K,
    threshold: float = DEFAULT_RETRIEVAL_THRESHOLD,
) -> list[dict]:
    """
    Retrieve top-K sibling chat chunks for a project (hybrid dense + lexical).
    Always excludes the current conversation (sibling-chat differentiation).
    """
    q_blob = await embed_text_async(query)
    if not q_blob:
        return []
    q_vec = blob_to_embedding(q_blob)
    q_tokens = _tokenize(query)

    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        if exclude_conversation_id:
            sql = """
                SELECT id, chat_session_id, chunk_text, role, embedding, created_at
                FROM chat_chunks
                WHERE project_id = ? AND chat_session_id != ? AND embedding IS NOT NULL
            """
            params = (project_id, exclude_conversation_id)
        else:
            sql = """
                SELECT id, chat_session_id, chunk_text, role, embedding, created_at
                FROM chat_chunks
                WHERE project_id = ? AND embedding IS NOT NULL
            """
            params = (project_id,)
        async with db.execute(sql, params) as cur:
            rows = await cur.fetchall()

    scored: list[dict] = []
    for r in rows:
        emb = r["embedding"]
        if not emb:
            continue
        dense = cosine_similarity(q_vec, blob_to_embedding(emb))
        lexical = _lexical_score(q_tokens, r["chunk_text"] or "")
        hybrid = _hybrid_score(dense, lexical)
        if _passes_threshold(dense, lexical, hybrid, threshold):
            scored.append(
                {
                    "id": r["id"],
                    "chunk_text": r["chunk_text"],
                    "role": r["role"],
                    "conversation_id": r["chat_session_id"],
                    "created_at": r["created_at"],
                    "score": hybrid,
                    "score_dense": dense,
                    "score_lexical": lexical,
                    "source": "chat",
                }
            )
    scored.sort(key=lambda x: x["score"], reverse=True)
    return scored[: max(1, top_k)]
