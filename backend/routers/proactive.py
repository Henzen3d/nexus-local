"""REST do Assistente Proativo — Fases 2 e 3.

* ``GET/PUT /api/proactive/settings`` — preferências do usuário (opt-in).
* ``POST /api/proactive/insights/{id}/ack`` ``{action: seen|dismissed|blocked}``
  — só o dono; insight de outro usuário responde **404** (não revela existência).
* ``GET /api/proactive/pending`` — insights ``ready`` não entregues (≤ 3), já
  expirando os vencidos (boot do app — F3.2.4).
* ``POST /api/proactive/insights/{id}/expand`` ``{mode: same|new_chat}`` —
  "Me conta aqui" (F3.3): ``same`` devolve o *prefill* (o envio é do usuário);
  ``new_chat`` cria a conversa iniciada pela IA com ``origin_insight_id``.

``admin-config`` e ``logs`` ficam para F4.
"""
from __future__ import annotations

from typing import Any, Literal, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from backend.auth import get_current_user
from backend.database import get_db
from backend.logging_config import get_logger
from backend.proactive import delivery
from backend.proactive.config import (
    ALLOWED_CATEGORIES,
    ALLOWED_SENSITIVITIES,
    get_user_settings,
    upsert_user_settings,
)

logger = get_logger(__name__)

router = APIRouter(prefix="/api/proactive", tags=["proactive"])


class ProactiveSettingsUpdate(BaseModel):
    enabled: Optional[bool] = None
    sensitivity: Optional[str] = None
    categories: Optional[list[str]] = None
    quiet_hours: Optional[dict[str, Any]] = None
    clear_quiet_hours: bool = False
    onboarding_seen: Optional[bool] = None


class AckBody(BaseModel):
    action: Literal["seen", "dismissed", "blocked"] = Field(..., description="seen | dismissed | blocked")


class ExpandBody(BaseModel):
    mode: Literal["same", "new_chat"] = Field("new_chat", description="same | new_chat")


@router.get("/settings")
async def read_settings(current_user: dict = Depends(get_current_user)) -> dict:
    db = await get_db()
    try:
        settings = await get_user_settings(db, current_user["id"])
        return {
            **settings.to_dict(),
            "allowed_categories": list(ALLOWED_CATEGORIES),
            "allowed_sensitivities": list(ALLOWED_SENSITIVITIES),
        }
    finally:
        await db.close()


@router.put("/settings")
async def write_settings(body: ProactiveSettingsUpdate, current_user: dict = Depends(get_current_user)) -> dict:
    if body.sensitivity is not None and body.sensitivity not in ALLOWED_SENSITIVITIES:
        raise HTTPException(status_code=422, detail="Sensibilidade inválida.")
    if body.categories is not None:
        unknown = [c for c in body.categories if c not in ALLOWED_CATEGORIES]
        if unknown:
            raise HTTPException(status_code=422, detail=f"Categorias inválidas: {', '.join(unknown)}")
    db = await get_db()
    try:
        settings = await upsert_user_settings(
            db,
            current_user["id"],
            enabled=body.enabled,
            sensitivity=body.sensitivity,
            categories=body.categories,
            quiet_hours=body.quiet_hours,
            clear_quiet_hours=body.clear_quiet_hours,
            onboarding_seen=body.onboarding_seen,
        )
        return {"ok": True, **settings.to_dict()}
    finally:
        await db.close()


_ACK_TRANSITIONS = {
    # action: (status final, statuses de origem em que a transição se aplica)
    "seen": ("seen", ("ready", "delivered")),
    "dismissed": ("dismissed", ("ready", "delivered", "seen")),
    "blocked": ("blocked", ("ready", "delivered", "seen", "dismissed")),
}


@router.post("/insights/{insight_id}/ack")
async def ack_insight(insight_id: str, body: AckBody, current_user: dict = Depends(get_current_user)) -> dict:
    db = await get_db()
    try:
        async with db.execute(
            "SELECT user_id, status, topic, topic_hash FROM proactive_insights WHERE id = ?",
            (insight_id,),
        ) as cur:
            row = await cur.fetchone()
        # Mesmo tratamento para inexistente e de outro usuário: 404 sem detalhes.
        if not row or row[0] != current_user["id"]:
            raise HTTPException(status_code=404, detail="Insight não encontrado.")

        current_status, topic, topic_hash = row[1], row[2], row[3]
        new_status, allowed_from = _ACK_TRANSITIONS[body.action]
        changed = False
        if current_status in allowed_from:
            if body.action == "seen":
                await db.execute(
                    "UPDATE proactive_insights SET status = 'seen', seen_at = datetime('now') WHERE id = ?",
                    (insight_id,),
                )
            else:
                await db.execute(
                    "UPDATE proactive_insights SET status = ?, seen_at = COALESCE(seen_at, datetime('now')) WHERE id = ?",
                    (new_status, insight_id),
                )
            changed = True
            current_status = new_status
        if body.action == "blocked":
            await db.execute(
                """INSERT OR IGNORE INTO proactive_topic_blocklist (user_id, topic_hash, topic_label)
                   VALUES (?, ?, ?)""",
                (current_user["id"], topic_hash, topic),
            )
            changed = True
        if changed:
            await db.commit()
        return {"ok": True, "id": insight_id, "status": current_status}
    finally:
        await db.close()


@router.get("/pending")
async def list_pending(current_user: dict = Depends(get_current_user)) -> dict:
    """F3.2.4 — mesmo conteúdo do ``flush`` de retorno, para o boot do app."""
    db = await get_db()
    try:
        insights = await delivery.pending_for_api(db, current_user["id"])
        return {"insights": insights}
    finally:
        await db.close()


async def _load_owned_insight(db, insight_id: str, user_id: str) -> dict:
    insight = await delivery.load_insight(db, insight_id)
    # Mesmo tratamento para inexistente e de outro usuário: 404 sem detalhes.
    if not insight or insight.get("user_id") != user_id:
        raise HTTPException(status_code=404, detail="Insight não encontrado.")
    return insight


@router.post("/insights/{insight_id}/expand")
async def expand_insight(insight_id: str, body: ExpandBody, current_user: dict = Depends(get_current_user)) -> dict:
    """F3.3.1 — "Me conta aqui"."""
    db = await get_db()
    try:
        insight = await _load_owned_insight(db, insight_id, current_user["id"])
        if insight.get("status") in ("failed", "expired", "blocked", "detected", "researching"):
            raise HTTPException(status_code=409, detail="Este insight não está mais disponível.")

        follow_ups = [f for f in (delivery._loads(insight.get("follow_ups_json"), []) or []) if isinstance(f, str)]
        if body.mode == "same":
            # Não escrevemos em nome do usuário: devolvemos o texto para o composer.
            prefill = (follow_ups[0] if follow_ups else "").strip()
            return {
                "ok": True,
                "mode": "same",
                "conversation_id": insight["conversation_id"],
                "prefill": prefill,
                "topic": insight.get("topic") or "",
            }

        try:
            result = await delivery.expand_new_chat(db, insight)
        except RuntimeError:
            raise HTTPException(status_code=409, detail="Não foi possível iniciar a conversa.")
        return {"ok": True, "mode": "new_chat", **result}
    finally:
        await db.close()
