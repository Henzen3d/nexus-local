"""
Background synthesis of project_memory from recent chat_chunks.
Trigger: after N new chat turns, or lightweight periodic cron.
"""

from __future__ import annotations

import json
import uuid
from typing import Optional

import aiosqlite

from backend.database import DB_PATH

from backend.logging_config import get_logger
logger = get_logger(__name__)

# Synthesize after this many new chat chunks since last run
SYNTHESIS_CHUNK_THRESHOLD = 8
MAX_CHUNKS_FOR_SYNTHESIS = 40
SUMMARY_MAX_CHARS = 2500


async def count_chat_chunks(project_id: str) -> int:
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute(
            "SELECT COUNT(*) FROM chat_chunks WHERE project_id = ?", (project_id,)
        ) as cur:
            row = await cur.fetchone()
            return int(row[0] or 0)


async def get_recent_chat_chunks(project_id: str, limit: int = MAX_CHUNKS_FOR_SYNTHESIS) -> list[dict]:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            """SELECT id, chunk_text, created_at FROM chat_chunks
               WHERE project_id = ?
               ORDER BY created_at DESC LIMIT ?""",
            (project_id, limit),
        ) as cur:
            rows = await cur.fetchall()
            return [dict(r) for r in rows]


def _heuristic_summary(
    chunks: list[dict],
    existing: Optional[str] = None,
    instructions: str = "",
    filenames: Optional[list[str]] = None,
) -> str:
    """
    Síntese Consciente do Projeto:
    Lê as conversas levando em conta Instruções e nomes dos Arquivos,
    extraindo fatos, decisões e preferências sem repetir as instruções.
    """
    bullets: list[str] = []
    inst_lower = (instructions or "").lower()
    files_str = ", ".join(filenames or [])

    for c in reversed(chunks):  # ordem cronológica
        text = (c.get("chunk_text") or "").strip()
        if not text:
            continue
        
        lines = [l.strip() for l in text.split("\n") if l.strip()]
        for line in lines:
            # Limpa prefixos
            clean_line = line
            for pref in ("pergunta:", "resposta:", "user:", "assistant:"):
                if clean_line.lower().startswith(pref):
                    clean_line = clean_line[len(pref):].strip()

            clean_line = " ".join(clean_line.split())
            if not clean_line or len(clean_line) < 15:
                continue

            # Evita repetir frases que já estão nas instruções do projeto
            if len(clean_line) > 25 and clean_line.lower() in inst_lower:
                continue

            if len(clean_line) > 200:
                clean_line = clean_line[:197] + "…"

            bullet_text = f"• {clean_line}"
            if bullet_text not in bullets:
                bullets.append(bullet_text)

            if len(bullets) >= 15:
                break
        if len(bullets) >= 15:
            break

    body = "\n".join(bullets) if bullets else "Ainda não há decisões ou fatos suficientes registrados nas conversas."
    header = "Resumo automático do projeto (atualizado a partir das conversas recentes):\n"
    if files_str:
        header = f"Resumo automático do projeto (acervo: {files_str}):\n"

    if existing and existing.strip() and "Resumo automático" not in existing[:80]:
        combined = f"{existing.strip()}\n\n---\n{header}{body}"
    else:
        combined = header + body

    if len(combined) > SUMMARY_MAX_CHARS:
        combined = combined[: SUMMARY_MAX_CHARS - 1] + "…"
    return combined


