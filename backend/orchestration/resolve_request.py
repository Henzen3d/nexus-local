"""Resolução de requisição: cache lookup + streaming LLM com failover cascade.

Extraído de websocket_chat (chat.py) — responsabilidade 11-13 do God function.
"""
from __future__ import annotations

import time
import asyncio
import json
import re
import uuid
import os
from typing import TYPE_CHECKING, Any

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

if TYPE_CHECKING:
    from fastapi import WebSocket
    from backend.cache.manager import CacheHit

logger = get_logger(__name__)

_MAX_FAILOVER_ATTEMPTS = int(os.getenv("FAILOVER_MAX_ATTEMPTS", "7"))
DEFAULT_FAILOVER_TOTAL_BUDGET_SECONDS = 45.0
DEFAULT_STREAM_TTFT_TIMEOUT_SECONDS = 25.0
MIN_RETRY_BUDGET_SECONDS = 3.0
DEFAULT_MIN_COMMIT_CHARS = int(os.getenv("FAILOVER_MIN_COMMIT_CHARS", "24"))
DEFAULT_MAX_PRECOMMIT_HOLD_MS = float(os.getenv("FAILOVER_MAX_PRECOMMIT_HOLD_MS", "450.0"))


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
        await ws.send_json({"type": "stream_clear"})
    except Exception:
        pass

    summary = build_cascade_error_summary(cascade_history, main_msg)
    try:
        await ws.send_json({
            "type": "error",
            "message": summary,
            "retry_suggested": True,
            "attempts": len(cascade_history),
        })
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
    """Carrega o orçamento de tempo total para o turno/failover da tabela meta ou env."""
    import os
    env_budget = os.getenv("FAILOVER_TOTAL_BUDGET_SECONDS")
    if env_budget:
        try:
            return float(env_budget)
        except ValueError:
            pass
    try:
        async with db.execute("SELECT value FROM meta WHERE key = 'failover_total_budget_sec'") as cur:
            row = await cur.fetchone()
        if row and row[0]:
            return float(row[0])
    except Exception:
        pass
    return DEFAULT_FAILOVER_TOTAL_BUDGET_SECONDS


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
    request_context: Any | None = None,
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

    total_budget = await get_failover_total_budget(db)
    turn_start_time = time.monotonic()
    cascade_history: list[dict] = []

    while attempt < _MAX_FAILOVER_ATTEMPTS and not success:
        now = time.monotonic()
        elapsed = now - turn_start_time
        remaining_budget = total_budget - elapsed
        if remaining_budget < MIN_RETRY_BUDGET_SECONDS:
            logger.warning(
                "Orçamento total de failover esgotado (%.1fs decorridos de %.1fs) após %d tentativas.",
                elapsed, total_budget, attempt
            )
            await send_and_persist_error(
                ws, db, conversation_id,
                "Tempo limite de resposta esgotado após tentativas de failover.",
                cascade_history,
                original_model_id,
                "",
            )
            return None

        attempt += 1
        full_response = ""
        if tokens_flushed_to_client:
            # Fix failover: se o modelo anterior já emitiu tokens ao cliente e falhou,
            # limpa o rascunho do frontend para o próximo modelo não misturar respostas.
            try:
                await ws.send_json({"type": "stream_clear"})
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
            )
        except NoAvailableModelError as e:
            err_msg = str(e)
            await send_and_persist_error(
                ws, db, conversation_id,
                err_msg,
                cascade_history,
                original_model_id,
                "",
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
        except ValueError as e:
            err_msg = str(e)
            logger.warning(
                "Falha ao carregar provedor '%s' para modelo '%s': %s. Acionando failover...",
                current_provider_id, current_model_id, err_msg
            )
            cascade_history.append({
                "attempt": attempt,
                "model_id": current_model_id,
                "provider_id": current_provider_id,
                "detail": f"Falha de configuração do provedor: {err_msg}",
            })
            attempted_model_ids.add(current_model_id)
            if attempt >= _MAX_FAILOVER_ATTEMPTS:
                await send_and_persist_error(
                    ws, db, conversation_id,
                    err_msg,
                    cascade_history,
                    current_model_id,
                    current_provider_id,
                )
                return None
            continue

        if not stream_started:
            await ws.send_json({
                "type": "stream_start",
                "conversation_id": conversation_id,
                "from_cache": False,
            })
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
                    await send_and_persist_error(
                        ws, db, conversation_id,
                        "Tempo limite de resposta esgotado após tentativas de failover.",
                        cascade_history,
                        current_model_id,
                        current_provider_id,
                    )
                    return None
                if attempt >= _MAX_FAILOVER_ATTEMPTS:
                    await send_and_persist_error(
                        ws, db, conversation_id,
                        "Todos os provedores elegíveis atingiram o limite temporário de requisições por minuto (RPM). Aguarde alguns instantes.",
                        cascade_history,
                        current_model_id,
                        current_provider_id,
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
                await send_and_persist_error(
                    ws, db, conversation_id,
                    "Tempo limite de resposta esgotado após tentativas de failover.",
                    cascade_history,
                    current_model_id,
                    current_provider_id,
                )
                return None

            max_ttft = DEFAULT_STREAM_TTFT_TIMEOUT_SECONDS if attempt == 1 else min(15.0, max(5.0, remaining_budget * 0.5))
            stream_ttft_timeout = max(0.5, min(max_ttft, remaining_budget))
            stream_start_time = time.perf_counter()
            first_token_received = False
            is_committed = False
            precommit_buffer: list[str] = []
            precommit_chars = 0
            candidate_response = ""
            token_buffer: list[str] = []
            last_flush = time.perf_counter()

            async def flush_tokens():
                nonlocal token_buffer, last_flush, tokens_flushed_to_client
                if token_buffer:
                    batch_text = "".join(token_buffer)
                    await ws.send_json({"type": "token", "content": batch_text})
                    token_buffer.clear()
                    last_flush = time.perf_counter()
                    tokens_flushed_to_client = True

            def commit_if_needed(force: bool = False):
                nonlocal is_committed, precommit_buffer, precommit_chars, token_buffer, candidate_response
                if is_committed:
                    return
                elapsed_ms = (time.perf_counter() - stream_start_time) * 1000.0
                if force or precommit_chars >= DEFAULT_MIN_COMMIT_CHARS or elapsed_ms >= DEFAULT_MAX_PRECOMMIT_HOLD_MS:
                    is_committed = True
                    if precommit_buffer:
                        buffered_str = "".join(precommit_buffer)
                        candidate_response += buffered_str
                        token_buffer.append(buffered_str)
                        precommit_buffer.clear()

            from backend.ranking.admission import admission_controller
            admission_acquired = admission_controller.acquire(current_model_id, current_provider_id)
            stream_iter = None
            try:
                try:
                    stream_iter = provider.stream_chat(model=model_name, messages=history, **stream_kwargs).__aiter__()

                    # Aguarda o primeiro token com prazo limite de TTFT (clamped ao restante do orçamento de tempo)
                    # Heartbeat visual a cada 3s para manter o frontend vivo durante esperas longas
                    try:
                        _heartbeat_task = None
                        async def _ttft_heartbeat():
                            """Envia pulsos visuais ao frontend durante espera do TTFT."""
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

                        _heartbeat_task = asyncio.create_task(_ttft_heartbeat())
                        try:
                            first_token = await asyncio.wait_for(
                                stream_iter.__anext__(),
                                timeout=stream_ttft_timeout,
                            )
                        finally:
                            if _heartbeat_task:
                                _heartbeat_task.cancel()
                                try:
                                    await _heartbeat_task
                                except (asyncio.CancelledError, Exception):
                                    pass

                        first_token_received = True
                        if request_context and hasattr(request_context, "record_phase"):
                            request_context.record_phase("llm_ttfb", stream_start_time)
                        token_str = str(first_token)
                        precommit_buffer.append(token_str)
                        precommit_chars += len(token_str)
                        commit_if_needed()
                        if is_committed:
                            await flush_tokens()
                    except (asyncio.TimeoutError, TimeoutError):
                        logger.warning(
                            "TTFT Timeout (%.1fs excedido) no provedor '%s' (modelo '%s'). Acionando failover cascade precoce.",
                            stream_ttft_timeout, current_provider_id, current_model_id,
                        )
                        from backend.ranking.health_registry import health_registry
                        health_registry.record_failure(current_model_id, current_provider_id, "TIMEOUT", stage="pre_stream")
                        cascade_history.append({
                            "attempt": attempt,
                            "model_id": current_model_id,
                            "provider_id": current_provider_id,
                            "detail": f"Tempo limite de resposta excedido ({int(stream_ttft_timeout)}s)",
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
                            await send_and_persist_error(
                                ws, db, conversation_id,
                                msg,
                                cascade_history,
                                current_model_id,
                                current_provider_id,
                            )
                            return None
                        continue

                    # Consome o restante do stream com micro-lotes de coalescência (~35ms ou 8 tokens)
                    # e guarda timeout entre tokens para não travar conexões abandonadas
                    while True:
                        try:
                            token = await asyncio.wait_for(stream_iter.__anext__(), timeout=35.0)
                        except StopAsyncIteration:
                            break
                        except (asyncio.TimeoutError, TimeoutError):
                            logger.warning(
                                "Timeout entre tokens (35s) no provedor '%s' (modelo '%s'). Finalizando stream.",
                                current_provider_id, current_model_id,
                            )
                            break

                        token_str = str(token)
                        if not is_committed:
                            precommit_buffer.append(token_str)
                            precommit_chars += len(token_str)
                            commit_if_needed()
                            if is_committed:
                                await flush_tokens()
                        else:
                            candidate_response += token_str
                            token_buffer.append(token_str)
                            if len(token_buffer) >= 8 or (time.perf_counter() - last_flush) >= 0.035:
                                await flush_tokens()

                    # Final de stream: se completou antes do threshold de commit (respostas muito curtas), força o commit
                    if not is_committed and precommit_buffer:
                        commit_if_needed(force=True)
                    await flush_tokens()
                except StopAsyncIteration:
                    if not is_committed and precommit_buffer:
                        commit_if_needed(force=True)
                    await flush_tokens()
            finally:
                if not is_committed:
                    # UX C2: buffer do candidato descartado integralmente se falhou antes do commit
                    precommit_buffer.clear()
                    token_buffer.clear()
                    candidate_response = ""
                if admission_acquired:
                    admission_controller.release(current_model_id, current_provider_id)
                    admission_acquired = False
                if stream_iter is not None:
                    try:
                        if hasattr(stream_iter, "aclose"):
                            await stream_iter.aclose()
                    except Exception:
                        pass

            # Salvaguarda de truncamento no raciocínio (R1)
            open_th = re.findall(r"<(think|thinking|reasoning|analysis)\b[^>]*>", candidate_response, re.IGNORECASE)
            close_th = re.findall(r"</(think|thinking|reasoning|analysis)>", candidate_response, re.IGNORECASE)
            if len(open_th) > len(close_th):
                tag_to_close = open_th[-1]
                closed_suffix = f"</{tag_to_close}>\n\n"
                candidate_response += closed_suffix
                token_buffer.append(closed_suffix)
                await flush_tokens()

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
                    token_buffer.append(notice)
                    await flush_tokens()

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
                    await send_and_persist_error(
                        ws, db, conversation_id,
                        msg,
                        cascade_history,
                        current_model_id,
                        current_provider_id,
                    )
                    return None
                continue

            full_response = candidate_response
            from backend.ranking.health_registry import health_registry
            ttft_measured_ms = (time.perf_counter() - stream_start_time) * 1000.0 if first_token_received else None
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
                "detail": f"Rate limit / cota esgotada: {str(e)}",
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
            await mark_model_exhausted(current_model_id, db, e.retry_after, str(e))
            elapsed_after = time.monotonic() - turn_start_time
            if (total_budget - elapsed_after) < MIN_RETRY_BUDGET_SECONDS or attempt >= _MAX_FAILOVER_ATTEMPTS:
                msg = (
                    "Tempo limite de resposta esgotado após tentativas de failover."
                    if (total_budget - elapsed_after) < MIN_RETRY_BUDGET_SECONDS
                    else "Limite de tentativas de failover excedido. O modelo está esgotado."
                )
                await send_and_persist_error(
                    ws, db, conversation_id,
                    msg,
                    cascade_history,
                    current_model_id,
                    current_provider_id,
                )
                return None
            continue
        except Exception as e:
            error_msg = str(e)
            if isinstance(e, RuntimeError) and any(
                term in error_msg.lower() for term in ("websocket", "disconnect", "close message", "not connected")
            ):
                logger.info(
                    "Conexão do cliente encerrada durante streaming (%s). Finalizando sem penalizar modelo nem failover.",
                    error_msg,
                )
                return None

            stage = "mid_stream" if is_committed else "pre_stream"
            from backend.ranking.health_registry import health_registry
            health_registry.record_failure(
                current_model_id,
                current_provider_id,
                "PRE_STREAM_ERR" if stage == "pre_stream" else "MID_STREAM_DROP",
                stage=stage,
            )
            next_failover_reason = getattr(e, "failover_reason", None) or "error"
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
                        tokens_flushed_to_client = True

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
            from backend.ranking.quota import is_quota_exhausted_error
            if is_quota_exhausted_error(error_msg):
                logger.warning(
                    "Cota/limite de uso esgotado no modelo '%s' (provedor '%s'): %s. Aplicando backoff longo de quota (mínimo 1h) e acionando failover...",
                    current_model_id, current_provider_id, error_msg,
                )
                cascade_history.append({
                    "attempt": attempt,
                    "model_id": current_model_id,
                    "provider_id": current_provider_id,
                    "detail": f"Cota/crédito esgotado: {error_msg}",
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
                from backend.ranking.token_bucket import token_bucket_manager
                await token_bucket_manager.on_rate_limit(current_provider_id)
                await mark_model_exhausted(current_model_id, db, retry_after=3600, error_msg=error_msg)
                attempted_model_ids.add(current_model_id)
                next_failover_reason = "rate_limit"
                elapsed_after = time.monotonic() - turn_start_time
                if (total_budget - elapsed_after) < MIN_RETRY_BUDGET_SECONDS:
                    await send_and_persist_error(
                        ws, db, conversation_id,
                        "Tempo limite de resposta esgotado após tentativas de failover.",
                        cascade_history,
                        current_model_id,
                        current_provider_id,
                    )
                    return None
                if not first_token_received and attempt < _MAX_FAILOVER_ATTEMPTS:
                    continue
                await send_and_persist_error(
                    ws, db, conversation_id,
                    f"Limite de cota de uso atingido para o modelo '{current_model_id}'. Tente novamente mais tarde.",
                    cascade_history,
                    current_model_id,
                    current_provider_id,
                )
                return None

            from backend.database import check_and_deactivate_model
            await check_and_deactivate_model(current_model_id, error_msg, db)

            cascade_history.append({
                "attempt": attempt,
                "model_id": current_model_id,
                "provider_id": current_provider_id,
                "detail": f"Erro do provedor: {error_msg}",
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
                await send_and_persist_error(
                    ws, db, conversation_id,
                    "Tempo limite de resposta esgotado após tentativas de failover.",
                    cascade_history,
                    current_model_id,
                    current_provider_id,
                )
                return None

            if not is_committed and attempt < _MAX_FAILOVER_ATTEMPTS:
                logger.warning(
                    "Erro antes do commit no modelo '%s' (provedor '%s'): %s. Tentando próximo modelo...",
                    current_model_id, current_provider_id, error_msg,
                )
                attempted_model_ids.add(current_model_id)
                continue

            await send_and_persist_error(
                ws, db, conversation_id,
                f"Erro ao chamar modelo: {error_msg}",
                cascade_history,
                current_model_id,
                current_provider_id,
            )
            return None

    if not success or not full_response.strip():
        logger.warning(
            "stream_from_llm encerrou sem sucesso após %s tentativas para conversa '%s'.",
            attempt, conversation_id,
        )
        await send_and_persist_error(
            ws, db, conversation_id,
            "Não foi possível obter resposta de nenhum dos modelos disponíveis. Tente novamente mais tarde.",
            cascade_history,
            current_model_id if 'current_model_id' in locals() else None,
            current_provider_id if 'current_provider_id' in locals() else None,
        )
        return None

    failover_meta = {
        "requested_model": original_model_id,
        "served_by": model_id,
        "failover_tier": getattr(resolved, "failover_tier", None),
        "spliced": False,
        "outcome": "success",
        "attempt_count": attempt,
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
) -> tuple[str, "CacheHit | None", str, str] | None:
    """Fluxo completo: tenta cache, depois LLM com failover.

    Retorna (full_response, cache_hit_or_none, resolved_model_id,
    resolved_provider_id) ou None em caso de falha irrecuperável.
    """
    cache_hit = await check_cache(
        model_id, history, context_fingerprint, bypass_cache, user_id,
        request_context=request_context
    )

    if cache_hit:
        full_response = await stream_from_cache(ws, conversation_id, cache_hit)
        return full_response, cache_hit, model_id, provider_id

    result = await stream_from_llm(
        ws, db, conversation_id, user_id, model_id, provider_id, history,
        temperature=temperature, max_tokens=max_tokens, auto_route_decision=auto_route_decision,
        reasoning_effort=reasoning_effort,
        request_context=request_context,
    )
    if result is None:
        return None

    full_response = result[0]
    resolved_model_id = result[1]
    resolved_provider_id = result[2]
    failover_meta = getattr(result, "failover_meta", {}) if hasattr(result, "failover_meta") else (result[3] if len(result) > 3 else {})

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
