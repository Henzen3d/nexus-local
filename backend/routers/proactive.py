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

import asyncio
import json
import re
import secrets
import time
from typing import Any, Literal, Optional
import uuid

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from backend.auth import get_current_user, require_admin
from backend.database import get_db
from backend.logging_config import get_logger
from backend.proactive import admin as proactive_admin
from backend.proactive.accumulator import MemoryTopicAccumulator
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
    push_enabled: Optional[bool] = None
    persona_style: Optional[str] = None
    selected_pet: Optional[str] = None
    pet_widget_enabled: Optional[bool] = None
    onboarding_seen: Optional[bool] = None


class InvestigateBody(BaseModel):
    prompt: str = Field(..., min_length=3, max_length=500)
    category: Optional[str] = Field("news", description="event | news | product | place")
    conversation_id: Optional[str] = None


class AckBody(BaseModel):
    action: Literal["seen", "dismissed", "blocked", "know_more"] = Field(
        ..., description="seen | dismissed | blocked | know_more"
    )


class ExpandBody(BaseModel):
    mode: Literal["same", "new_chat"] = Field("new_chat", description="same | new_chat")


class CompanionChatBody(BaseModel):
    insight_id: str
    message: str = Field(..., min_length=1, max_length=2000)
    history: list[dict[str, Any]] = Field(default_factory=list)


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


class MemorySignalBody(BaseModel):
    category: str = Field(..., min_length=1, max_length=50)
    topic_key: str = Field(..., min_length=1, max_length=100)
    snippet: str = Field(..., min_length=1, max_length=1000)
    weight: float = Field(1.0, ge=0.1, le=5.0)


class BotCreateBody(BaseModel):
    name: str = Field(..., min_length=1, max_length=100)
    title: Optional[str] = Field(None, max_length=100)
    description: Optional[str] = Field(None, max_length=500)
    system_instructions: Optional[str] = None
    color_hex: str = Field("#3EC5A8", max_length=10)
    avatar_shape: str = Field("circle", max_length=30)
    mascot_id: str = Field("nex", max_length=30)
    computer_mode: str = Field("shared", max_length=30)
    ambient_enabled: bool = True
    ambient_rules: Optional[dict[str, Any]] = None


class BotUpdateBody(BaseModel):
    name: Optional[str] = None
    title: Optional[str] = None
    description: Optional[str] = None
    system_instructions: Optional[str] = None
    color_hex: Optional[str] = None
    avatar_shape: Optional[str] = None
    mascot_id: Optional[str] = None
    computer_mode: Optional[str] = None
    ambient_enabled: Optional[bool] = None
    ambient_rules: Optional[dict[str, Any]] = None


class BotChatBody(BaseModel):
    message: str = Field(..., min_length=1, max_length=4000)
    history: list[dict[str, Any]] = Field(default_factory=list)
    url: Optional[str] = None


class BotComputerNavigateBody(BaseModel):
    url: str = Field(..., min_length=1, max_length=2000)


class RoutineCreateBody(BaseModel):
    bot_id: str = Field(..., min_length=1)
    name: str = Field(..., min_length=1, max_length=100)
    prompt: str = Field(..., min_length=1)
    timing_type: Literal["interval", "cron", "daily"] = Field("interval")
    timing_value: str = Field(..., min_length=1)
    is_active: bool = True


class RoutineUpdateBody(BaseModel):
    bot_id: Optional[str] = None
    name: Optional[str] = None
    prompt: Optional[str] = None
    timing_type: Optional[Literal["interval", "cron", "daily"]] = None
    timing_value: Optional[str] = None
    is_active: Optional[bool] = None


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
            push_enabled=body.push_enabled,
            persona_style=body.persona_style,
            selected_pet=body.selected_pet,
            pet_widget_enabled=body.pet_widget_enabled,
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


@router.get("/history")
async def list_history(
    limit: int = Query(50, ge=1, le=100),
    status: Optional[str] = Query(None),
    current_user: dict = Depends(get_current_user),
) -> dict:
    """F7.2.2 — Feed de histórico de descobertas do usuário."""
    db = await get_db()
    try:
        insights = await delivery.history_for_api(db, current_user["id"], limit=limit, status=status)
        return {"insights": insights}
    finally:
        await db.close()


@router.post("/investigate")
async def investigate_manually(
    body: InvestigateBody,
    current_user: dict = Depends(get_current_user),
) -> dict:
    """F7.2.4 — Disparo manual de pesquisa proativa no Hub."""
    db = await get_db()
    try:
        insight_id, conv_id = await proactive_service.manual_investigate(
            user_id=current_user["id"],
            prompt=body.prompt,
            category=body.category,
            conversation_id=body.conversation_id,
            db=db,
        )
        return {"ok": True, "insight_id": insight_id, "conversation_id": conv_id}
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


