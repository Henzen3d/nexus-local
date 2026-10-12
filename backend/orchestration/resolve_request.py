"""Resolução de requisição: cache lookup + streaming LLM com failover cascade.

Extraído de websocket_chat (chat.py) — responsabilidade 11-13 do God function.
"""
from __future__ import annotations

import asyncio
import json
import uuid
from typing import TYPE_CHECKING, Any

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
    temperature: float | None = None,
    max_tokens: int | None = None,
    auto_route_decision: Any | None = None,
    reasoning_effort: str | None = None,
) -> tuple[str, str, str] | None:
    """Executa o streaming LLM com failover cascade.

    Retorna (full_response, resolved_model_id, resolved_provider_id) ou None
    se todas as tentativas falharam.
    """
    attempt = 0
    success = False
    original_model_id = model_id
    full_response = ""
    vision_relay_retry_done = False

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

        # Consulta capacidades de reasoning do modelo selecionado/resolvido
        async with db.execute(
            "SELECT reasoning_control, reasoning_levels, reasoning_default FROM models WHERE id = ?",
            (current_model_id,),
        ) as cur:
            m_row = await cur.fetchone()

        ctrl = (m_row[0] if m_row and m_row[0] else "none").strip()
        levels_raw = m_row[1] if m_row else None
        default_level = m_row[2] if m_row else None
        if levels_raw and isinstance(levels_raw, str):
            try:
                allowed_levels = json.loads(levels_raw)
            except Exception:
                allowed_levels = []
        elif isinstance(levels_raw, list):
            allowed_levels = levels_raw
        else:
            allowed_levels = []

        active_effort: str | None = None
        active_ctrl: str | None = None

        if reasoning_effort:
            if ctrl in ("none", "always_on", ""):
                drop_reason = "failover" if resolved.was_failover else "unsupported_model"
                await ws.send_json({
                    "type": "effort_dropped",
                    "reason": drop_reason,
                    "model_id": current_model_id,
                    "requested": reasoning_effort,
                })
            elif allowed_levels and reasoning_effort not in allowed_levels:
                if default_level and default_level in allowed_levels:
                    active_effort = default_level
                    active_ctrl = ctrl
                else:
                    await ws.send_json({
                        "type": "effort_dropped",
                        "reason": "invalid_level",
                        "model_id": current_model_id,
                        "requested": reasoning_effort,
                    })
            else:
                active_effort = reasoning_effort
                active_ctrl = ctrl

        try:
            stream_kwargs: dict[str, Any] = {}
            if temperature is not None:
                stream_kwargs["temperature"] = float(temperature)
            if max_tokens is not None:
                stream_kwargs["max_tokens"] = int(max_tokens)
            if active_effort is not None:
                stream_kwargs["reasoning_effort"] = active_effort
            if active_ctrl is not None:
                stream_kwargs["reasoning_control"] = active_ctrl

            async for token in provider.stream_chat(model=model_name, messages=history, **stream_kwargs):
                token_str = str(token)
                full_response += token_str
                await ws.send_json({"type": "token", "content": token_str})

            await mark_model_success(current_model_id, db)
            await record_request(current_model_id, db)
            success = True

            was_auto = 1 if auto_route_decision else 0
            if resolved.was_failover or was_auto:
                log_id = str(uuid.uuid4())
                route_intent_val = (
                    auto_route_decision.intent.value
                    if hasattr(auto_route_decision, "intent") and hasattr(auto_route_decision.intent, "value")
                    else str(getattr(auto_route_decision, "intent", ""))
                ) if auto_route_decision else None
                route_conf_val = getattr(auto_route_decision, "confidence", None)
                route_lat_val = getattr(auto_route_decision, "decision_latency_ms", None)
                route_policy_val = getattr(auto_route_decision, "policy", None)

                await db.execute(
                    """INSERT INTO model_usage_log
                       (id, model_id, provider_id, conversation_id, user_id,
                        was_fallback, fallback_from_model_id, fallback_reason,
                        was_auto_routed, route_intent, route_confidence, route_latency_ms, route_policy)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                    (
                        log_id, current_model_id, current_provider_id,
                        conversation_id, user_id,
                        1 if resolved.was_failover else 0,
                        original_model_id if resolved.was_failover else None,
                        resolved.failover_reason or "rate_limit" if resolved.was_failover else None,
                        was_auto,
                        route_intent_val,
                        route_conf_val,
                        route_lat_val,
                        route_policy_val,
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
            # Rede de segurança HTTP 400 com termos de reasoning:
            # Se a chamada falhou com erro citando parâmetros de reasoning, emite effort_dropped
            # com reason 'provider_rejected' e retenta UMA ÚNICA vez sem esforço, sem desativar o modelo.
            is_reasoning_reject = (
                active_effort is not None
                and (
                    "reasoning_effort" in error_msg.lower()
                    or "thinkingconfig" in error_msg.lower()
                    or "thinking_config" in error_msg.lower()
                    or "unsupported parameter" in error_msg.lower()
                    or ("effort" in error_msg.lower() and "400" in error_msg)
                )
            )
            if is_reasoning_reject:
                logger.warning(
                    "Provedor rejeitou parâmetro de reasoning (%s). Retentando sem esforço.",
                    error_msg
                )
                await ws.send_json({
                    "type": "effort_dropped",
                    "reason": "provider_rejected",
                    "model_id": current_model_id,
                    "requested": active_effort,
                })
                stream_kwargs.pop("reasoning_effort", None)
                stream_kwargs.pop("reasoning_control", None)
                active_effort = None
                active_ctrl = None
                try:
                    full_response = ""
                    async for token in provider.stream_chat(model=model_name, messages=history, **stream_kwargs):
                        token_str = str(token)
                        full_response += token_str
                        await ws.send_json({"type": "token", "content": token_str})

                    await mark_model_success(current_model_id, db)
                    await record_request(current_model_id, db)
                    success = True

                    model_id = current_model_id
                    provider_id = current_provider_id
                    break
                except Exception as retry_err:
                    error_msg = str(retry_err)

            from backend.orchestration.handle_attachments import (
                history_contains_images,
                is_vision_refusal_error,
                replace_images_with_relay,
            )
            if (
                not vision_relay_retry_done
                and history_contains_images(history)
                and is_vision_refusal_error(error_msg)
            ):
                try:
                    history = await replace_images_with_relay(
                        history, user_id=user_id, conversation_id=conversation_id
                    )
                    vision_relay_retry_done = True
                    full_response = ""
                    attempt -= 1
                    continue
                except Exception:
                    logger.error(
                        "Vision Relay fallback falhou após recusa de imagem",
                        exc_info=True,
                    )
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
    temperature: float | None = None,
    max_tokens: int | None = None,
    auto_route_decision: Any | None = None,
    reasoning_effort: str | None = None,
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
        ws, db, conversation_id, user_id, model_id, provider_id, history,
        temperature=temperature, max_tokens=max_tokens, auto_route_decision=auto_route_decision,
        reasoning_effort=reasoning_effort,
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
