"""Resolução de requisição: cache lookup + streaming LLM com failover cascade.

Extraído de websocket_chat (chat.py) — responsabilidade 11-13 do God function.
"""
from __future__ import annotations

import math
import time
import asyncio
import json
import re
import uuid
import os
from typing import TYPE_CHECKING, Any, Literal

from backend.logging_config import get_logger
from starlette.websockets import WebSocketDisconnect
from backend.providers.base import RateLimitError
from backend.providers.registry import get_provider, get_model_name
from backend.ranking import (
    resolve_model_with_failover,
    NoAvailableModelError,
    mark_model_exhausted,
    mark_model_success,
)
from backend.ranking.quota_tracker import record_request
from backend.orchestration.ws_protocol import (
    StreamClearEvent,
    StreamStartEvent,
    StreamTokenEvent,
    build_stream_end_failure,
    dump_ws_event,
)

if TYPE_CHECKING:
    from fastapi import WebSocket
    from backend.cache.manager import CacheHit
    from backend.ranking.failover import FallbackRequirements

logger = get_logger(__name__)

def _parse_positive_finite_float(
    raw: Any,
    *,
    min_val: float = 0.05,
    max_val: float = 3600.0,
) -> float | None:
    """Valida que um valor de configuração é número finito estritamente positivo dentro da faixa."""
    if raw is None:
        return None
    try:
        val = float(str(raw).strip())
    except (TypeError, ValueError):
        return None
    if not math.isfinite(val) or val <= 0.0:
        return None
    if val < min_val or val > max_val:
        return None
    return val


_MAX_FAILOVER_ATTEMPTS = int(os.getenv("FAILOVER_MAX_ATTEMPTS", "7"))
DEFAULT_FAILOVER_TOTAL_BUDGET_SECONDS = 45.0
DEFAULT_STREAM_TTFT_TIMEOUT_SECONDS = (
    _parse_positive_finite_float(os.getenv("FAILOVER_STREAM_TTFT_TIMEOUT_SECONDS"))
    or 25.0
)
DEFAULT_INTER_TOKEN_TIMEOUT_SECONDS = (
    _parse_positive_finite_float(os.getenv("FAILOVER_INTER_TOKEN_TIMEOUT_SECONDS"))
    or 35.0
)
MIN_RETRY_BUDGET_SECONDS = 3.0
DEFAULT_MIN_COMMIT_CHARS = int(os.getenv("FAILOVER_MIN_COMMIT_CHARS", "24"))
DEFAULT_MAX_PRECOMMIT_HOLD_MS = (
    _parse_positive_finite_float(os.getenv("FAILOVER_MAX_PRECOMMIT_HOLD_MS"), min_val=1.0, max_val=30000.0)
    or 450.0
)


class _InterTokenTimeoutError(Exception):
    """Sinaliza silêncio prolongado entre tokens após o início do stream (nunca conta como sucesso)."""

    def __init__(self, timeout_s: float, partial_chars: int, committed: bool):
        self.timeout_s = timeout_s
        self.partial_chars = partial_chars
        self.committed = committed
        super().__init__(f"Inter-token timeout ({timeout_s:.1f}s)")


def _build_cascade_debug_log(cascade_history: list[dict], main_msg: str) -> str:
    """Log técnico completo do failover cascade — usado APENAS para logger do backend."""
    if not cascade_history:
        return main_msg
    lines = [f"{main_msg} | Cascade ({len(cascade_history)} tentativas):"]
    for i, entry in enumerate(cascade_history, 1):
        m_id = entry.get("model_id", "?")
        p_id = entry.get("provider_id", "")
        detail = entry.get("detail", "Sem detalhes")
        prov_str = f" via {p_id}" if p_id else ""
        lines.append(f"  {i}. {m_id}{prov_str}: {detail}")
    return "\n".join(lines)


def build_cascade_error_summary(cascade_history: list[dict], main_msg: str) -> str:
    """Mensagem humanizada para o USUÁRIO — nunca expõe model IDs, provider IDs ou erros técnicos."""
    if not cascade_history:
        return main_msg
    n = len(cascade_history)
    if n == 1:
        return (
            f"{main_msg}\n\n"
            "Tentei um modelo alternativo, mas ele estava temporariamente indisponível. "
            "Tente novamente em alguns instantes."
        )
    if n <= 3:
        return (
            f"{main_msg}\n\n"
            f"Tentei {n} modelos alternativos, mas todos estavam temporariamente indisponíveis. "
            "Tente novamente em alguns instantes."
        )
    return (
        f"{main_msg}\n\n"
        f"Tentei {n} modelos alternativos sem sucesso. Os servidores podem estar "
        "sobrecarregados — tente novamente em alguns minutos."
    )


async def send_and_persist_error(
    ws: "WebSocket",
    db,
    conversation_id: str,
    main_msg: str,
    cascade_history: list[dict],
    current_model_id: str | None = None,
    current_provider_id: str | None = None,
    turn_id: str | None = None,
    *,
    reason: str = "provider_error",
    outcome: Literal["error", "empty", "timeout", "cancelled"] = "error",
):
    # Log técnico completo para diagnóstico do backend (nunca enviado ao frontend)
    if cascade_history:
        logger.warning(
            _build_cascade_debug_log(cascade_history, main_msg),
            extra={"conversation_id": conversation_id},
        )

    # Fix failover: limpa qualquer rascunho de stream residual no frontend antes
    # de entregar o erro, evitando texto parcial "travado" na bolha.
    try:
        await ws.send_json(
            dump_ws_event(StreamClearEvent(turn_id=turn_id, conversation_id=conversation_id or None))
        )
    except Exception:
        pass

    summary = build_cascade_error_summary(cascade_history, main_msg)
    try:
        err_payload: dict[str, Any] = {
            "type": "error",
            "message": summary,
            "retry_suggested": True,
            "attempts": len(cascade_history),
        }
        if turn_id:
            err_payload["turn_id"] = turn_id
        if conversation_id:
            err_payload["conversation_id"] = conversation_id
        await ws.send_json(err_payload)
        await ws.send_json(build_stream_end_failure(
            reason=reason,
            outcome=outcome,
            conversation_id=conversation_id or None,
            turn_id=turn_id,
            message=summary,
        ))
    except Exception:
        pass

    if db and conversation_id:
        try:
            from backend.orchestration.persist_turn import save_assistant_message
            await save_assistant_message(
                db,
                conversation_id=conversation_id,
                full_response=summary,
                model_id=current_model_id or "",
                provider_id=current_provider_id or "",
                kind="error",
            )
        except Exception as save_err:
            logger.debug("Falha ao persistir mensagem de erro do assistente: %s", save_err)


class StreamLlmResult(tuple):
    """Tupla de retorno de stream_from_llm: (full_response, model_id, provider_id) com failover_meta acessível."""
    failover_meta: dict

    def __new__(cls, full_response: str, model_id: str, provider_id: str, failover_meta: dict | None = None):
        inst = super().__new__(cls, (full_response, model_id, provider_id))
        inst.failover_meta = failover_meta or {}
        return inst


