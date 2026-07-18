"""
Projects API — CRUD, files, memory, listing.
"""

from __future__ import annotations

import os
import uuid
import hashlib
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from pydantic import BaseModel, ConfigDict, Field

from backend.auth import get_current_user
from backend.database import get_db
from backend.projects.indexer import schedule_file_index, index_project_file
from backend.projects.memory_job import maybe_synthesize_project_memory, upsert_project_memory

from backend.logging_config import get_logger
logger = get_logger(__name__)

router = APIRouter(prefix="/api/projects", tags=["projects"])

STORAGE_ROOT = Path(__file__).resolve().parent.parent / "storage" / "project_files"
STORAGE_ROOT.mkdir(parents=True, exist_ok=True)


# ── Schemas ──────────────────────────────────────────────────────────────────

class ProjectCreate(BaseModel):
    model_config = ConfigDict(protected_namespaces=())
    name: str
    description: Optional[str] = ""
    instructions: Optional[str] = ""
    model_default: Optional[str] = None


class ProjectUpdate(BaseModel):
    model_config = ConfigDict(protected_namespaces=())
    name: Optional[str] = None
    description: Optional[str] = None
    instructions: Optional[str] = None
    model_default: Optional[str] = None
    is_favorite: Optional[bool] = None
    archived: Optional[bool] = None
    retrieval_top_k: Optional[int] = Field(default=None, ge=1, le=20)
    retrieval_threshold: Optional[float] = Field(default=None, ge=0.0, le=1.0)


class ProjectMemoryPatch(BaseModel):
    summary_text: str


# ── Helpers ──────────────────────────────────────────────────────────────────

async def _get_owned_project(db, project_id: str, user_id: str):
    async with db.execute(
        """SELECT id, user_id, name, description, instructions, model_default,
                  is_favorite, archived, retrieval_top_k, retrieval_threshold,
                  created_at, updated_at
           FROM projects WHERE id = ?""",
        (project_id,),
    ) as cur:
        row = await cur.fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="Projeto não encontrado.")
    if row[1] != user_id:
        raise HTTPException(status_code=403, detail="Acesso não autorizado.")
    return row


def _project_dict(row, file_count=0, chat_count=0, memory_preview=None):
    return {
        "id": row[0],
        "name": row[2],
        "description": row[3] or "",
        "instructions": row[4] or "",
        "model_default": row[5],
        "is_favorite": bool(row[6]),
        "archived": bool(row[7]),
        "retrieval_top_k": row[8] if row[8] is not None else 6,
        "retrieval_threshold": row[9] if row[9] is not None else 0.38,
        "created_at": row[10],
        "updated_at": row[11],
        "file_count": file_count,
        "chat_count": chat_count,
        "memory_preview": memory_preview,
    }


# ── CRUD ─────────────────────────────────────────────────────────────────────

async def _migrate_project_tags(db, user_id: str) -> int:
    """
    One-shot: convert legacy conversation.project_tag groups into real projects.
    - Creates a project per distinct non-empty tag (matched by name, case-insensitive)
    - Sets conversations.project_id for those chats
    Returns number of projects created.
    """
    created = 0
    try:
        async with db.execute(
            """SELECT DISTINCT TRIM(project_tag) AS tag
               FROM conversations
               WHERE user_id = ?
                 AND project_tag IS NOT NULL
                 AND TRIM(project_tag) != ''""",
            (user_id,),
        ) as cur:
            tags = [r[0] for r in await cur.fetchall() if r[0]]
    except Exception:
        return 0

    for tag in tags:
        # Prefer exact name match; also try slug-ish forms
        async with db.execute(
            """SELECT id FROM projects
               WHERE user_id = ? AND archived = 0
                 AND (LOWER(name) = LOWER(?) OR LOWER(name) = LOWER(?))
               LIMIT 1""",
            (user_id, tag, tag.replace("-", " ")),
        ) as cur:
            existing = await cur.fetchone()

        if existing:
            project_id = existing[0]
        else:
            project_id = str(uuid.uuid4())
            # Humanize slug: nicolas stays nicolas; fix-servicos → Fix Servicos-ish
            display = tag.replace("-", " ").strip()
            if display:
                display = display[:1].upper() + display[1:]
            await db.execute(
                """INSERT INTO projects (id, user_id, name, description)
                   VALUES (?, ?, ?, ?)""",
                (project_id, user_id, display or tag, f"Migrado da tag «{tag}»"),
            )
            await db.execute(
                """INSERT INTO project_memory (id, project_id, summary_text)
                   VALUES (?, ?, '')""",
                (str(uuid.uuid4()), project_id),
            )
            created += 1

        await db.execute(
            """UPDATE conversations
               SET project_id = ?
               WHERE user_id = ?
                 AND project_id IS NULL
                 AND project_tag IS NOT NULL
                 AND TRIM(project_tag) = ?""",
            (project_id, user_id, tag),
        )

    if tags:
        await db.commit()
    return created