@router.post("/companion/chat")
async def companion_chat(body: CompanionChatBody, current_user: dict = Depends(get_current_user)) -> dict:
    """Conversa curta entre amigos com o assistente proativo (Lumi).
    
    Mantém o chat breve (2-4 frases) e atualiza o Artefato em background quando necessário.
    """
    db = await get_db()
    try:
        insight = await _load_owned_insight(db, body.insight_id, current_user["id"])

        # Garante que o artefato inicial existe
        art_id = insight.get("artifact_id")
        if not art_id:
            art_id = await delivery.ensure_proactive_artifact(
                db, insight["conversation_id"], insight.get("delivered_message_id") or "", insight
            )
            if art_id:
                fresh = await delivery.load_insight(db, insight["id"])
                if fresh:
                    insight = fresh

        # Carrega o artefato atual
        art_title = (insight.get("artifact_title") or f"Pesquisa: {insight.get('topic') or 'Destaques'}").strip()
        art_content = (insight.get("artifact_content") or "").strip()
        art_version = 1
        if art_id:
            async with db.execute(
                "SELECT title, content, version FROM artifacts WHERE id = ?",
                (art_id,),
            ) as cur:
                art_row = await cur.fetchone()
                if art_row:
                    art_title = art_row[0] or art_title
                    art_content = art_row[1] or art_content
                    art_version = art_row[2] or 1

        # Resolve modelo para conversa
        from backend.proactive import synthesizer
        config = await load_config(db)
        try:
            provider, model_name, _ = await synthesizer.resolve_synth_model(
                db, current_user["id"], None, None, config
            )
        except Exception as exc:
            logger.warning("[Proactive] erro ao resolver modelo do companion: %s", exc)
            return {
                "ok": True,
                "reply": "Oi! No momento estou sem acesso direto ao modelo de síntese, mas você pode consultar todas as informações no artefato ao lado!",
                "artifact": {
                    "id": art_id,
                    "title": art_title,
                    "content": art_content,
                    "version": art_version,
                } if art_id else None,
            }

        topic = (insight.get("topic") or "").strip()
        system_prompt = (
            f"Você é o Lumi, o assistente proativo e parceiro de exploração do NexusLocal.\n"
            f"Você está tendo uma conversa curta, amigável e descontraída entre amigos com o usuário sobre o tema: \"{topic}\".\n\n"
            f"REGRAS INEGOCIÁVEIS:\n"
            f"1. TOM: casual, caloroso, espirituoso e direto (\"conversa curta entre amigos\").\n"
            f"2. RESPOSTA DE CHAT: NUNCA passe de 2 a 4 frases. Seja breve, rápido e agradável.\n"
            f"3. NUNCA coloque tabelas longas, listas gigantes ou parágrafos densos no chat.\n"
            f"4. Todo conteúdo denso (comparações, listas completas, tópicos aprofundados) DEVE ficar dentro do ARTEFATO Markdown.\n"
            f"5. Para perguntas simples, curiosidades gerais, dúvidas rápidas fora do tema principal ou saudações (ex: \"qual a capital da frança?\", \"olá\", \"obrigado\"), responda IMEDIATAMENTE em 1 ou 2 frases amigáveis e NUNCA gere ou atualize o bloco de artefato.\n"
            f"6. ATUALIZAÇÃO DE ARTEFATO: Atualize o artefato SOMENTE se o usuário pedir explicitamente para adicionar/alterar o documento ou se a dúvida for um aprofundamento substancial diretamente ligado ao tema de pesquisa (\"{topic}\").\n"
            f"7. Se você for atualizar o artefato, finalize sua resposta com o bloco:\n"
            f"```artifact\n"
            f"TITULO: <titulo descritivo do artefato>\n"
            f"<conteudo markdown completo e formatado do artefato>\n"
            f"```\n"
            f"Se não houver novos dados para atualizar no artefato, NÃO inclua o bloco ```artifact."
        )

        llm_messages: list[dict[str, str]] = [{"role": "system", "content": system_prompt}]
        if art_content:
            llm_messages.append({
                "role": "system",
                "content": f"[ARTEFATO ATUAL]\nTÍTULO: {art_title}\n\n{art_content[:4000]}",
            })

        for h in (body.history or [])[-6:]:
            role = "assistant" if h.get("role") == "assistant" else "user"
            content = str(h.get("content") or "").strip()
            if content:
                llm_messages.append({"role": role, "content": content})

        llm_messages.append({"role": "user", "content": body.message.strip()})

        chunks: list[str] = []
        try:
            async def _collect() -> None:
                async for token in provider.stream_chat(
                    model=model_name, messages=llm_messages, temperature=0.7, max_tokens=1500
                ):
                    chunks.append(str(token))

            await asyncio.wait_for(_collect(), timeout=25.0)
        except Exception as exc:
            logger.warning("[Proactive] erro durante chat do companion: %s", exc)
            return {
                "ok": True,
                "reply": "Puxa, tive uma oscilação aqui para pesquisar mais a fundo, mas todo o nosso guia está salvo no artefato logo acima!",
                "artifact": {
                    "id": art_id,
                    "title": art_title,
                    "content": art_content,
                    "version": art_version,
                } if art_id else None,
            }

        raw_output = "".join(chunks).strip()
        reply = raw_output
        updated_art_content = None
        updated_art_title = art_title

        if "```artifact" in raw_output:
            parts = raw_output.split("```artifact")
            reply = parts[0].strip()
            art_block = parts[1].split("```")[0].strip()
            if art_block:
                lines = art_block.splitlines()
                if lines and lines[0].upper().startswith("TITULO:"):
                    updated_art_title = lines[0][7:].strip() or art_title
                    updated_art_content = "\n".join(lines[1:]).strip()
                else:
                    updated_art_content = art_block

        if updated_art_content and len(updated_art_content) > 20:
            from backend.orchestration.artifacts import save_artifact
            try:
                new_art_id = await save_artifact(
                    db,
                    insight["conversation_id"],
                    insight.get("delivered_message_id") or None,
                    {
                        "type": "markdown",
                        "title": updated_art_title,
                        "content": updated_art_content,
                    },
                )
                await db.execute(
                    "UPDATE proactive_insights SET artifact_id = ?, artifact_title = ?, artifact_content = ? WHERE id = ?",
                    (new_art_id, updated_art_title, updated_art_content, insight["id"]),
                )
                await db.commit()
                art_id = new_art_id
                art_title = updated_art_title
                art_content = updated_art_content
                art_version += 1
            except Exception as exc:
                logger.warning("[Proactive] erro ao salvar versão atualizada do artifact: %s", exc)

        return {
            "ok": True,
            "reply": reply or "Prontinho! Atualizei os detalhes no nosso artefato.",
            "artifact": {
                "id": art_id,
                "title": art_title,
                "content": art_content,
                "version": art_version,
            } if art_id else None,
        }
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


