"""backend/tools/dispatcher.py — Ponto central de despacho e execução de ferramentas.
Pipeline: KillSwitch -> RateLimit -> CacheCheck -> FailoverCascade -> Sanitization -> CacheSave -> UsageLog.
"""
from __future__ import annotations

import collections
import time
import uuid
from datetime import datetime, timezone
from typing import Optional
import aiosqlite

from backend.logging_config import get_logger
from backend.tools.base import DEFAULT_TTL, ToolResult
from backend.tools.cache import get_cached, set_cached
from backend.tools.failover import resolve_tool
from backend.tools.registry import get_providers
from backend.tools.security import sanitize_data

logger = get_logger(__name__)

# Sliding window in memory for user rate limiting: user_id -> deque of timestamps
_USER_CALLS: dict[str, collections.deque] = collections.defaultdict(lambda: collections.deque(maxlen=100))
DEFAULT_RATE_LIMIT_PER_MINUTE = 10


def _check_user_rate_limit(user_id: str, max_per_minute: int = DEFAULT_RATE_LIMIT_PER_MINUTE) -> bool:
    """Verifica se o usuário excedeu o limite de chamadas por minuto (sliding window de 60s)."""
    now = time.time()
    queue = _USER_CALLS[user_id]

    # Remove chamadas com mais de 60 segundos
    while queue and queue[0] <= now - 60.0:
        queue.popleft()

    if len(queue) >= max_per_minute:
        return False

    queue.append(now)
    return True


async def is_tools_globally_enabled(db: aiosqlite.Connection) -> bool:
    """Verifica se as ferramentas estão globalmente ativadas na tabela meta."""
    try:
        async with db.execute("SELECT value FROM meta WHERE key = 'tool_global_enabled'") as cur:
            row = await cur.fetchone()
            if row and row[0] is not None:
                return row[0].lower() in ("true", "1", "yes")
    except Exception:
        pass
    return True


async def log_tool_usage(
    family: str,
    provider_id: str,
    user_id: Optional[str],
    conversation_id: Optional[str],
    cache_hit: bool,
    latency_ms: float,
    status: str,
    error_message: Optional[str],
    db: aiosqlite.Connection,
) -> None:
    """Grava o uso da ferramenta na tabela tool_usage_log para observabilidade e auditoria."""
    log_id = str(uuid.uuid4())
    try:
        await db.execute(
            """
            INSERT INTO tool_usage_log
            (id, family, provider_id, user_id, conversation_id, cache_hit, latency_ms, status, error_message, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, datetime('now'))
            """,
            (
                log_id,
                family,
                provider_id,
                user_id,
                conversation_id,
                1 if cache_hit else 0,
                round(latency_ms, 2),
                status,
                (error_message or "")[:500],
            )
        )
        await db.commit()
    except Exception as e:
        logger.error("[ToolDispatcher] Erro ao gravar tool_usage_log: %s", e)


async def dispatch_tool(
    family: str,
    params: dict,
    user_id: str = "anonymous",
    db: Optional[aiosqlite.Connection] = None,
    conversation_id: Optional[str] = None,
) -> ToolResult:
    """Pipeline central para despacho de chamadas de ferramentas.

    1. Verifica kill-switch global
    2. Aplica rate limiting por usuário
    3. Consulta cache determinístico
    4. Se cache miss, aciona o failover cascade
    5. Sanitiza os dados retornados
    6. Armazena no cache se TTL > 0
    7. Registra auditoria no tool_usage_log
    """
    t_start = time.perf_counter()

    if db is None:
        from backend.database import DB_PATH
        async with aiosqlite.connect(DB_PATH) as conn:
            return await dispatch_tool(family, params, user_id, conn, conversation_id)

    # 1. Kill-switch global
    if not await is_tools_globally_enabled(db):
        return ToolResult(
            success=False,
            data={},
            provider_id="system",
            family=family,
            error="O sistema de ferramentas externas está temporariamente desativado pelo administrador.",
        )

    # 2. Rate limit por usuário (ignora para chamadas de sistema interno ou testes)
    if user_id and user_id not in ("system", "test_runner", "admin"):
        if not _check_user_rate_limit(user_id):
            return ToolResult(
                success=False,
                data={},
                provider_id="system",
                family=family,
                error="Limite de requisições de ferramentas excedido (máximo 10 por minuto). Aguarde um instante.",
            )

    # 3. Cache check
    providers = get_providers(family)
    primary_provider = providers[0] if providers else None
    cache_key: Optional[str] = None
    ttl = DEFAULT_TTL.get(family, 900)

    if primary_provider:
        try:
            cache_key = primary_provider.cache_key(params)
            ttl = primary_provider.ttl_seconds
        except Exception:
            cache_key = None

    if cache_key and ttl > 0:
        cached_result = await get_cached(cache_key, db)
        if cached_result:
            logger.info("[ToolDispatcher] Cache hit para %s (%s)", family, cache_key)
            await log_tool_usage(
                family=family,
                provider_id=cached_result.provider_id,
                user_id=user_id,
                conversation_id=conversation_id,
                cache_hit=True,
                latency_ms=0.5,
                status="ok",
                error_message=None,
                db=db,
            )
            return cached_result

    # 4. Failover Cascade
    result = await resolve_tool(family, params, db)
    elapsed_ms = (time.perf_counter() - t_start) * 1000.0
    result.latency_ms = elapsed_ms

    # 5. Sanitização
    if result.data:
        result.data = sanitize_data(result.data)

    # 6. Grava no cache se teve sucesso e ttl > 0
    if result.success and cache_key and ttl > 0:
        await set_cached(cache_key, result, ttl, db)

    # 7. Registra log de uso
    status_str = "ok" if result.success else "error"
    await log_tool_usage(
        family=family,
        provider_id=result.provider_id,
        user_id=user_id,
        conversation_id=conversation_id,
        cache_hit=False,
        latency_ms=elapsed_ms,
        status=status_str,
        error_message=result.error,
        db=db,
    )

    logger.info(
        "[ToolDispatcher] %s via %s | cached=False | latency=%.1fms | status=%s",
        family,
        result.provider_id,
        elapsed_ms,
        status_str,
    )
    return result