class ResolveAndStreamResult(tuple):
    """Tupla de retorno de resolve_and_stream: (full_response, cache_hit, resolved_model_id, resolved_provider_id) com failover_meta acessível."""
    failover_meta: dict

    def __new__(cls, full_response: str, cache_hit: Any | None, resolved_model_id: str, resolved_provider_id: str, failover_meta: dict | None = None):
        inst = super().__new__(cls, (full_response, cache_hit, resolved_model_id, resolved_provider_id))
        inst.failover_meta = failover_meta or {}
        return inst


async def get_failover_total_budget(db) -> float:
    """Carrega o orçamento de tempo total da cascata (precedência: env > meta > padrão 45s)."""
    env_val = _parse_positive_finite_float(os.getenv("FAILOVER_TOTAL_BUDGET_SECONDS"))
    if env_val is not None:
        return env_val
    if db:
        try:
            async with db.execute("SELECT value FROM meta WHERE key = 'failover_total_budget_sec'") as cur:
                row = await cur.fetchone()
            meta_val = _parse_positive_finite_float(row[0] if row else None)
            if meta_val is not None:
                return meta_val
        except Exception:
            pass
    return DEFAULT_FAILOVER_TOTAL_BUDGET_SECONDS


async def get_failover_stream_ttft_timeout(db) -> float:
    """Carrega o limite de TTFT do stream inicial (precedência: env > meta > padrão 25s)."""
    env_val = _parse_positive_finite_float(os.getenv("FAILOVER_STREAM_TTFT_TIMEOUT_SECONDS"))
    if env_val is not None:
        return env_val
    if db:
        try:
            async with db.execute("SELECT value FROM meta WHERE key = 'stream_ttft_timeout_sec'") as cur:
                row = await cur.fetchone()
            meta_val = _parse_positive_finite_float(row[0] if row else None)
            if meta_val is not None:
                return meta_val
        except Exception:
            pass
    return DEFAULT_STREAM_TTFT_TIMEOUT_SECONDS


async def get_failover_inter_token_timeout(db) -> float:
    """Carrega o timeout entre tokens após início da geração (precedência: env > meta > padrão 35s)."""
    env_val = _parse_positive_finite_float(os.getenv("FAILOVER_INTER_TOKEN_TIMEOUT_SECONDS"))
    if env_val is not None:
        return env_val
    if db:
        try:
            async with db.execute("SELECT value FROM meta WHERE key = 'stream_inter_token_timeout_sec'") as cur:
                row = await cur.fetchone()
            meta_val = _parse_positive_finite_float(row[0] if row else None)
            if meta_val is not None:
                return meta_val
        except Exception:
            pass
    return DEFAULT_INTER_TOKEN_TIMEOUT_SECONDS


async def check_cache(
    model_id: str,
    history: list[dict],
    context_fingerprint: str,
    bypass_cache: bool,
    user_id: str,
    request_context: Any | None = None,
) -> "CacheHit | None":
    """Consulta o cache (exact + semantic) ou retorna None se bypass."""
    if bypass_cache:
        return None
    t0 = time.perf_counter()
    try:
        from backend.cache.manager import cache_manager
        hit = await cache_manager.get(
            model_id,
            history,
            context_fingerprint=context_fingerprint or None,
            request_context=request_context,
            user_id=user_id,
        )
        if request_context and hasattr(request_context, "record_phase"):
            request_context.record_phase("fast_path", t0)
        return hit
    except Exception:
        logger.error("Erro ao consultar cache", exc_info=True, extra={
            "model_id": model_id,
        })
        return None