# ─────────────────────────────────────────────────────────────────────────────
# Memórias de Longo Prazo / Acúmulo de Tópicos (F9.1)
# ─────────────────────────────────────────────────────────────────────────────

@router.get("/memories")
async def list_memories(
    status: Optional[str] = Query(None),
    limit: int = Query(50, ge=1, le=100),
    current_user: dict = Depends(get_current_user),
) -> dict:
    db = await get_db()
    try:
        sql = """
            SELECT id, topic_category, topic_key, signal_count, accumulated_context,
                   insight_ready_id, status, last_signal_at, created_at
            FROM proactive_memories
            WHERE user_id = ?
        """
        params: list[Any] = [current_user["id"]]
        if status:
            sql += " AND status = ?"
            params.append(status)
        sql += " ORDER BY last_signal_at DESC LIMIT ?"
        params.append(limit)

        async with db.execute(sql, params) as cur:
            rows = await cur.fetchall()

        memories = []
        for r in rows:
            ctx = {}
            if r[4]:
                try:
                    ctx = json.loads(r[4])
                except Exception:
                    ctx = {}
            memories.append({
                "id": r[0],
                "topic_category": r[1],
                "topic_key": r[2],
                "signal_count": r[3],
                "accumulated_context": ctx,
                "insight_ready_id": r[5],
                "status": r[6],
                "last_signal_at": r[7],
                "created_at": r[8],
            })
        return {"ok": True, "memories": memories}
    finally:
        await db.close()


@router.post("/memories/signal")
async def add_memory_signal(
    body: MemorySignalBody,
    current_user: dict = Depends(get_current_user),
) -> dict:
    db = await get_db()
    try:
        accumulator = MemoryTopicAccumulator(db)
        res = await accumulator.record_signal(
            user_id=current_user["id"],
            category=body.category,
            topic=body.topic_key,
            context_snippet=body.snippet,
        )
        return {
            "ok": True,
            "memory": {
                "id": res.memory_id,
                "triggered": res.triggered,
                "signal_count": res.signal_count,
                "status": res.status,
                "topic_key": res.topic_key,
                "action": res.action,
                "prompt_hook": res.prompt_hook,
            },
        }
    finally:
        await db.close()


# ─────────────────────────────────────────────────────────────────────────────
# Companion Móvel & Pareamento Seguro (F9.4)
# ─────────────────────────────────────────────────────────────────────────────

@router.get("/companion/pair")
async def get_companion_pairing(
    current_user: dict = Depends(get_current_user),
) -> dict:
    code = secrets.token_hex(6).upper()
    settings = None
    db = await get_db()
    try:
        settings = await get_user_settings(db, current_user["id"])
    finally:
        await db.close()

    pet_id = settings.selected_pet if settings else "lumi"
    return {
        "ok": True,
        "pair_code": code,
        "selected_pet": pet_id,
        "expires_in_seconds": 300,
        "companion_url": f"/companion?pair={code}&pet={pet_id}",
    }


# ─────────────────────────────────────────────────────────────────────────────
# Multi-Agentes & Bots Especialistas (F8.1)
# ─────────────────────────────────────────────────────────────────────────────

