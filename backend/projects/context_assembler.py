"""
Context Assembler — Serviço unificado de montagem de contexto e cálculo de capacidade
para Projetos do NexusLocal (Paridade Claude.ai).

Alimenta TANTO o cálculo da Barra de Capacidade na UI QUANTO a injeção real no prompt:
- Ordem de Precedência Estrita:
    1. Instruções do Projeto
    2. Memória do Projeto
    3. Manifesto de Arquivos Completo (sempre presente para resposta global)
    4. Contexto de Arquivos (Modo Integral se couber, ou Modo RAG com citações [Fonte: ...])
    5. Conversas Irmãs (quando couber)
- Isolamento Absoluto por project_id em todas as consultas SQL e vetoriais.
- Backfill automático de token_count e file_size para registros existentes.
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass, field
from typing import Optional, Any

import aiosqlite

from backend.database import DB_PATH
from backend.logging_config import get_logger
from backend.projects.vector_store import (
    DEFAULT_RETRIEVAL_THRESHOLD,
    DEFAULT_TOP_K,
    search_file_chunks,
)
from backend.projects.indexer import retrieve_related_chats
from backend.projects.context_builder import (
    compute_safe_input_tokens,
    fit_chunks_to_token_budget,
    apply_token_budget,
    DEFAULT_SAFE_INPUT_CAP,
    DEFAULT_MAX_FILE_RAG_TOKENS,
    DEFAULT_MAX_CHAT_RAG_TOKENS,
    _format_chat_block,
    _format_file_block,
)
from backend.orchestration.build_context import BASE_SYSTEM_PROMPT

logger = get_logger(__name__)

# Capacidade base de referência: 128k tokens (131.072)
DEFAULT_PROJECT_CAPACITY = 131072

# Limite máximo de injeção direta integral antes de comutar para RAG (tokens)
DEFAULT_DIRECT_INJECTION_CAP = 32000


def estimate_tokens(text: str) -> int:
    """Estimativa rápida e consistente de tokens (1 token ≈ 4 caracteres)."""
    if not text:
        return 0
    return max(1, len(text) // 4)


def format_bytes(size: int) -> str:
    """Formata bytes para exibição amigável (ex: 2,8 kB, 1,2 MB)."""
    if size < 1024:
        return f"{size} B"
    elif size < 1024 * 1024:
        kb = size / 1024
        return f"{kb:.1f} kB".replace(".", ",")
    else:
        mb = size / (1024 * 1024)
        return f"{mb:.1f} MB".replace(".", ",")


@dataclass
class ProjectContextResult:
    system_content: str
    project_id: str
    instructions_used: bool = False
    memory_project_used: bool = False
    memory_global_used: bool = False
    file_chunks: list[dict] = field(default_factory=list)
    chat_chunks: list[dict] = field(default_factory=list)
    tokens_est: int = 0
    trimmed: list[str] = field(default_factory=list)
    debug: dict = field(default_factory=dict)
    budget_note: str = ""
    mode: str = "full"  # "full" | "rag"
    manifest_used: bool = True


async def _backfill_file_metadata(db: aiosqlite.Connection, file_row: dict) -> dict:
    """Garante file_size e token_count preenchidos na memória e no banco."""
    file_id = file_row["id"]
    size_bytes = file_row.get("size_bytes") or 0
    file_size = file_row.get("file_size") or size_bytes
    token_count = file_row.get("token_count") or 0
    extracted_text = file_row.get("extracted_text") or ""

    needs_update = False
    if file_size == 0 and size_bytes > 0:
        file_size = size_bytes
        needs_update = True
    if token_count == 0 and extracted_text:
        token_count = estimate_tokens(extracted_text)
        needs_update = True

    if needs_update:
        try:
            await db.execute(
                "UPDATE project_files SET file_size = ?, token_count = ? WHERE id = ?",
                (file_size, token_count, file_id),
            )
            await db.commit()
        except Exception as e:
            logger.warning("[context_assembler] Backfill file update warning: %s", e)

    updated = dict(file_row)
    updated["file_size"] = file_size
    updated["token_count"] = token_count
    return updated


async def calculate_project_capacity(
    project_id: str,
    capacity_limit: int = DEFAULT_PROJECT_CAPACITY,
    db_path: str = DB_PATH,
) -> dict:
    """
    Calcula a capacidade e uso de contexto do projeto.
    Usado tanto pelo endpoint de status para a UI quanto pelo montador de prompt.
    """
    if not project_id:
        return {
            "project_id": "",
            "total_tokens": 0,
            "capacity_limit": capacity_limit,
            "usage_percent": 0.0,
            "mode": "full",
            "is_amber": False,
            "is_rag_active": False,
            "breakdown": {
                "instructions_tokens": 0,
                "memory_tokens": 0,
                "files_tokens": 0,
                "file_count": 0,
            },
            "files_manifest": [],
        }

    async with aiosqlite.connect(db_path) as db:
        db.row_factory = aiosqlite.Row

        # 1. Instruções
        async with db.execute(
            "SELECT instructions FROM projects WHERE id = ? AND archived = 0",
            (project_id,),
        ) as cur:
            p_row = await cur.fetchone()
        instructions = (p_row["instructions"] or "") if p_row else ""
        inst_tokens = estimate_tokens(instructions)

        # 2. Memória
        async with db.execute(
            "SELECT summary_text, token_count FROM project_memory WHERE project_id = ?",
            (project_id,),
        ) as cur:
            m_row = await cur.fetchone()
        memory_text = (m_row["summary_text"] or "") if m_row else ""
        mem_tokens = m_row["token_count"] if (m_row and m_row["token_count"]) else estimate_tokens(memory_text)

        # 3. Arquivos (com backfill on-the-fly)
        async with db.execute(
            """SELECT id, filename, mime_type, raw_path, extracted_text, size_bytes,
                      file_size, file_hash, token_count, index_status
               FROM project_files
               WHERE project_id = ?
               ORDER BY created_at ASC""",
            (project_id,),
        ) as cur:
            f_rows = await cur.fetchall()

        manifest_list = []
        files_tokens = 0
        for r in f_rows:
            f_dict = await _backfill_file_metadata(db, dict(r))
            t_count = f_dict.get("token_count") or 0
            f_size = f_dict.get("file_size") or f_dict.get("size_bytes") or 0
            files_tokens += t_count
            manifest_list.append({
                "id": f_dict["id"],
                "filename": f_dict["filename"],
                "size_bytes": f_size,
                "size_formatted": format_bytes(f_size),
                "token_count": t_count,
                "index_status": f_dict.get("index_status", "ready"),
                "file_hash": f_dict.get("file_hash"),
            })

    total_tokens = inst_tokens + mem_tokens + files_tokens
    usage_percent = round(min(100.0, (total_tokens / max(1, capacity_limit)) * 100), 1)

    # Modo Integral vs RAG:
    # Se os arquivos ultrapassarem a capacidade de injeção direta segura, ativa RAG
    mode = "full"
    if files_tokens > DEFAULT_DIRECT_INJECTION_CAP or total_tokens > capacity_limit:
        mode = "rag"

    is_amber = usage_percent >= 70.0
    is_rag_active = (mode == "rag") or (usage_percent >= 100.0)

    return {
        "project_id": project_id,
        "total_tokens": total_tokens,
        "capacity_limit": capacity_limit,
        "usage_percent": usage_percent,
        "mode": mode,
        "is_amber": is_amber,
        "is_rag_active": is_rag_active,
        "breakdown": {
            "instructions_tokens": inst_tokens,
            "memory_tokens": mem_tokens,
            "files_tokens": files_tokens,
            "file_count": len(manifest_list),
        },
        "files_manifest": manifest_list,
    }


def build_file_manifest(files: list[dict]) -> str:
    """
    Manifesto de Arquivos Sempre Presente:
    Índice compacto com todos os arquivos do projeto (nome, extensão, tamanho, tokens),
    permitindo que o modelo responda perguntas sobre o acervo mesmo em modo RAG.
    """
    if not files:
        return ""

    total_size = sum((f.get("file_size") or f.get("size_bytes") or 0) for f in files)
    total_tokens = sum((f.get("token_count") or 0) for f in files)

    lines = [
        "## Índice do Acervo de Arquivos do Projeto",
        f"Total: {len(files)} arquivo(s) | Tamanho: {format_bytes(total_size)} | ~{total_tokens} tokens",
        "Arquivos disponíveis no workspace deste projeto:",
    ]
    for f in files:
        name = f.get("filename", "desconhecido")
        size = format_bytes(f.get("file_size") or f.get("size_bytes") or 0)
        tok = f.get("token_count", 0)
        status = f.get("index_status", "ready")
        status_note = f" [{status}]" if status not in ("ready", None) else ""
        lines.append(f"- `{name}` ({size}, ~{tok} tokens){status_note}")

    return "\n".join(lines)


async def assemble_project_context(
    project_id: str,
    query: str = "",
    exclude_conversation_id: Optional[str] = None,
    context_window: int = 8192,
    reserve_for_history: int = 1500,
    reserve_for_response: int = 1024,
    safe_input_tokens: Optional[int] = None,
    base_system: str = "",
    extra_system_suffix: str = "",
    known_tpm: Optional[int] = None,
    provider_id: Optional[str] = None,
    request_context: Optional[Any] = None,
    include_debug: bool = False,
    db_path: str = DB_PATH,
) -> ProjectContextResult:
    """
    Montador de Contexto Único:
    Ordem Estrita:
      1. Instruções do Projeto
      2. Memória do Projeto
      3. Manifesto de Arquivos (sempre presente)
      4. Conteúdo de Arquivos (Integral no modo 'full' OU Chunks RAG com [Fonte: ...] no modo 'rag')
      5. Conversas Irmãs (quando couber)
    """
    if not project_id:
        return ProjectContextResult(
            system_content=base_system or BASE_SYSTEM_PROMPT,
            project_id="",
            tokens_est=estimate_tokens(base_system or BASE_SYSTEM_PROMPT),
        )

    # 1. Carrega dados do projeto garantindo isolamento por project_id
    async with aiosqlite.connect(db_path) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            """SELECT id, name, description, instructions, model_default,
                      retrieval_top_k, retrieval_threshold
               FROM projects WHERE id = ? AND archived = 0""",
            (project_id,),
        ) as cur:
            p_row = await cur.fetchone()
        project = dict(p_row) if p_row else None

        if not project:
            return ProjectContextResult(
                system_content=base_system or BASE_SYSTEM_PROMPT,
                project_id=project_id,
                tokens_est=estimate_tokens(base_system or BASE_SYSTEM_PROMPT),
            )

        # Memória do projeto
        async with db.execute(
            "SELECT summary_text, token_count FROM project_memory WHERE project_id = ?",
            (project_id,),
        ) as cur:
            m_row = await cur.fetchone()
        memory_text = (m_row["summary_text"] or "") if m_row else ""

        # Arquivos do projeto
        async with db.execute(
            """SELECT id, filename, mime_type, raw_path, extracted_text, size_bytes,
                      file_size, file_hash, token_count, index_status
               FROM project_files
               WHERE project_id = ?
               ORDER BY created_at ASC""",
            (project_id,),
        ) as cur:
            f_rows = await cur.fetchall()

        project_files = []
        for r in f_rows:
            f_backfilled = await _backfill_file_metadata(db, dict(r))
            project_files.append(f_backfilled)

    # 2. Orçamento seguro de tokens
    safe_total = safe_input_tokens or compute_safe_input_tokens(
        context_window,
        known_tpm=known_tpm,
        provider_id=provider_id,
        hard_cap=DEFAULT_SAFE_INPUT_CAP,
    )

    available_for_context = max(
        1024,
        safe_total - reserve_for_history - reserve_for_response - estimate_tokens(base_system)
    )

    instructions = (project.get("instructions") or "").strip()
    inst_tokens = estimate_tokens(instructions)
    mem_tokens = estimate_tokens(memory_text)

    # Orçamento restante para arquivos
    files_budget = max(500, available_for_context - inst_tokens - mem_tokens)

    # 3. Decisão: Modo Integral (Full) vs. Modo Recuperação (RAG)
    total_files_tokens = sum((f.get("token_count") or 0) for f in project_files)
    ready_files = [
        f for f in project_files
        if f.get("extracted_text") and (f.get("extracted_text") or "").strip()
    ]

    mode = "full"
    if total_files_tokens > files_budget or total_files_tokens > DEFAULT_DIRECT_INJECTION_CAP:
        mode = "rag"

    # Se não houver arquivos ou se nenhum tiver texto extraído, mantém full (sem RAG forçado)
    if not ready_files:
        mode = "full"

    # 4. Montagem das seções
    # Manifesto compacto de arquivos sempre presente
    manifest_md = build_file_manifest(project_files)

    file_hits: list[dict] = []
    chat_hits: list[dict] = []
    file_content_block = ""
    trimmed: list[str] = []
    budget_notes: list[str] = []

    if mode == "full" and ready_files:
        # MODO INTEGRAL: Injeta todo o conteúdo extraído de cada arquivo pronto
        file_blocks = []
        for f in ready_files:
            fname = f.get("filename", "documento")
            content = (f.get("extracted_text") or "").strip()
            file_blocks.append(f"### Arquivo: `{fname}`\n```\n{content}\n```")
        
        file_content_block = (
            "\n\n## Conteúdo Integral dos Arquivos do Projeto\n"
            "O acervo completo dos arquivos deste projeto está disponível abaixo para consulta direta:\n\n"
            + "\n\n---\n\n".join(file_blocks)
        )
    elif mode == "rag" and ready_files:
        # MODO RECUPERAÇÃO (RAG): Busca vetorial híbrida enriquecida
        top_k = project.get("retrieval_top_k") or DEFAULT_TOP_K
        threshold = project.get("retrieval_threshold") or DEFAULT_RETRIEVAL_THRESHOLD

        # Enriquece a query com título e descrição do projeto para maior precisão
        p_name = project.get("name") or ""
        p_desc = project.get("description") or ""
        enriched_query = query or ""
        if p_name or p_desc:
            enriched_query = f"{p_name}: {p_desc} — {query}".strip()

        try:
            file_hits = await search_file_chunks(
                project_id,
                enriched_query,
                top_k=top_k,
                threshold=threshold,
                request_context=request_context,
            )
            if not file_hits and threshold > 0.28:
                file_hits = await search_file_chunks(
                    project_id,
                    enriched_query,
                    top_k=top_k,
                    threshold=max(0.28, threshold * 0.55),
                    request_context=request_context,
                )
        except Exception as e:
            logger.error("[context_assembler] RAG file retrieval error:", exc_info=e)

        # Sub-orçamento para chunks RAG
        rag_tokens_budget = min(files_budget, DEFAULT_MAX_FILE_RAG_TOKENS)
        file_hits, f_trunc = fit_chunks_to_token_budget(file_hits, rag_tokens_budget)
        if f_trunc:
            trimmed.append("files:rag_fitted")

        if file_hits:
            file_blocks = []
            for hit in file_hits:
                src_file = hit.get("filename", "arquivo")
                chunk_txt = (hit.get("chunk_text") or "").strip()
                file_blocks.append(f"[Fonte: {src_file}]\n{chunk_txt}")

            file_content_block = (
                "\n\n## Trechos Relevantes dos Arquivos do Projeto (Modo Recuperação - RAG)\n"
                "Consulte os trechos abaixo para responder à solicitação do usuário. "
                "Ao citar informações específicas destes trechos, informe a fonte correspondente no formato [Fonte: nome_do_arquivo].\n\n"
                + "\n\n---\n\n".join(file_blocks)
            )
        else:
            file_content_block = (
                "\n\n## Modo Recuperação (RAG) Ativo\n"
                "Os arquivos do projeto estão indexados. Nenhuma seção específica obteve correspondência alta com a mensagem atual, "
                "mas o acervo completo está listado no Índice acima."
            )

    # Busca de conversas irmãs (se houver query)
    if query and query.strip():
        try:
            chat_hits = await retrieve_related_chats(
                query,
                project_id,
                exclude_conversation_id=exclude_conversation_id,
                top_k=3,
                threshold=0.38,
                request_context=request_context,
            )
            chat_hits, c_trunc = fit_chunks_to_token_budget(chat_hits, DEFAULT_MAX_CHAT_RAG_TOKENS)
            if c_trunc:
                trimmed.append("chats:fitted")
        except Exception as e:
            logger.warning("[context_assembler] Related chats retrieval warning: %s", e)

    chat_content_block = ""
    if chat_hits:
        chat_content_block = "\n\n" + _format_chat_block(chat_hits)

    # 5. Montagem com Ordem Estrita de Precedência
    # 1. Instruções do Projeto
    instructions_block = (
        f"\n\n## Instruções do Projeto «{project.get('name', '')}»\n{instructions}"
        if instructions
        else ""
    )

    # 2. Memória do Projeto
    memory_block = (
        f"\n\n## Memória do Projeto\n{memory_text.strip()}"
        if memory_text and memory_text.strip()
        else ""
    )

    # 3. Manifesto de Arquivos
    manifest_block = f"\n\n{manifest_md}" if manifest_md else ""

    parts = {
        "system": base_system or BASE_SYSTEM_PROMPT,
        "instructions": instructions_block,
        "memory": memory_block,
        "manifest": manifest_block,
        "files": file_content_block,
        "related_chats": chat_content_block,
        "extra": extra_system_suffix or "",
    }

    # Aplica poda de orçamento garantindo que Instruções e Memória tenham precedência máxima
    trimmed_parts, dropped = apply_token_budget(
        parts,
        budget_tokens=available_for_context + estimate_tokens(base_system),
        drop_order=["related_chats", "files", "manifest", "memory"],
    )
    trimmed.extend(dropped)

    system_content = "".join([
        trimmed_parts["system"],
        trimmed_parts["instructions"],
        trimmed_parts["memory"],
        trimmed_parts["manifest"],
        trimmed_parts["files"],
        trimmed_parts["related_chats"],
        trimmed_parts["extra"],
    ])

    tokens_est = estimate_tokens(system_content)

    debug_info = {
        "project_id": project_id,
        "project_name": project.get("name"),
        "mode": mode,
        "safe_input_tokens": safe_total,
        "available_for_context": available_for_context,
        "total_files_tokens": total_files_tokens,
        "instructions_tokens": inst_tokens,
        "memory_tokens": mem_tokens,
        "files_count": len(project_files),
        "file_hits_count": len(file_hits),
        "chat_hits_count": len(chat_hits),
        "tokens_est": tokens_est,
        "trimmed": trimmed,
    }

    return ProjectContextResult(
        system_content=system_content,
        project_id=project_id,
        instructions_used=bool(instructions),
        memory_project_used=bool(memory_text.strip()),
        memory_global_used=False,
        file_chunks=file_hits,
        chat_chunks=chat_hits,
        tokens_est=tokens_est,
        trimmed=trimmed,
        debug=debug_info,
        budget_note=" ".join(budget_notes),
        mode=mode,
        manifest_used=bool(manifest_md),
    )
