import asyncio
import json
import time
import uuid

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from backend.attachments import move_attachments_to_conversation
from backend.auth import decode_token
from backend.database import get_db
from backend.fusion.orchestrator import executar_fusion
from backend.logging_config import configure_logging, get_logger
from backend.memory import extract_user_memory_background
from backend.orchestration.build_context import (
    BASE_SYSTEM_PROMPT,
    build_memory_context,
    resolve_project_context,
)
from backend.orchestration.handle_attachments import (
    check_model_vision_support,
    load_attachments,
    load_history,
)
from pathlib import Path
import os

from backend.orchestration.persist_turn import (
    detect_and_save_artifacts,
    ensure_conversation,
    run_post_turn_indexing,
    save_assistant_message,
    save_ui_blocks,
    save_user_message,
    save_web_search_metadata,
    save_process_steps,
)
from backend.ui_blocks.extract import extract_ui
from backend.ui_blocks.should_offer import should_offer_ui
from backend.orchestration.resolve_request import resolve_and_stream
from backend.web_search import (
    execute_agentic_search,
    format_search_results,
    get_web_search_config,
    resolve_and_execute_search,
    should_search,
)

# Retrocompatibilidade: fusion/orchestrator.py importava estes nomes de chat.py.
# Re-exportados do novo módulo compartilhado para não quebrar imports externos.
from backend.orchestration.artifacts import (  # noqa: F401
    detect_artifact,
    detect_artifacts,
    save_artifact as _save_artifact,
)

configure_logging()
logger = get_logger(__name__)

router = APIRouter()

_user_sockets: dict[str, set[WebSocket]] = {}


def register_socket(user_id: str, ws: WebSocket) -> None:
    _user_sockets.setdefault(user_id, set()).add(ws)


def unregister_socket(user_id: str, ws: WebSocket) -> None:
    if user_id in _user_sockets:
        _user_sockets[user_id].discard(ws)
        if not _user_sockets[user_id]:
            _user_sockets.pop(user_id, None)


async def notify_user_sockets(user_id: str, message: dict) -> None:
    """Disparo defensivo para todos os sockets ativos do usuário."""
    sockets = list(_user_sockets.get(user_id, set()))
    for ws in sockets:
        try:
            await ws.send_json(message)
        except Exception:
            if user_id in _user_sockets:
                _user_sockets[user_id].discard(ws)


@router.websocket("/ws/chat")
async def websocket_chat(ws: WebSocket):
    """Controller WebSocket fino: autentica, lê mensagens e delega para orquestração."""
    token = ws.query_params.get("token")
    user = None
    if token:
        user = decode_token(token)

    if not user:
        await ws.accept()
        await ws.send_json({"type": "error", "message": "Autenticação requerida."})
        await ws.close(code=4001)
        return

    await ws.accept()
    user_id = user["id"]
    register_socket(user_id, ws)

    try:
        await ws.send_json({"type": "ready"})
    except Exception:
        pass

    db = await get_db()
    keepalive_task: asyncio.Task | None = None

    async def _server_keepalive() -> None:
        try:
            while True:
                await asyncio.sleep(25)
                await ws.send_json({"type": "ping"})
        except Exception:
            return

    try:
        keepalive_task = asyncio.create_task(_server_keepalive())

        while True:
            raw = await ws.receive_text()
            try:
                req = json.loads(raw)
            except json.JSONDecodeError:
                await ws.send_json({"type": "error", "message": "JSON inválido."})
                continue

            msg_type = req.get("type")
            if msg_type == "ping":
                await ws.send_json({"type": "pong"})
                continue
            if msg_type == "pong":
                continue

            conversation_id = req.get("conversation_id")
            user_message = (req.get("message") or "").strip()
            model_id = req.get("model_id")
            provider_id = req.get("provider_id")
            bypass_cache = req.get("bypass_cache", False)
            raw_attachment_ids = req.get("attachment_ids") or []
            attachment_ids = [a for a in raw_attachment_ids if isinstance(a, str) and a.strip()]
            request_project_id = req.get("project_id")
            project_context_debug = bool(req.get("project_context_debug", False))
            use_memory = req.get("use_memory", True)
            if isinstance(use_memory, str):
                use_memory = use_memory.lower() not in ("0", "false", "no", "off")
            fusion_mode = req.get("fusion", False)

            is_auto = (model_id == "auto" or not model_id)
            if (not user_message and not attachment_ids):
                await ws.send_json({"type": "error", "message": "Mensagem ou anexo requerido."})
                continue

            if not is_auto and (not model_id or not provider_id):
                await ws.send_json({"type": "error", "message": "Campos obrigatórios faltando."})
                continue

            if not user_message and attachment_ids:
                user_message = "(arquivo anexado)"

            try:
                await _process_turn(
                    ws, db, req, user, conversation_id, user_message, model_id,
                    provider_id, bypass_cache, attachment_ids, request_project_id,
                    project_context_debug, use_memory, fusion_mode,
                )
            except WebSocketDisconnect:
                raise
            except Exception:
                logger.exception("turno de chat falhou")
                try:
                    await ws.send_json({
                        "type": "error",
                        "message": "Falha ao processar a mensagem.",
                    })
                    await ws.send_json({"type": "stream_end", "finish_reason": "error"})
                except Exception:
                    break

    except WebSocketDisconnect:
        pass
    finally:
        if user and "id" in user:
            unregister_socket(user["id"], ws)
        if keepalive_task is not None:
            keepalive_task.cancel()
            try:
                await keepalive_task
            except (asyncio.CancelledError, Exception):
                pass
        await db.close()


