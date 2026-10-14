"""REST do Assistente Proativo — Fases 2, 3 e 4.

Usuário (``get_current_user``; tudo escopado pelo ``user_id`` do token):

* ``GET/PUT /api/proactive/settings`` — preferências (opt-in), tópicos
  bloqueados e mini-estatística (F4.1.1/F4.1.2). ``enabled=false`` cancela os
  pipelines em voo e expira pendentes (F4.1.5).
* ``POST /api/proactive/settings/onboarding-seen`` — marca o onboarding como
  visto sem mexer em ``enabled`` (F4.1.4).
* ``DELETE /api/proactive/blocklist/{topic_hash}`` — desbloquear tópico (F4.1.3).
* ``POST /api/proactive/insights/{id}/ack`` ``{action: seen|dismissed|blocked|know_more}``
  — só o dono; insight de outro usuário responde **404** (não revela existência).
* ``GET /api/proactive/pending`` — insights ``ready`` não entregues (≤ 3).
* ``POST /api/proactive/insights/{id}/expand`` ``{mode: same|new_chat}`` — "Me conta aqui".

Admin (``require_admin``):

* ``GET/PUT /api/proactive/admin-config`` — kill-switch, modelos, caps (F4.4.1).
* ``GET /api/proactive/logs`` — linhas anonimizadas (F4.4.2).
* ``GET /api/proactive/admin-stats`` — contadores, taxas e p95 (F4.4.3).
"""
from __future__ import annotations

from typing import Any, Literal, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from backend.auth import get_current_user, require_admin
from backend.database import get_db
from backend.logging_config import get_logger
from backend.proactive import admin as proactive_admin
from backend.proactive import delivery
from backend.proactive import service as proactive_service
from backend.proactive.config import (
    ADMIN_FIELD_LIMITS,
    ALLOWED_CATEGORIES,
    ALLOWED_SENSITIVITIES,
    get_user_settings,
    load_config,
    save_admin_config,
    upsert_user_settings,
    validate_admin_updates,
    validate_quiet_hours,
)

logger = get_logger(__name__)

router = APIRouter(prefix="/api/proactive", tags=["proactive"])

#: Onboarding só depois de o usuário já ter usado o chat (F4.2.1)
ONBOARDING_MIN_CONVERSATIONS = 3


class ProactiveSettingsUpdate(BaseModel):
    """Todos os campos com default ``None`` (lição da auditoria: ``Optional`` sem default é obrigatório no v2)."""

    enabled: Optional[bool] = None
    sensitivity: Optional[str] = None
    categories: Optional[list[str]] = None
    quiet_hours: Optional[dict[str, Any]] = None
    clear_quiet_hours: bool = False
    onboarding_seen: Optional[bool] = None


class AckBody(BaseModel):
    action: Literal["seen", "dismissed", "blocked", "know_more"] = Field(
        ..., description="seen | dismissed | blocked | know_more"
    )


class ExpandBody(BaseModel):
    mode: Literal["same", "new_chat"] = Field("new_chat", description="same | new_chat")


class AdminConfigUpdate(BaseModel):
    enabled_global: Optional[bool] = None
    detector_provider_id: Optional[str] = None
    detector_model_id: Optional[str] = None
    synth_provider_id: Optional[str] = None
    synth_model_id: Optional[str] = None
    allow_chat_model_fallback: Optional[bool] = None
    max_per_hour_conv: Optional[int] = None
    max_per_day_user: Optional[int] = None
    topic_cooldown_hours: Optional[int] = None
    max_pending: Optional[int] = None
    concurrency: Optional[int] = None
    total_timeout_s: Optional[float] = None
    research_timeout_s: Optional[float] = None
    synth_timeout_s: Optional[float] = None
    expiry_news_hours: Optional[int] = None
    expiry_default_days: Optional[int] = None
    onboarding_enabled: Optional[bool] = None


async def _settings_payload(db, user_id: str) -> dict:
    settings = await get_user_settings(db, user_id)
    config = await load_config(db)
    blocked = await proactive_admin.list_blocked_topics(db, user_id)
    stats = await proactive_admin.user_stats(db, user_id)
    conversations = await proactive_admin.conversation_count(db, user_id)
    return {
        **settings.to_dict(),
        "allowed_categories": list(ALLOWED_CATEGORIES),
        "allowed_sensitivities": list(ALLOWED_SENSITIVITIES),
        "blocked_topics": blocked,
        "stats": stats,
        "conversation_count": conversations,
        # F4.2.1 — uma vez, só depois de ≥ 3 conversas, fonte da verdade no servidor.
        # F5.4.3 — e só quando o admin liberou o onboarding (rollout gradual);
        # o kill-switch global também segura o modal.
        "onboarding_eligible": (
            config.enabled_global
            and config.onboarding_enabled
            and settings.onboarding_seen_at is None
            and not settings.enabled
            and conversations >= ONBOARDING_MIN_CONVERSATIONS
        ),
    }


