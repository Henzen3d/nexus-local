from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Optional
from backend.cache.manager import cache_manager

router = APIRouter(prefix="/api/cache", tags=["cache"])


class SettingsUpdate(BaseModel):
    enabled: Optional[bool] = None
    exact_enabled: Optional[bool] = None
    semantic_enabled: Optional[bool] = None
    exact_ttl_hours: Optional[int] = None
    semantic_ttl_hours: Optional[int] = None
    similarity_threshold: Optional[float] = None


@router.get("/stats")
async def get_stats():
    return await cache_manager.stats()


@router.get("/settings")
async def get_settings():
    return await cache_manager.get_settings()


@router.patch("/settings")
async def update_settings(body: SettingsUpdate):
    updates = {k: v for k, v in body.model_dump().items() if v is not None}
    if not updates:
        raise HTTPException(status_code=400, detail="Nenhum campo para atualizar.")
    await cache_manager.update_settings(updates)
    return {"ok": True}


@router.get("/entries/{cache_type}")
async def list_entries(cache_type: str, limit: int = 50):
    if cache_type not in ("exact", "semantic"):
        raise HTTPException(status_code=400, detail="cache_type deve ser 'exact' ou 'semantic'")
    return await cache_manager.list_entries(cache_type, limit)


@router.delete("/entries/{cache_type}/{entry_id}")
async def delete_entry(cache_type: str, entry_id: str):
    await cache_manager.delete_entry(entry_id, cache_type)
    return {"ok": True}


@router.delete("/clear")
async def clear_cache(expired_only: bool = False):
    if expired_only:
        result = await cache_manager.clear_expired()
        return {"ok": True, **result}
    await cache_manager.clear_all()
    return {"ok": True, "cleared": "all"}