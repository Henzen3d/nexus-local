"""
CacheManager — Caching inteligente para NexusLocal
===================================================
Duas camadas:
  1. Exact  → SHA-256(model_id + messages) — hit em < 1ms
  2. Semantic → embedding do último prompt + cosine similarity — hit em ~5ms

Depende de fastembed (opcional).
  pip install fastembed

Se fastembed não estiver instalado, apenas o cache exato funciona.
"""

import asyncio
import hashlib
import json
import uuid
import struct
from datetime import datetime, timedelta
from typing import Optional, NamedTuple
import aiosqlite

from backend.database import DB_PATH

# ── numpy é a única dependência obrigatória para cosseno ──────────────────────
try:
    import numpy as np
    _HAS_NUMPY = True
except ImportError:
    _HAS_NUMPY = False

# ── fastembed é opcional ───────────────────────────────────────────────────────
_EMBEDDER = None
_EMBEDDER_INIT = False
_EMBEDDER_ERROR: Optional[str] = None


def _init_embedder() -> Optional[object]:
    global _EMBEDDER, _EMBEDDER_INIT, _EMBEDDER_ERROR
    if _EMBEDDER_INIT:
        return _EMBEDDER
    _EMBEDDER_INIT = True
    try:
        from fastembed import TextEmbedding
        # Modelo multilíngue leve (~120MB, ONNX, sem torch)
        _EMBEDDER = TextEmbedding(
            model_name="sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"
        )
        print("✅ Cache semântico pronto (paraphrase-multilingual-MiniLM-L12-v2)")
    except ImportError:
        _EMBEDDER_ERROR = "fastembed não instalado. Rode: pip install fastembed"
        print(f"⚠️  {_EMBEDDER_ERROR}")
    except Exception as e:
        _EMBEDDER_ERROR = str(e)
        print(f"⚠️  Erro ao inicializar embedder: {e}")
    return _EMBEDDER


# ── Utilidades de embedding ───────────────────────────────────────────────────

def _embedding_to_blob(vec) -> bytes:
    """Serializa numpy array float32 como bytes."""
    arr = np.array(vec, dtype=np.float32)
    return arr.tobytes()


def _blob_to_embedding(blob: bytes):
    """Desserializa bytes → numpy array float32."""
    return np.frombuffer(blob, dtype=np.float32)


def _cosine_similarity(a, b) -> float:
    """Similaridade cosseno entre dois vetores numpy."""
    denom = np.linalg.norm(a) * np.linalg.norm(b)
    if denom == 0:
        return 0.0
    return float(np.dot(a, b) / denom)


def _embed_text(text: str) -> Optional[bytes]:
    """Gera embedding de um texto e retorna como BLOB. Roda sync (thread pool)."""
    embedder = _init_embedder()
    if embedder is None or not _HAS_NUMPY:
        return None
    embeddings = list(embedder.embed([text]))
    return _embedding_to_blob(embeddings[0])


