"""Carregamento de histórico, injeção de documentos e Vision Relay.

Extraído de `backend/routers/chat.py` (responsabilidades 8 e 6 da função God).
"""

from __future__ import annotations

import asyncio
import logging

from backend.attachments.storage import get_absolute_path
from backend.logging_config import get_logger

logger = get_logger(__name__)

_DOC_INJECT_MAX_CHARS = 6000


def _read_file_b64(path: str) -> str:
    """Lê arquivo binário → base64 (síncrono; projetado para run_in_executor)."""
    import base64

    with open(path, "rb") as f:
        return base64.b64encode(f.read()).decode("utf-8")


async def load_history(
    db,
    conversation_id: str,
    user_msg_id: str,
    attachments_by_msg: dict,
    extracted_text_by_id: dict,
    model_supports_vision: bool,
    web_search_used: bool,
    search_results: list,
    web_search_query: str,
    search_config: dict | None,
    format_search_results_fn,
    user_id: str,
) -> tuple[list[dict], int, str | None]:
    """Monta o histórico de mensagens com attachments, docs e imagens.

    Retorna (history, relay_used, relay_model_id).
    """
    from backend.web_search import format_search_results as _fmt
    from backend.vision_relay.relay import describe_image_via_relay

    # Carrega mensagens ordenadas
    async with db.execute(
        """SELECT id, role, content FROM messages
           WHERE conversation_id = ?
           ORDER BY created_at ASC""",
        (conversation_id,),
    ) as cur:
        messages_rows = [
            {"id": r[0], "role": r[1], "content": r[2]}
            for r in await cur.fetchall()
        ]

    relay_used = 0
    relay_model_id: str | None = None
    history: list[dict] = []

    for msg in messages_rows:
        msg_atts = attachments_by_msg.get(msg["id"], [])
        text_content = msg["content"]

        # 0. Web Search injection
        if msg["id"] == user_msg_id and web_search_used and search_results:
            search_context = (
                format_search_results_fn(
                    search_results,
                    web_search_query,
                    template=(search_config or {}).get("injection_template"),
                )
                if format_search_results_fn
                else _fmt(
                    search_results,
                    web_search_query,
                    template=(search_config or {}).get("injection_template"),
                )
            )
            text_content = f"{search_context}\n\n---\n\n{text_content}"

        # 1. Document injection
        docs = [a for a in msg_atts if a["file_type"] == "document"]
        if docs:
            doc_context = ""
            for d in docs:
                ext_text = extracted_text_by_id.get(d["id"], "")
                if ext_text and len(ext_text) > _DOC_INJECT_MAX_CHARS:
                    ext_text = (
                        ext_text[:_DOC_INJECT_MAX_CHARS].rstrip()
                        + "\n…[documento truncado para caber no contexto do modelo]"
                    )
                doc_context += f"\n\n--- Conteúdo de {d['filename']} ---\n{ext_text}\n"
            text_content = f"{doc_context}\n\n---\n\n{text_content}"

        # 2. Image handling
        images = [a for a in msg_atts if a["file_type"] == "image"]
        if images:
            if model_supports_vision:
                parts: list[dict] = [{"type": "text", "text": text_content}]
                for img in images:
                    try:
                        abs_img_path = get_absolute_path(img["storage_path"])
                        b64 = await asyncio.to_thread(_read_file_b64, abs_img_path)
                        parts.append(
                            {
                                "type": "image_url",
                                "image_url": {
                                    "url": f"data:{img['mime_type']};base64,{b64}"
                                },
                            }
                        )
                    except Exception:
                        logger.exception(
                            "Erro ao ler/encoded imagem base64",
                            extra={"filename": img.get("filename")},
                        )
                history.append({"role": msg["role"], "content": parts})
            else:
                # Vision Relay
                image_descriptions: list[str] = []
                for img in images:
                    try:
                        res = await describe_image_via_relay(
                            img["storage_path"],
                            img["mime_type"],
                            img["file_hash"],
                            user_id=user_id,
                            conversation_id=conversation_id,
                        )
                        desc = res["description"]
                        image_descriptions.append(
                            f"[Descrição da imagem {img['filename']}]: {desc}"
                        )
                        if msg["id"] == user_msg_id:
                            relay_used = 1
                            relay_model_id = res["relay_model"]
                    except Exception as e:
                        logger.error(
                            "Vision Relay falhou",
                            exc_info=True,
                            extra={
                                "filename": img.get("filename"),
                                "conversation_id": conversation_id,
                            },
                        )
                        raise e

                if image_descriptions:
                    descriptions_block = "\n\n".join(image_descriptions)
                    text_content = f"{descriptions_block}\n\n---\n\n{text_content}"
                history.append({"role": msg["role"], "content": text_content})
        else:
            history.append({"role": msg["role"], "content": text_content})

    return history, relay_used, relay_model_id


async def load_attachments(db, conversation_id: str) -> tuple[dict, dict]:
    """Carrega todos os anexos da conversa em batch.

    Retorna (attachments_by_msg, extracted_text_by_id).
    """
    async with db.execute(
        """SELECT id, message_id, filename, mime_type, file_type, storage_path,
                  file_hash, extracted_text
           FROM attachments
           WHERE message_id IN (SELECT id FROM messages WHERE conversation_id = ?)""",
        (conversation_id,),
    ) as cur:
        att_rows = await cur.fetchall()

    attachments_by_msg: dict[str, list[dict]] = {}
    extracted_text_by_id: dict[str, str] = {}

    for row in att_rows:
        (
            att_id,
            m_id,
            filename,
            mime_type,
            file_type,
            storage_path,
            file_hash,
            extracted_text,
        ) = row
        if extracted_text is not None:
            extracted_text_by_id[att_id] = extracted_text
        if m_id:
            if m_id not in attachments_by_msg:
                attachments_by_msg[m_id] = []
            attachments_by_msg[m_id].append(
                {
                    "id": att_id,
                    "filename": filename,
                    "mime_type": mime_type,
                    "file_type": file_type,
                    "storage_path": storage_path,
                    "file_hash": file_hash,
                }
            )

    return attachments_by_msg, extracted_text_by_id


async def check_model_vision_support(db, model_id: str) -> bool:
    """Verifica se o modelo suporta entrada visual."""
    async with db.execute(
        "SELECT supports_vision FROM models WHERE id = ?", (model_id,)
    ) as cur:
        row = await cur.fetchone()
    return bool(row[0]) if row else False
