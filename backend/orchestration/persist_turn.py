"""Persistência de turno: criação de conversa, mensagens, artifacts, web search, indexing.

Toda a lógica de escrita no banco durante um turno de chat foi extraída aqui
do controller WebSocket (`backend/routers/chat.py`), seguindo SRP.
"""

from __future__ import annotations

import json
import re
import uuid
from typing import Any

from backend.logging_config import get_logger
from backend.orchestration.artifacts import detect_artifacts, save_artifact

logger = get_logger(__name__)

# IDs de conversa são sempre UUID v4 gerados pelo servidor. Validar o formato
# antes de usar o valor em queries e, principalmente, em caminhos do filesystem
# (storage/attachments/{conversation_id}) elimina qualquer vetor de traversal.
_CONVERSATION_ID_RE = re.compile(r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$")


class ConversationAccessError(Exception):
    """Conversa inexistente, com ID malformado ou pertencente a outro usuário."""


def is_valid_conversation_id(conversation_id: str | None) -> bool:
    return bool(conversation_id) and bool(_CONVERSATION_ID_RE.match(str(conversation_id)))


async def verify_conversation_owner(db, conversation_id: str, user_id: str) -> None:
    """Garante que *conversation_id* existe e pertence a *user_id*.

    Levanta ``ConversationAccessError`` caso contrário. Deve ser chamado antes
    de qualquer leitura/escrita de histórico iniciada pelo cliente (WebSocket),
    que até então confiava cegamente no ``conversation_id`` recebido.
    """
    if not is_valid_conversation_id(conversation_id):
        raise ConversationAccessError("ID de conversa inválido.")
    async with db.execute(
        "SELECT user_id FROM conversations WHERE id = ?", (conversation_id,)
    ) as cur:
        row = await cur.fetchone()
    if not row or row[0] != user_id:
        # Mesma mensagem para "não existe" e "não é sua": evita enumeração.
        raise ConversationAccessError("Conversa não encontrada.")


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

    Levanta ``ConversationAccessError`` se o ID informado não pertencer ao usuário.
    """
    if conversation_id:
        await verify_conversation_owner(db, conversation_id, user_id)
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
    kind: str = "normal",
) -> str:
    """Persiste a mensagem do assistente e atualiza ``updated_at`` da conversa."""
    assistant_msg_id = str(uuid.uuid4())
    await db.execute(
        """INSERT INTO messages (id, conversation_id, role, content, model_id, provider, relay_used, relay_model, kind)
           VALUES (?, ?, 'assistant', ?, ?, ?, ?, ?, ?)""",
        (assistant_msg_id, conversation_id, full_response, model_id, provider_id, relay_used, relay_model_id, kind),
    )
    await db.execute(
        "UPDATE conversations SET updated_at = datetime('now'), model_id = ?, provider_id = ? WHERE id = ?",
        (model_id, provider_id, conversation_id),
    )
    await db.commit()
    return assistant_msg_id


async def save_ui_blocks(
    db,
    message_id: str,
    envelope: dict[str, Any] | None,
    source: str = "model",
) -> None:
    """Persiste os blocos do envelope nexus-ui/1 na tabela message_ui_blocks."""
    if not envelope or not envelope.get("blocks"):
        return
    try:
        await db.execute(
            """INSERT INTO message_ui_blocks (message_id, payload, source)
               VALUES (?, ?, ?)
               ON CONFLICT(message_id) DO UPDATE SET payload = excluded.payload, source = excluded.source""",
            (message_id, json.dumps(envelope), source),
        )
        await db.commit()
    except Exception as e:
        logger.error("Erro ao salvar message_ui_blocks:", exc_info=e)


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


async def save_process_steps(
    db, message_id: str, steps: list[dict] | None, duration_ms: int | None = None
) -> None:
    """Grava a árvore de pesquisa/ações e o tempo de execução na mensagem do assistente."""
    if not steps and duration_ms is None:
        return
    try:
        steps_json = json.dumps(steps) if steps else None
        if steps_json is not None and duration_ms is not None:
            await db.execute(
                "UPDATE messages SET process_steps = ?, process_duration_ms = ? WHERE id = ?",
                (steps_json, duration_ms, message_id),
            )
        elif steps_json is not None:
            await db.execute(
                "UPDATE messages SET process_steps = ? WHERE id = ?",
                (steps_json, message_id),
            )
        elif duration_ms is not None:
            await db.execute(
                "UPDATE messages SET process_duration_ms = ? WHERE id = ?",
                (duration_ms, message_id),
            )
        await db.commit()
    except Exception as e:
        logger.error("Erro ao salvar process_steps / duration_ms:", exc_info=e)


async def detect_and_save_artifacts(
    db,
    ws,
    conversation_id: str,
    assistant_msg_id: str,
    full_response: str,
    skip_svg: bool = False,
    user_message: str = "",
) -> list[dict]:
    """
    Detecta artifacts na resposta, persiste-os no banco e emite eventos WS.

    Retorna lista de dicts ``{"id", "type", "title"}``.
    """
    if not full_response:
        return []

    artifacts_list: list[dict] = []
    try:
        detected_list = detect_artifacts(full_response, user_message=user_message)
        for detected in detected_list:
            if skip_svg and detected.get("type") == "svg":
                continue
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
