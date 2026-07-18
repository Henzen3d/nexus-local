"""Persistência de turno: criação de conversa, mensagens, artifacts, web search, indexing.

Toda a lógica de escrita no banco durante um turno de chat foi extraída aqui
do controller WebSocket (`backend/routers/chat.py`), seguindo SRP.
"""

from __future__ import annotations

import json
import uuid
from typing import Any

from backend.logging_config import get_logger
from backend.orchestration.artifacts import detect_artifacts, save_artifact

logger = get_logger(__name__)


async def ensure_conversation(
    db,
    conversation_id: str | None,
    user_id: str,
    user_message: str,
    model_id: str,
    provider_id: str,
    request_project_id: str | None,
) -> tuple[str, str | None, dict | None]:
    """
    Garante que uma conversa existe no banco. Se *conversation_id* for None,
    cria uma nova conversa com título automático.

    Retorna ``(conversation_id, project_id, created_payload)``.
    Se a conversa já existia, *created_payload* é ``None``.
    """
    if conversation_id:
        return conversation_id, None, None

    new_id = str(uuid.uuid4())
    title = user_message[:60] + ("…" if len(user_message) > 60 else "")

    bind_project_id = None
    if request_project_id:
        async with db.execute(
            "SELECT id FROM projects WHERE id = ? AND user_id = ? AND archived = 0",
            (request_project_id, user_id),
        ) as cur:
            if await cur.fetchone():
                bind_project_id = request_project_id

    await db.execute(
        """INSERT INTO conversations (id, user_id, title, model_id, provider_id, project_id)
           VALUES (?, ?, ?, ?, ?, ?)""",
        (new_id, user_id, title, model_id, provider_id, bind_project_id),
    )
    if bind_project_id:
        await db.execute(
            "UPDATE projects SET updated_at = datetime('now') WHERE id = ?",
            (bind_project_id,),
        )
    await db.commit()

    payload = {
        "type": "conversation_created",
        "conversation_id": new_id,
        "title": title,
        "project_id": bind_project_id,
    }
    return new_id, bind_project_id, payload


async def save_user_message(
    db, conversation_id: str, user_message: str, model_id: str, provider_id: str
) -> str:
    """Persiste a mensagem do usuário e retorna seu ID."""
    user_msg_id = str(uuid.uuid4())
    await db.execute(
        """INSERT INTO messages (id, conversation_id, role, content, model_id, provider)
           VALUES (?, ?, 'user', ?, ?, ?)""",
        (user_msg_id, conversation_id, user_message, model_id, provider_id),
    )
    await db.commit()
    return user_msg_id


async def save_assistant_message(
    db,
    conversation_id: str,
    full_response: str,
    model_id: str,
    provider_id: str,
    relay_used: int = 0,
    relay_model_id: str | None = None,
) -> str:
    """Persiste a mensagem do assistente e atualiza ``updated_at`` da conversa."""
    assistant_msg_id = str(uuid.uuid4())
    await db.execute(
        """INSERT INTO messages (id, conversation_id, role, content, model_id, provider, relay_used, relay_model)
           VALUES (?, ?, 'assistant', ?, ?, ?, ?, ?)""",
        (assistant_msg_id, conversation_id, full_response, model_id, provider_id, relay_used, relay_model_id),
    )
    await db.execute(
        "UPDATE conversations SET updated_at = datetime('now') WHERE id = ?",
        (conversation_id,),
    )
    await db.commit()
    return assistant_msg_id


async def save_web_search_metadata(
    db,
    user_msg_id: str,
    web_search_used: bool,
    web_search_query: str,
    web_search_sources: list[dict],
) -> None:
    """Atualiza a mensagem do usuário com metadados de web search."""
    if not web_search_used:
        return
    await db.execute(
        """UPDATE messages
           SET web_search_used = ?, web_search_query = ?, web_search_sources = ?
           WHERE id = ?""",
        (1, web_search_query, json.dumps(web_search_sources), user_msg_id),
    )
    await db.commit()


async def detect_and_save_artifacts(
    db,
    ws,
    conversation_id: str,
    assistant_msg_id: str,
    full_response: str,
) -> list[dict]:
    """
    Detecta artifacts na resposta, persiste-os no banco e emite eventos WS.

    Retorna lista de dicts ``{"id", "type", "title"}``.
    """
    if not full_response:
        return []

    artifacts_list: list[dict] = []
    try:
        detected_list = detect_artifacts(full_response)
        for detected in detected_list:
            art_id = await save_artifact(db, conversation_id, assistant_msg_id, detected)
            artifacts_list.append(
                {"id": art_id, "type": detected["type"], "title": detected["title"]}
            )
            await ws.send_json(
                {
                    "type": "artifact",
                    "id": art_id,
                    "artifact_type": detected["type"],
                    "title": detected["title"],
                    "conv_id": conversation_id,
                    "msg_id": assistant_msg_id,
                }
            )
    except Exception:
        logger.exception("Failed to detect/save artifacts for msg=%s", assistant_msg_id)

    return artifacts_list


async def run_post_turn_indexing(
    conversation_id: str,
    active_project_id: str | None,
    user_message: str,
    full_response: str,
) -> None:
    """Indexa o turno Q+A para RAG de sibling-chats e dispara síntese de memória."""
    if not active_project_id or not full_response:
        return

    try:
        from backend.projects.indexer import index_chat_turn
        from backend.projects.memory_job import maybe_synthesize_project_memory

        await index_chat_turn(
            conversation_id, active_project_id, user_message, full_response
        )
        await maybe_synthesize_project_memory(active_project_id)
    except Exception:
        logger.exception(
            "Post-turn indexing failed for conv=%s project=%s",
            conversation_id,
            active_project_id,
        )
