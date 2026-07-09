from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel
from typing import Optional
from backend.database import get_db
from backend.auth import get_current_user
from backend.vision_relay import get_vision_relay_config

router = APIRouter(prefix="/api/vision-relay", tags=["vision-relay"])

class VisionRelayConfigUpdate(BaseModel):
    relay_provider_id: Optional[str]
    relay_model_id: Optional[str]
    relay_system_prompt: Optional[str]
    enabled: Optional[int]
    cache_descriptions: Optional[int]

@router.get("/config")
async def get_config(current_user: dict = Depends(get_current_user)):
    db = await get_db()
    try:
        cfg = await get_vision_relay_config(db)
        if not cfg:
            raise HTTPException(status_code=404, detail="Configuração do Vision Relay não encontrada.")
        return cfg
    finally:
        await db.close()

@router.post("/config")
async def update_config(body: VisionRelayConfigUpdate, current_user: dict = Depends(get_current_user)):
    db = await get_db()
    try:
        # Check if row exists
        async with db.execute("SELECT id FROM vision_relay_config WHERE id = 1") as cur:
            row = await cur.fetchone()
        
        if row:
            await db.execute(
                """UPDATE vision_relay_config
                   SET relay_provider_id = ?, relay_model_id = ?, relay_system_prompt = ?, enabled = ?, cache_descriptions = ?
                   WHERE id = 1""",
                (
                    body.relay_provider_id,
                    body.relay_model_id,
                    body.relay_system_prompt,
                    body.enabled if body.enabled is not None else 1,
                    body.cache_descriptions if body.cache_descriptions is not None else 1
                )
            )
        else:
            await db.execute(
                """INSERT INTO vision_relay_config (id, relay_provider_id, relay_model_id, relay_system_prompt, enabled, cache_descriptions)
                   VALUES (1, ?, ?, ?, ?, ?)""",
                (
                    body.relay_provider_id,
                    body.relay_model_id,
                    body.relay_system_prompt,
                    body.enabled if body.enabled is not None else 1,
                    body.cache_descriptions if body.cache_descriptions is not None else 1
                )
            )
        await db.commit()
        return {"ok": True}
    finally:
        await db.close()
