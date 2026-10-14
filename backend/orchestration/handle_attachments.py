"""Carregamento de histórico, injeção de documentos e Vision Relay.

Extraído de `backend/routers/chat.py` (responsabilidades 8 e 6 da função God).
"""

from __future__ import annotations

import asyncio
import base64
import hashlib
import os

from backend.attachments.storage import get_absolute_path
from backend.logging_config import get_logger

logger = get_logger(__name__)

_DOC_INJECT_MIN_CHARS = 6000
_DOC_INJECT_MAX_CHARS = 24000


def _read_file_b64(path: str) -> str:
    """Lê arquivo binário → base64 (síncrono; projetado para run_in_executor)."""
    with open(path, "rb") as f:
        return base64.b64encode(f.read()).decode("utf-8")


def doc_inject_max_chars(safe_input_tokens: int) -> int:
    """Fatia do orçamento de input, piso 6000, teto ~24k caracteres."""
    raw = int(safe_input_tokens or 0) * 3
    return max(_DOC_INJECT_MIN_CHARS, min(_DOC_INJECT_MAX_CHARS, raw))


def select_document_excerpt(text: str, query: str, max_chars: int) -> str:
    """Injeta o documento inteiro se couber; senão trechos que batem com a pergunta."""
    if not text:
        return ""
    cap = max(_DOC_INJECT_MIN_CHARS, min(_DOC_INJECT_MAX_CHARS, int(max_chars or _DOC_INJECT_MIN_CHARS)))
    if len(text) <= cap:
        return text

    from backend.projects.chunker import chunk_text
    from backend.projects.context_builder import _simple_keyword_score

    chunks = chunk_text(text, chunk_size=min(1200, cap))
    if not chunks:
        return text[:cap].rstrip() + "\n…[documento truncado para caber no contexto do modelo]"

    scored: list[tuple[float, int, str]] = []
    for i, chunk in enumerate(chunks):
        score = _simple_keyword_score(query, chunk) if query else 0.0
        scored.append((score, i, chunk))

    hits = [item for item in scored if item[0] > 0]
    pool = hits if hits else scored
    pool.sort(key=lambda item: (-item[0], item[1]))

    selected: list[tuple[int, str]] = []
    used = 0
    for _score, idx, chunk in pool:
        extra = len(chunk) + (2 if selected else 0)
        if used + extra > cap:
            continue
        selected.append((idx, chunk))
        used += extra

    if not selected:
        selected = [(scored[0][1], scored[0][2][:cap])]

    selected.sort(key=lambda item: item[0])
    omitted = len(chunks) - len(selected)
    body = "\n\n".join(chunk for _idx, chunk in selected)
    if omitted > 0:
        body += f"\n…[{omitted} trecho(s) do documento ficaram de fora do contexto]"
    return body


def history_contains_images(history: list[dict]) -> bool:
    for msg in history:
        content = msg.get("content")
        if isinstance(content, list):
            for part in content:
                if isinstance(part, dict) and part.get("type") == "image_url":
                    return True
    return False


def is_vision_refusal_error(err: object) -> bool:
    text = str(err or "").lower()
    if not text:
        return False
    needles = (
        "not support image",
        "doesn't support image",
        "images are not supported",
        "image inputs",
        "vision is not supported",
        "does not support vision",
        "cannot process image",
        "can't process image",
        "multimodal",
        "input_modalities",
        "unsupported content",
    )
    if any(n in text for n in needles):
        return True
    if "image_url" in text and any(
        w in text for w in ("support", "invalid", "unknown", "not allowed", "unsupported")
    ):
        return True
    return False


def _parse_data_url(url: str) -> tuple[str, bytes]:
    if not url.startswith("data:"):
        return "image/png", b""
    header, _, data = url.partition(",")
    mime = "image/png"
    if header.startswith("data:") and ";" in header:
        mime = header[5:].split(";", 1)[0] or mime
    try:
        return mime, base64.b64decode(data)
    except Exception:
        return mime, b""