@router.get("")
async def list_projects(
    sort: str = "updated",  # updated | name | created
    q: Optional[str] = None,
    include_archived: bool = False,
    current_user: dict = Depends(get_current_user),
):
    db = await get_db()
    try:
        # Promote legacy tag-based groups into first-class projects
        try:
            await _migrate_project_tags(db, current_user["id"])
        except Exception as e:
            logger.info("[projects] tag migration skipped: %s", e)

        order = {
            "name": "p.name COLLATE NOCASE ASC",
            "created": "p.created_at DESC",
            "updated": "p.updated_at DESC",
        }.get(sort, "p.updated_at DESC")

        sql = f"""
            SELECT p.id, p.user_id, p.name, p.description, p.instructions, p.model_default,
                   p.is_favorite, p.archived, p.retrieval_top_k, p.retrieval_threshold,
                   p.created_at, p.updated_at,
                   (SELECT COUNT(*) FROM project_files pf WHERE pf.project_id = p.id) AS file_count,
                   (SELECT COUNT(*) FROM conversations c WHERE c.project_id = p.id) AS chat_count,
                   (SELECT substr(pm.summary_text, 1, 200) FROM project_memory pm WHERE pm.project_id = p.id) AS mem
            FROM projects p
            WHERE p.user_id = ?
        """
        params: list = [current_user["id"]]
        if not include_archived:
            sql += " AND p.archived = 0"
        if q and q.strip():
            sql += " AND (p.name LIKE ? OR p.description LIKE ?)"
            like = f"%{q.strip()}%"
            params.extend([like, like])
        sql += f" ORDER BY p.is_favorite DESC, {order}"

        async with db.execute(sql, params) as cur:
            rows = await cur.fetchall()
        return [
            {
                **_project_dict(r, file_count=r[12], chat_count=r[13], memory_preview=r[14]),
            }
            for r in rows
        ]
    finally:
        await db.close()