@router.get("/settings")
async def read_settings(current_user: dict = Depends(get_current_user)) -> dict:
    db = await get_db()
    try:
        return await _settings_payload(db, current_user["id"])
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
    quiet_hours = None
    if body.quiet_hours is not None:
        try:
            quiet_hours = validate_quiet_hours(body.quiet_hours)
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc))
    db = await get_db()
    try:
        before = await get_user_settings(db, current_user["id"])
        settings = await upsert_user_settings(
            db,
            current_user["id"],
            enabled=body.enabled,
            sensitivity=body.sensitivity,
            categories=body.categories,
            quiet_hours=quiet_hours,
            clear_quiet_hours=body.clear_quiet_hours,
            onboarding_seen=body.onboarding_seen,
        )
        extra: dict[str, Any] = {}
        if before.enabled and not settings.enabled:
            # F4.1.5 — desligar: cancela o que está rodando e expira pendentes; histórico fica
            extra["disabled"] = await proactive_service.disable_user(db, current_user["id"])
        return {"ok": True, **(await _settings_payload(db, current_user["id"])), **extra}
    finally:
        await db.close()


@router.post("/settings/onboarding-seen")
async def onboarding_seen(current_user: dict = Depends(get_current_user)) -> dict:
    """F4.1.4 — marca ``onboarding_seen_at`` sem alterar ``enabled``."""
    db = await get_db()
    try:
        settings = await upsert_user_settings(db, current_user["id"], onboarding_seen=True)
        return {"ok": True, "onboarding_seen_at": settings.onboarding_seen_at, "enabled": settings.enabled}
    finally:
        await db.close()


@router.delete("/blocklist/{topic_hash}")
async def unblock_topic(topic_hash: str, current_user: dict = Depends(get_current_user)) -> dict:
    """F4.1.3 — desbloquear tópico (idempotente; só a blocklist do próprio usuário)."""
    db = await get_db()
    try:
        result = await proactive_admin.unblock_topic(db, current_user["id"], topic_hash)
        return {"ok": True, "topic_hash": topic_hash, **result}
    finally:
        await db.close()


_ACK_TRANSITIONS = {
    # action: (status final, statuses de origem em que a transição se aplica)
    "seen": ("seen", ("ready", "delivered")),
    "dismissed": ("dismissed", ("ready", "delivered", "seen")),
    "blocked": ("blocked", ("ready", "delivered", "seen", "dismissed")),
    # métrica "quero saber mais" — não muda o status (F4.1.1 stats.know_more_30d)
    "know_more": (None, ()),
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
        if body.action == "know_more":
            await db.execute(
                "UPDATE proactive_insights SET know_more_at = COALESCE(know_more_at, datetime('now')) WHERE id = ?",
                (insight_id,),
            )
            changed = True
        elif current_status in allowed_from:
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
        return {"ok": True, "id": insight_id, "status": current_status, "topic_hash": topic_hash}
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
        # "Me conta aqui" conta como "quero saber mais" (métrica F4)
        await db.execute(
            "UPDATE proactive_insights SET know_more_at = COALESCE(know_more_at, datetime('now')) WHERE id = ?",
            (insight_id,),
        )
        await db.commit()
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


# ─────────────────────────────────────────────────────────────────────────────
# Admin (F4.4)
# ─────────────────────────────────────────────────────────────────────────────

@router.get("/admin-config")
async def read_admin_config(_: dict = Depends(require_admin)) -> dict:
    db = await get_db()
    try:
        config = await load_config(db, force=True)
        return {**config.to_dict(), "limits": {k: list(v) for k, v in ADMIN_FIELD_LIMITS.items()}}
    finally:
        await db.close()


@router.put("/admin-config")
async def write_admin_config(body: AdminConfigUpdate, _: dict = Depends(require_admin)) -> dict:
    """F4.4.1 — persiste em ``meta`` e invalida o cache (vale sem reiniciar o backend).
    ``enabled_global=false`` é o kill-switch (F4.4.4): cancela pipelines e expira pendentes."""
    try:
        updates = validate_admin_updates(body.model_dump(exclude_none=True))
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    if not updates:
        raise HTTPException(status_code=422, detail="Nenhum campo para atualizar.")
    db = await get_db()
    try:
        before = await load_config(db, force=True)
        config = await save_admin_config(db, updates)
        extra: dict[str, Any] = {}
        if before.enabled_global and not config.enabled_global:
            extra["kill_switch"] = await proactive_service.apply_kill_switch(db)
            logger.warning("[Proactive] kill-switch acionado pelo admin: %s", extra["kill_switch"])
        return {"ok": True, **config.to_dict(), "limits": {k: list(v) for k, v in ADMIN_FIELD_LIMITS.items()}, **extra}
    finally:
        await db.close()


@router.get("/logs")
async def read_logs(
    limit: int = Query(50, ge=1, le=proactive_admin.LOGS_MAX_LIMIT),
    offset: int = Query(0, ge=0),
    status: Optional[str] = Query(None),
    _: dict = Depends(require_admin),
) -> dict:
    """F4.4.2 — nunca inclui o texto da mensagem do usuário nem ``synthesized_text``."""
    db = await get_db()
    try:
        return await proactive_admin.list_logs(db, limit=limit, offset=offset, status=status or None)
    finally:
        await db.close()


@router.get("/admin-stats")
async def read_admin_stats(
    days: int = Query(proactive_admin.DAILY_DEFAULT_DAYS, ge=1, le=proactive_admin.DAILY_MAX_DAYS),
    _: dict = Depends(require_admin),
) -> dict:
    """F4.4.3 + F5.2.4/F5.2.5: janelas 24 h/7 d, p95, série diária, tokens e alarme."""
    db = await get_db()
    try:
        return await proactive_admin.admin_stats(db, days=days)
    finally:
        await db.close()
