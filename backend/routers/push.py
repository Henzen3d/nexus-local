"""Router para Web Push no PWA — Fase 6 (F6.1.3).

Rotas autenticadas para gerenciamento de inscrições e chave pública VAPID.
"""
from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel, Field

from backend.auth import get_current_user
from backend.database import get_db
from backend.logging_config import get_logger
from backend.proactive import push

logger = get_logger(__name__)

router = APIRouter(prefix="/api/push", tags=["push"])


class PushKeys(BaseModel):
    p256dh: str
    auth: str


class SubscribeBody(BaseModel):
    endpoint: str = Field(..., min_length=10)
    keys: PushKeys
    user_agent: Optional[str] = None


class UnsubscribeBody(BaseModel):
    endpoint: str = Field(..., min_length=10)


@router.get("/vapid-public-key")
async def get_vapid_key(current_user: dict = Depends(get_current_user)) -> dict:
    """Retorna a chave pública VAPID (base64url) para inscrição no navegador."""
    db = await get_db()
    try:
        public_key = await push.get_vapid_public_key(db)
        return {"publicKey": public_key}
    finally:
        await db.close()


@router.post("/subscribe")
async def subscribe(
    body: SubscribeBody,
    request: Request,
    current_user: dict = Depends(get_current_user),
) -> dict:
    """Registra uma assinatura de Web Push para o usuário atual."""
    user_agent = body.user_agent or request.headers.get("user-agent")
    db = await get_db()
    try:
        sub_id = await push.save_subscription(
            db,
            user_id=current_user["id"],
            endpoint=body.endpoint,
            p256dh=body.keys.p256dh,
            auth=body.keys.auth,
            user_agent=user_agent,
        )
        return {"ok": True, "subscription_id": sub_id}
    finally:
        await db.close()


@router.delete("/subscribe")
async def unsubscribe(
    endpoint: Optional[str] = Query(None),
    body: Optional[UnsubscribeBody] = None,
    current_user: dict = Depends(get_current_user),
) -> dict:
    """Remove a assinatura de Web Push associada ao usuário."""
    target_endpoint = (body.endpoint if body else None) or endpoint
    if not target_endpoint:
        raise HTTPException(status_code=422, detail="Endpoint é obrigatório.")

    db = await get_db()
    try:
        removed = await push.remove_subscription(db, current_user["id"], target_endpoint)
        return {"ok": True, "removed": removed}
    finally:
        await db.close()


@router.post("/test")
async def send_test_push(current_user: dict = Depends(get_current_user)) -> dict:
    """Envia uma notificação Web Push de teste para o próprio usuário."""
    db = await get_db()
    try:
        payload = {
            "title": "NexusLocal",
            "body": "Notificações nativas ativadas com sucesso! ✦",
            "url": "/",
        }
        sent = await push.send_push_notification(db, current_user["id"], payload)
        if sent == 0:
            return {
                "ok": False,
                "sent": 0,
                "reason": "Nenhum dispositivo inscrito ou todas as tentativas falharam.",
            }
        return {"ok": True, "sent": sent}
    finally:
        await db.close()