@router.post("")
async def create_project(body: ProjectCreate, current_user: dict = Depends(get_current_user)):
    name = (body.name or "").strip()
    if not name:
        raise HTTPException(status_code=400, detail="Nome do projeto é obrigatório.")
    project_id = str(uuid.uuid4())
    db = await get_db()
    try:
        await db.execute(
            """INSERT INTO projects
               (id, user_id, name, description, instructions, model_default)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (
                project_id,
                current_user["id"],
                name,
                (body.description or "").strip(),
                (body.instructions or "").strip(),
                body.model_default,
            ),
        )
        # Empty memory row ready for editing
        await db.execute(
            """INSERT INTO project_memory (id, project_id, summary_text)
               VALUES (?, ?, '')""",
            (str(uuid.uuid4()), project_id),
        )
        await db.commit()
        row = await _get_owned_project(db, project_id, current_user["id"])
        return _project_dict(row)
    finally:
        await db.close()


@router.get("/{project_id}")
async def get_project(project_id: str, current_user: dict = Depends(get_current_user)):
    db = await get_db()
    try:
        row = await _get_owned_project(db, project_id, current_user["id"])
        async with db.execute(
            "SELECT COUNT(*) FROM project_files WHERE project_id = ?", (project_id,)
        ) as cur:
            file_count = (await cur.fetchone())[0]
        async with db.execute(
            "SELECT COUNT(*) FROM conversations WHERE project_id = ?", (project_id,)
        ) as cur:
            chat_count = (await cur.fetchone())[0]
        async with db.execute(
            "SELECT summary_text, last_synthesized_at FROM project_memory WHERE project_id = ?",
            (project_id,),
        ) as cur:
            mem = await cur.fetchone()
        data = _project_dict(row, file_count=file_count, chat_count=chat_count)
        data["memory"] = {
            "summary_text": mem[0] if mem else "",
            "last_synthesized_at": mem[1] if mem else None,
            "scope_badge": "Apenas você",
        }
        return data
    finally:
        await db.close()


@router.patch("/{project_id}")
async def update_project(
    project_id: str,
    body: ProjectUpdate,
    current_user: dict = Depends(get_current_user),
):
    db = await get_db()
    try:
        await _get_owned_project(db, project_id, current_user["id"])
        fields = []
        params = []
        mapping = {
            "name": body.name,
            "description": body.description,
            "instructions": body.instructions,
            "model_default": body.model_default,
            "retrieval_top_k": body.retrieval_top_k,
            "retrieval_threshold": body.retrieval_threshold,
        }
        for col, val in mapping.items():
            if val is not None:
                if col == "name" and not str(val).strip():
                    raise HTTPException(status_code=400, detail="Nome não pode ser vazio.")
                fields.append(f"{col} = ?")
                params.append(val.strip() if isinstance(val, str) else val)
        if body.is_favorite is not None:
            fields.append("is_favorite = ?")
            params.append(1 if body.is_favorite else 0)
        if body.archived is not None:
            fields.append("archived = ?")
            params.append(1 if body.archived else 0)
        if not fields:
            raise HTTPException(status_code=400, detail="Nada para atualizar.")
        fields.append("updated_at = datetime('now')")
        params.append(project_id)
        await db.execute(
            f"UPDATE projects SET {', '.join(fields)} WHERE id = ?",
            params,
        )
        await db.commit()
        row = await _get_owned_project(db, project_id, current_user["id"])
        return _project_dict(row)
    finally:
        await db.close()


@router.delete("/{project_id}")
async def delete_project(project_id: str, current_user: dict = Depends(get_current_user)):
    db = await get_db()
    try:
        await _get_owned_project(db, project_id, current_user["id"])
        # Collect file paths for cleanup
        async with db.execute(
            "SELECT raw_path FROM project_files WHERE project_id = ?", (project_id,)
        ) as cur:
            paths = [r[0] for r in await cur.fetchall() if r[0]]
        # Detach conversations (keep chats as avulsos)
        await db.execute(
            "UPDATE conversations SET project_id = NULL WHERE project_id = ?",
            (project_id,),
        )
        await db.execute("DELETE FROM projects WHERE id = ?", (project_id,))
        await db.commit()
        for p in paths:
            try:
                fp = Path(p)
                if not fp.is_absolute():
                    fp = Path(__file__).resolve().parent.parent / p
                if fp.exists():
                    fp.unlink()
            except Exception:
                pass
        return {"ok": True}
    finally:
        await db.close()


# ── Memory ───────────────────────────────────────────────────────────────────

@router.patch("/{project_id}/memory")
async def patch_project_memory(
    project_id: str,
    body: ProjectMemoryPatch,
    current_user: dict = Depends(get_current_user),
):
    db = await get_db()
    try:
        await _get_owned_project(db, project_id, current_user["id"])
        await upsert_project_memory(project_id, body.summary_text or "")
        await db.execute(
            "UPDATE projects SET updated_at = datetime('now') WHERE id = ?",
            (project_id,),
        )
        await db.commit()
        return {
            "ok": True,
            "summary_text": body.summary_text or "",
            "scope_badge": "Apenas você",
        }
    finally:
        await db.close()


@router.post("/{project_id}/memory/synthesize")
async def synthesize_memory(project_id: str, current_user: dict = Depends(get_current_user)):
    db = await get_db()
    try:
        await _get_owned_project(db, project_id, current_user["id"])
    finally:
        await db.close()
    summary = await maybe_synthesize_project_memory(project_id, force=True)
    return {"ok": True, "summary_text": summary or ""}


# ── Files ────────────────────────────────────────────────────────────────────

@router.get("/{project_id}/files")
async def list_project_files(project_id: str, current_user: dict = Depends(get_current_user)):
    db = await get_db()
    try:
        await _get_owned_project(db, project_id, current_user["id"])
        async with db.execute(
            """SELECT id, filename, mime_type, size_bytes, index_status, index_error,
                      indexed_at, created_at
               FROM project_files WHERE project_id = ?
               ORDER BY created_at DESC""",
            (project_id,),
        ) as cur:
            rows = await cur.fetchall()
        return [
            {
                "id": r[0],
                "filename": r[1],
                "mime_type": r[2],
                "size_bytes": r[3],
                "index_status": r[4],
                "index_error": r[5],
                "indexed_at": r[6],
                "created_at": r[7],
            }
            for r in rows
        ]
    finally:
        await db.close()


@router.post("/{project_id}/files")
async def upload_project_file(
    project_id: str,
    file: UploadFile = File(...),
    current_user: dict = Depends(get_current_user),
):
    db = await get_db()
    try:
        await _get_owned_project(db, project_id, current_user["id"])
        contents = await file.read()
        size_bytes = len(contents)
        if size_bytes == 0:
            raise HTTPException(status_code=400, detail="Arquivo vazio.")
        if size_bytes > 25 * 1024 * 1024:
            raise HTTPException(status_code=400, detail="Arquivo excede 25MB.")

        file_id = f"pf_{uuid.uuid4().hex}"
        safe_name = os.path.basename(file.filename or "arquivo.txt")
        dest_dir = STORAGE_ROOT / project_id
        dest_dir.mkdir(parents=True, exist_ok=True)
        dest_path = dest_dir / f"{file_id}_{safe_name}"
        dest_path.write_bytes(contents)

        mime = file.content_type or "application/octet-stream"
        extracted = None
        try:
            from backend.attachments.extractors import extract_text


            extracted = await extract_text(str(dest_path), mime)
        except Exception as e:
            # Keep file; indexing will mark error if no text
            logger.warning("[projects] extract warning:", exc_info=e)

        rel_path = str(dest_path.relative_to(Path(__file__).resolve().parent.parent))

        await db.execute(
            """INSERT INTO project_files
               (id, project_id, filename, mime_type, raw_path, extracted_text,
                size_bytes, index_status)
               VALUES (?, ?, ?, ?, ?, ?, ?, 'pending')""",
            (
                file_id,
                project_id,
                safe_name,
                mime,
                rel_path.replace("\\", "/"),
                extracted,
                size_bytes,
            ),
        )
        await db.execute(
            "UPDATE projects SET updated_at = datetime('now') WHERE id = ?",
            (project_id,),
        )
        await db.commit()
    finally:
        await db.close()

    # Background indexing
    schedule_file_index(file_id)

    return {
        "id": file_id,
        "filename": safe_name,
        "mime_type": mime,
        "size_bytes": size_bytes,
        "index_status": "pending",
    }


@router.post("/{project_id}/files/{file_id}/reindex")
async def reindex_file(
    project_id: str,
    file_id: str,
    current_user: dict = Depends(get_current_user),
):
    db = await get_db()
    try:
        await _get_owned_project(db, project_id, current_user["id"])
        async with db.execute(
            "SELECT id FROM project_files WHERE id = ? AND project_id = ?",
            (file_id, project_id),
        ) as cur:
            if not await cur.fetchone():
                raise HTTPException(status_code=404, detail="Arquivo não encontrado.")
    finally:
        await db.close()
    result = await index_project_file(file_id)
    return result


@router.post("/{project_id}/files/reindex-all")
async def reindex_all_files(
    project_id: str,
    current_user: dict = Depends(get_current_user),
):
    """
    Re-chunk + re-embed every file in the project (e.g. after chunker improvements).
    Runs sequentially to avoid saturating the embedder.
    """
    db = await get_db()
    try:
        await _get_owned_project(db, project_id, current_user["id"])
        async with db.execute(
            "SELECT id, filename FROM project_files WHERE project_id = ? ORDER BY created_at ASC",
            (project_id,),
        ) as cur:
            rows = await cur.fetchall()
    finally:
        await db.close()

    results = []
    for file_id, filename in rows:
        res = await index_project_file(file_id)
        results.append({"id": file_id, "filename": filename, **res})

    ok = sum(1 for r in results if r.get("ok"))
    return {"ok": ok == len(results), "total": len(results), "indexed": ok, "results": results}


@router.delete("/{project_id}/files/{file_id}")
async def delete_project_file(
    project_id: str,
    file_id: str,
    current_user: dict = Depends(get_current_user),
):
    db = await get_db()
    try:
        await _get_owned_project(db, project_id, current_user["id"])
        async with db.execute(
            "SELECT raw_path FROM project_files WHERE id = ? AND project_id = ?",
            (file_id, project_id),
        ) as cur:
            row = await cur.fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Arquivo não encontrado.")
        await db.execute("DELETE FROM project_files WHERE id = ?", (file_id,))
        await db.execute(
            "UPDATE projects SET updated_at = datetime('now') WHERE id = ?",
            (project_id,),
        )
        await db.commit()
        if row[0]:
            try:
                fp = Path(row[0])
                if not fp.is_absolute():
                    fp = Path(__file__).resolve().parent.parent / row[0]
                if fp.exists():
                    fp.unlink()
            except Exception:
                pass
        return {"ok": True}
    finally:
        await db.close()


# ── Chats inside project ─────────────────────────────────────────────────────

@router.get("/{project_id}/chats")
async def list_project_chats(project_id: str, current_user: dict = Depends(get_current_user)):
    db = await get_db()
    try:
        await _get_owned_project(db, project_id, current_user["id"])
        async with db.execute(
            """SELECT c.id, c.title, c.model_id, c.provider_id, c.created_at, c.updated_at,
                      COUNT(m.id) as message_count
               FROM conversations c
               LEFT JOIN messages m ON m.conversation_id = c.id
               WHERE c.project_id = ? AND c.user_id = ?
               GROUP BY c.id
               ORDER BY c.updated_at DESC""",
            (project_id, current_user["id"]),
        ) as cur:
            rows = await cur.fetchall()
        return [
            {
                "id": r[0],
                "title": r[1],
                "model_id": r[2],
                "provider_id": r[3],
                "created_at": r[4],
                "updated_at": r[5],
                "message_count": r[6],
            }
            for r in rows
        ]
    finally:
        await db.close()


class ProjectChatCreate(BaseModel):
    model_config = ConfigDict(protected_namespaces=())
    title: Optional[str] = None
    model_id: Optional[str] = None
    provider_id: Optional[str] = None


@router.post("/{project_id}/chats")
async def create_project_chat(
    project_id: str,
    body: Optional[ProjectChatCreate] = None,
    current_user: dict = Depends(get_current_user),
):
    body = body or ProjectChatCreate()
    db = await get_db()
    try:
        await _get_owned_project(db, project_id, current_user["id"])
        conv_id = str(uuid.uuid4())
        title = (body.title or "Nova conversa").strip() or "Nova conversa"
        await db.execute(
            """INSERT INTO conversations
               (id, user_id, title, model_id, provider_id, project_id)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (
                conv_id,
                current_user["id"],
                title,
                body.model_id,
                body.provider_id,
                project_id,
            ),
        )
        await db.execute(
            "UPDATE projects SET updated_at = datetime('now') WHERE id = ?",
            (project_id,),
        )
        await db.commit()
        return {"id": conv_id, "project_id": project_id, "title": title}
    finally:
        await db.close()
