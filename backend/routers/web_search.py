from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel
from typing import Optional, List
from backend.database import get_db
from backend.auth import get_current_user
from backend.web_search.providers import get_web_search_config

router = APIRouter(prefix="/api/web-search", tags=["web-search"])

class WebSearchConfigUpdate(BaseModel):
    enabled: Optional[int]
    search_provider: Optional[str]
    api_key: Optional[str]
    max_results: Optional[int]
    heuristic_enabled: Optional[int]
    heuristic_sensitivity: Optional[str]
    injection_template: Optional[str]

@router.get("/config")
async def get_config(current_user: dict = Depends(get_current_user)):
    db = await get_db()
    try:
        cfg = await get_web_search_config(db)
        if not cfg:
            raise HTTPException(status_code=404, detail="Configuração de busca web não encontrada.")
        
        # Load injection template as well
        async with db.execute("SELECT injection_template FROM web_search_config WHERE id = 1") as cur:
            row = await cur.fetchone()
        cfg["injection_template"] = row[0] if row else ""
        return cfg
    finally:
        await db.close()

@router.post("/config")
async def update_config(body: WebSearchConfigUpdate, current_user: dict = Depends(get_current_user)):
    db = await get_db()
    try:
        async with db.execute("SELECT id FROM web_search_config WHERE id = 1") as cur:
            row = await cur.fetchone()
        
        fields_to_update = body.model_dump(exclude_unset=True)
        
        if row:
            update_fields = []
            params = []
            for field, val in fields_to_update.items():
                update_fields.append(f"{field} = ?")
                params.append(val)
            
            if update_fields:
                query = f"UPDATE web_search_config SET {', '.join(update_fields)} WHERE id = 1"
                await db.execute(query, tuple(params))
        else:
            fields = []
            placeholders = []
            params = []
            for field, val in fields_to_update.items():
                fields.append(field)
                placeholders.append("?")
                params.append(val)
            
            if fields:
                query = f"INSERT INTO web_search_config (id, {', '.join(fields)}) VALUES (1, {', '.join(placeholders)})"
                await db.execute(query, tuple(params))
        
        await db.commit()
        return {"ok": True}
    finally:
        await db.close()

@router.get("/logs")
async def get_logs(limit: int = 50, current_user: dict = Depends(get_current_user)):
    db = await get_db()
    try:
        if current_user.get("role") != "admin":
            async with db.execute(
                """SELECT id, conversation_id, message_id, query, trigger_type, results_count, created_at
                   FROM web_search_log
                   WHERE user_id = ?
                   ORDER BY created_at DESC
                   LIMIT ?""",
                (current_user["id"], limit)
            ) as cur:
                rows = await cur.fetchall()
        else:
            async with db.execute(
                """SELECT id, conversation_id, message_id, query, trigger_type, results_count, created_at
                   FROM web_search_log
                   ORDER BY created_at DESC
                   LIMIT ?""",
                (limit,)
            ) as cur:
                rows = await cur.fetchall()
        
        logs = []
        for r in rows:
            logs.append({
                "id": r[0],
                "conversation_id": r[1],
                "message_id": r[2],
                "query": r[3],
                "trigger_type": r[4],
                "results_count": r[5],
                "created_at": r[6]
            })
        return logs
    finally:
        await db.close()
