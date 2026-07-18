"""Resolução de requisição: cache lookup + streaming LLM com failover cascade.

Extraído de websocket_chat (chat.py) — responsabilidade 11-13 do God function.
"""
from __future__ import annotations

import asyncio
import uuid
from typing import TYPE_CHECKING

from backend.logging_config import get_logger
from backend.providers.base import RateLimitError
from backend.providers.registry import get_provider, get_model_name
from backend.ranking import (
    resolve_model_with_failover,
    NoAvailableModelError,
    mark_model_exhausted,
    mark_model_success,
)
from backend.ranking.quota_tracker import record_request

if TYPE_CHECKING:
    from fastapi import WebSocket
    from backend.cache.manager import CacheHit

logger = get_logger(__name__)

_MAX_FAILOVER_ATTEMPTS = 3


async def check_cache(
    model_id: str,
    history: list[dict],
    context_fingerprint: str,
    bypass_cache: bool,
) -> "CacheHit | None":
    """Consulta o cache (exact + semantic) ou retorna None se bypass."""
    if bypass_cache:
        return None
    try:
        from backend.cache.manager import cache_manager
        return await cache_manager.get(
            model_id,
            history,
            context_fingerprint=context_fingerprint or None,
        )
    except Exception:
        logger.error("Erro ao consultar cache", exc_info=True, extra={
            "model_id": model_id,
        })
        return None


async def stream_from_cache(
    ws: "WebSocket",
    conversation_id: str,
    cache_hit: "CacheHit",
) -> str:
    """Serve uma resposta do cache com fake-streaming para UX consistente."""
    await ws.send_json({
        "type": "stream_start",
        "conversation_id": conversation_id,
        "from_cache": True,
        "cache_type": cache_hit.cache_type,
        "cache_similarity": round(cache_hit.similarity, 4),
    })

    full_response = cache_hit.response
    chunk_size = 4
    for i in range(0, len(full_response), chunk_size):
        chunk = full_response[i:i + chunk_size]
        await ws.send_json({"type": "token", "content": chunk})
        await asyncio.sleep(0.004)

    return full_response


async def stream_from_llm(
    ws: "WebSocket",
    db,
    conversation_id: str,
    user_id: str,
    model_id: str,
    provider_id: str,
    history: list[dict],
) -> tuple[str, str, str] | None:
    """Executa o streaming LLM com failover cascade.

    Retorna (full_response, resolved_model_id, resolved_provider_id) ou None
    se todas as tentativas falharam.
    """
    attempt = 0
    success = False
    original_model_id = model_id
    full_response = ""

    while attempt < _MAX_FAILOVER_ATTEMPTS and not success:
        attempt += 1

        try:
            resolved = await resolve_model_with_failover(
                model_id if attempt == 1 else original_model_id,
                db,
                failover_enabled=True,
            )
        except NoAvailableModelError as e:
            await ws.send_json({"type": "error", "message": str(e)})
            return None

        if resolved.was_failover:
            await ws.send_json({
                "type": "failover_notice",
                "original_model": original_model_id,
                "fallback_model": resolved.display_name,
                "reason": resolved.failover_reason or "rate_limit",
            })

        current_model_id = resolved.model_id
        current_provider_id = resolved.provider_id

        try:
            provider = await get_provider(current_provider_id, db, user_id=user_id)
            model_name = await get_model_name(current_model_id, db)
        except ValueError as e:
            await ws.send_json({"type": "error", "message": str(e)})
            return None

        if attempt == 1:
            await ws.send_json({
                "type": "stream_start",
                "conversation_id": conversation_id,
                "from_cache": False,
            })

        try:
            async for token in provider.stream_chat(model=model_name, messages=history):
                token_str = str(token)
                full_response += token_str
                await ws.send_json({"type": "token", "content": token_str})

            await mark_model_success(current_model_id, db)
            await record_request(current_model_id, db)
            success = True

            if resolved.was_failover:
                log_id = str(uuid.uuid4())
                await db.execute(
                    """INSERT INTO model_usage_log
                       (id, model_id, provider_id, conversation_id, user_id,
                        was_fallback, fallback_from_model_id, fallback_reason)
                       VALUES (?, ?, ?, ?, ?, 1, ?, ?)""",
                    (
                        log_id, current_model_id, current_provider_id,
                        conversation_id, user_id,
                        original_model_id,
                        resolved.failover_reason or "rate_limit",
                    ),
                )
                await db.commit()

            model_id = current_model_id
            provider_id = current_provider_id

        except RateLimitError as e:
            await mark_model_exhausted(current_model_id, db, e.retry_after, str(e))
            if attempt == _MAX_FAILOVER_ATTEMPTS:
                await ws.send_json({
                    "type": "error",
                    "message": "Limite de tentativas de failover excedido. O modelo está esgotado.",
                })
            else:
                continue
        except Exception as e:
            error_msg = str(e)
            await ws.send_json({
                "type": "error",
                "message": f"Erro ao chamar modelo: {error_msg}",
            })
            from backend.database import check_and_deactivate_model
            await check_and_deactivate_model(current_model_id, error_msg, db)
            return None

    if not success:
        return None

    return full_response, model_id, provider_id


async def resolve_and_stream(
    ws: "WebSocket",
    db,
    conversation_id: str,
    user_id: str,
    model_id: str,
    provider_id: str,
    history: list[dict],
    context_fingerprint: str,
    bypass_cache: bool,
) -> tuple[str, "CacheHit | None", str, str] | None:
    """Fluxo completo: tenta cache, depois LLM com failover.

    Retorna (full_response, cache_hit_or_none, resolved_model_id,
    resolved_provider_id) ou None em caso de falha irrecuperável.
    """
    cache_hit = await check_cache(
        model_id, history, context_fingerprint, bypass_cache
    )

    if cache_hit:
        full_response = await stream_from_cache(ws, conversation_id, cache_hit)
        return full_response, cache_hit, model_id, provider_id

    result = await stream_from_llm(
        ws, db, conversation_id, user_id, model_id, provider_id, history
    )
    if result is None:
        return None

    full_response, resolved_model_id, resolved_provider_id = result

    # Save to cache in background (semantic key includes memory fingerprint)
    if full_response:
        try:
            from backend.cache.manager import cache_manager
            asyncio.create_task(
                cache_manager.set(
                    resolved_model_id,
                    history,
                    full_response,
                    context_fingerprint=context_fingerprint or None,
                )
            )
        except Exception:
            logger.warning("Não foi possível agendar cache.set em background",
                           exc_info=True)

    return full_response, None, resolved_model_id, resolved_provider_id
