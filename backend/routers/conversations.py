import json
import re
import time
from typing import Optional
import aiosqlite
from fastapi import APIRouter, HTTPException, Depends, Query
from backend.database import (
    get_db,
    get_chat_turn_state,
    get_latest_incomplete_turn_for_conversation,
)
from backend.logging_config import get_logger
from backend.models import ConversationUpdate
from backend.auth import get_current_user
from backend.attachments.signing import attachment_url
from backend.orchestration.build_context import clean_model_display_name

logger = get_logger(__name__)
router = APIRouter(prefix="/api/conversations", tags=["conversations"])


def _build_match_snippet(content: str, query: str, radius: int = 45) -> str:
    """Extrai um trecho curto e seguro ao redor da primeira ocorrência encontrada na mensagem."""
    normalized = re.sub(r"\s+", " ", (content or "")).strip()
    if not normalized:
        return ""
    q = (query or "").strip().lower()
    idx = normalized.lower().find(q) if q else -1
    if idx < 0:
        return normalized[: radius * 2] + ("…" if len(normalized) > radius * 2 else "")
    start = max(0, idx - radius)
    end = min(len(normalized), idx + len(q) + radius)
    prefix = "…" if start > 0 else ""
    suffix = "…" if end < len(normalized) else ""
    return f"{prefix}{normalized[start:end]}{suffix}"


@router.get("")
async def list_conversations(
    search: Optional[str] = None,
    filter: Optional[str] = None,
    project_id: Optional[str] = None,
    page: int = 1,
    limit: int = 100,
    current_user: dict = Depends(get_current_user)
):
    t0 = time.perf_counter()
    db = await get_db()
    try:
        term = (search or "").strip()

        async def _run_list_query(with_projects_join: bool):
            project_select = ", p.name" if with_projects_join else ", NULL"
            project_join = (
                "\n            LEFT JOIN projects p ON p.id = c.project_id AND p.user_id = c.user_id"
                if with_projects_join
                else ""
            )
            # Pagina primeiro sobre `conversations` (usando índices por user_id + updated_at/favorited_at)
            # e só conta mensagens para as conversas retornadas na página (T3.1).
            query = f"""
            SELECT c.id, c.title, c.model_id, c.provider_id,
                   c.created_at, c.updated_at,
                   c.is_favorite, c.favorited_at,
                   c.project_tag,
                   c.project_id,
                   c.origin_insight_id{project_select}
            FROM conversations c{project_join}
            WHERE c.user_id = ?
        """
            params: list = [current_user["id"]]

            if term:
                like_term = f"%{term}%"
                query += (
                    " AND (c.title LIKE ? OR EXISTS ("
                    "SELECT 1 FROM messages m WHERE m.conversation_id = c.id AND m.content LIKE ?"
                    "))"
                )
                params.extend([like_term, like_term])

            if project_id:
                query += " AND c.project_id = ?"
                params.append(project_id)

            if filter == "favorites":
                query += " AND c.is_favorite = 1"

            if filter == "favorites":
                query += " ORDER BY c.favorited_at DESC, c.id ASC"
            else:
                query += " ORDER BY c.updated_at DESC, c.id ASC"

            if limit > 0:
                safe_page = max(1, int(page))
                offset = (safe_page - 1) * limit
                query += " LIMIT ? OFFSET ?"
                params.append(limit)
                params.append(offset)

            async with db.execute(query, params) as cur:
                return await cur.fetchall()

        try:
            rows = await _run_list_query(with_projects_join=True)
        except Exception:
            rows = await _run_list_query(with_projects_join=False)

        msg_counts: dict[str, int] = {}
        matched_messages: dict[str, tuple[str, str]] = {}
        if rows:
            conv_ids = [r[0] for r in rows]
            for start in range(0, len(conv_ids), 500):
                chunk = conv_ids[start : start + 500]
                placeholders = ",".join("?" for _ in chunk)
                async with db.execute(
                    f"SELECT conversation_id, COUNT(*) FROM messages WHERE conversation_id IN ({placeholders}) GROUP BY conversation_id",
                    chunk,
                ) as cnt_cur:
                    for cid, cnt in await cnt_cur.fetchall():
                        msg_counts[cid] = int(cnt or 0)

                if term:
                    like_term = f"%{term}%"
                    async with db.execute(
                        f"""SELECT id, conversation_id, content
                            FROM messages
                            WHERE conversation_id IN ({placeholders})
                              AND content LIKE ?
                            ORDER BY created_at DESC""",
                        [*chunk, like_term],
                    ) as match_cur:
                        for mid, cid, content in await match_cur.fetchall():
                            if cid not in matched_messages:
                                matched_messages[cid] = (mid, _build_match_snippet(content or "", term))

        elapsed_ms = (time.perf_counter() - t0) * 1000.0
        logger.debug(
            "[conversations.list] filter=%s has_search=%s page=%d limit=%d returned=%d elapsed_ms=%.2f",
            "favorites" if filter == "favorites" else "all",
            bool(term),
            page,
            limit,
            len(rows),
            elapsed_ms,
        )

        return [
            {
                "id": r[0], "title": r[1], "model_id": r[2],
                "provider_id": r[3], "created_at": r[4],
                "updated_at": r[5], "message_count": msg_counts.get(r[0], 0),
                "is_favorite": bool(r[6]),
                "favorited_at": r[7],
                "project_tag": r[8] if len(r) > 8 else None,
                "project_id": r[9] if len(r) > 9 else None,
                # F3.3.4: conversa iniciada pelo assistente proativo ("Me conta aqui")
                "origin_insight_id": r[10] if len(r) > 10 else None,
                "project_name": r[11] if len(r) > 11 else None,
                "matched_message_id": matched_messages[r[0]][0] if r[0] in matched_messages else None,
                "matched_snippet": matched_messages[r[0]][1] if r[0] in matched_messages else None,
            }
            for r in rows
        ]
    finally:
        await db.close()


