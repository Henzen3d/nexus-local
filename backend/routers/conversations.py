import json
from typing import Optional
import aiosqlite
from fastapi import APIRouter, HTTPException, Depends
from backend.database import get_db
from backend.models import ConversationUpdate
from backend.auth import get_current_user
from backend.attachments.signing import attachment_url
from backend.orchestration.build_context import clean_model_display_name

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
                      c.project_id,
                      c.origin_insight_id
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
                # F3.3.4: conversa iniciada pelo assistente proativo ("Me conta aqui")
                "origin_insight_id": r[11] if len(r) > 11 else None,
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
            "SELECT id, title, model_id, provider_id, created_at, user_id, is_favorite, favorited_at, project_tag, project_id, origin_insight_id FROM conversations WHERE id = ?",
            (conversation_id,),
        ) as cur:
            conv = await cur.fetchone()
        if not conv:
            raise HTTPException(status_code=404, detail="Conversa não encontrada.")
        
        # Verifica propriedade da conversa
        if conv[5] != current_user["id"]:
            raise HTTPException(status_code=403, detail="Acesso não autorizado a esta conversa.")

        async with db.execute(
            """SELECT m.id, m.role, m.content, m.model_id, m.created_at, mod.display_name, p.name, m.provider, m.relay_used, m.relay_model,
                      m.web_search_used, m.web_search_query, m.web_search_sources, m.process_steps,
                      COALESCE(m.kind, 'normal'), m.proactive_insight_id, m.fusion_metadata
               FROM messages m
               LEFT JOIN models mod ON m.model_id = mod.id
               LEFT JOIN providers p ON mod.provider_id = p.id
               WHERE m.conversation_id = ?
               ORDER BY m.created_at ASC""",
            (conversation_id,),
        ) as cur:
            messages = await cur.fetchall()

        # Insights proativos das bolhas desta conversa (F2.6.3 / F3.3.2) — só do dono.
        # Inclui a 1ª mensagem de um chat iniciado por "Me conta aqui" (insight de outra conversa).
        msg_insights: dict[str, dict] = {}
        try:
            from backend.proactive.delivery import INSIGHT_COLUMNS, attach_origin_titles, insight_public_dict

            insight_ids = sorted({m[15] for m in messages if len(m) > 15 and m[15] and (m[14] or "normal") == "proactive"})
            if insight_ids:
                placeholders = ",".join("?" for _ in insight_ids)
                async with db.execute(
                    f"""SELECT {', '.join(INSIGHT_COLUMNS)} FROM proactive_insights
                        WHERE user_id = ? AND id IN ({placeholders})""",
                    (current_user["id"], *insight_ids),
                ) as cur:
                    found = [dict(zip(INSIGHT_COLUMNS, row)) for row in await cur.fetchall()]
                spawned = [i for i in found if i.get("spawned_conversation_id") == conversation_id]
                if spawned:
                    await attach_origin_titles(db, spawned)
                by_id = {i["id"]: insight_public_dict(i) for i in found}
                for m in messages:
                    if len(m) > 15 and m[15] in by_id:
                        msg_insights[m[0]] = by_id[m[15]]
        except Exception:
            msg_insights = {}

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
                
                thumb_url = attachment_url(thumb_path)
                file_url = attachment_url(storage_path)
                
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

        # Puxa ui_blocks desta conversa se houver
        msg_ui_blocks = {}
        try:
            async with db.execute(
                """SELECT message_id, payload 
                   FROM message_ui_blocks 
                   WHERE message_id IN (SELECT id FROM messages WHERE conversation_id = ?)""",
                (conversation_id,),
            ) as cur:
                ui_rows = await cur.fetchall()
            for r_mid, r_payload in ui_rows:
                try:
                    if isinstance(r_payload, str):
                        msg_ui_blocks[r_mid] = json.loads(r_payload)
                    elif isinstance(r_payload, dict):
                        msg_ui_blocks[r_mid] = r_payload
                except Exception:
                    pass
        except Exception:
            pass

        def _loads(raw):
            if not raw:
                return None
            if isinstance(raw, (list, dict)):
                return raw
            try:
                return json.loads(raw)
            except Exception:
                return None

        built = []
        pending_search = None
        for m in messages:
            item = {
                "id": m[0],
                "role": m[1],
                "content": m[2],
                "model_id": m[3],
                "created_at": m[4],
                "model_display_name": clean_model_display_name(
                    m[5] or (m[3].split('/')[-1] if m[3] else None),
                    m[6] or m[7] or (m[3].split('/')[0] if m[3] and '/' in m[3] else None)
                ),
                "provider": m[6] or m[7] or (m[3].split('/')[0] if m[3] and '/' in m[3] else None),
                "relay_used": bool(m[8]),
                "relay_model": m[9],
                "artifacts": msg_artifacts.get(m[0], []),
                "attachments": msg_attachments.get(m[0], []),
                "ui_blocks": msg_ui_blocks.get(m[0]),
                "web_search_used": bool(m[10]) if len(m) > 10 else False,
                "web_search_query": m[11] if len(m) > 11 else None,
                "web_search_sources": _loads(m[12]) if len(m) > 12 else None,
                "process_steps": _loads(m[13]) if len(m) > 13 else None,
                "kind": (m[14] if len(m) > 14 else None) or "normal",
                "proactive_insight_id": m[15] if len(m) > 15 else None,
            }
            if item["kind"] == "proactive":
                item["insight"] = msg_insights.get(item["id"])
            if item["role"] == "user" and item["web_search_used"]:
                pending_search = {
                    "web_search_used": True,
                    "web_search_query": item["web_search_query"],
                    "web_search_sources": item["web_search_sources"] or [],
                }
            elif item["role"] == "assistant" and pending_search:
                item["web_search_used"] = item["web_search_used"] or pending_search["web_search_used"]
                item["web_search_query"] = item["web_search_query"] or pending_search["web_search_query"]
                if not item["web_search_sources"]:
                    item["web_search_sources"] = pending_search["web_search_sources"]
                pending_search = None

            # Reconstrói a bolha virtual de status do Fusion para reter histórico completo após refresh
            if item["role"] == "assistant" and len(m) > 16 and m[16]:
                fdata = _loads(m[16])
                if isinstance(fdata, dict):
                    built.append({
                        "id": f"fusion-{m[0]}",
                        "role": "fusion_status",
                        "content": "",
                        "fusion_statuses": fdata.get("statuses", []),
                        "fusion_judge_model_id": fdata.get("judge_model_id"),
                        "fusion_grounding": fdata.get("grounding"),
                        "fusion_refined_prompt": fdata.get("refined_prompt"),
                        "created_at": m[4],
                    })

            built.append(item)

        return {
            "id": conv[0], "title": conv[1], "model_id": conv[2],
            "provider_id": conv[3], "created_at": conv[4],
            "is_favorite": bool(conv[6]), "favorited_at": conv[7],
            "project_tag": conv[8] if len(conv) > 8 else None,
            "project_id": conv[9] if len(conv) > 9 else None,
            "origin_insight_id": conv[10] if len(conv) > 10 else None,
            "messages": built,
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
