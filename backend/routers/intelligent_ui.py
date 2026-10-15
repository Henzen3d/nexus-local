"""Configuração do Intelligent UI (blocos `nexus-ui/1` na bolha).

- ``GET  /api/intelligent-ui/config`` — qualquer usuário autenticado. O frontend
  precisa saber se o recurso está ligado e quais hosts de imagem o servidor
  confia, para repetir a mesma checagem antes de montar o ``<img>``.
- ``POST /api/intelligent-ui/config`` — só admin. Grava na tabela singleton e
  passa a valer imediatamente para os próximos turnos (sem restart).
- ``GET  /api/intelligent-ui/stats`` — só admin. Contadores do processo
  (oferecido / produzido / válido / descartado por motivo) para decidir se vale
  manter o recurso ligado. Zera no restart.
"""

from __future__ import annotations

import json
from typing import Any, Dict, List, Optional, Union

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from backend.auth import get_current_user, require_admin
from backend.database import get_db
from backend.ui_blocks.telemetry import intelligent_ui_telemetry
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


@router.get("/stats")
async def get_stats(current_user: dict = Depends(require_admin)) -> Dict[str, Any]:
    return intelligent_ui_telemetry.snapshot()


class RuntimeCorrectionOffer(BaseModel):
    message_id: str = Field(min_length=1, max_length=64)


@router.post('/correction-offered')
async def runtime_correction_offer(body: RuntimeCorrectionOffer, current_user: dict = Depends(get_current_user)):
    """Counts sandbox failures without receiving their text. Owner-only, flag gated."""
    db = await get_db()
    try:
        cfg = await get_intelligent_ui_config(db)
        async with db.execute(
            "SELECT m.model_id, b.payload FROM messages m JOIN conversations c ON c.id = m.conversation_id "
            "JOIN message_ui_blocks b ON b.message_id = m.id "
            "WHERE m.id = ? AND m.role = 'assistant' AND c.user_id = ?",
            (body.message_id, current_user['id']),
        ) as cur:
            row = await cur.fetchone()
        if not row or not any(block.get('type') == 'sandbox' for block in json.loads(row[1]).get('blocks', [])):
            raise HTTPException(status_code=404, detail='Message not found')
        if cfg.enabled:
            intelligent_ui_telemetry.offer_correction(current_user['id'], body.message_id, row[0] or '')
        return {'ok': True}
    finally:
        await db.close()


class SceneEventRequest(BaseModel):
    event: str = Field(min_length=1, max_length=32)


@router.post('/scene-event')
async def record_scene_event(body: SceneEventRequest, current_user: dict = Depends(get_current_user)):
    """Counts scene lifecycle telemetry: scene_mounted, scene_error, scene_fix_requested."""
    if body.event in ('scene_mounted', 'scene_error', 'scene_fix_requested'):
        intelligent_ui_telemetry.record_scene_event(body.event)
    return {'ok': True}