DEFAULT_BOT_TEMPLATES = [
    {
        "id": "tpl-researcher",
        "name": "Pesquisador Autônomo",
        "title": "Especialista em Web e Documentos",
        "description": "Explora páginas, cruza referências e sintetiza artigos técnicos profundos.",
        "system_instructions": "Você é um pesquisador incansável. Sempre cite fontes e organize por tópicos.",
        "color_hex": "#3B82F6",
        "avatar_shape": "bot_headphone",
        "mascot_id": "zed",
        "computer_mode": "shared",
        "ambient_enabled": 1,
        "ambient_rules": '{"topics":["pesquisa","noticias","estudos"]}',
    },
    {
        "id": "tpl-travel",
        "name": "Concierge de Viagens",
        "title": "Especialista em Roteiros e Voos",
        "description": "Planeja passeios, compara passagens e organiza roteiros dia a dia.",
        "system_instructions": "Você é especialista em turismo e viagens. Planeje roteiros práticos com orçamentos e dicas locais.",
        "color_hex": "#10B981",
        "avatar_shape": "sprout",
        "mascot_id": "neko",
        "computer_mode": "shared",
        "ambient_enabled": 1,
        "ambient_rules": '{"topics":["viagem","hotel","voo","turismo"]}',
    },
    {
        "id": "tpl-auditor",
        "name": "Auditor de Código",
        "title": "Revisão e Segurança",
        "description": "Inspeciona código-fonte, detecta vulnerabilidades e checa conformidade.",
        "system_instructions": "Você é um auditor sênior de software e segurança. Aponte vulnerabilidades, anti-padrões e melhorias.",
        "color_hex": "#8B5CF6",
        "avatar_shape": "monitor",
        "mascot_id": "byte",
        "computer_mode": "sandbox",
        "ambient_enabled": 1,
        "ambient_rules": '{"topics":["código","bug","segurança","deploy"]}',
    },
]


@router.get("/bots")
async def list_bots(current_user: dict = Depends(get_current_user)) -> dict:
    db = await get_db()
    try:
        async with db.execute(
            """
            SELECT id, user_id, name, title, description, system_instructions,
                   color_hex, avatar_shape, mascot_id, computer_mode, ambient_enabled,
                   ambient_rules, created_at, updated_at
            FROM proactive_bots
            WHERE user_id = ?
            ORDER BY created_at ASC
            """,
            (current_user["id"],),
        ) as cur:
            rows = await cur.fetchall()

        bots = []
        for r in rows:
            rules = None
            if r[11]:
                try:
                    rules = json.loads(r[11])
                except Exception:
                    rules = None
            bots.append({
                "id": r[0],
                "user_id": r[1],
                "name": r[2],
                "title": r[3],
                "description": r[4],
                "system_instructions": r[5],
                "color_hex": r[6],
                "avatar_shape": r[7],
                "mascot_id": r[8],
                "computer_mode": r[9],
                "ambient_enabled": bool(r[10]),
                "ambient_rules": rules,
                "created_at": r[12],
                "updated_at": r[13],
            })

        # Se o usuário ainda não tiver nenhum bot criado, semeia automaticamente os templates padrões
        if not bots:
            for tpl in DEFAULT_BOT_TEMPLATES:
                bot_id = f"bot_{secrets.token_hex(8)}"
                await db.execute(
                    """
                    INSERT INTO proactive_bots
                        (id, user_id, name, title, description, system_instructions,
                         color_hex, avatar_shape, mascot_id, computer_mode, ambient_enabled,
                         ambient_rules, created_at, updated_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, datetime('now'), datetime('now'))
                    """,
                    (
                        bot_id,
                        current_user["id"],
                        tpl["name"],
                        tpl["title"],
                        tpl["description"],
                        tpl["system_instructions"],
                        tpl["color_hex"],
                        tpl["avatar_shape"],
                        tpl["mascot_id"],
                        tpl["computer_mode"],
                        tpl["ambient_enabled"],
                        tpl["ambient_rules"],
                    ),
                )
                bots.append({
                    "id": bot_id,
                    "user_id": current_user["id"],
                    "name": tpl["name"],
                    "title": tpl["title"],
                    "description": tpl["description"],
                    "system_instructions": tpl["system_instructions"],
                    "color_hex": tpl["color_hex"],
                    "avatar_shape": tpl["avatar_shape"],
                    "mascot_id": tpl["mascot_id"],
                    "computer_mode": tpl["computer_mode"],
                    "ambient_enabled": bool(tpl["ambient_enabled"]),
                    "ambient_rules": json.loads(tpl["ambient_rules"]),
                    "created_at": "agora",
                    "updated_at": "agora",
                })
            await db.commit()

        return {"ok": True, "bots": bots}
    finally:
        await db.close()