@router.get("/turn-status")
async def get_turn_status(
    request_id: str = Query(..., min_length=1),
    current_user: dict = Depends(get_current_user),
):
    """Consulta o status durável de um turno identificado por request_id para reconciliação pós-reload."""
    db = await get_db()
    try:
        state = await get_chat_turn_state(db, current_user["id"], request_id)
        if not state:
            return {"found": False, "request_id": request_id, "status": "unknown"}

        status_val = state.get("status") or "accepted"
        asst_id = state.get("assistant_message_id")
        conv_id = state.get("conversation_id")
        if status_val != "completed" and asst_id and conv_id:
            async with db.execute(
                "SELECT id FROM messages WHERE id = ? AND conversation_id = ? AND role = 'assistant'",
                (asst_id, conv_id),
            ) as cur:
                if await cur.fetchone():
                    status_val = "completed"

        return {
            "found": True,
            "request_id": state["request_id"],
            "status": status_val,
            "conversation_id": conv_id,
            "project_id": state.get("project_id"),
            "user_message_id": state.get("user_message_id"),
            "assistant_message_id": asst_id,
            "partial_content": state.get("partial_content") or "",
            "model_id": state.get("model_id"),
            "provider_id": state.get("provider_id"),
            "error_message": state.get("error_message"),
            "updated_at": state.get("updated_at"),
        }
    finally:
        await db.close()


@router.get("/{conversation_id}")
async def get_conversation(conversation_id: str, current_user: dict = Depends(get_current_user)):
    t0 = time.perf_counter()
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

        try:
            async with db.execute(
                """SELECT m.id, m.role, m.content, m.model_id, m.created_at, mod.display_name, p.name, m.provider, m.relay_used, m.relay_model,
                          m.web_search_used, m.web_search_query, m.web_search_sources, m.process_steps,
                          COALESCE(m.kind, 'normal'), m.proactive_insight_id, m.fusion_metadata, m.process_duration_ms,
                          m.memory_used_json, m.relay_status, m.turn_status
                   FROM messages m
                   LEFT JOIN models mod ON m.model_id = mod.id
                   LEFT JOIN providers p ON mod.provider_id = p.id
                   WHERE m.conversation_id = ?
                   ORDER BY m.created_at ASC""",
                (conversation_id,),
            ) as cur:
                messages = await cur.fetchall()
        except Exception:
            async with db.execute(
                """SELECT m.id, m.role, m.content, m.model_id, m.created_at, mod.display_name, p.name, m.provider, m.relay_used, m.relay_model,
                          m.web_search_used, m.web_search_query, m.web_search_sources, m.process_steps,
                          COALESCE(m.kind, 'normal'), m.proactive_insight_id, m.fusion_metadata, m.process_duration_ms
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
            msg_kind = (m[14] if len(m) > 14 else None) or "normal"
            msg_role = "error" if msg_kind == "error" else m[1]
            sources_val = _loads(m[12]) if len(m) > 12 else None
            if isinstance(sources_val, list):
                for idx, src in enumerate(sources_val, start=1):
                    if isinstance(src, dict) and "index" not in src:
                        src["index"] = idx

            mem_used_val = _loads(m[18]) if len(m) > 18 else None
            item = {
                "id": m[0],
                "role": msg_role,
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
                "relay_status": m[19] if len(m) > 19 else None,
                "turn_status": m[20] if len(m) > 20 else None,
                "memory_used": mem_used_val if isinstance(mem_used_val, list) else None,
                "artifacts": msg_artifacts.get(m[0], []),
                "attachments": msg_attachments.get(m[0], []),
                "ui_blocks": msg_ui_blocks.get(m[0]),
                "web_search_used": bool(m[10]) if len(m) > 10 else False,
                "web_search_query": m[11] if len(m) > 11 else None,
                "web_search_sources": sources_val,
                "process_steps": _loads(m[13]) if len(m) > 13 else None,
                "process_duration_ms": m[17] if len(m) > 17 else None,
                "kind": msg_kind,
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

        logger.debug(
            "[conversations.get] message_count=%d elapsed_ms=%.2f",
            len(built),
            (time.perf_counter() - t0) * 1000.0,
        )

        pending_turn = await get_latest_incomplete_turn_for_conversation(
            db, current_user["id"], conversation_id
        )

        project_name = None
        if len(conv) > 9 and conv[9]:
            try:
                async with db.execute(
                    "SELECT name FROM projects WHERE id = ? AND user_id = ?",
                    (conv[9], current_user["id"]),
                ) as p_cur:
                    p_row = await p_cur.fetchone()
                    if p_row:
                        project_name = p_row[0]
            except Exception:
                project_name = None

        return {
            "id": conv[0], "title": conv[1], "model_id": conv[2],
            "provider_id": conv[3], "created_at": conv[4],
            "is_favorite": bool(conv[6]), "favorited_at": conv[7],
            "project_tag": conv[8] if len(conv) > 8 else None,
            "project_id": conv[9] if len(conv) > 9 else None,
            "project_name": project_name,
            "origin_insight_id": conv[10] if len(conv) > 10 else None,
            "messages": built,
            "pending_turn": pending_turn,
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
