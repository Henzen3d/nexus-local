"""backend/tools/cache.py — Gerenciamento de cache SQLite com TTL para ferramentas.
"""
from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from typing import Optional
import aiosqlite

from backend.logging_config import get_logger
from backend.tools.base import ToolResult

logger = get_logger(__name__)


async def get_cached(cache_key: str, db: aiosqlite.Connection) -> Optional[ToolResult]:
    """Recupera resultado do cache se existir e não estiver expirado."""
    now = datetime.now(timezone.utc).isoformat()
    try:
        async with db.execute(
            """
            SELECT family, provider, response, expires_at, hit_count
            FROM tool_cache
            WHERE cache_key = ? AND expires_at > ?
            """,
            (cache_key, now)
        ) as cur:
            row = await cur.fetchone()

        if not row:
            return None

        family, provider, response_json, expires_at, hit_count = row
        data = json.loads(response_json)

        # Incrementa contador de hits
        await db.execute(
            "UPDATE tool_cache SET hit_count = hit_count + 1 WHERE cache_key = ?",
            (cache_key,)
        )
        await db.commit()

        return ToolResult(
            success=True,
            data=data,
            provider_id=provider,
            family=family,
            cached=True,
            latency_ms=0.5,
        )

    except Exception as e:
        logger.warning("[ToolCache] Erro ao buscar cache para %s: %s", cache_key, e)
        return None


async def set_cached(
    cache_key: str,
    result: ToolResult,
    ttl_seconds: int,
    db: aiosqlite.Connection,
) -> bool:
    """Armazena resultado no cache com tempo de vida (TTL)."""
    if ttl_seconds <= 0 or not result.success:
        return False

    now_dt = datetime.now(timezone.utc)
    expires_dt = now_dt + timedelta(seconds=ttl_seconds)

    now_str = now_dt.isoformat()
    expires_str = expires_dt.isoformat()

    try:
        response_json = json.dumps(result.data, ensure_ascii=False)
        await db.execute(
            """
            INSERT INTO tool_cache
            (cache_key, family, provider, response, created_at, expires_at, hit_count)
            VALUES (?, ?, ?, ?, ?, ?, 0)
            ON CONFLICT(cache_key) DO UPDATE SET
                response = excluded.response,
                created_at = excluded.created_at,
                expires_at = excluded.expires_at
            """,
            (cache_key, result.family, result.provider_id, response_json, now_str, expires_str)
        )
        await db.commit()
        return True
    except Exception as e:
        logger.error("[ToolCache] Erro ao gravar cache para %s: %s", cache_key, e)
        return False


async def evict_expired(db: aiosqlite.Connection) -> int:
    """Remove todas as entradas expiradas da tabela tool_cache."""
    now = datetime.now(timezone.utc).isoformat()
    try:
        cur = await db.execute("DELETE FROM tool_cache WHERE expires_at <= ?", (now,))
        deleted = cur.rowcount
        await db.commit()
        if deleted > 0:
            logger.info("[ToolCache] %d entradas expiradas removidas do cache", deleted)
        return deleted
    except Exception as e:
        logger.error("[ToolCache] Erro na limpeza periódica do cache: %s", e)
        return 0


async def invalidate_family(family: str, db: aiosqlite.Connection) -> int:
    """Invalida todas as entradas em cache para uma família inteira."""
    try:
        cur = await db.execute("DELETE FROM tool_cache WHERE family = ?", (family,))
        deleted = cur.rowcount
        await db.commit()
        logger.info("[ToolCache] Cache invalidado para a família '%s' (%d entradas)", family, deleted)
        return deleted
    except Exception as e:
        logger.error("[ToolCache] Erro ao invalidar cache da família %s: %s", family, e)
        return 0