async def _process_turn(
    ws, db, req, user, conversation_id, user_message, model_id,
    provider_id, bypass_cache, attachment_ids, request_project_id,
    project_context_debug, use_memory, fusion_mode,
):
    """Processa um turno completo de chat (uma mensagem do usuário)."""
    user_id = user["id"]
    process_started_at = time.perf_counter()
    is_auto = (model_id == "auto" or not model_id)
    auto_route_decision = None

    # ── Image Generation Intent Check ───────────────────────────────
    image_job_created = False
    img_prompt = None

    from backend.image_gen.config import get_image_gen_config
    from backend.image_gen.intent import classify_image_intent

    img_config = await get_image_gen_config(db)
    is_slash = user_message.startswith(("/imagem", "/img", "/image"))

    if img_config.enabled and (img_config.auto_detect or is_slash):
        image_intent = classify_image_intent(user_message)
        if image_intent == "raster":
            is_pure_slash = is_slash
            if is_slash:
                parts = user_message.split(maxsplit=1)
                img_prompt = parts[1].strip() if len(parts) > 1 else ""
            else:
                img_prompt = user_message.strip()

            if not img_prompt:
                await ws.send_json({"type": "error", "message": "Prompt de imagem vazio."})
                if is_pure_slash:
                    await ws.send_json({"type": "stream_end"})
                    return
            else:
                from backend.image_gen.queue import count_daily_tasks, insert_image_task
                from backend.image_gen.worker import notify_new_task

                daily_count = await count_daily_tasks(db, user_id)
                if daily_count >= img_config.daily_cap_per_user:
                    await ws.send_json({
                        "type": "error",
                        "message": f"Limite diário de imagens atingido ({img_config.daily_cap_per_user}/dia).",
                    })
                    if is_pure_slash:
                        await ws.send_json({"type": "stream_end"})
                        return
                elif is_pure_slash:
                    # Slash puro (/imagem ...): grava conversa, user message, placeholder e fecha o turno imediatamente
                    conversation_id, _proj_id, created_payload = await ensure_conversation(
                        db, conversation_id, user_id, user_message,
                        img_config.model_id or "cloudflare/flux-1-schnell",
                        img_config.provider_id or "cloudflare",
                        request_project_id,
                    )
                    if created_payload:
                        created_payload["conversation_id"] = conversation_id
                        await ws.send_json(created_payload)

                    await save_user_message(
                        db, conversation_id, user_message,
                        img_config.model_id or "cloudflare/flux-1-schnell",
                        img_config.provider_id or "cloudflare",
                    )

                    placeholder_msg_id = await save_assistant_message(
                        db,
                        conversation_id,
                        "Gerando imagem…",
                        img_config.model_id or "cloudflare/flux-1-schnell",
                        img_config.provider_id or "cloudflare",
                    )

                    task_id = await insert_image_task(
                        db,
                        conversation_id=conversation_id,
                        user_id=user_id,
                        message_id=placeholder_msg_id,
                        prompt=img_prompt,
                        model_id=img_config.model_id,
                    )
                    notify_new_task()

                    await ws.send_json({
                        "type": "image_pending",
                        "task_id": task_id,
                        "message_id": placeholder_msg_id,
                        "conversation_id": conversation_id,
                        "msg_id": placeholder_msg_id,
                        "conv_id": conversation_id,
                        "prompt": img_prompt,
                    })

                    # Despacha stream_end imediatamente para destravar o composer
                    await ws.send_json({
                        "type": "stream_end",
                        "message_id": placeholder_msg_id,
                        "conversation_id": conversation_id,
                        "finish_reason": "image_pending",
                    })
                    return
                else:
                    image_job_created = True

    # ── Auto-Router Inteligente (Smart Intent Router) ────────────────
    if is_auto:
        prev_model_id = None
        prev_intent = None
        raw_history = []
        if conversation_id:
            async with db.execute(
                "SELECT model_id FROM messages WHERE conversation_id = ? AND role = 'assistant' ORDER BY created_at DESC LIMIT 1",
                (conversation_id,)
            ) as cur:
                row = await cur.fetchone()
                if row and row[0]:
                    prev_model_id = row[0]
            async with db.execute(
                "SELECT route_intent FROM model_usage_log WHERE conversation_id = ? AND was_auto_routed = 1 ORDER BY created_at DESC LIMIT 1",
                (conversation_id,)
            ) as cur:
                row = await cur.fetchone()
                if row and row[0]:
                    prev_intent = row[0]
            async with db.execute(
                "SELECT role, content FROM messages WHERE conversation_id = ? ORDER BY created_at ASC",
                (conversation_id,)
            ) as cur:
                raw_history = [{"role": r[0], "content": r[1]} for r in await cur.fetchall()]

        from backend.ranking.smart_router import classify_intent, select_best_model
        from backend.database import get_router_policy

        intent_res = classify_intent(
            prompt=user_message,
            attachments=attachment_ids,
            web_search=bool(req.get("web_search", False)),
            history=raw_history,
            previous_intent=prev_intent,
        )
        policy = await get_router_policy(db)
        auto_route_decision = await select_best_model(
            intent_res, policy, db, previous_model_id=prev_model_id
        )
        model_id = auto_route_decision.chosen_model_id
        provider_id = auto_route_decision.provider_id

        # Emite evento auto_route_decision com transparência antes dos primeiros tokens
        await ws.send_json({
            "type": "auto_route_decision",
            "chosen_model_id": auto_route_decision.chosen_model_id,
            "chosen_model_name": auto_route_decision.chosen_model_name,
            "provider_id": auto_route_decision.provider_id,
            "intent": auto_route_decision.intent.value,
            "reason_pt": auto_route_decision.reason_pt,
            "confidence": auto_route_decision.confidence,
            "policy": auto_route_decision.policy,
            "temperature": auto_route_decision.temperature,
            "decision_latency_ms": auto_route_decision.decision_latency_ms,
            "matched_signals": auto_route_decision.matched_signals,
        })


    # ── Ensure conversation ─────────────────────────────────────────
    conversation_id, _proj_id, created_payload = await ensure_conversation(
        db, conversation_id, user_id, user_message,
        model_id, provider_id, request_project_id,
    )
    if created_payload:
        created_payload["conversation_id"] = conversation_id
        await ws.send_json(created_payload)

    # ── Save user message ───────────────────────────────────────────
    user_msg_id = await save_user_message(
        db, conversation_id, user_message, model_id, provider_id
    )

    # ── Job de imagem em paralelo para pedido misto ─────────────────
    if image_job_created and img_prompt:
        from backend.image_gen.queue import insert_image_task
        from backend.image_gen.worker import notify_new_task

        placeholder_msg_id = await save_assistant_message(
            db,
            conversation_id,
            "Gerando imagem…",
            img_config.model_id or "cloudflare/flux-1-schnell",
            img_config.provider_id or "cloudflare",
        )
        task_id = await insert_image_task(
            db,
            conversation_id=conversation_id,
            user_id=user_id,
            message_id=placeholder_msg_id,
            prompt=img_prompt,
            model_id=img_config.model_id,
        )
        notify_new_task()
        await ws.send_json({
            "type": "image_pending",
            "task_id": task_id,
            "message_id": placeholder_msg_id,
            "conversation_id": conversation_id,
            "msg_id": placeholder_msg_id,
            "conv_id": conversation_id,
            "prompt": img_prompt,
        })

    # ── Attachments ─────────────────────────────────────────────────
    if attachment_ids:
        await move_attachments_to_conversation(attachment_ids, conversation_id, user_msg_id, db)

    # ── Web Search ──────────────────────────────────────────────────
    web_search_used, web_search_query, web_search_sources, search_results, search_config, process_steps = (
        await _resolve_web_search(
            ws, db, req, user_message, user_msg_id, user_id, conversation_id
        )
    )

    # ── Load history with attachments ───────────────────────────────
    attachments_by_msg, extracted_text_by_id = await load_attachments(db, conversation_id)
    model_supports_vision = await check_model_vision_support(db, model_id)

    history, relay_used, relay_model_id = await load_history(
        db, conversation_id, user_msg_id, attachments_by_msg,
        extracted_text_by_id, model_supports_vision,
        web_search_used, search_results, web_search_query,
        search_config, format_search_results, user_id,
        user_query=user_message, model_id=model_id, provider_id=provider_id,
    )

    # ── Build context (memory + project RAG) ────────────────────────
    user_mem_text, context_fingerprint = await build_memory_context(
        user, conversation_id, user_message, use_memory, provider_id, model_id
    )

    active_project_id, system_instruction = await resolve_project_context(
        db, ws, conversation_id, request_project_id, user, model_id,
        provider_id, user_message, history, project_context_debug,
        BASE_SYSTEM_PROMPT, user_mem_text,
    )

    if image_job_created:
        system_instruction += "\n\nO usuário pediu uma imagem raster que está sendo gerada separadamente. Não escreva código SVG nem gere tags de imagem neste turno."

    if web_search_used:
        system_instruction += (
            "\n\nPESQUISA NA WEB: A pesquisa online já foi executada para esta pergunta e os resultados atualizados estão presentes no contexto. "
            "Responda diretamente com base nessas informações e fontes fornecidas, agindo como um assistente conectado e utilizando os dados obtidos, "
            "SEM afirmar que não possui acesso à internet ou que não pode acessar a web."
        )

    # ── Intelligent UI: oferta de catálogo condicional (Spec Seção 8) ───
    if os.getenv("INTELLIGENT_UI_ENABLED", "false").lower() in ("true", "1", "yes"):
        if should_offer_ui(user_message):
            try:
                cat_file = Path(__file__).resolve().parent.parent / "ui_blocks" / "catalog.txt"
                if cat_file.exists():
                    cat_content = cat_file.read_text(encoding="utf-8")
                    if (len(cat_content) / 4) <= 400:
                        system_instruction += "\n\n" + cat_content
            except Exception as e:
                logger.error("Erro ao carregar catálogo Intelligent UI:", exc_info=e)

    history = [{"role": "system", "content": system_instruction}] + history

    # ── Fusion mode: delegate ───────────────────────────────────────
    if fusion_mode:
        await executar_fusion(
            user_message, history, ws, conversation_id,
            user_id,
            force_grounding=req.get("web_search", False),
            web_search_already_done=bool(web_search_used),
            client_timezone_offset=req.get("client_timezone_offset"),
        )
        return

    # ── Resolve: cache or LLM com failover & parâmetros adaptativos ──
    reasoning_effort_raw = req.get("reasoning_effort")
    reasoning_effort = str(reasoning_effort_raw).strip() if reasoning_effort_raw else None

    result = await resolve_and_stream(
        ws, db, conversation_id, user_id, model_id, provider_id,
        history, context_fingerprint, bypass_cache,
        temperature=auto_route_decision.temperature if auto_route_decision else None,
        auto_route_decision=auto_route_decision,
        reasoning_effort=reasoning_effort,
    )
    if result is None:
        return

    full_response, cache_hit, model_id, provider_id = result

    # ── Intelligent UI: extração de fence antes de persistir ──────────
    full_response, ui_envelope = extract_ui(full_response)

    # ── Persist assistant message ───────────────────────────────────
    assistant_msg_id = await save_assistant_message(
        db, conversation_id, full_response, model_id, provider_id,
        relay_used, relay_model_id,
    )

    if ui_envelope:
        await save_ui_blocks(db, assistant_msg_id, ui_envelope, source="model")

    # ── Index Q+A for RAG ───────────────────────────────────────────
    await run_post_turn_indexing(
        conversation_id, active_project_id, user_message, full_response
    )

    # ── Save web search metadata ────────────────────────────────────
    await save_web_search_metadata(
        db, user_msg_id, web_search_used, web_search_query, web_search_sources
    )
    await save_process_steps(db, assistant_msg_id, process_steps)

    # ── Detect + save artifacts ─────────────────────────────────────
    artifacts_list = await detect_and_save_artifacts(
        db,
        ws,
        conversation_id,
        assistant_msg_id,
        full_response,
        skip_svg=image_job_created,
        user_message=user_message,
    )

    # ── Stream end ──────────────────────────────────────────────────
    stream_end_payload = {
        "type": "stream_end",
        "message_id": assistant_msg_id,
        "conversation_id": conversation_id,
        "from_cache": cache_hit is not None,
        "cache_type": cache_hit.cache_type if cache_hit else None,
        "cache_similarity": round(cache_hit.similarity, 4) if cache_hit else None,
        "artifact_id": artifacts_list[0]["id"] if artifacts_list else None,
        "artifact_type": artifacts_list[0]["type"] if artifacts_list else None,
        "artifact_title": artifacts_list[0]["title"] if artifacts_list else None,
        "artifacts": artifacts_list,
        "relay_used": bool(relay_used),
        "relay_model": relay_model_id,
        "web_search_used": bool(web_search_used),
        "web_search_query": web_search_query,
        "web_search_sources": web_search_sources,
        "process_steps": process_steps,
        "process_duration_ms": round((time.perf_counter() - process_started_at) * 1000),
        "source_count": len(web_search_sources),
    }
    if ui_envelope:
        stream_end_payload["ui_blocks"] = ui_envelope

    await ws.send_json(stream_end_payload)

    # ── Background memory extraction ────────────────────────────────
    if user and "id" in user and use_memory:
        asyncio.create_task(
            extract_user_memory_background(
                user["id"], conversation_id, model_id, provider_id
            )
        )