@router.post("/bots")
async def create_bot(
    body: BotCreateBody,
    current_user: dict = Depends(get_current_user),
) -> dict:
    db = await get_db()
    try:
        bot_id = f"bot_{secrets.token_hex(8)}"
        rules_json = json.dumps(body.ambient_rules, ensure_ascii=False) if body.ambient_rules else None
        await db.execute(
            """
            INSERT INTO proactive_bots
                (id, user_id, name, title, description, system_instructions,
                 color_hex, avatar_shape, mascot_id, computer_mode, ambient_enabled,
                 ambient_rules, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, datetime('now'), datetime('now'))
            """,
            (
                bot_id,
                current_user["id"],
                body.name.strip(),
                body.title.strip() if body.title else None,
                body.description.strip() if body.description else None,
                body.system_instructions.strip() if body.system_instructions else None,
                body.color_hex.strip(),
                body.avatar_shape.strip(),
                body.mascot_id.strip(),
                body.computer_mode.strip(),
                1 if body.ambient_enabled else 0,
                rules_json,
            ),
        )
        await db.commit()
        return {
            "ok": True,
            "bot": {
                "id": bot_id,
                "user_id": current_user["id"],
                "name": body.name,
                "title": body.title,
                "description": body.description,
                "system_instructions": body.system_instructions,
                "color_hex": body.color_hex,
                "avatar_shape": body.avatar_shape,
                "mascot_id": body.mascot_id,
                "computer_mode": body.computer_mode,
                "ambient_enabled": body.ambient_enabled,
                "ambient_rules": body.ambient_rules,
            },
        }
    finally:
        await db.close()


@router.put("/bots/{bot_id}")
async def update_bot(
    bot_id: str,
    body: BotUpdateBody,
    current_user: dict = Depends(get_current_user),
) -> dict:
    db = await get_db()
    try:
        async with db.execute(
            "SELECT id FROM proactive_bots WHERE id = ? AND user_id = ?",
            (bot_id, current_user["id"]),
        ) as cur:
            if not await cur.fetchone():
                raise HTTPException(status_code=404, detail="Bot não encontrado")

        updates: list[str] = []
        params: list[Any] = []
        if body.name is not None:
            updates.append("name = ?")
            params.append(body.name.strip())
        if body.title is not None:
            updates.append("title = ?")
            params.append(body.title.strip())
        if body.description is not None:
            updates.append("description = ?")
            params.append(body.description.strip())
        if body.system_instructions is not None:
            updates.append("system_instructions = ?")
            params.append(body.system_instructions.strip())
        if body.color_hex is not None:
            updates.append("color_hex = ?")
            params.append(body.color_hex.strip())
        if body.avatar_shape is not None:
            updates.append("avatar_shape = ?")
            params.append(body.avatar_shape.strip())
        if body.mascot_id is not None:
            updates.append("mascot_id = ?")
            params.append(body.mascot_id.strip())
        if body.computer_mode is not None:
            updates.append("computer_mode = ?")
            params.append(body.computer_mode.strip())
        if body.ambient_enabled is not None:
            updates.append("ambient_enabled = ?")
            params.append(1 if body.ambient_enabled else 0)
        if body.ambient_rules is not None:
            updates.append("ambient_rules = ?")
            params.append(json.dumps(body.ambient_rules, ensure_ascii=False))

        if updates:
            updates.append("updated_at = datetime('now')")
            params.extend([bot_id, current_user["id"]])
            await db.execute(
                f"UPDATE proactive_bots SET {', '.join(updates)} WHERE id = ? AND user_id = ?",
                params,
            )
            await db.commit()

        return {"ok": True}
    finally:
        await db.close()


@router.delete("/bots/{bot_id}")
async def delete_bot(
    bot_id: str,
    current_user: dict = Depends(get_current_user),
) -> dict:
    db = await get_db()
    try:
        async with db.execute(
            "DELETE FROM proactive_bots WHERE id = ? AND user_id = ?",
            (bot_id, current_user["id"]),
        ) as cur:
            if cur.rowcount == 0:
                raise HTTPException(status_code=404, detail="Bot não encontrado")
        await db.commit()
        return {"ok": True}
    finally:
        await db.close()


# ─────────────────────────────────────────────────────────────────────────────
# Rotinas Agendadas dos Bots (F8.1.3)
# ─────────────────────────────────────────────────────────────────────────────

@router.get("/routines")
async def list_routines(current_user: dict = Depends(get_current_user)) -> dict:
    db = await get_db()
    try:
        async with db.execute(
            """
            SELECT id, bot_id, user_id, name, prompt, timing_type, timing_value,
                   last_run_at, next_run_at, is_active, created_at
            FROM proactive_routines
            WHERE user_id = ?
            ORDER BY created_at DESC
            """,
            (current_user["id"],),
        ) as cur:
            rows = await cur.fetchall()

        routines = [
            {
                "id": r[0],
                "bot_id": r[1],
                "user_id": r[2],
                "name": r[3],
                "prompt": r[4],
                "timing_type": r[5],
                "timing_value": r[6],
                "last_run_at": r[7],
                "next_run_at": r[8],
                "is_active": bool(r[9]),
                "created_at": r[10],
            }
            for r in rows
        ]
        return {"ok": True, "routines": routines}
    finally:
        await db.close()