async def replace_images_with_relay(
    history: list[dict],
    user_id: str,
    conversation_id: str | None = None,
) -> list[dict]:
    """Troca image_url do histórico por descrições do Vision Relay."""
    from backend.vision_relay.relay import describe_image_via_relay

    out: list[dict] = []
    for msg in history:
        content = msg.get("content")
        if not isinstance(content, list) or not any(
            isinstance(p, dict) and p.get("type") == "image_url" for p in content
        ):
            out.append(msg)
            continue

        texts: list[str] = []
        descriptions: list[str] = []
        for part in content:
            if not isinstance(part, dict):
                continue
            if part.get("type") == "text":
                texts.append(part.get("text") or "")
            elif part.get("type") == "image_url":
                url = (part.get("image_url") or {}).get("url") or ""
                mime, raw = _parse_data_url(url)
                if not raw:
                    continue
                file_hash = hashlib.sha256(raw).hexdigest()
                res = await describe_image_via_relay(
                    None,
                    mime,
                    file_hash,
                    user_id,
                    conversation_id,
                    image_bytes=raw,
                )
                descriptions.append(f"[Descrição da imagem]: {res['description']}")

        text_content = "\n".join(texts)
        if descriptions:
            text_content = f"{chr(10).join(descriptions)}\n\n---\n\n{text_content}"
        out.append({"role": msg["role"], "content": text_content})
    return out


async def _doc_inject_cap(db, model_id: str | None, provider_id: str | None) -> int:
    if not model_id:
        return _DOC_INJECT_MIN_CHARS
    ctx = 8192
    try:
        async with db.execute(
            "SELECT context_length FROM models WHERE id = ?", (model_id,)
        ) as cur:
            row = await cur.fetchone()
            if row and row[0]:
                ctx = int(row[0])
    except Exception:
        logger.debug("Não leu context_length para fatia de anexo", exc_info=True)
    from backend.projects.context_builder import compute_safe_input_tokens

    safe = compute_safe_input_tokens(ctx, provider_id=provider_id)
    return doc_inject_max_chars(safe)


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
    user_query: str = "",
    model_id: str | None = None,
    provider_id: str | None = None,
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
    max_doc_chars = await _doc_inject_cap(db, model_id, provider_id)
    question = user_query or ""

    for msg in messages_rows:
        msg_atts = attachments_by_msg.get(msg["id"], [])
        text_content = msg["content"]
        if msg["id"] == user_msg_id and not question:
            question = text_content or ""

        # 0. Web Search injection
        scraped_pages = (search_config or {}).get("scraped_pages")
        if msg["id"] == user_msg_id and web_search_used and (search_results or scraped_pages):
            search_context = (
                format_search_results_fn(
                    search_results,
                    web_search_query,
                    template=(search_config or {}).get("injection_template"),
                    scraped_pages=scraped_pages,
                )
                if format_search_results_fn
                else _fmt(
                    search_results,
                    web_search_query,
                    template=(search_config or {}).get("injection_template"),
                    scraped_pages=scraped_pages,
                )
            )
            text_content = f"{search_context}\n\n---\n\n{text_content}"

        # 1. Document injection
        docs = [a for a in msg_atts if a["file_type"] == "document"]
        if docs:
            doc_context = ""
            for idx, d in enumerate(docs, 1):
                ext_text = extracted_text_by_id.get(d["id"], "")
                if ext_text:
                    ext_text = select_document_excerpt(
                        ext_text,
                        query=question or text_content or "",
                        max_chars=max_doc_chars,
                    )
                safe_fn = (d.get("filename") or "documento").replace('"', '&quot;').replace('<', '&lt;').replace('>', '&gt;')
                doc_context += f'\n<fonte id="{idx}" origem="{safe_fn}">\n{ext_text}\n</fonte>\n'
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


# ── Poda do histórico ────────────────────────────────────────────────────────
# Custo aproximado de uma imagem inline (base64) em tokens de entrada. Os
# provedores cobram por tiles (~85–1500 tokens); contar os caracteres do base64
# (chars/4) superestimaria em 100x e podaria a conversa inteira.
_IMAGE_PART_TOKENS = 1000
_PER_MESSAGE_OVERHEAD_TOKENS = 4