async def stream_from_cache(
    ws: "WebSocket",
    conversation_id: str,
    cache_hit: "CacheHit",
    turn_id: str | None = None,
) -> str:
    """Serve uma resposta do cache com fake-streaming para UX consistente."""
    await ws.send_json(
        dump_ws_event(
            StreamStartEvent(
                conversation_id=conversation_id,
                turn_id=turn_id,
                from_cache=True,
                cache_type=cache_hit.cache_type,
                cache_similarity=round(cache_hit.similarity, 4),
            )
        )
    )

    full_response = cache_hit.response
    chunk_size = 4
    for i in range(0, len(full_response), chunk_size):
        chunk = full_response[i:i + chunk_size]
        await ws.send_json(
            dump_ws_event(StreamTokenEvent(content=chunk, turn_id=turn_id, conversation_id=conversation_id))
        )
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
    request_context: Any | None = None,
    turn_id: str | None = None,
    fallback_requirements: FallbackRequirements | None = None,
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
    attempted_model_ids: set[str] = set()
    stream_started = False
    next_failover_reason = "rate_limit"
    tokens_flushed_to_client = False
    client_ttft_recorded = False

    total_budget = await get_failover_total_budget(db)
    base_stream_ttft_timeout = await get_failover_stream_ttft_timeout(db)
    inter_token_timeout = await get_failover_inter_token_timeout(db)
    turn_start_time = time.monotonic()
    cascade_history: list[dict] = []
    turn_first_send_ms: float | None = None
    turn_precommit_hold_ms: float | None = None
    turn_failover_recovery_ms: float | None = None
    first_token_elapsed_ms: float | None = None
    effort_compat_retries = 0

    async def fail_turn(
        message: str,
        model: str | None,
        provider: str | None,
        *,
        reason: str = "provider_error",
        outcome: Literal["error", "empty", "timeout", "cancelled"] = "error",
    ) -> None:
        await send_and_persist_error(
            ws, db, conversation_id, message, cascade_history, model, provider,
            turn_id=turn_id, reason=reason, outcome=outcome,
        )

    def can_retry() -> bool:
        remaining = total_budget - (time.monotonic() - turn_start_time)
        return remaining >= MIN_RETRY_BUDGET_SECONDS and attempt + effort_compat_retries < _MAX_FAILOVER_ATTEMPTS

    while attempt + effort_compat_retries < _MAX_FAILOVER_ATTEMPTS and not success:
        now = time.monotonic()
        elapsed = now - turn_start_time
        remaining_budget = total_budget - elapsed
        if remaining_budget < MIN_RETRY_BUDGET_SECONDS:
            logger.warning(
                "Orçamento total de failover esgotado (%.1fs decorridos de %.1fs) após %d tentativas.",
                elapsed, total_budget, attempt
            )
            await fail_turn(
                "Tempo limite de resposta esgotado após tentativas de failover.",
                original_model_id, "", reason="failover_budget_exhausted", outcome="timeout",
            )
            return None

        attempt += 1
        full_response = ""
        if tokens_flushed_to_client:
            # Fix failover: se o modelo anterior já emitiu tokens ao cliente e falhou,
            # limpa o rascunho do frontend para o próximo modelo não misturar respostas.
            try:
                await ws.send_json(
                    dump_ws_event(StreamClearEvent(turn_id=turn_id, conversation_id=conversation_id or None))
                )
            except Exception:
                pass
            tokens_flushed_to_client = False

        try:
            resolved = await resolve_model_with_failover(
                model_id if attempt == 1 else original_model_id,
                db,
                failover_reason=next_failover_reason,
                failover_enabled=True,
                exclude_model_ids=list(attempted_model_ids),
                user_id=user_id,
                **({"requirements": fallback_requirements} if fallback_requirements else {}),
            )
        except NoAvailableModelError:
            await fail_turn(
                "Nenhum modelo elegível está disponível. Tente novamente mais tarde.",
                original_model_id, None, reason="no_available_model",
            )
            return None

        if resolved.was_failover:
            # UX C2: Failover invisível. Não emitimos failover_notice antecipado para não
            # poluir o cliente com toasts caso o modelo reserva responda com sucesso.
            # O modelo que respondeu é identificado no metadata terminal (stream_end).
            if history and isinstance(history, list) and history[0].get("role") == "system":
                sys_content = history[0].get("content") or ""
                new_ident = f"O modelo de inteligência artificial em execução neste turno é: {resolved.display_name} (via {resolved.provider_id})."
                sys_content = re.sub(
                    r"O modelo de inteligência artificial em execução neste turno é:[^\n]+",
                    new_ident,
                    sys_content,
                )
                history[0]["content"] = sys_content

            # Adapta o histórico para a janela de contexto do modelo reserva
            try:
                from backend.orchestration.handle_attachments import resolve_input_budget, trim_history_to_budget
                from backend.projects.context_builder import estimate_tokens
                fb_budget = await resolve_input_budget(db, resolved.model_id, resolved.provider_id)
                sys_msg = history[0] if history and history[0].get("role") == "system" else None
                msgs = history[1:] if sys_msg else history
                reserved = estimate_tokens(sys_msg.get("content", "")) if sys_msg else 0
                trimmed_msgs, _ = trim_history_to_budget(msgs, fb_budget, reserved_tokens=reserved)
                history = ([sys_msg] if sys_msg else []) + trimmed_msgs
            except Exception as fb_err:
                logger.debug("Falha ao ajustar orçamento no failover: %s", fb_err)

        current_model_id = resolved.model_id
        current_provider_id = resolved.provider_id

        if attempt > 1:
            try:
                prev_info = cascade_history[-1] if cascade_history else None
                detail = (
                    f"Tentativa anterior falhou ({prev_info['detail']}). "
                    f"Alternando para {resolved.display_name} ({current_provider_id})."
                    if prev_info
                    else f"Alternando para {resolved.display_name} ({current_provider_id})."
                )
                await ws.send_json({
                    "type": "process_step_start",
                    "id": f"failover-{attempt}",
                    "step_type": "tool",
                    "title": f"Failover ({attempt}/{_MAX_FAILOVER_ATTEMPTS}): {resolved.display_name}",
                    "detail": detail,
                    "status": "running",
                })
            except Exception:
                pass

        try:
            provider = await get_provider(current_provider_id, db, user_id=user_id)
            model_name = await get_model_name(current_model_id, db)
        except ValueError:
            logger.warning(
                "Falha ao carregar provedor '%s' para modelo '%s'. Acionando failover...",
                current_provider_id, current_model_id,
            )
            cascade_history.append({
                "attempt": attempt,
                "model_id": current_model_id,
                "provider_id": current_provider_id,
                "detail": "Falha de configuração do provedor.",
                "reason": "provider_configuration",
            })
            attempted_model_ids.add(current_model_id)
            if not can_retry():
                await fail_turn(
                    "Não foi possível carregar um modelo disponível. Tente novamente mais tarde.",
                    current_model_id, current_provider_id, reason="provider_configuration",
                )
                return None
            continue

        if not stream_started:
            await ws.send_json(
                dump_ws_event(
                    StreamStartEvent(
                        conversation_id=conversation_id,
                        turn_id=turn_id,
                        from_cache=False,
                    )
                )
            )
            stream_started = True

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
            is_reasoning_capable = bool(
                active_effort
                or (ctrl and ctrl not in ("none", ""))
                or any(k in current_model_id.lower() for k in ("deepseek-r1", "deepseek-reasoner", "qwq", "hy4", "hunyuan", "qwen-max", "thinking", "reasoning", "reasoner"))
                or any(k in str(model_name).lower() for k in ("deepseek-r1", "deepseek-reasoner", "qwq", "hy4", "hunyuan", "qwen-max", "thinking", "reasoning", "reasoner"))
                or re.search(r"(?:^|[\/\-_])(o1|o3|o4|r1)(?:[\-_]|$)", current_model_id.lower())
                or re.search(r"(?:^|[\/\-_])(o1|o3|o4|r1)(?:[\-_]|$)", str(model_name).lower())
            )
            if is_reasoning_capable:
                curr_max = int(max_tokens) if max_tokens is not None else 4096
                # Não altera se o usuário estiver em voice_mode (onde max_tokens é propositalmente <= 300)
                if curr_max > 300 and curr_max <= 4096:
                    stream_kwargs["max_tokens"] = 8192
                elif max_tokens is not None:
                    stream_kwargs["max_tokens"] = int(max_tokens)
                else:
                    stream_kwargs["max_tokens"] = 8192
            elif max_tokens is not None:
                stream_kwargs["max_tokens"] = int(max_tokens)
            if active_effort is not None:
                stream_kwargs["reasoning_effort"] = active_effort
            if active_ctrl is not None:
                stream_kwargs["reasoning_control"] = active_ctrl

            # ── Token Bucket Preventivo com Histerese (JEV Fast Plano 16) ────
            from backend.ranking.token_bucket import token_bucket_manager
            is_sticky = bool(
                auto_route_decision
                and "sticky_routing_cache" in getattr(auto_route_decision, "matched_signals", [])
                and current_model_id == getattr(auto_route_decision, "chosen_model_id", None)
            )
            token_allowed = await token_bucket_manager.consume_token(
                current_provider_id, is_sticky=is_sticky
            )
            if not token_allowed:
                logger.warning(
                    "JEV Anti-429: Provedor '%s' (modelo '%s') sem quota preventiva de RPM. Acionando failover cascade.",
                    current_provider_id,
                    current_model_id,
                )
                cascade_history.append({
                    "attempt": attempt,
                    "model_id": current_model_id,
                    "provider_id": current_provider_id,
                    "detail": "Limite preventivo de RPM (Token Bucket) atingido.",
                })
                if attempt > 1:
                    try:
                        await ws.send_json({
                            "type": "process_step_end",
                            "id": f"failover-{attempt}",
                            "status": "failed",
                        })
                    except Exception:
                        pass
                attempted_model_ids.add(current_model_id)
                elapsed_after = time.monotonic() - turn_start_time
                if (total_budget - elapsed_after) < MIN_RETRY_BUDGET_SECONDS:
                    await fail_turn(
                        "Tempo limite de resposta esgotado após tentativas de failover.",
                        current_model_id, current_provider_id, reason="failover_budget_exhausted", outcome="timeout",
                    )
                    return None
                if attempt >= _MAX_FAILOVER_ATTEMPTS:
                    await fail_turn(
                        "Todos os provedores elegíveis atingiram o limite temporário de requisições por minuto (RPM). Aguarde alguns instantes.",
                        current_model_id, current_provider_id, reason="rate_limit", outcome="error",
                    )
                    return None
                continue

            elapsed_now = time.monotonic() - turn_start_time
            remaining_budget = total_budget - elapsed_now
            if remaining_budget < MIN_RETRY_BUDGET_SECONDS:
                logger.warning(
                    "Orçamento total de failover esgotado (%.1fs decorridos de %.1fs) antes do início do stream.",
                    elapsed_now, total_budget
                )
                await fail_turn(
                    "Tempo limite de resposta esgotado após tentativas de failover.",
                    current_model_id, current_provider_id, reason="failover_budget_exhausted", outcome="timeout",
                )
                return None

            max_ttft = base_stream_ttft_timeout if attempt == 1 else min(15.0, max(5.0, remaining_budget * 0.5))
            stream_ttft_timeout = max(0.5, min(max_ttft, remaining_budget))
            first_token_received = False
            first_token_elapsed_ms = None
            is_committed = False
            candidate_response = ""
            measurement_attempt = attempt + effort_compat_retries

            async def _consume_candidate_stream(
                call_kwargs: dict,
                *,
                ttft_budget_s: float,
            ) -> tuple[str, bool, float | None, bool]:
                """Consumidor único de stream (usado pela tentativa normal e pelo retry sem esforço)."""
                nonlocal tokens_flushed_to_client, client_ttft_recorded, is_committed
                nonlocal turn_first_send_ms, turn_precommit_hold_ms, turn_failover_recovery_ms

                is_committed = False
                stream_start_mono = time.monotonic()
                stream_start_perf = time.perf_counter()
                local_first_nonempty_mono: float | None = None
                local_first_token_ms: float | None = None
                local_first_frame_sent_mono: float | None = None
                local_committed = False
                precommit_buffer: list[str] = []
                precommit_chars = 0
                local_response = ""
                token_buffer: list[str] = []
                last_flush_mono = stream_start_mono

                async def flush_tokens():
                    nonlocal last_flush_mono, tokens_flushed_to_client, client_ttft_recorded
                    nonlocal local_first_frame_sent_mono, turn_first_send_ms, turn_precommit_hold_ms
                    nonlocal turn_failover_recovery_ms
                    if token_buffer:
                        batch_text = "".join(token_buffer)
                        await ws.send_json(
                            dump_ws_event(
                                StreamTokenEvent(
                                    content=batch_text,
                                    turn_id=turn_id,
                                    conversation_id=conversation_id or None,
                                )
                            )
                        )
                        now_mono = time.monotonic()
                        token_buffer.clear()
                        last_flush_mono = now_mono
                        tokens_flushed_to_client = True
                        if local_first_frame_sent_mono is None:
                            local_first_frame_sent_mono = now_mono
                            if local_first_nonempty_mono is not None:
                                hold_ms = round((now_mono - local_first_nonempty_mono) * 1000.0, 2)
                                turn_precommit_hold_ms = hold_ms
                                if request_context and hasattr(request_context, "phase_latencies"):
                                    request_context.phase_latencies["precommit_hold_ms"] = hold_ms
                            if attempt > 1 and turn_failover_recovery_ms is None:
                                rec_ms = round((now_mono - turn_start_time) * 1000.0, 2)
                                turn_failover_recovery_ms = rec_ms
                                if request_context and hasattr(request_context, "phase_latencies"):
                                    request_context.phase_latencies["failover_recovery_ms"] = rec_ms
                                    request_context.phase_latencies["failover_cascade"] = rec_ms
                        if not client_ttft_recorded:
                            turn_first_send_ms = round((now_mono - turn_start_time) * 1000.0, 2)
                            if request_context and hasattr(request_context, "record_phase"):
                                turn_started_at = getattr(request_context, "started_at", None)
                                if turn_started_at is not None:
                                    request_context.record_phase("client_ttft", turn_started_at)
                                else:
                                    request_context.phase_latencies["client_ttft"] = turn_first_send_ms
                            client_ttft_recorded = True

                def commit_if_needed(force: bool = False):
                    nonlocal local_committed, local_response, is_committed
                    if local_committed:
                        return
                    elapsed_ms = (time.monotonic() - stream_start_mono) * 1000.0
                    if force or precommit_chars >= DEFAULT_MIN_COMMIT_CHARS or elapsed_ms >= DEFAULT_MAX_PRECOMMIT_HOLD_MS:
                        local_committed = True
                        is_committed = True
                        if precommit_buffer:
                            buffered_str = "".join(precommit_buffer)
                            local_response += buffered_str
                            token_buffer.append(buffered_str)
                            precommit_buffer.clear()

                from backend.ranking.admission import admission_controller
                admission_acquired = admission_controller.acquire(current_model_id, current_provider_id)
                stream_iter = None
                pending_next_token: asyncio.Task | None = None
                heartbeat_task: asyncio.Task | None = None

                async def _cancel_and_drain_pending():
                    nonlocal pending_next_token
                    task = pending_next_token
                    pending_next_token = None
                    if task is None:
                        return
                    if not task.done():
                        task.cancel()
                    try:
                        await task
                    except BaseException:
                        # Consome qualquer erro concorrente / StopAsyncIteration / CancelledError
                        # para nunca vazar "Task exception was never retrieved".
                        pass

                try:
                    stream_iter = provider.stream_chat(model=model_name, messages=history, **call_kwargs).__aiter__()

                    async def _ttft_heartbeat():
                        await asyncio.sleep(3.0)
                        while True:
                            try:
                                await ws.send_json({
                                    "type": "process_step_update",
                                    "id": f"model-connect-{attempt}",
                                    "title": "Conectando ao modelo...",
                                    "status": "working",
                                })
                            except Exception:
                                break
                            await asyncio.sleep(3.0)

                    # Fase 1: aguarda primeiro delta não vazio dentro do deadline monotônico de TTFT
                    ttft_deadline = stream_start_mono + max(0.05, float(ttft_budget_s))
                    heartbeat_task = asyncio.create_task(_ttft_heartbeat())
                    try:
                        while local_first_nonempty_mono is None:
                            rem_ttft = ttft_deadline - time.monotonic()
                            if rem_ttft <= 0.0:
                                raise asyncio.TimeoutError()
                            if pending_next_token is None:
                                pending_next_token = asyncio.create_task(stream_iter.__anext__())
                            done, _ = await asyncio.wait({pending_next_token}, timeout=rem_ttft)
                            if not done:
                                raise asyncio.TimeoutError()
                            task = pending_next_token
                            pending_next_token = None
                            try:
                                tok = task.result()
                            except StopAsyncIteration:
                                # Stream encerrou sem produzir nenhum delta não vazio
                                return local_response, False, None, local_committed
                            tok_str = str(tok) if tok is not None else ""
                            if not tok_str:
                                continue
                            now_mono = time.monotonic()
                            local_first_nonempty_mono = now_mono
                            local_first_token_ms = (now_mono - stream_start_mono) * 1000.0
                            if request_context and hasattr(request_context, "record_phase"):
                                request_context.record_phase("llm_ttfb", stream_start_perf)
                                request_context.record_phase(f"llm_ttft_attempt_{measurement_attempt}", stream_start_perf)
                            precommit_buffer.append(tok_str)
                            precommit_chars += len(tok_str)
                            commit_if_needed()
                            if local_committed:
                                await flush_tokens()
                    finally:
                        if heartbeat_task is not None:
                            heartbeat_task.cancel()
                            try:
                                await heartbeat_task
                            except BaseException:
                                pass
                            heartbeat_task = None

                    # Fase 2: consome restante do stream com uma única tarefa __anext__ pendente por vez
                    # e timeout monotônico entre tokens (inter_token_timeout).
                    last_token_mono = time.monotonic()
                    while True:
                        now_mono = time.monotonic()
                        inter_remaining = inter_token_timeout - (now_mono - last_token_mono)
                        if inter_remaining <= 0.0:
                            raise _InterTokenTimeoutError(
                                inter_token_timeout,
                                len(local_response) + precommit_chars,
                                local_committed,
                            )

                        wait_timeout = inter_remaining
                        precommit_deadline_wait = False
                        if not local_committed and precommit_buffer:
                            elapsed_ms = (now_mono - stream_start_mono) * 1000.0
                            hold_remaining = max(0.0, (DEFAULT_MAX_PRECOMMIT_HOLD_MS - elapsed_ms) / 1000.0)
                            if hold_remaining <= 0.0:
                                commit_if_needed(force=True)
                                await flush_tokens()
                                continue
                            if hold_remaining < wait_timeout:
                                wait_timeout = hold_remaining
                                precommit_deadline_wait = True

                        if pending_next_token is None:
                            pending_next_token = asyncio.create_task(stream_iter.__anext__())
                        done, _ = await asyncio.wait({pending_next_token}, timeout=wait_timeout)
                        if not done:
                            if precommit_deadline_wait and not local_committed:
                                commit_if_needed(force=True)
                                await flush_tokens()
                                continue
                            raise _InterTokenTimeoutError(
                                inter_token_timeout,
                                len(local_response) + precommit_chars,
                                local_committed,
                            )

                        task = pending_next_token
                        pending_next_token = None
                        try:
                            token = task.result()
                        except StopAsyncIteration:
                            break
                        except (asyncio.TimeoutError, TimeoutError):
                            raise _InterTokenTimeoutError(
                                inter_token_timeout,
                                len(local_response) + precommit_chars,
                                local_committed,
                            )

                        token_str = str(token) if token is not None else ""
                        if not token_str:
                            continue
                        last_token_mono = time.monotonic()
                        if not local_committed:
                            precommit_buffer.append(token_str)
                            precommit_chars += len(token_str)
                            commit_if_needed()
                            if local_committed:
                                await flush_tokens()
                        else:
                            local_response += token_str
                            token_buffer.append(token_str)
                            if len(token_buffer) >= 8 or (last_token_mono - last_flush_mono) >= 0.035:
                                await flush_tokens()

                    # Fim natural do stream: se resposta curta não atingiu min_commit_chars, força commit
                    if not local_committed and precommit_buffer:
                        commit_if_needed(force=True)
                    await flush_tokens()
                    return local_response, True, local_first_token_ms, local_committed
                finally:
                    if heartbeat_task is not None:
                        heartbeat_task.cancel()
                        try:
                            await heartbeat_task
                        except BaseException:
                            pass
                    await _cancel_and_drain_pending()
                    if not local_committed:
                        precommit_buffer.clear()
                        token_buffer.clear()
                        local_response = ""
                    if admission_acquired:
                        admission_controller.release(current_model_id, current_provider_id)
                    if stream_iter is not None:
                        try:
                            if hasattr(stream_iter, "aclose"):
                                await stream_iter.aclose()
                        except Exception:
                            pass

            stream_attempt_start_perf = time.perf_counter()
            try:
                try:
                    result = await _consume_candidate_stream(stream_kwargs, ttft_budget_s=stream_ttft_timeout)
                except Exception as exc:
                    # Reuse this candidate only for a parameter rejection before it
                    # publishes any text. The retry shares the ordinary outcome handling.
                    detail = str(exc).lower()
                    compatibility_error = active_effort is not None and any(
                        term in detail for term in (
                            "reasoning_effort", "thinkingconfig", "thinking_config",
                        )
                    )
                    if not compatibility_error or is_committed or effort_compat_retries or not can_retry():
                        raise
                    effort_compat_retries += 1
                    measurement_attempt += 1
                    await ws.send_json({
                        "type": "effort_dropped",
                        "reason": "provider_rejected",
                        "model_id": current_model_id,
                        "requested": active_effort,
                    })
                    stream_kwargs.pop("reasoning_effort", None)
                    stream_kwargs.pop("reasoning_control", None)
                    stream_attempt_start_perf = time.perf_counter()
                    remaining = total_budget - (time.monotonic() - turn_start_time)
                    if remaining <= 0:
                        raise asyncio.TimeoutError()
                    stream_ttft_timeout = min(stream_ttft_timeout, remaining)
                    result = await _consume_candidate_stream(stream_kwargs, ttft_budget_s=stream_ttft_timeout)
                candidate_response, first_token_received, first_token_elapsed_ms, is_committed = result
            except (asyncio.TimeoutError, TimeoutError):
                # Série própria para timeouts de TTFT (nunca misturada em llm_ttft_attempt_N)
                if request_context and hasattr(request_context, "record_phase"):
                    request_context.record_phase(
                        f"llm_ttft_timeout_attempt_{measurement_attempt}", stream_attempt_start_perf
                    )
                logger.warning(
                    "TTFT Timeout (%.1fs excedido) no provedor '%s' (modelo '%s'). Acionando failover cascade precoce.",
                    stream_ttft_timeout, current_provider_id, current_model_id,
                )
                from backend.ranking.health_registry import health_registry
                health_registry.record_failure(current_model_id, current_provider_id, "TIMEOUT", stage="pre_stream")
                ttft_fail_ms = (time.perf_counter() - stream_attempt_start_perf) * 1000.0
                cascade_history.append({
                    "attempt": attempt,
                    "model_id": current_model_id,
                    "provider_id": current_provider_id,
                    "detail": f"Tempo limite de resposta excedido ({int(stream_ttft_timeout)}s)",
                    "latency_ms": round(ttft_fail_ms, 2),
                    "reason": "ttft_timeout",
                })
                if attempt > 1:
                    try:
                        await ws.send_json({
                            "type": "process_step_end",
                            "id": f"failover-{attempt}",
                            "status": "failed",
                        })
                    except Exception:
                        pass
                attempted_model_ids.add(current_model_id)
                elapsed_after = time.monotonic() - turn_start_time
                if (total_budget - elapsed_after) < MIN_RETRY_BUDGET_SECONDS or attempt >= _MAX_FAILOVER_ATTEMPTS:
                    msg = (
                        "Tempo limite de resposta esgotado após tentativas de failover."
                        if (total_budget - elapsed_after) < MIN_RETRY_BUDGET_SECONDS
                        else f"Tempo limite de resposta excedido ({int(stream_ttft_timeout)}s) no modelo '{current_model_id}'."
                    )
                    await fail_turn(
                        msg, current_model_id, current_provider_id,
                        reason="ttft_timeout", outcome="timeout",
                    )
                    return None
                continue
            except _InterTokenTimeoutError as it_err:
                if request_context and hasattr(request_context, "record_phase"):
                    request_context.record_phase(
                        f"llm_inter_token_timeout_attempt_{measurement_attempt}", stream_attempt_start_perf
                    )
                logger.warning(
                    "Timeout entre tokens (%.1fs) no provedor '%s' (modelo '%s').",
                    it_err.timeout_s, current_provider_id, current_model_id,
                )
                from backend.ranking.health_registry import health_registry
                health_registry.record_failure(
                    current_model_id, current_provider_id, "MID_STREAM_TIMEOUT", stage="mid_stream"
                )
                cascade_history.append({
                    "attempt": attempt,
                    "model_id": current_model_id,
                    "provider_id": current_provider_id,
                    "detail": f"Silêncio prolongado entre tokens ({it_err.timeout_s:.1f}s)",
                    "reason": "inter_token_timeout",
                })
                if attempt > 1:
                    try:
                        await ws.send_json({
                            "type": "process_step_end",
                            "id": f"failover-{attempt}",
                            "status": "failed",
                        })
                    except Exception:
                        pass
                attempted_model_ids.add(current_model_id)
                next_failover_reason = "inter_token_timeout"
                if it_err.committed:
                    tokens_flushed_to_client = True
                elapsed_after = time.monotonic() - turn_start_time
                if (total_budget - elapsed_after) >= MIN_RETRY_BUDGET_SECONDS and attempt < _MAX_FAILOVER_ATTEMPTS:
                    continue
                await fail_turn(
                    "A geração foi interrompida por silêncio prolongado do modelo.",
                    current_model_id, current_provider_id, reason="inter_token_timeout", outcome="timeout",
                )
                return None

            # Salvaguarda de truncamento no raciocínio (R1)
            open_th = re.findall(r"<(think|thinking|reasoning|analysis)\b[^>]*>", candidate_response, re.IGNORECASE)
            close_th = re.findall(r"</(think|thinking|reasoning|analysis)>", candidate_response, re.IGNORECASE)
            if len(open_th) > len(close_th):
                tag_to_close = open_th[-1]
                closed_suffix = f"</{tag_to_close}>\n\n"
                candidate_response += closed_suffix
                await ws.send_json({"type": "token", "content": closed_suffix})
                tokens_flushed_to_client = True

            pure_answer = re.sub(
                r"<(think|thinking|reasoning|analysis)\b[^>]*>[\s\S]*?</\1>",
                "",
                candidate_response,
                flags=re.IGNORECASE,
            ).strip()

            if candidate_response.strip() and not pure_answer:
                logger.warning(
                    "Modelo '%s' (provedor '%s') esgotou tokens no raciocínio sem gerar resposta visível.",
                    current_model_id, current_provider_id,
                )
                elapsed_now = time.monotonic() - turn_start_time
                if attempt < _MAX_FAILOVER_ATTEMPTS and (total_budget - elapsed_now) >= MIN_RETRY_BUDGET_SECONDS:
                    cascade_history.append({
                        "attempt": attempt,
                        "model_id": current_model_id,
                        "provider_id": current_provider_id,
                        "detail": "Modelo esgotou o limite de tokens durante o raciocínio sem gerar resposta.",
                    })
                    attempted_model_ids.add(current_model_id)
                    tokens_flushed_to_client = True
                    next_failover_reason = "length_exhaustion"
                    continue
                else:
                    notice = (
                        "\n\n[Aviso: O modelo esgotou seu limite de geração durante a etapa de raciocínio. "
                        "Tente reduzir o esforço de raciocínio ou reformular a pergunta.]"
                    )
                    candidate_response += notice
                    await ws.send_json({"type": "token", "content": notice})
                    tokens_flushed_to_client = True

            if not candidate_response.strip():
                logger.warning(
                    "Modelo '%s' (provedor '%s') não gerou nenhum token de resposta. Acionando failover cascade...",
                    current_model_id, current_provider_id,
                )
                from backend.ranking.health_registry import health_registry
                health_registry.record_failure(current_model_id, current_provider_id, "ZERO_TOKEN", stage="pre_stream")
                from backend.ranking.canonical import apply_zero_token_cooldown
                await apply_zero_token_cooldown(
                    current_model_id,
                    db,
                    retry_after=600,
                )
                cascade_history.append({
                    "attempt": attempt,
                    "model_id": current_model_id,
                    "provider_id": current_provider_id,
                    "detail": "Modelo finalizou sem gerar nenhum token de resposta.",
                })
                if attempt > 1:
                    try:
                        await ws.send_json({
                            "type": "process_step_end",
                            "id": f"failover-{attempt}",
                            "status": "failed",
                        })
                    except Exception:
                        pass
                attempted_model_ids.add(current_model_id)
                next_failover_reason = "silent_failure"
                elapsed_after = time.monotonic() - turn_start_time
                if (total_budget - elapsed_after) < MIN_RETRY_BUDGET_SECONDS or attempt >= _MAX_FAILOVER_ATTEMPTS:
                    msg = (
                        "Tempo limite de resposta esgotado após tentativas de failover."
                        if (total_budget - elapsed_after) < MIN_RETRY_BUDGET_SECONDS
                        else f"O modelo '{current_model_id}' não retornou nenhuma resposta após o failover."
                    )
                    await fail_turn(
                        msg, current_model_id, current_provider_id,
                        reason="empty_model_response", outcome="empty",
                    )
                    return None
                continue

            full_response = candidate_response
            from backend.ranking.health_registry import health_registry
            ttft_measured_ms = first_token_elapsed_ms if first_token_received else None
            health_registry.record_success(current_model_id, current_provider_id, ttft_ms=ttft_measured_ms)

            await mark_model_success(current_model_id, db)
            await record_request(current_model_id, db)
            success = True
            if attempt > 1:
                try:
                    await ws.send_json({
                        "type": "process_step_end",
                        "id": f"failover-{attempt}",
                        "status": "completed",
                    })
                except Exception:
                    pass

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

        except asyncio.CancelledError:
            logger.info(
                "Streaming cancelado pelo cliente/sistema no modelo '%s' (provedor '%s'). Limpando recursos e propagando cancelamento sem failover.",
                current_model_id, current_provider_id,
            )
            raise
        except (WebSocketDisconnect, ConnectionResetError, BrokenPipeError) as ws_err:
            logger.info(
                "Conexão do cliente perdida durante streaming no modelo '%s' (provedor '%s'): %s. Encerrando sem penalizar modelo nem failover.",
                current_model_id, current_provider_id, ws_err,
            )
            return None
        except RateLimitError as e:
            next_failover_reason = getattr(e, "failover_reason", None) or "rate_limit"
            from backend.ranking.token_bucket import token_bucket_manager
            await token_bucket_manager.on_rate_limit(current_provider_id)
            cascade_history.append({
                "attempt": attempt,
                "model_id": current_model_id,
                "provider_id": current_provider_id,
                "detail": "Limite de requisições excedido (rate limit).",
                "reason": "rate_limit",
            })
            if attempt > 1:
                try:
                    await ws.send_json({
                        "type": "process_step_end",
                        "id": f"failover-{attempt}",
                        "status": "failed",
                    })
                except Exception:
                    pass
            attempted_model_ids.add(current_model_id)
            from backend.ranking.health_registry import health_registry
            health_registry.record_failure(current_model_id, current_provider_id, "RATE_LIMIT_429", stage="pre_stream")
            await mark_model_exhausted(current_model_id, db, e.retry_after, "HTTP 429 rate limit")
            elapsed_after = time.monotonic() - turn_start_time
            if (total_budget - elapsed_after) < MIN_RETRY_BUDGET_SECONDS or not can_retry():
                msg = (
                    "Tempo limite de resposta esgotado após tentativas de failover."
                    if (total_budget - elapsed_after) < MIN_RETRY_BUDGET_SECONDS
                    else "Limite de tentativas de failover excedido. O modelo está esgotado."
                )
                await fail_turn(
                    msg, current_model_id, current_provider_id,
                    reason="rate_limit", outcome="error",
                )
                return None
            continue
        except Exception as e:
            error_msg = str(e)
            if isinstance(e, RuntimeError) and any(
                term in error_msg.lower() for term in (
                    "websocket.send", "websocket.disconnect", "websocket is not connected", "close message has been sent",
                )
            ):
                logger.info(
                    "Conexão do cliente encerrada durante streaming. Finalizando sem penalizar modelo nem failover.",
                )
                return None

            stage = "mid_stream" if is_committed else "pre_stream"
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

            # T1.1: Extrai status_code estruturado e classifica via ranking/classifier.py
            from backend.ranking.classifier import classify_failure, extract_structured_error
            structured = extract_structured_error(e)
            http_status = structured.get("status_code")
            classification = classify_failure(
                provider=current_provider_id,
                http_status=http_status,
                body=error_msg,
                tokens_emitted=1 if is_committed else 0,
                stage=stage,
            )
            outcome = classification["outcome"]
            scope = classification["scope"]
            reason = classification["reason"]
            cooldown = classification.get("cooldown", 0)

            # T2.1: Credencial-level quarantine para 402 (insufficient_user_quota / err_credit_gate)
            if outcome == "QUOTA_402" or reason == "quota_exhausted":
                logger.warning(
                    "Cota/crédito esgotado na credencial do provedor '%s' (modelo '%s'). Aplicando quarentena de credencial de 1h...",
                    current_provider_id, current_model_id,
                )
                from backend.ranking.quota import quarantine_credential
                api_key = getattr(provider, "api_key", None)
                await quarantine_credential(
                    current_provider_id,
                    api_key,
                    db,
                    duration_seconds=cooldown or 3600,
                    reason="quota_exhausted",
                )
                await mark_model_exhausted(current_model_id, db, retry_after=cooldown or 3600, error_msg="quota_exhausted")
                from backend.ranking.health_registry import health_registry
                health_registry.record_failure(current_model_id, current_provider_id, "QUOTA_402", stage=stage)
                cascade_history.append({
                    "attempt": attempt,
                    "model_id": current_model_id,
                    "provider_id": current_provider_id,
                    "detail": "Crédito ou cota esgotada.",
                    "reason": "quota_exhausted",
                })
                if attempt > 1:
                    try:
                        await ws.send_json({
                            "type": "process_step_end",
                            "id": f"failover-{attempt}",
                            "status": "failed",
                        })
                    except Exception:
                        pass
                attempted_model_ids.add(current_model_id)
                next_failover_reason = "quota_exhausted"
                elapsed_after = time.monotonic() - turn_start_time
                if (total_budget - elapsed_after) < MIN_RETRY_BUDGET_SECONDS:
                    await fail_turn(
                        "Tempo limite de resposta esgotado após tentativas de failover.",
                        current_model_id, current_provider_id, reason="failover_budget_exhausted", outcome="timeout",
                    )
                    return None
                if not is_committed and can_retry():
                    continue
                await fail_turn(
                    "Limite de cota do modelo atingido. Tente novamente mais tarde.",
                    current_model_id, current_provider_id, reason="quota_exhausted", outcome="error",
                )
                return None

            # T1.3: Rate limit 429
            if outcome == "RATE_LIMIT_429" or reason == "rate_limit":
                retry_after = getattr(e, "retry_after", None) or cooldown or 60
                from backend.ranking.token_bucket import token_bucket_manager
                await token_bucket_manager.on_rate_limit(current_provider_id)
                await mark_model_exhausted(current_model_id, db, retry_after, "HTTP 429 rate limit")
                from backend.ranking.health_registry import health_registry
                health_registry.record_failure(current_model_id, current_provider_id, "RATE_LIMIT_429", stage=stage)
                cascade_history.append({
                    "attempt": attempt,
                    "model_id": current_model_id,
                    "provider_id": current_provider_id,
                    "detail": "Limite de requisições excedido (rate limit).",
                    "reason": "rate_limit",
                })
                if attempt > 1:
                    try:
                        await ws.send_json({
                            "type": "process_step_end",
                            "id": f"failover-{attempt}",
                            "status": "failed",
                        })
                    except Exception:
                        pass
                attempted_model_ids.add(current_model_id)
                next_failover_reason = "rate_limit"
                elapsed_after = time.monotonic() - turn_start_time
                if (total_budget - elapsed_after) < MIN_RETRY_BUDGET_SECONDS or not can_retry():
                    msg = (
                        "Tempo limite de resposta esgotado após tentativas de failover."
                        if (total_budget - elapsed_after) < MIN_RETRY_BUDGET_SECONDS
                        else "Limite de tentativas de failover excedido. O modelo está esgotado."
                    )
                    await fail_turn(
                        msg, current_model_id, current_provider_id,
                        reason="rate_limit", outcome="error",
                    )
                    return None
                continue

            # T1.2 & T2.2: LLM7 HTTP 400 model_unavailable (cooldown temporário sem desativação permanente)
            if outcome == "MODEL_UNAVAILABLE" or reason == "model_unavailable":
                logger.warning(
                    "Modelo '%s' temporariamente indisponível no provedor '%s' (HTTP 400 model_unavailable). Aplicando cooldown temporário de %ds...",
                    current_model_id, current_provider_id, cooldown or 300,
                )
                await mark_model_exhausted(current_model_id, db, retry_after=cooldown or 300, error_msg="model_unavailable")
                from backend.ranking.health_registry import health_registry
                health_registry.record_failure(current_model_id, current_provider_id, "MODEL_UNAVAILABLE", stage=stage)
                cascade_history.append({
                    "attempt": attempt,
                    "model_id": current_model_id,
                    "provider_id": current_provider_id,
                    "detail": "Modelo temporariamente indisponível no provedor.",
                    "reason": "model_unavailable",
                })
                if attempt > 1:
                    try:
                        await ws.send_json({
                            "type": "process_step_end",
                            "id": f"failover-{attempt}",
                            "status": "failed",
                        })
                    except Exception:
                        pass
                attempted_model_ids.add(current_model_id)
                next_failover_reason = "model_unavailable"
                elapsed_after = time.monotonic() - turn_start_time
                if (total_budget - elapsed_after) < MIN_RETRY_BUDGET_SECONDS:
                    await fail_turn(
                        "Tempo limite de resposta esgotado após tentativas de failover.",
                        current_model_id, current_provider_id, reason="failover_budget_exhausted", outcome="timeout",
                    )
                    return None
                if not is_committed and can_retry():
                    continue
                await fail_turn(
                    "Modelo temporariamente indisponível. Tente novamente mais tarde.",
                    current_model_id, current_provider_id, reason="model_unavailable", outcome="error",
                )
                return None

            # T1.2: Requisição Inválida (scope=request, cooldown=0) — aborta cascata com o mesmo payload
            if outcome == "INVALID_REQUEST" or scope == "request":
                logger.warning(
                    "Requisição inválida (HTTP 400 schema/payload) no modelo '%s' (provedor '%s'): %s. Interrompendo cascata.",
                    current_model_id, current_provider_id, classification.get("status_message"),
                )
                from backend.ranking.health_registry import health_registry
                health_registry.record_failure(current_model_id, current_provider_id, "INVALID_REQUEST", stage=stage)
                cascade_history.append({
                    "attempt": attempt,
                    "model_id": current_model_id,
                    "provider_id": current_provider_id,
                    "detail": "Requisição inválida enviada ao modelo.",
                    "reason": "invalid_request",
                })
                if attempt > 1:
                    try:
                        await ws.send_json({
                            "type": "process_step_end",
                            "id": f"failover-{attempt}",
                            "status": "failed",
                        })
                    except Exception:
                        pass
                await fail_turn(
                    "Requisição inválida enviada ao modelo. Verifique os parâmetros e tente novamente.",
                    current_model_id, current_provider_id, reason="invalid_request", outcome="error",
                )
                return None

            from backend.ranking.health_registry import health_registry
            health_registry.record_failure(
                current_model_id,
                current_provider_id,
                outcome if outcome in ("MODEL_DEPRECATED", "MODEL_NOT_FOUND_404") else ("PRE_STREAM_ERR" if stage == "pre_stream" else "MID_STREAM_DROP"),
                stage=stage,
            )
            from backend.database import check_and_deactivate_model
            await check_and_deactivate_model(current_model_id, error_msg, db, diagnostic_safe=True)

            cascade_history.append({
                "attempt": attempt,
                "model_id": current_model_id,
                "provider_id": current_provider_id,
                "detail": "Erro do provedor.",
                "reason": reason or "provider_error",
            })
            if attempt > 1:
                try:
                    await ws.send_json({
                        "type": "process_step_end",
                        "id": f"failover-{attempt}",
                        "status": "failed",
                    })
                except Exception:
                    pass

            elapsed_after = time.monotonic() - turn_start_time
            if (total_budget - elapsed_after) < MIN_RETRY_BUDGET_SECONDS:
                await fail_turn(
                    "Tempo limite de resposta esgotado após tentativas de failover.",
                    current_model_id, current_provider_id, reason="failover_budget_exhausted", outcome="timeout",
                )
                return None

            if not is_committed and can_retry():
                logger.warning(
                    "Erro antes do commit no modelo '%s' (provedor '%s'): %s. Tentando próximo modelo...",
                    current_model_id, current_provider_id, type(e).__name__,
                )
                attempted_model_ids.add(current_model_id)
                next_failover_reason = getattr(e, "failover_reason", None) or "error"
                continue

            await fail_turn(
                "Erro ao chamar o modelo. Tente novamente mais tarde.",
                current_model_id, current_provider_id, reason="provider_error", outcome="error",
            )
            return None

    if not success or not full_response.strip():
        logger.warning(
            "stream_from_llm encerrou sem sucesso após %s tentativas para conversa '%s'.",
            attempt, conversation_id,
        )
        await fail_turn(
            "Não foi possível obter resposta de nenhum dos modelos disponíveis. Tente novamente mais tarde.",
            current_model_id if 'current_model_id' in locals() else None, current_provider_id if 'current_provider_id' in locals() else None, reason="no_available_model", outcome="error",
        )
        return None

    failover_meta = {
        "requested_model": original_model_id,
        "served_by": model_id,
        "failover_tier": getattr(resolved, "failover_tier", None),
        "spliced": False,
        "outcome": "success",
        "attempt_count": attempt + effort_compat_retries,
        "ttft_ms": round(first_token_elapsed_ms, 2) if first_token_elapsed_ms is not None else None,
        "first_send_ms": turn_first_send_ms,
        "precommit_hold_ms": turn_precommit_hold_ms,
        "failover_recovery_ms": turn_failover_recovery_ms,
        "cascade_history": cascade_history,
    }
    return StreamLlmResult(full_response, model_id, provider_id, failover_meta=failover_meta)


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
    request_context: Any | None = None,
    turn_id: str | None = None,
    fallback_requirements: FallbackRequirements | None = None,
    cache_response: bool = True,
) -> tuple[str, "CacheHit | None", str, str] | None:
    """Fluxo completo: tenta cache, depois LLM com failover.

    Retorna (full_response, cache_hit_or_none, resolved_model_id,
    resolved_provider_id) ou None em caso de falha irrecuperável.
    """
    cache_hit = await check_cache(
        model_id, history, context_fingerprint, bypass_cache or not cache_response, user_id,
        request_context=request_context
    )

    if cache_hit:
        full_response = await stream_from_cache(ws, conversation_id, cache_hit, turn_id=turn_id)
        return full_response, cache_hit, model_id, provider_id

    result = await stream_from_llm(
        ws, db, conversation_id, user_id, model_id, provider_id, history,
        temperature=temperature, max_tokens=max_tokens, auto_route_decision=auto_route_decision,
        reasoning_effort=reasoning_effort,
        request_context=request_context,
        turn_id=turn_id,
        **({"fallback_requirements": fallback_requirements} if fallback_requirements else {}),
    )
    if result is None:
        return None

    full_response = result[0]
    resolved_model_id = result[1]
    resolved_provider_id = result[2]
    failover_meta = getattr(result, "failover_meta", {}) if hasattr(result, "failover_meta") else (result[3] if len(result) > 3 else {})

    # Save to cache in background (semantic key includes memory fingerprint)
    if full_response and cache_response:
        try:
            from backend.cache.manager import cache_manager
            asyncio.create_task(
                cache_manager.set(
                    resolved_model_id,
                    history,
                    full_response,
                    context_fingerprint=context_fingerprint or None,
                    user_id=user_id,
                    request_context=request_context,
                )
            )
        except Exception:
            logger.warning("Não foi possível agendar cache.set em background",
                           exc_info=True)

    return ResolveAndStreamResult(full_response, None, resolved_model_id, resolved_provider_id, failover_meta=failover_meta)


