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


def _heuristic_summary(chunks: list[dict], existing: Optional[str] = None) -> str:
    """
    Offline-friendly summary when no LLM extractor is wired.
    Collapses recent Q/A lines into a bullet digest.
    """
    bullets: list[str] = []
    for c in reversed(chunks):  # chronological
        text = (c.get("chunk_text") or "").strip()
        if not text:
            continue
        # Prefer the question line
        line = text.split("\n")[0]
        if line.lower().startswith("pergunta:"):
            line = line[9:].strip()
        line = " ".join(line.split())
        if len(line) > 180:
            line = line[:177] + "…"
        if line and line not in bullets:
            bullets.append(f"• {line}")
        if len(bullets) >= 15:
            break

    body = "\n".join(bullets) if bullets else "Ainda não há histórico suficiente para memória."
    header = "Resumo automático do projeto (atualizado a partir das conversas recentes):\n"
    if existing and existing.strip() and "Resumo automático" not in existing[:80]:
        # Preserve manual edits as preface
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
                   SET summary_text = ?, last_synthesized_at = datetime('now'),
                       source_chat_ids = ?
                   WHERE id = ?""",
                (summary_text, ids_json, mem_id),
            )
        else:
            mem_id = str(uuid.uuid4())
            await db.execute(
                """INSERT INTO project_memory
                   (id, project_id, summary_text, last_synthesized_at, source_chat_ids)
                   VALUES (?, ?, ?, datetime('now'), ?)""",
                (mem_id, project_id, summary_text, ids_json),
            )
        await db.commit()
        return mem_id


async def maybe_synthesize_project_memory(project_id: str, force: bool = False) -> Optional[str]:
    """
    Run synthesis if enough new chunks accumulated (or force=True).
    Returns new summary text or None if skipped.
    """
    if not project_id:
        return None

    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT summary_text, last_synthesized_at, source_chat_ids FROM project_memory WHERE project_id = ?",
            (project_id,),
        ) as cur:
            mem = await cur.fetchone()

    chunks = await get_recent_chat_chunks(project_id)
    if not chunks and not force:
        return None

    n = len(chunks)
    if not force and n < SYNTHESIS_CHUNK_THRESHOLD and mem:
        return None

    existing = mem["summary_text"] if mem else None
    # If user manually edited recently and we only have few chunks, still allow force
    summary = _heuristic_summary(chunks, existing=existing if force else None)
    # When not forcing and existing looks manual (no auto header), append carefully
    if mem and not force and existing and "Resumo automático" not in (existing or "")[:100]:
        summary = _heuristic_summary(chunks, existing=existing)

    source_ids = [c["id"] for c in chunks]
    await upsert_project_memory(project_id, summary, source_ids)
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