def estimate_message_tokens(msg: dict) -> int:
    """Estimativa de tokens de uma mensagem (texto ou multimodal)."""
    from backend.projects.context_builder import estimate_tokens

    content = msg.get("content")
    total = _PER_MESSAGE_OVERHEAD_TOKENS
    if isinstance(content, str):
        total += estimate_tokens(content)
    elif isinstance(content, list):
        for part in content:
            if not isinstance(part, dict):
                continue
            if part.get("type") == "text":
                total += estimate_tokens(part.get("text") or "")
            elif part.get("type") == "image_url":
                total += _IMAGE_PART_TOKENS
    return total


def trim_history_to_budget(
    history: list[dict],
    budget_tokens: int,
    reserved_tokens: int = 0,
    min_keep: int = 2,
) -> tuple[list[dict], int]:
    """Mantém as mensagens mais recentes que cabem em ``budget_tokens``.

    - ``reserved_tokens`` é o que já está comprometido fora do histórico
      (system prompt, memória, contexto de projeto).
    - A última mensagem do usuário é SEMPRE mantida, mesmo que sozinha
      exceda o orçamento (o provedor devolve um erro claro nesse caso, em vez
      de a aplicação descartar silenciosamente a pergunta).
    - Remove sempre do início (mensagens mais antigas) para preservar a
      coerência do fim da conversa; nunca remove menos que ``min_keep`` do fim
      se elas couberem.

    Retorna ``(history_podado, mensagens_removidas)``.
    """
    if not history:
        return history, 0
    available = max(0, int(budget_tokens) - int(reserved_tokens))
    costs = [estimate_message_tokens(m) for m in history]
    if sum(costs) <= available:
        return history, 0

    kept: list[dict] = []
    used = 0
    for idx in range(len(history) - 1, -1, -1):
        cost = costs[idx]
        is_last = idx == len(history) - 1
        if is_last or used + cost <= available or len(kept) < min_keep and used + cost <= available * 1.2:
            kept.append(history[idx])
            used += cost
            continue
        break
    kept.reverse()
    # Não começar o histórico com uma resposta do assistente órfã (alguns
    # provedores — Anthropic/Gemini — exigem que a primeira mensagem seja do usuário).
    while len(kept) > 1 and kept[0].get("role") == "assistant":
        kept.pop(0)
    removed = len(history) - len(kept)
    if removed:
        logger.info(
            "Histórico podado para caber no orçamento de entrada",
            extra={
                "removed_messages": removed,
                "kept_messages": len(kept),
                "budget_tokens": available,
                "estimated_tokens": used,
            },
        )
    return kept, removed


async def resolve_input_budget(db, model_id: str | None, provider_id: str | None) -> int:
    """Orçamento de tokens de entrada para o modelo (context_length × margem, TPM, provedor)."""
    from backend.projects.context_builder import compute_safe_input_tokens

    ctx_window = 8192
    known_tpm = None
    if model_id:
        try:
            async with db.execute(
                """SELECT m.context_length, q.known_tpm
                   FROM models m
                   LEFT JOIN model_quota_status q ON q.model_id = m.id
                   WHERE m.id = ?""",
                (model_id,),
            ) as cur:
                row = await cur.fetchone()
                if row and row[0]:
                    ctx_window = int(row[0])
                if row and len(row) > 1 and row[1]:
                    known_tpm = int(row[1])
        except Exception:
            try:
                async with db.execute(
                    "SELECT context_length FROM models WHERE id = ?", (model_id,)
                ) as cur:
                    row = await cur.fetchone()
                    if row and row[0]:
                        ctx_window = int(row[0])
            except Exception:
                logger.debug("Não leu context_length para orçamento do histórico", exc_info=True)
    # O hard_cap padrão (7000) é pensado para a injeção de RAG de projetos; para o
    # histórico usamos um teto maior, configurável, respeitando TPM e regras por provedor.
    try:
        history_cap = int(os.getenv("HISTORY_INPUT_TOKEN_CAP", "32000"))
    except ValueError:
        history_cap = 32000
    return compute_safe_input_tokens(
        ctx_window, known_tpm=known_tpm, provider_id=provider_id, hard_cap=max(2048, history_cap)
    )