async def upsert_project_memory(
    project_id: str,
    summary_text: str,
    source_chat_ids: Optional[list[str]] = None,
) -> str:
    token_count = max(1, len(summary_text) // 4) if summary_text.strip() else 0
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute(
            "SELECT id FROM project_memory WHERE project_id = ?", (project_id,)
        ) as cur:
            row = await cur.fetchone()
        ids_json = json.dumps(source_chat_ids or [])
        if row:
            mem_id = row[0]
            await db.execute(
                """UPDATE project_memory
                   SET summary_text = ?, token_count = ?, last_synthesized_at = datetime('now'),
                       source_chat_ids = ?
                   WHERE id = ?""",
                (summary_text, token_count, ids_json, mem_id),
            )
        else:
            mem_id = str(uuid.uuid4())
            await db.execute(
                """INSERT INTO project_memory
                   (id, project_id, summary_text, token_count, last_synthesized_at, source_chat_ids)
                   VALUES (?, ?, ?, ?, datetime('now'), ?)""",
                (mem_id, project_id, summary_text, token_count, ids_json),
            )
        await db.commit()
        return mem_id


async def maybe_synthesize_project_memory(project_id: str, force: bool = False) -> Optional[str]:
    """
    Executa a síntese de memória do projeto.
    Se force=True ou se houver conversas acumuladas, sintetiza a partir de chat_chunks
    e do histórico real de messages de conversas do projeto.
    """
    if not project_id:
        return None

    instructions = ""
    filenames = []
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT summary_text, last_synthesized_at, source_chat_ids FROM project_memory WHERE project_id = ?",
            (project_id,),
        ) as cur:
            mem = await cur.fetchone()

        # Instruções
        async with db.execute("SELECT instructions FROM projects WHERE id = ?", (project_id,)) as cur:
            p_row = await cur.fetchone()
            if p_row and p_row["instructions"]:
                instructions = p_row["instructions"]

        # Arquivos
        async with db.execute("SELECT filename FROM project_files WHERE project_id = ?", (project_id,)) as cur:
            f_rows = await cur.fetchall()
            filenames = [r["filename"] for r in f_rows if r["filename"]]

    # 1. Busca chunks em chat_chunks
    chunks = await get_recent_chat_chunks(project_id)

    # 2. Se tiver poucos chunks ou nenhum (ex: chats criados antes da indexação ou sem chunks),
    # consulta diretamente a tabela messages das conversas deste project_id!
    if len(chunks) < 5:
        async with aiosqlite.connect(DB_PATH) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute(
                """SELECT c.id as conv_id, m.id as msg_id, m.role, m.content, m.created_at
                   FROM conversations c
                   JOIN messages m ON m.conversation_id = c.id
                   WHERE c.project_id = ? AND m.content IS NOT NULL AND TRIM(m.content) != ''
                   ORDER BY m.created_at ASC LIMIT 40""",
                (project_id,),
            ) as cur:
                msg_rows = await cur.fetchall()

            # Agrupa pares pergunta-resposta
            current_q = ""
            for r in msg_rows:
                role = r["role"]
                content = (r["content"] or "").strip()
                if role == "user":
                    current_q = content
                elif role == "assistant" and current_q:
                    pair = f"Pergunta: {current_q}\nResposta: {content}"
                    chunks.append({
                        "id": f"msg-{r['msg_id']}",
                        "chunk_text": pair[:2500],
                        "created_at": r["created_at"],
                    })
                    current_q = ""

    if not chunks and not force:
        return None

    n = len(chunks)
    if not force and n < SYNTHESIS_CHUNK_THRESHOLD and mem and mem["summary_text"]:
        return None

    existing = mem["summary_text"] if mem else None
    summary = _heuristic_summary(
        chunks,
        existing=existing if force else None,
        instructions=instructions,
        filenames=filenames,
    )
    if mem and not force and existing and "Resumo automático" not in (existing or "")[:100]:
        summary = _heuristic_summary(
            chunks,
            existing=existing,
            instructions=instructions,
            filenames=filenames,
        )

    source_ids = [c["id"] for c in chunks]
    await upsert_project_memory(project_id, summary, source_ids)
    return summary
    return summary


async def ingest_external_findings(
    project_id: str,
    findings: list[str],
    source_label: str = "external",
) -> Optional[str]:
    """
    Proactive cross-source retrieval hook (plan §5).
    When external connectors (web search, free-registry notes, etc.) surface
    durable facts, append them into project_memory without replacing manual text.
    No-op if findings is empty — safe to call when sources are not connected.
    """
    clean = [f.strip() for f in (findings or []) if f and str(f).strip()]
    if not project_id or not clean:
        return None

    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute(
            "SELECT summary_text FROM project_memory WHERE project_id = ?",
            (project_id,),
        ) as cur:
            row = await cur.fetchone()
    existing = (row[0] if row else "") or ""

    block_lines = [f"• [{source_label}] {f}" for f in clean[:10]]
    block = "\n".join(block_lines)
    if block in existing:
        return existing

    header = "\n\n## Achados de fontes externas\n"
    if "## Achados de fontes externas" in existing:
        combined = existing.rstrip() + "\n" + block
    else:
        combined = (existing.rstrip() + header + block).strip()
    if len(combined) > SUMMARY_MAX_CHARS:
        combined = combined[: SUMMARY_MAX_CHARS - 1] + "…"
    await upsert_project_memory(project_id, combined)
    return combined


async def synthesize_all_active_projects() -> int:
    """Periodic job: walk projects with recent chat activity."""
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute(
            """SELECT DISTINCT project_id FROM chat_chunks
               WHERE project_id IS NOT NULL
               ORDER BY created_at DESC LIMIT 50"""
        ) as cur:
            rows = await cur.fetchall()
    count = 0
    for (pid,) in rows:
        try:
            out = await maybe_synthesize_project_memory(pid)
            if out:
                count += 1
        except Exception as e:
            logger.error("[project_memory] synthesis failed for %s:", pid, exc_info=e)
    return count