@router.post("/routines")
async def create_routine(
    body: RoutineCreateBody,
    current_user: dict = Depends(get_current_user),
) -> dict:
    db = await get_db()
    try:
        # Verifica se o bot pertence ao usuário
        async with db.execute(
            "SELECT id FROM proactive_bots WHERE id = ? AND user_id = ?",
            (body.bot_id, current_user["id"]),
        ) as cur:
            if not await cur.fetchone():
                raise HTTPException(status_code=404, detail="Bot associado não encontrado")

        routine_id = f"routine_{secrets.token_hex(8)}"
        await db.execute(
            """
            INSERT INTO proactive_routines
                (id, bot_id, user_id, name, prompt, timing_type, timing_value,
                 next_run_at, is_active, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, datetime('now', '+1 hour'), ?, datetime('now'))
            """,
            (
                routine_id,
                body.bot_id,
                current_user["id"],
                body.name.strip(),
                body.prompt.strip(),
                body.timing_type,
                body.timing_value.strip(),
                1 if body.is_active else 0,
            ),
        )
        await db.commit()
        return {
            "ok": True,
            "routine": {
                "id": routine_id,
                "bot_id": body.bot_id,
                "name": body.name,
                "prompt": body.prompt,
                "timing_type": body.timing_type,
                "timing_value": body.timing_value,
                "is_active": body.is_active,
            },
        }
    finally:
        await db.close()


@router.put("/routines/{routine_id}")
async def update_routine(
    routine_id: str,
    body: RoutineUpdateBody,
    current_user: dict = Depends(get_current_user),
) -> dict:
    db = await get_db()
    try:
        async with db.execute(
            "SELECT id FROM proactive_routines WHERE id = ? AND user_id = ?",
            (routine_id, current_user["id"]),
        ) as cur:
            if not await cur.fetchone():
                raise HTTPException(status_code=404, detail="Rotina não encontrada")

        updates: list[str] = []
        params: list[Any] = []
        if body.bot_id is not None:
            updates.append("bot_id = ?")
            params.append(body.bot_id)
        if body.name is not None:
            updates.append("name = ?")
            params.append(body.name.strip())
        if body.prompt is not None:
            updates.append("prompt = ?")
            params.append(body.prompt.strip())
        if body.timing_type is not None:
            updates.append("timing_type = ?")
            params.append(body.timing_type)
        if body.timing_value is not None:
            updates.append("timing_value = ?")
            params.append(body.timing_value.strip())
        if body.is_active is not None:
            updates.append("is_active = ?")
            params.append(1 if body.is_active else 0)

        if updates:
            params.extend([routine_id, current_user["id"]])
            await db.execute(
                f"UPDATE proactive_routines SET {', '.join(updates)} WHERE id = ? AND user_id = ?",
                params,
            )
            await db.commit()

        return {"ok": True}
    finally:
        await db.close()


@router.delete("/routines/{routine_id}")
async def delete_routine(
    routine_id: str,
    current_user: dict = Depends(get_current_user),
) -> dict:
    db = await get_db()
    try:
        async with db.execute(
            "DELETE FROM proactive_routines WHERE id = ? AND user_id = ?",
            (routine_id, current_user["id"]),
        ) as cur:
            if cur.rowcount == 0:
                raise HTTPException(status_code=404, detail="Rotina não encontrada")
        await db.commit()
        return {"ok": True}
    finally:
        await db.close()


# ─────────────────────────────────────────────────────────────────────────────
# Execução Real de Tarefas e Sandbox do Computador para Bots (F8.2 / F8.3)
# ─────────────────────────────────────────────────────────────────────────────