def _estimate_tokens(text: str) -> int:
    """Estimativa rápida de tokens (chars / 4)."""
    return max(1, len(text) // 4)


# ── Resultado do cache ────────────────────────────────────────────────────────

class CacheHit(NamedTuple):
    response: str
    cache_type: str       # 'exact' | 'semantic'
    similarity: float     # 1.0 para exact, 0-1 para semantic
    entry_id: str
    token_est: int


# ── Cache Manager ─────────────────────────────────────────────────────────────

class CacheManager:

    # ── Settings ──────────────────────────────────────────────────────────────

    async def get_settings(self) -> dict:
        async with aiosqlite.connect(DB_PATH) as db:
            async with db.execute("SELECT key, value FROM cache_settings") as cur:
                rows = await cur.fetchall()
        settings = {k: v for k, v in rows}
        return {
            "enabled":             settings.get("enabled", "true") == "true",
            "exact_enabled":       settings.get("exact_enabled", "true") == "true",
            "semantic_enabled":    settings.get("semantic_enabled", "true") == "true",
            "exact_ttl_hours":     int(settings.get("exact_ttl_hours", "168")),
            "semantic_ttl_hours":  int(settings.get("semantic_ttl_hours", "72")),
            "similarity_threshold": float(settings.get("similarity_threshold", "0.92")),
        }

    async def update_settings(self, updates: dict) -> None:
        async with aiosqlite.connect(DB_PATH) as db:
            for k, v in updates.items():
                await db.execute(
                    "INSERT OR REPLACE INTO cache_settings (key, value) VALUES (?, ?)",
                    (k, str(v).lower() if isinstance(v, bool) else str(v)),
                )
            await db.commit()

    # ── Public: get ───────────────────────────────────────────────────────────

    async def get(
        self,
        model_id: str,
        messages: list[dict],
    ) -> Optional[CacheHit]:
        settings = await self.get_settings()

        if not settings["enabled"]:
            return None

        # 1. Exact cache
        if settings["exact_enabled"]:
            hit = await self._get_exact(
                model_id, messages, settings["exact_ttl_hours"]
            )
            if hit:
                return hit

        # 2. Semantic cache
        if settings["semantic_enabled"] and _HAS_NUMPY:
            last_user = next(
                (m["content"] for m in reversed(messages) if m["role"] == "user"),
                None,
            )
            if last_user:
                hit = await self._get_semantic(
                    model_id,
                    last_user,
                    settings["similarity_threshold"],
                    settings["semantic_ttl_hours"],
                )
                if hit:
                    return hit

        return None

    # ── Public: set ───────────────────────────────────────────────────────────

    async def set(
        self,
        model_id: str,
        messages: list[dict],
        response: str,
    ) -> None:
        settings = await self.get_settings()
        if not settings["enabled"]:
            return

        token_est = _estimate_tokens(response)

        # Exact cache entry
        if settings["exact_enabled"]:
            await self._set_exact(model_id, messages, response, token_est)

        # Semantic cache entry
        if settings["semantic_enabled"] and _HAS_NUMPY:
            last_user = next(
                (m["content"] for m in reversed(messages) if m["role"] == "user"),
                None,
            )
            if last_user:
                loop = asyncio.get_event_loop()
                blob = await loop.run_in_executor(None, _embed_text, last_user)
                if blob:
                    await self._set_semantic(model_id, last_user, blob, response, token_est)

    # ── Public: stats ─────────────────────────────────────────────────────────

    async def stats(self) -> dict:
        async with aiosqlite.connect(DB_PATH) as db:
            async with db.execute(
                """SELECT COUNT(*), COALESCE(SUM(hits),0), COALESCE(SUM(token_est * hits),0)
                   FROM cache_exact"""
            ) as cur:
                exact_count, exact_hits, exact_tokens = await cur.fetchone()

            async with db.execute(
                """SELECT COUNT(*), COALESCE(SUM(hits),0), COALESCE(SUM(token_est * hits),0)
                   FROM cache_semantic"""
            ) as cur:
                sem_count, sem_hits, sem_tokens = await cur.fetchone()

        return {
            "exact": {
                "entries": exact_count,
                "hits": exact_hits,
                "tokens_saved": exact_tokens,
            },
            "semantic": {
                "entries": sem_count,
                "hits": sem_hits,
                "tokens_saved": sem_tokens,
                "embedder_ready": _EMBEDDER_INIT and _EMBEDDER is not None,
                "embedder_error": _EMBEDDER_ERROR,
            },
            "total_hits": (exact_hits or 0) + (sem_hits or 0),
            "total_tokens_saved": (exact_tokens or 0) + (sem_tokens or 0),
        }

    async def list_entries(self, cache_type: str = "exact", limit: int = 50) -> list:
        table = "cache_exact" if cache_type == "exact" else "cache_semantic"
        async with aiosqlite.connect(DB_PATH) as db:
            col = "hash" if cache_type == "exact" else "prompt_text"
            async with db.execute(
                f"""SELECT id, {col}, model_id, hits, token_est, created_at, last_hit
                    FROM {table} ORDER BY hits DESC LIMIT ?""",
                (limit,),
            ) as cur:
                rows = await cur.fetchall()
        return [
            {
                "id": r[0],
                "key": r[1][:80] + "…" if len(r[1]) > 80 else r[1],
                "model_id": r[2],
                "hits": r[3],
                "token_est": r[4],
                "created_at": r[5],
                "last_hit": r[6],
            }
            for r in rows
        ]

    async def delete_entry(self, entry_id: str, cache_type: str) -> None:
        table = "cache_exact" if cache_type == "exact" else "cache_semantic"
        async with aiosqlite.connect(DB_PATH) as db:
            await db.execute(f"DELETE FROM {table} WHERE id = ?", (entry_id,))
            await db.commit()

    async def clear_all(self) -> None:
        async with aiosqlite.connect(DB_PATH) as db:
            await db.execute("DELETE FROM cache_exact")
            await db.execute("DELETE FROM cache_semantic")
            await db.commit()

    async def clear_expired(self) -> dict:
        settings = await self.get_settings()
        cutoff_exact = (
            datetime.now() - timedelta(hours=settings["exact_ttl_hours"])
        ).isoformat()
        cutoff_sem = (
            datetime.now() - timedelta(hours=settings["semantic_ttl_hours"])
        ).isoformat()
        async with aiosqlite.connect(DB_PATH) as db:
            async with db.execute(
                "DELETE FROM cache_exact WHERE created_at < ?", (cutoff_exact,)
            ) as cur:
                exact_del = cur.rowcount
            async with db.execute(
                "DELETE FROM cache_semantic WHERE created_at < ?", (cutoff_sem,)
            ) as cur:
                sem_del = cur.rowcount
            await db.commit()
        return {"exact_deleted": exact_del, "semantic_deleted": sem_del}

    # ── Private: exact ────────────────────────────────────────────────────────

    def _hash_messages(self, model_id: str, messages: list) -> str:
        key = model_id + json.dumps(messages, ensure_ascii=False, sort_keys=True)
        return hashlib.sha256(key.encode()).hexdigest()

    async def _get_exact(
        self, model_id: str, messages: list, ttl_hours: int
    ) -> Optional[CacheHit]:
        h = self._hash_messages(model_id, messages)
        cutoff = (datetime.now() - timedelta(hours=ttl_hours)).isoformat()

        async with aiosqlite.connect(DB_PATH) as db:
            async with db.execute(
                """SELECT id, response, token_est FROM cache_exact
                   WHERE hash = ? AND model_id = ? AND created_at > ?
                   LIMIT 1""",
                (h, model_id, cutoff),
            ) as cur:
                row = await cur.fetchone()

            if not row:
                return None

            await db.execute(
                "UPDATE cache_exact SET hits=hits+1, last_hit=datetime('now') WHERE id=?",
                (row[0],),
            )
            await db.commit()

        return CacheHit(
            response=row[1],
            cache_type="exact",
            similarity=1.0,
            entry_id=row[0],
            token_est=row[2],
        )

    async def _set_exact(
        self, model_id: str, messages: list, response: str, token_est: int
    ) -> None:
        h = self._hash_messages(model_id, messages)
        async with aiosqlite.connect(DB_PATH) as db:
            # Skip if already exists (upsert via hits+1)
            async with db.execute(
                "SELECT id FROM cache_exact WHERE hash=? AND model_id=?", (h, model_id)
            ) as cur:
                existing = await cur.fetchone()
            if existing:
                return
            await db.execute(
                """INSERT INTO cache_exact (id, hash, model_id, response, token_est)
                   VALUES (?, ?, ?, ?, ?)""",
                (str(uuid.uuid4()), h, model_id, response, token_est),
            )
            await db.commit()

    # ── Private: semantic ─────────────────────────────────────────────────────

    async def _get_semantic(
        self,
        model_id: str,
        prompt_text: str,
        threshold: float,
        ttl_hours: int,
    ) -> Optional[CacheHit]:
        # Generate query embedding (in thread pool to not block event loop)
        loop = asyncio.get_event_loop()
        blob = await loop.run_in_executor(None, _embed_text, prompt_text)
        if blob is None:
            return None

        query_vec = _blob_to_embedding(blob)
        cutoff = (datetime.now() - timedelta(hours=ttl_hours)).isoformat()

        # Load all candidates for this model
        async with aiosqlite.connect(DB_PATH) as db:
            async with db.execute(
                """SELECT id, embedding, response, token_est FROM cache_semantic
                   WHERE model_id = ? AND created_at > ?""",
                (model_id, cutoff),
            ) as cur:
                rows = await cur.fetchall()

        if not rows:
            return None

        # Vectorized cosine similarity — fast even for 10k entries
        best_sim = 0.0
        best_row = None
        for row in rows:
            vec = _blob_to_embedding(row[1])
            sim = _cosine_similarity(query_vec, vec)
            if sim > best_sim:
                best_sim = sim
                best_row = row

        if best_sim < threshold or best_row is None:
            return None

        # Update hit counter
        async with aiosqlite.connect(DB_PATH) as db:
            await db.execute(
                """UPDATE cache_semantic
                   SET hits=hits+1, last_hit=datetime('now'), similarity=?
                   WHERE id=?""",
                (best_sim, best_row[0]),
            )
            await db.commit()

        return CacheHit(
            response=best_row[2],
            cache_type="semantic",
            similarity=best_sim,
            entry_id=best_row[0],
            token_est=best_row[3],
        )

    async def _set_semantic(
        self,
        model_id: str,
        prompt_text: str,
        embedding_blob: bytes,
        response: str,
        token_est: int,
    ) -> None:
        async with aiosqlite.connect(DB_PATH) as db:
            # Avoid near-duplicate entries: if very similar already exists, skip
            async with db.execute(
                """SELECT id FROM cache_semantic
                   WHERE model_id = ? AND prompt_text = ?
                   LIMIT 1""",
                (model_id, prompt_text),
            ) as cur:
                if await cur.fetchone():
                    return
            await db.execute(
                """INSERT INTO cache_semantic
                   (id, prompt_text, embedding, response, model_id, token_est)
                   VALUES (?, ?, ?, ?, ?, ?)""",
                (str(uuid.uuid4()), prompt_text, embedding_blob, response, model_id, token_est),
            )
            await db.commit()


# Singleton
cache_manager = CacheManager()