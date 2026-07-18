import asyncio
import json
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
from backend.orchestration.persist_turn import (
    detect_and_save_artifacts,
    ensure_conversation,
    run_post_turn_indexing,
    save_assistant_message,
    save_user_message,
    save_web_search_metadata,
)
from backend.orchestration.resolve_request import resolve_and_stream
from backend.web_search import (
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

            if (not user_message and not attachment_ids) or not model_id or not provider_id:
                await ws.send_json({"type": "error", "message": "Campos obrigatórios faltando."})
                continue

            if not user_message and attachment_ids:
                user_message = "(arquivo anexado)"

            await _process_turn(
                ws, db, req, user, conversation_id, user_message, model_id,
                provider_id, bypass_cache, attachment_ids, request_project_id,
                project_context_debug, use_memory, fusion_mode,
            )

    except WebSocketDisconnect:
        pass
    finally:
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

    # ── Attachments ─────────────────────────────────────────────────
    if attachment_ids:
        await move_attachments_to_conversation(attachment_ids, conversation_id, user_msg_id, db)

    # ── Web Search ──────────────────────────────────────────────────
    web_search_used, web_search_query, web_search_sources, search_results, search_config = (
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

    # ── Resolve: cache or LLM with failover ────────────────────────
    result = await resolve_and_stream(
        ws, db, conversation_id, user_id, model_id, provider_id,
        history, context_fingerprint, bypass_cache,
    )
    if result is None:
        return

    full_response, cache_hit, model_id, provider_id = result

    # ── Persist assistant message ───────────────────────────────────
    assistant_msg_id = await save_assistant_message(
        db, conversation_id, full_response, model_id, provider_id,
        relay_used, relay_model_id,
    )

    # ── Index Q+A for RAG ───────────────────────────────────────────
    await run_post_turn_indexing(
        conversation_id, active_project_id, user_message, full_response
    )

    # ── Save web search metadata ────────────────────────────────────
    await save_web_search_metadata(
        db, user_msg_id, web_search_used, web_search_query, web_search_sources
    )

    # ── Detect + save artifacts ─────────────────────────────────────
    artifacts_list = await detect_and_save_artifacts(
        db, ws, conversation_id, assistant_msg_id, full_response
    )

    # ── Stream end ──────────────────────────────────────────────────
    await ws.send_json({
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
    })

    # ── Background memory extraction ────────────────────────────────
    if user and "id" in user and use_memory:
        asyncio.create_task(
            extract_user_memory_background(
                user["id"], conversation_id, model_id, provider_id
            )
        )


async def _resolve_web_search(
    ws, db, req, user_message, user_msg_id, user_id, conversation_id
) -> tuple[bool, str, list, list, dict | None]:
    """Resolve e executa web search se aplicável.

    Returns (web_search_used, web_search_query, web_search_sources,
             search_results, search_config).
    """
    web_search_requested = req.get("web_search", False)
    web_search_used = False
    web_search_query = ""
    web_search_sources: list = []
    search_results: list = []

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

        try:
            search_results = await resolve_and_execute_search(
                web_search_query, db, search_config
            )
            if search_results:
                web_search_used = True
                web_search_sources = [
                    {"title": r["title"], "url": r["url"]} for r in search_results
                ]

                log_id = str(uuid.uuid4())
                await db.execute(
                    """INSERT INTO web_search_log
                       (id, conversation_id, message_id, query,
                        trigger_type, results_count, user_id)
                       VALUES (?, ?, ?, ?, ?, ?, ?)""",
                    (
                        log_id, conversation_id, user_msg_id,
                        web_search_query, trigger_type,
                        len(search_results), user_id,
                    ),
                )
                await db.commit()
        except Exception:
            logger.error(
                "web search resolve/execute failed",
                exc_info=True,
                extra={"query": web_search_query, "user_id": user_id},
            )
            search_results = []

    return web_search_used, web_search_query, web_search_sources, search_results, search_config