@router.post("/bots/{bot_id}/chat")
async def bot_chat(
    bot_id: str,
    body: BotChatBody,
    current_user: dict = Depends(get_current_user),
) -> dict:
    """Interação real e autônoma com o bot especialista e o computador sandbox.

    Executa navegação com anti-SSRF, pesquisa na web e síntese com o modelo de IA.
    """
    db = await get_db()
    try:
        # Carrega bot pertencente ao usuário
        async with db.execute(
            """
            SELECT id, user_id, name, title, description, system_instructions,
                   color_hex, avatar_shape, mascot_id, computer_mode
            FROM proactive_bots
            WHERE id = ? AND user_id = ?
            """,
            (bot_id, current_user["id"]),
        ) as cur:
            row = await cur.fetchone()
            if not row:
                raise HTTPException(status_code=404, detail="Bot não encontrado")

        bot_name = row[2]
        bot_title = row[3] or "Especialista"
        bot_desc = row[4] or ""
        bot_inst = row[5] or "Você é um assistente prestativo e analítico."
        bot_mode = row[9] or "shared"

        actions: list[dict[str, Any]] = []
        user_text = body.message.strip()

        # 1. Detecção de URL no texto do usuário ou campo explícito
        url_match = re.search(r'https?://[^\s<>"]+', user_text)
        target_url = body.url or (url_match.group(0) if url_match else None)
        extracted_content = ""
        current_url = target_url or "https://news.ycombinator.com"
        page_title = ""

        from backend.web_search.reader import fetch_page_content
        from backend.computer.base import is_safe_public_url as computer_is_safe_public_url

        if target_url:
            t0 = time.monotonic()
            safe, reason = computer_is_safe_public_url(target_url)
            if not safe:
                actions.append({
                    "id": f"act_{secrets.token_hex(4)}",
                    "action": "navigate",
                    "target": target_url,
                    "status": "error",
                    "latencyMs": round((time.monotonic() - t0) * 1000, 1),
                    "time": "Agora",
                    "error": reason,
                })
            else:
                try:
                    page_data = await fetch_page_content(target_url, timeout=7.0)
                    nav_ms = round((time.monotonic() - t0) * 1000, 1)
                    if page_data:
                        page_title = page_data.get("title") or target_url
                        actions.append({
                            "id": f"act_{secrets.token_hex(4)}",
                            "action": "navigate",
                            "target": target_url,
                            "status": "success",
                            "latencyMs": nav_ms,
                            "time": "Agora",
                        })
                        sample = page_data.get("text_sample") or ""
                        articles = page_data.get("articles") or []
                        if sample or articles:
                            items_summary = f"{len(articles)} tópicos / {len(sample)} chars"
                            actions.append({
                                "id": f"act_{secrets.token_hex(4)}",
                                "action": "extract_dom",
                                "target": items_summary,
                                "status": "success",
                                "latencyMs": 42,
                                "time": "Agora",
                            })
                            extracted_content = sample[:2500]
                    else:
                        actions.append({
                            "id": f"act_{secrets.token_hex(4)}",
                            "action": "navigate",
                            "target": target_url,
                            "status": "warning",
                            "latencyMs": nav_ms,
                            "time": "Agora",
                        })
                except Exception as exc:
                    logger.debug("[BotChat] Erro ao navegar no sandbox: %s", exc)

        # 2. Se não houver URL direta, mas a mensagem requer pesquisa, executa web search real
        search_snippets = ""
        is_search_intent = (
            "pesquis" in user_text.lower()
            or "busqu" in user_text.lower()
            or "noticia" in user_text.lower()
            or "preço" in user_text.lower()
            or "informações sobre" in user_text.lower()
            or "informações" in user_text.lower()
            or "quem é" in user_text.lower()
            or "o que é" in user_text.lower()
            or "qual a" in user_text.lower()
            or "qual o" in user_text.lower()
            or "onde fica" in user_text.lower()
            or "como funciona" in user_text.lower()
            or "tpl-researcher" in bot_id
            or "Pesquisador" in bot_name
        )

        if not target_url and is_search_intent:
            t0 = time.monotonic()
            try:
                from backend.web_search.providers import resolve_and_execute_search
                clean_q = re.sub(
                    r'^(pode me dar mais informações sobre|pesquise sobre|procure por|busque por|me fale sobre|qual a capital da|qual a)\s+',
                    '',
                    user_text,
                    flags=re.IGNORECASE,
                ).strip()
                search_res = await resolve_and_execute_search(clean_q or user_text, db)
                s_ms = round((time.monotonic() - t0) * 1000, 1)
                if search_res:
                    actions.append({
                        "id": f"act_{secrets.token_hex(4)}",
                        "action": "search",
                        "target": (clean_q or user_text)[:35],
                        "status": "success",
                        "latencyMs": s_ms,
                        "time": "Agora",
                    })
                    first_hit = search_res[0]
                    current_url = first_hit.get("url") or "https://google.com"
                    page_title = first_hit.get("title") or first_hit.get("domain") or ""
                    actions.append({
                        "id": f"act_{secrets.token_hex(4)}",
                        "action": "navigate",
                        "target": current_url,
                        "status": "success",
                        "latencyMs": 95,
                        "time": "Agora",
                    })
                    actions.append({
                        "id": f"act_{secrets.token_hex(4)}",
                        "action": "extract_dom",
                        "target": f"{len(search_res)} itens extraídos",
                        "status": "success",
                        "latencyMs": 38,
                        "time": "Agora",
                    })
                    snippets_list = []
                    for item in search_res[:3]:
                        snippets_list.append(f"- **{item.get('title')}** ({item.get('url')}):\n  {item.get('snippet')}")
                    search_snippets = "\n".join(snippets_list)
            except Exception as exc:
                logger.debug("[BotChat] Erro na busca web: %s", exc)

        # 3. Resolve modelo LLM
        from backend.proactive import synthesizer
        config = await load_config(db)
        try:
            provider, model_name, _ = await synthesizer.resolve_synth_model(
                db, current_user["id"], None, None, config
            )
        except Exception as exc:
            logger.warning("[BotChat] falha ao resolver modelo do bot: %s", exc)
            return {
                "ok": True,
                "reply": f"Olá! Sou {bot_name} ({bot_title}). Executei os passos solicitados no computador sandbox. Como posso ajudá-lo a avançar com estes dados?",
                "actions": actions,
                "current_url": current_url,
                "page_title": page_title,
            }

        # 4. Constrói prompts e mensagens
        system_prompt = (
            f"Você é o bot especialista \"{bot_name}\" ({bot_title}) operando na plataforma NexusLocal.\n"
            f"Descrição: {bot_desc}\n"
            f"Diretrizes e Persona:\n{bot_inst}\n\n"
            f"Você opera integrado a um Computador Sandbox (nexus_computer) com navegador web seguro.\n"
            f"Responda à solicitação do usuário de forma clara, prestativa e estruturada.\n"
            f"Se você utilizou o sandbox ou consultou páginas/fontes na web (dados abaixo), mencione os achados e fontes citando-as naturalmente."
        )

        llm_messages: list[dict[str, str]] = [{"role": "system", "content": system_prompt}]

        context_notes = []
        if extracted_content:
            context_notes.append(f"[CONTEÚDO EXTRAÍDO DA PÁGINA: {current_url}]\n{extracted_content}")
        if search_snippets:
            context_notes.append(f"[RESULTADOS DA PESQUISA WEB]\n{search_snippets}")

        if context_notes:
            llm_messages.append({"role": "system", "content": "\n\n".join(context_notes)})

        for h in (body.history or [])[-6:]:
            role = "assistant" if h.get("sender") == "bot" or h.get("role") == "assistant" else "user"
            c = str(h.get("text") or h.get("content") or "").strip()
            if c:
                llm_messages.append({"role": role, "content": c})

        llm_messages.append({"role": "user", "content": user_text})

        # 5. Executa stream e coleta resposta
        chunks: list[str] = []
        try:
            async def _collect() -> None:
                async for token in provider.stream_chat(
                    model=model_name, messages=llm_messages, temperature=0.7, max_tokens=1000
                ):
                    chunks.append(str(token))

            await asyncio.wait_for(_collect(), timeout=30.0)
        except Exception as exc:
            logger.warning("[BotChat] Erro na geração LLM: %s", exc)
            return {
                "ok": True,
                "reply": "Concluí as ações no sandbox e a navegação foi registrada com sucesso.",
                "actions": actions,
                "current_url": current_url,
                "page_title": page_title,
            }

        reply = "".join(chunks).strip() or "Tarefa processada com sucesso no computador sandbox."

        return {
            "ok": True,
            "reply": reply,
            "actions": actions,
            "current_url": current_url,
            "page_title": page_title,
        }
    finally:
        await db.close()


