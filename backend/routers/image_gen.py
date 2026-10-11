from typing import Any, Dict, List
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from backend.auth import get_current_user, require_admin
from backend.database import get_db
from backend.image_gen.config import (
    get_image_gen_config,
    update_image_gen_config,
    list_image_models,
)
from backend.image_gen.queue import list_user_tasks

router = APIRouter(prefix="/api/image-gen", tags=["image-gen"])


class ImageGenConfigUpdate(BaseModel):
    enabled: bool | None = None
    auto_detect: bool | None = None
    provider_id: str | None = None
    model_id: str | None = None
    steps: int | None = None
    width: int | None = None
    height: int | None = None
    daily_cap_per_user: int | None = None


@router.get("/config")
async def get_config(current_user: dict = Depends(get_current_user)) -> Dict[str, Any]:
    db = await get_db()
    try:
        cfg = await get_image_gen_config(db)
        return cfg.to_dict()
    finally:
        await db.close()


@router.post("/config")
async def save_config(
    body: ImageGenConfigUpdate,
    current_user: dict = Depends(require_admin),
) -> Dict[str, Any]:
    db = await get_db()
    try:
        updates = body.dict(exclude_unset=True)
        updated = await update_image_gen_config(db, updates)
        return updated.to_dict()
    finally:
        await db.close()


@router.get("/models")
async def get_models(current_user: dict = Depends(get_current_user)) -> List[Dict[str, Any]]:
    db = await get_db()
    try:
        return await list_image_models(db)
    finally:
        await db.close()


@router.get("/tasks")
async def get_tasks(
    limit: int = 20,
    current_user: dict = Depends(get_current_user),
) -> List[Dict[str, Any]]:
    db = await get_db()
    try:
        return await list_user_tasks(db, current_user["id"], limit=limit)
    finally:
        await db.close()
