"""Configuração do Intelligent UI (blocos `nexus-ui/1` na bolha).

- ``GET  /api/intelligent-ui/config`` — qualquer usuário autenticado. O frontend
  precisa saber se o recurso está ligado e quais hosts de imagem o servidor
  confia, para repetir a mesma checagem antes de montar o ``<img>``.
- ``POST /api/intelligent-ui/config`` — só admin. Grava na tabela singleton e
  passa a valer imediatamente para os próximos turnos (sem restart).
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Union

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from backend.auth import get_current_user, require_admin
from backend.database import get_db
from backend.ui_blocks.config import (
    MAX_IMAGE_HOSTS,
    get_intelligent_ui_config,
    normalize_hosts,
    update_intelligent_ui_config,
)

router = APIRouter(prefix="/api/intelligent-ui", tags=["intelligent-ui"])


class IntelligentUiConfigUpdate(BaseModel):
    # `= None` permite enviar só o que mudou (merge no backend).
    enabled: Optional[bool] = None
    image_hosts: Optional[Union[List[str], str]] = Field(default=None, max_length=4000)
    allow_private_http: Optional[bool] = None


@router.get("/config")
async def get_config(current_user: dict = Depends(get_current_user)) -> Dict[str, Any]:
    db = await get_db()
    try:
        cfg = await get_intelligent_ui_config(db)
        return cfg.to_dict()
    finally:
        await db.close()


@router.post("/config")
async def save_config(
    body: IntelligentUiConfigUpdate,
    current_user: dict = Depends(require_admin),
) -> Dict[str, Any]:
    updates = body.model_dump(exclude_unset=True)
    if "image_hosts" in updates and updates["image_hosts"] is not None:
        updates["image_hosts"] = normalize_hosts(updates["image_hosts"])[:MAX_IMAGE_HOSTS]
    db = await get_db()
    try:
        cfg = await update_intelligent_ui_config(db, updates)
        return {"ok": True, "config": cfg.to_dict()}
    finally:
        await db.close()