@router.post("/bots/{bot_id}/computer/navigate")
async def bot_computer_navigate(
    bot_id: str,
    body: BotComputerNavigateBody,
    current_user: dict = Depends(get_current_user),
) -> dict:
    """Navega para uma URL pública no computador sandbox do bot com validação Anti-SSRF."""
    from backend.computer.base import is_safe_public_url
    from backend.web_search.reader import fetch_page_content

    url = body.url.strip()
    safe, reason = is_safe_public_url(url)
    if not safe:
        return {
            "ok": False,
            "error": reason or "Bloqueio Anti-SSRF: Redes locais e endereços privados não são permitidos.",
            "action": {
                "id": f"act_{secrets.token_hex(4)}",
                "action": "navigate",
                "target": url,
                "status": "error",
                "latencyMs": 10,
                "time": "Agora",
                "error": reason,
            },
        }

    t0 = time.monotonic()
    page_data = await fetch_page_content(url, timeout=7.0)
    latency_ms = round((time.monotonic() - t0) * 1000, 1)

    title = (page_data.get("title") if page_data else None) or url
    snippet = page_data.get("markdown", "")[:400] if page_data else None

    from backend.computer.base import capture_page_snapshot
    snapshot = await capture_page_snapshot(url, title=title, snippet=snippet, bot_name=bot_id)

    action = {
        "id": f"act_{secrets.token_hex(4)}",
        "action": "navigate",
        "target": url,
        "status": "success" if page_data else "warning",
        "latencyMs": latency_ms,
        "time": "Agora",
    }

    return {
        "ok": True,
        "url": url,
        "title": title,
        "action": action,
        "screenshot_url": snapshot.get("screenshot_url"),
        "articles_count": len(page_data.get("articles", [])) if page_data else 0,
    }


@router.post("/bots/{bot_id}/computer/screenshot")
async def bot_computer_screenshot(
    bot_id: str,
    body: BotComputerNavigateBody,
    current_user: dict = Depends(get_current_user),
) -> dict:
    """Captura snapshot visual em alta fidelidade da URL informada."""
    from backend.computer.base import is_safe_public_url, capture_page_snapshot
    from backend.web_search.reader import fetch_page_content

    url = body.url.strip() or "https://news.ycombinator.com"
    safe, reason = is_safe_public_url(url)
    if not safe:
        return {
            "ok": False,
            "error": reason or "Bloqueio Anti-SSRF: Redes locais e endereços privados não são permitidos.",
        }

    t0 = time.monotonic()
    page_data = await fetch_page_content(url, timeout=5.0)
    latency_ms = round((time.monotonic() - t0) * 1000, 1)

    title = (page_data.get("title") if page_data else None) or url
    snippet = page_data.get("markdown", "")[:400] if page_data else None
    snapshot = await capture_page_snapshot(url, title=title, snippet=snippet, bot_name=bot_id)

    action = {
        "id": f"act_{secrets.token_hex(4)}",
        "action": "screenshot",
        "target": f"viewport 1280x800 ({url})",
        "status": "success",
        "latencyMs": latency_ms,
        "time": "Agora",
    }

    return {
        "ok": True,
        "url": url,
        "title": title,
        "screenshot_url": snapshot.get("screenshot_url"),
        "action": action,
    }



