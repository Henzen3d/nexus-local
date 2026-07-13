"""build_context — montagem do system prompt com memória e project RAG.

Responsabilidades extraídas de chat.py (itens 9-10 da Fase 5 do AUDIT-REPORT):
  - Injeção de memória/perfil + fingerprint
  - Context builder de projetos (RAG: instructions + memory + files + chats)
  - Assembly final do system_instruction
"""

from __future__ import annotations

import logging
from typing import Any, List

from backend.logging_config import get_logger
from backend.memory import build_memory_block, build_memory_fingerprint
from backend.database import (
    get_user_profile,
    get_relevant_memory,
    get_memory_summary,
    get_conversation_project_tag,
)

logger = get_logger(__name__)

BASE_SYSTEM_PROMPT = (
    "Você é o NexusLocal, uma IA assistente útil.\n"
    "Sempre que o usuário solicitar a criação de arquivos, códigos ou documentos (como HTML, SVG, Markdown, CSS, JS ou JSX), "
    "forneça o código completo diretamente dentro de um único bloco de código markdown correspondente (fenced code block).\n"
    "Importante: NÃO dê instruções de empacotamento, compactação ZIP, instalação de pipelines de CI/CD ou "
    "scripts de automação (como scripts BASH ou Node.js para criar o arquivo), a menos que o usuário "
    "solicite isso explicitamente. O download e a visualização do arquivo são gerenciados automaticamente pela interface.\n"
    "RESTRIÇÃO CRÍTICA: Você NÃO possui acesso a nenhuma ferramenta externa (search_web, read_file, buscar_paginas_web, "
    "buscar_google, ler_arquivo, ou qualquer outra). NÃO tente chamar ou invocar ferramentas. "
    "Responda sempre diretamente com base no contexto e histórico fornecidos."
)


async def build_memory_context(
    user: dict | None,
    conversation_id: str,
    user_message: str,
    use_memory: bool,
    provider_id: str,
    model_id: str,
) -> tuple[str, str]:
    """Carrega perfil + memórias e retorna (memory_text, fingerprint).

    Substitui os itens 9 do AUDIT-REPORT (linhas 611-665 do chat.py original).
    """
    if not user or "id" not in user or not use_memory:
        return "", "nomem"

    user_id = user["id"]

    try:
        profile = await get_user_profile(user_id)
        mem_enabled = bool(profile.get("memory_enabled", 1))
        mem_rows: list = []
        global_sum = None
        project_sum = None

        if mem_enabled:
            try:
                from backend.memory import (
                    repair_identity_family_confusion,
                    refresh_memory_summaries,
                )
                repaired = await repair_identity_family_confusion(user_id)
                if repaired:
                    await refresh_memory_summaries(
                        user_id,
                        conversation_id=conversation_id,
                        provider_id=provider_id,
                        model_id=model_id,
                        use_llm=False,
                    )
            except Exception as rep_err:
                logger.warning(
                    "memory repair (injection-time) failed",
                    exc_info=rep_err,
                    extra={"conversation_id": conversation_id, "user_id": user_id},
                )

            mem_rows = await get_relevant_memory(user_id, user_message or "", limit=30)
            global_sum = await get_memory_summary(user_id, "global", "")
            project_tag = await get_conversation_project_tag(conversation_id)
            if project_tag:
                project_sum = await get_memory_summary(
                    user_id, "project", project_tag.lower()
                )

        summaries = [s for s in (global_sum, project_sum) if s]
        mem_text = build_memory_block(
            mem_rows,
            profile=profile,
            global_summary=global_sum,
            project_summary=project_sum,
        )
        fingerprint = build_memory_fingerprint(mem_rows, profile=profile, summaries=summaries)
        return mem_text, fingerprint

    except Exception as mem_err:
        logger.error(
            "failed to load memories/profile for context injection",
            exc_info=mem_err,
            extra={"conversation_id": conversation_id, "user_id": user_id},
        )
        return "", ""