async def build_final_model_metadata(
    db,
    requested_model_id: str,
    resolved_model_id: str,
    resolved_provider_id: str,
    failover_tier: str | None = None,
    spliced: bool = False,
    outcome: str = "success",
    attempt_count: int = 1,
) -> dict:
    """Campos do payload ``stream_end`` que identificam o modelo que RESpondeu
    (pós-failover) — usado pelo badge de modelo da resposta no frontend.

    ``was_fallback`` compara o modelo solicitado com o resolvido: diferente
    significa que a cascata de failover trocou o modelo no meio do turno.
    Nunca lança: falha de consulta degrada para o próprio id do modelo.
    """
    display_name: str | None = None
    try:
        async with db.execute(
            "SELECT display_name, name FROM models WHERE id = ?",
            (resolved_model_id,),
        ) as cur:
            row = await cur.fetchone()
        if row:
            display_name = row[0] or row[1]
    except Exception:
        display_name = None

    return {
        "was_fallback": resolved_model_id != requested_model_id,
        "final_model_id": resolved_model_id,
        "final_model_name": display_name or resolved_model_id,
        "final_provider_id": resolved_provider_id,
        "requested_model": requested_model_id,
        "served_by": resolved_model_id,
        "failover_tier": failover_tier,
        "spliced": spliced,
        "outcome": outcome,
        "attempt_count": attempt_count,
    }
