from typing import Optional
from fastapi import APIRouter, HTTPException, Depends
from backend.database import get_db
from backend.models import ConversationUpdate
from backend.auth import get_current_user

router = APIRouter(prefix="/api/conversations", tags=["conversations"])


@router.get("")
async def list_conversations(
    search: Optional[str] = None,
    filter: Optional[str] = None,
    page: int = 1,
    limit: int = 100,
    current_user: dict = Depends(get_current_user)
):
    db = await get_db()
    try:
        query = """
            SELECT c.id, c.title, c.model_id, c.provider_id,
                      c.created_at, c.updated_at,
                      COUNT(m.id) as message_count,
                      c.is_favorite, c.favorited_at,
                      c.project_tag,
                      c.project_id
               FROM conversations c
               LEFT JOIN messages m ON m.conversation_id = c.id
               WHERE c.user_id = ?
        """
        params = [current_user["id"]]

        if search:
            query += " AND c.title LIKE ?"
            params.append(f"%{search}%")

        if filter == "favorites":
            query += " AND c.is_favorite = 1"

        query += " GROUP BY c.id"

        if filter == "favorites":
            query += " ORDER BY c.favorited_at DESC"
        else:
            query += " ORDER BY c.updated_at DESC"

        if limit > 0:
            offset = (page - 1) * limit
            query += " LIMIT ? OFFSET ?"
            params.append(limit)
            params.append(offset)

        async with db.execute(query, params) as cur:
            rows = await cur.fetchall()
        return [
            {
                "id": r[0], "title": r[1], "model_id": r[2],
                "provider_id": r[3], "created_at": r[4],
                "updated_at": r[5], "message_count": r[6],
                "is_favorite": bool(r[7]),
                "favorited_at": r[8],
                "project_tag": r[9] if len(r) > 9 else None,
                "project_id": r[10] if len(r) > 10 else None,
            }
            for r in rows
        ]
    finally:
        await db.close()


@router.get("/{conversation_id}")
async def get_conversation(conversation_id: str, current_user: dict = Depends(get_current_user)):
    db = await get_db()
    try:
        async with db.execute(
            "SELECT id, title, model_id, provider_id, created_at, user_id, is_favorite, favorited_at, project_tag, project_id FROM conversations WHERE id = ?",
            (conversation_id,),
        ) as cur:
            conv = await cur.fetchone()
        if not conv:
            raise HTTPException(status_code=404, detail="Conversa não encontrada.")
        
        # Verifica propriedade da conversa
        if conv[5] != current_user["id"]:
            raise HTTPException(status_code=403, detail="Acesso não autorizado a esta conversa.")

        async with db.execute(
            """SELECT m.id, m.role, m.content, m.model_id, m.created_at, mod.display_name, p.name, m.provider, m.relay_used, m.relay_model
               FROM messages m
               LEFT JOIN models mod ON m.model_id = mod.id
               LEFT JOIN providers p ON mod.provider_id = p.id
               WHERE m.conversation_id = ?
               ORDER BY m.created_at ASC""",
            (conversation_id,),
        ) as cur:
            messages = await cur.fetchall()

        # Puxa todos os artifacts desta conversa para associar com cada mensagem
        async with db.execute(
            "SELECT id, msg_id, type, title FROM artifacts WHERE conv_id = ?",
            (conversation_id,),
        ) as cur:
            art_rows = await cur.fetchall()

        msg_artifacts = {}
        for row in art_rows:
            a_id, m_id, a_type, a_title = row
            if m_id:
                if m_id not in msg_artifacts:
                    msg_artifacts[m_id] = []
                msg_artifacts[m_id].append({
                    "id": a_id,
                    "type": a_type,
                    "title": a_title
                })

        # Puxa todos os attachments desta conversa para associar com cada mensagem
        async with db.execute(
            """SELECT id, message_id, filename, mime_type, file_type, size_bytes, thumbnail_path, storage_path, extracted_text 
               FROM attachments 
               WHERE message_id IN (SELECT id FROM messages WHERE conversation_id = ?)""",
            (conversation_id,),
        ) as cur:
            att_rows = await cur.fetchall()

        msg_attachments = {}
        for row in att_rows:
            a_id, m_id, filename, mime_type, file_type, size_bytes, thumb_path, storage_path, ext_text = row
            if m_id:
                if m_id not in msg_attachments:
                    msg_attachments[m_id] = []
                
                thumb_url = f"/attachments/{thumb_path}" if thumb_path else None
                file_url = f"/attachments/{storage_path}"
                
                msg_attachments[m_id].append({
                    "id": a_id,
                    "filename": filename,
                    "mime_type": mime_type,
                    "file_type": file_type,
                    "size_bytes": size_bytes,
                    "thumbnail_url": thumb_url,
                    "file_url": file_url,
                    "extracted_text": ext_text
                })

        return {
            "id": conv[0], "title": conv[1], "model_id": conv[2],
            "provider_id": conv[3], "created_at": conv[4],
            "is_favorite": bool(conv[6]), "favorited_at": conv[7],
            "project_tag": conv[8] if len(conv) > 8 else None,
            "project_id": conv[9] if len(conv) > 9 else None,
            "messages": [
                {
                    "id": m[0],
                    "role": m[1],
                    "content": m[2],
                    "model_id": m[3],
                    "created_at": m[4],
                    "model_display_name": m[5] or (m[3].split('/')[-1] if m[3] else None),
                    "provider": m[6] or m[7] or (m[3].split('/')[0] if m[3] and '/' in m[3] else None),
                    "relay_used": bool(m[8]),
                    "relay_model": m[9],
                    "artifacts": msg_artifacts.get(m[0], []),
                    "attachments": msg_attachments.get(m[0], [])
                }
                for m in messages
            ],
        }
    finally:
        await db.close()