async def resolve_project_context(
    db,
    ws,
    conversation_id: str,
    request_project_id: str | None,
    user: dict,
    model_id: str,
    provider_id: str,
    user_message: str,
    history: list,
    project_context_debug: bool,
    base_system: str,
    user_mem_text: str,
) -> tuple[str | None, str]:
    """Resolve o project_id ativo e, se houver, constrói o context RAG.

    Retorna (active_project_id, system_instruction).

    Substitui o item 10 do AUDIT-REPORT (linhas 677-806 do chat.py original).
    """
    active_project_id = None

    try:
        async with db.execute(
            "SELECT project_id FROM conversations WHERE id = ?",
            (conversation_id,),
        ) as cur:
            prow = await cur.fetchone()
            active_project_id = prow[0] if prow and prow[0] else None

        if not active_project_id and request_project_id:
            async with db.execute(
                "SELECT id FROM projects WHERE id = ? AND user_id = ? AND archived = 0",
                (request_project_id, user["id"]),
            ) as cur:
                if await cur.fetchone():
                    await db.execute(
                        "UPDATE conversations SET project_id = ? WHERE id = ? AND user_id = ?",
                        (request_project_id, conversation_id, user["id"]),
                    )
                    await db.commit()
                    active_project_id = request_project_id
    except Exception as e:
        logger.warning(
            "failed to resolve project_id",
            exc_info=e,
            extra={"conversation_id": conversation_id},
        )

    system_instruction = base_system + (user_mem_text or "")

    if not active_project_id:
        return None, system_instruction

    try:
        from backend.projects.context_builder import (
            build_project_context,
            compute_safe_input_tokens,
            estimate_tokens,
        )

        ctx_window = 8192
        known_tpm = None
        try:
            async with db.execute(
                """SELECT m.context_length, q.known_tpm
                   FROM models m
                   LEFT JOIN model_quota_status q ON q.model_id = m.id
                   WHERE m.id = ?""",
                (model_id,),
            ) as cur:
                mrow = await cur.fetchone()
                if mrow and mrow[0]:
                    ctx_window = int(mrow[0])
                if mrow and len(mrow) > 1 and mrow[1]:
                    known_tpm = int(mrow[1])
        except Exception:
            try:
                async with db.execute(
                    "SELECT context_length FROM models WHERE id = ?",
                    (model_id,),
                ) as cur:
                    mrow = await cur.fetchone()
                    if mrow and mrow[0]:
                        ctx_window = int(mrow[0])
            except Exception:
                pass

        hist_chars = sum(
            len(str(m.get("content") or ""))
            if not isinstance(m.get("content"), list)
            else sum(len(str(p.get("text", ""))) for p in m["content"] if isinstance(p, dict))
            for m in history
        )
        reserve_hist = max(1500, hist_chars // 4)
        safe_input = compute_safe_input_tokens(
            ctx_window,
            known_tpm=known_tpm,
            provider_id=provider_id,
        )

        pctx = await build_project_context(
            project_id=active_project_id,
            query=user_message or "",
            exclude_conversation_id=conversation_id,
            context_window=ctx_window,
            reserve_for_history=reserve_hist,
            reserve_for_response=1024,
            include_debug=project_context_debug,
            base_system=base_system,
            extra_system_suffix=user_mem_text or "",
            known_tpm=known_tpm,
            provider_id=provider_id,
            safe_input_tokens=safe_input,
        )
        system_instruction = pctx.system_content

        if pctx.budget_note:
            try:
                await ws.send_json({
                    "type": "project_context_notice",
                    "message": pctx.budget_note,
                    "tokens_est": pctx.tokens_est,
                    "safe_input_tokens": safe_input,
                })
            except Exception:
                pass

        if project_context_debug:
            await ws.send_json({
                "type": "project_context_debug",
                "project_id": active_project_id,
                "debug": pctx.debug,
                "file_chunks": [
                    {
                        "filename": c.get("filename"),
                        "score": round(c.get("score", 0), 4),
                        "preview": (c.get("chunk_text") or "")[:200],
                    }
                    for c in pctx.file_chunks
                ],
                "chat_chunks": [
                    {
                        "conversation_id": c.get("conversation_id"),
                        "score": round(c.get("score", 0), 4),
                        "preview": (c.get("chunk_text") or "")[:200],
                    }
                    for c in pctx.chat_chunks
                ],
                "tokens_est": pctx.tokens_est,
                "trimmed": pctx.trimmed,
                "safe_input_tokens": safe_input,
                "system_tokens_est": estimate_tokens(system_instruction),
            })
    except Exception as e:
        logger.error(
            "context_builder error",
            exc_info=e,
            extra={"conversation_id": conversation_id, "project_id": active_project_id},
        )

    return active_project_id, system_instruction