async def _resolve_web_search(
    ws, db, req, user_message, user_msg_id, user_id, conversation_id
) -> tuple[bool, str, list, list, dict | None, list]:
    """Resolve e executa web search se aplicável.

    Returns (web_search_used, web_search_query, web_search_sources,
             search_results, search_config, process_steps).
    """
    web_search_requested = req.get("web_search", False)
    web_search_used = False
    web_search_query = ""
    web_search_sources: list = []
    search_results: list = []
    process_steps: list[dict] = []

    search_config = await get_web_search_config(db)

    should_do_search = False
    trigger_type = None

    if search_config and search_config["enabled"]:
        if web_search_requested:
            should_do_search = True
            trigger_type = "manual"
        elif search_config["heuristic_enabled"]:
            should, _score = should_search(
                user_message, search_config["heuristic_sensitivity"]
            )
            if should:
                should_do_search = True
                trigger_type = "heuristic"

    if should_do_search:
        web_search_query = user_message
        await ws.send_json({"type": "search_start", "query": web_search_query})

        async def send_ws_event(evt: dict):
            if evt.get("type") == "process_step_start":
                process_steps.append({
                    "id": evt.get("id"),
                    "type": evt.get("step_type") or "tool",
                    "title": evt.get("title") or "",
                    "detail": evt.get("detail"),
                    "status": "running",
                })
            elif evt.get("type") == "process_step_end":
                for step in process_steps:
                    if step.get("id") == evt.get("id"):
                        step["status"] = evt.get("status") or "completed"
            try:
                await ws.send_json(evt)
            except Exception:
                pass

        search_failed = False
        search_results = []
        scraped_pages = []

        try:
            agent_result = await execute_agentic_search(
                user_message, db, search_config, on_event=send_ws_event
            )
            search_results = agent_result.get("search_results", [])
            scraped_pages = agent_result.get("scraped_pages", [])
            executed_queries = agent_result.get("executed_queries", [user_message])
            primary_query = executed_queries[0] if executed_queries else user_message

            if search_results or scraped_pages:
                web_search_used = True

                # Combina páginas lidas no Deep Reader com resultados gerais da busca
                sources_map = {}
                for page in scraped_pages:
                    p_url = page.get("url")
                    if p_url:
                        sample = (page.get("text_sample") or "").strip()
                        sources_map[p_url] = {
                            "title": page.get("title") or p_url,
                            "url": p_url,
                            "snippet": sample[:280],
                        }
                for r in search_results:
                    r_url = r.get("url")
                    if not r_url:
                        continue
                    snippet = (r.get("snippet") or "").strip()[:280]
                    if r_url not in sources_map:
                        sources_map[r_url] = {
                            "title": r.get("title") or r_url,
                            "url": r_url,
                            "snippet": snippet,
                        }
                    elif snippet and not sources_map[r_url].get("snippet"):
                        sources_map[r_url]["snippet"] = snippet

                web_search_sources = list(sources_map.values())

                if search_config:
                    search_config["scraped_pages"] = scraped_pages

                log_id = str(uuid.uuid4())
                await db.execute(
                    """INSERT INTO web_search_log
                       (id, conversation_id, message_id, query,
                        trigger_type, results_count, user_id)
                       VALUES (?, ?, ?, ?, ?, ?, ?)""",
                    (
                        log_id, conversation_id, user_msg_id,
                        primary_query, trigger_type,
                        len(web_search_sources), user_id,
                    ),
                )
                await db.commit()
        except Exception:
            search_failed = True
            logger.error(
                "agentic web search failed",
                exc_info=True,
                extra={"query": web_search_query, "user_id": user_id},
            )
            search_results = []
            scraped_pages = []

    return web_search_used, web_search_query, web_search_sources, search_results, search_config, process_steps