@router.patch("/{conversation_id}")
async def update_conversation(conversation_id: str, body: ConversationUpdate, current_user: dict = Depends(get_current_user)):
    db = await get_db()
    try:
        async with db.execute("SELECT user_id FROM conversations WHERE id = ?", (conversation_id,)) as cur:
            row = await cur.fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Conversa não encontrada.")
        if row[0] != current_user["id"]:
            raise HTTPException(status_code=403, detail="Acesso não autorizado.")

        fields = body.model_dump(exclude_unset=True)

        if "title" in fields and body.title is not None:
            await db.execute(
                "UPDATE conversations SET title = ?, updated_at = datetime('now') WHERE id = ?",
                (body.title, conversation_id),
            )
        if "project_tag" in fields:
            tag = (body.project_tag or "").strip() or None
            await db.execute(
                "UPDATE conversations SET project_tag = ?, updated_at = datetime('now') WHERE id = ?",
                (tag, conversation_id),
            )
        if "project_id" in fields:
            # null / "" detaches chat from project
            raw = body.project_id if isinstance(body.project_id, str) else ""
            pid = raw.strip() or None
            if pid:
                async with db.execute(
                    "SELECT id FROM projects WHERE id = ? AND user_id = ?",
                    (pid, current_user["id"]),
                ) as cur:
                    if not await cur.fetchone():
                        raise HTTPException(status_code=404, detail="Projeto não encontrado.")
            await db.execute(
                "UPDATE conversations SET project_id = ?, updated_at = datetime('now') WHERE id = ?",
                (pid, conversation_id),
            )
        await db.commit()
        return {
            "ok": True,
            "project_tag": fields.get("project_tag", body.project_tag),
            "project_id": fields.get("project_id", body.project_id),
        }
    finally:
        await db.close()


@router.delete("/{conversation_id}")
async def delete_conversation(conversation_id: str, current_user: dict = Depends(get_current_user)):
    db = await get_db()
    try:
        async with db.execute("SELECT user_id FROM conversations WHERE id = ?", (conversation_id,)) as cur:
            row = await cur.fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Conversa não encontrada.")
        if row[0] != current_user["id"]:
            raise HTTPException(status_code=403, detail="Acesso não autorizado.")

        await db.execute("DELETE FROM conversations WHERE id = ?", (conversation_id,))
        await db.commit()
        return {"ok": True}
    finally:
        await db.close()


@router.patch("/{conversation_id}/favorite")
async def favorite_conversation(conversation_id: str, current_user: dict = Depends(get_current_user)):
    db = await get_db()
    try:
        async with db.execute("SELECT user_id, is_favorite FROM conversations WHERE id = ?", (conversation_id,)) as cur:
            row = await cur.fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Conversa não encontrada.")
        if row[0] != current_user["id"]:
            raise HTTPException(status_code=403, detail="Acesso não autorizado.")

        new_favorite = 0 if row[1] else 1
        if new_favorite:
            await db.execute(
                "UPDATE conversations SET is_favorite = 1, favorited_at = datetime('now') WHERE id = ?",
                (conversation_id,),
            )
        else:
            await db.execute(
                "UPDATE conversations SET is_favorite = 0, favorited_at = NULL WHERE id = ?",
                (conversation_id,),
            )
        await db.commit()
        return {"ok": True, "is_favorite": bool(new_favorite)}
    finally:
        await db.close()


@router.patch("/{conversation_id}/rename")
async def rename_conversation_route(conversation_id: str, body: ConversationUpdate, current_user: dict = Depends(get_current_user)):
    if not body.title or not body.title.strip():
        raise HTTPException(status_code=400, detail="Título obrigatório.")
    if len(body.title) > 100:
        raise HTTPException(status_code=400, detail="O título não pode ter mais de 100 caracteres.")
    db = await get_db()
    try:
        async with db.execute("SELECT user_id FROM conversations WHERE id = ?", (conversation_id,)) as cur:
            row = await cur.fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Conversa não encontrada.")
        if row[0] != current_user["id"]:
            raise HTTPException(status_code=403, detail="Acesso não autorizado.")

        await db.execute(
            "UPDATE conversations SET title = ? WHERE id = ?",
            (body.title, conversation_id),
        )
        await db.commit()
        return {"ok": True}
    finally:
        await db.close()
