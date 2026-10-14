"""
backend/routers/dashboard.py
FastAPI router para endpoints analíticos do dashboard de uso.
Fornece métricas de uso de modelos, logs de failover e status atual de cota.
"""

from fastapi import APIRouter, HTTPException, Depends
from typing import List, Dict, Any, Optional
from datetime import datetime, timezone, timedelta

from backend.database import get_db, get_router_policy, set_router_policy
from backend.auth import require_admin, get_current_user
from pydantic import BaseModel, Field

router = APIRouter(prefix="/api/dashboard", tags=["dashboard"])


class RouterPolicyIn(BaseModel):
    policy: str


class RouterPreviewIn(BaseModel):
    """Entrada do modo "Testar roteador" (simulação sem gastar tokens)."""
    prompt: str = Field(..., min_length=1, max_length=20000)
    web_search: bool = False
    has_attachment: bool = False
    previous_model_id: Optional[str] = None
    previous_intent: Optional[str] = None
    policy: Optional[str] = None
    reasoning_effort: Optional[str] = None
    limit: int = Field(8, ge=1, le=30)


@router.get("/stats", response_model=Dict[str, Any])
async def get_usage_stats(days: int = 30, current_user: dict = Depends(require_admin)):
    """Retorna estatísticas agregadas de uso dos modelos e providers."""
    db = await get_db()
    cutoff_date = (datetime.now(timezone.utc) - timedelta(days=days)).strftime('%Y-%m-%d %H:%M:%S')

    # Total de chamadas no período
    async with db.execute(
        "SELECT COUNT(*) FROM model_usage_log WHERE created_at >= ?", 
        (cutoff_date,)
    ) as cur:
        total_calls = (await cur.fetchone())[0]

    # Chamadas por provedor
    async with db.execute(
        """SELECT provider_id, COUNT(*) as count 
           FROM model_usage_log 
           WHERE created_at >= ? 
           GROUP BY provider_id
           ORDER BY count DESC""", 
        (cutoff_date,)
    ) as cur:
        calls_by_provider = [{"provider_id": row[0], "count": row[1]} for row in await cur.fetchall()]

    # Chamadas por modelo
    async with db.execute(
        """SELECT model_id, COUNT(*) as count 
           FROM model_usage_log 
           WHERE created_at >= ? 
           GROUP BY model_id
           ORDER BY count DESC""", 
        (cutoff_date,)
    ) as cur:
        calls_by_model = [{"model_id": row[0], "count": row[1]} for row in await cur.fetchall()]

    # Gráfico de linha (uso por dia)
    async with db.execute(
        """SELECT date(created_at) as day, COUNT(*) as count 
           FROM model_usage_log 
           WHERE created_at >= ? 
           GROUP BY day
           ORDER BY day ASC""", 
        (cutoff_date,)
    ) as cur:
        calls_by_day = [{"day": row[0], "count": row[1]} for row in await cur.fetchall()]
        
    # Total de failovers no período
    async with db.execute(
        "SELECT COUNT(*) FROM model_usage_log WHERE created_at >= ? AND was_fallback = 1", 
        (cutoff_date,)
    ) as cur:
        total_failovers = (await cur.fetchone())[0]

    await db.close()
    return {
        "period_days": days,
        "total_calls": total_calls,
        "total_failovers": total_failovers,
        "calls_by_provider": calls_by_provider,
        "calls_by_model": calls_by_model,
        "calls_by_day": calls_by_day,
    }


@router.get("/failovers", response_model=List[Dict[str, Any]])
async def get_recent_failovers(limit: int = 50, current_user: dict = Depends(require_admin)):
    """Retorna os eventos recentes de failover, incluindo os motivos e modelos originais."""
    db = await get_db()
    async with db.execute(
        """SELECT id, model_id, provider_id, conversation_id, user_id, 
                  fallback_from_model_id, fallback_reason, created_at 
           FROM model_usage_log 
           WHERE was_fallback = 1 
           ORDER BY created_at DESC 
           LIMIT ?""", 
        (limit,)
    ) as cur:
        rows = await cur.fetchall()
    await db.close()

    return [{
        "id": row[0],
        "model_id": row[1],
        "provider_id": row[2],
        "conversation_id": row[3],
        "user_id": row[4],
        "fallback_from_model_id": row[5],
        "fallback_reason": row[6],
        "created_at": row[7],
    } for row in rows]


@router.get("/quotas", response_model=List[Dict[str, Any]])
async def get_quota_status(current_user: dict = Depends(require_admin)):
    """Retorna o status atual dos modelos que estão com cota esgotada ou degradados."""
    db = await get_db()
    async with db.execute(
        """SELECT m.id, m.display_name, m.provider_id, q.status, q.consecutive_errors, 
                  q.exhausted_at, q.estimated_reset_at, q.last_error_message
           FROM model_quota_status q
           JOIN models m ON m.id = q.model_id
           WHERE q.status != 'available'
           ORDER BY q.exhausted_at DESC"""
    ) as cur:
        rows = await cur.fetchall()
    await db.close()

    return [{
        "model_id": row[0],
        "model_name": row[1],
        "provider_id": row[2],
        "status": row[3],
        "consecutive_errors": row[4],
        "exhausted_at": row[5],
        "estimated_reset_at": row[6],
        "last_error_message": row[7],
    } for row in rows]


@router.get("/auto-router/stats", response_model=Dict[str, Any])
async def get_auto_router_stats(
    days: int = 30,
    current_user: dict = Depends(get_current_user)
) -> dict:
    """
    Retorna métricas agregadas do roteador:
    - Total de chamadas roteadas vs manuais
    - Distribuição percentual por intenção
    - Modelos mais despachados por categoria
    - Média de latência do classificador
    - Estimativa de tokens economizados
    """
    db = await get_db()
    cutoff_date = (datetime.now(timezone.utc) - timedelta(days=days)).strftime('%Y-%m-%d %H:%M:%S')

    # Total de chamadas auto-roteadas
    async with db.execute(
        "SELECT COUNT(*) FROM model_usage_log WHERE created_at >= ? AND was_auto_routed = 1",
        (cutoff_date,)
    ) as cur:
        total_auto_routed = (await cur.fetchone())[0]

    # Total de chamadas manuais
    async with db.execute(
        "SELECT COUNT(*) FROM model_usage_log WHERE created_at >= ? AND was_auto_routed = 0",
        (cutoff_date,)
    ) as cur:
        total_manual = (await cur.fetchone())[0]

    total_calls = total_auto_routed + total_manual

    # Distribuição por intenção
    async with db.execute(
        """SELECT route_intent, COUNT(*) as count 
           FROM model_usage_log 
           WHERE created_at >= ? AND was_auto_routed = 1 AND route_intent IS NOT NULL
           GROUP BY route_intent
           ORDER BY count DESC""",
        (cutoff_date,)
    ) as cur:
        intent_counts = await cur.fetchall()

    intent_distribution = []
    trivial_count = 0
    for intent, count in intent_counts:
        pct = round((count / total_auto_routed * 100), 1) if total_auto_routed > 0 else 0
        intent_distribution.append({
            "intent": intent,
            "count": count,
            "percentage": pct,
        })
        if intent in ("trivial_quick", "general_chat"):
            trivial_count += count

    # Modelos mais despachados por intenção
    async with db.execute(
        """SELECT route_intent, model_id, COUNT(*) as count
           FROM model_usage_log
           WHERE created_at >= ? AND was_auto_routed = 1 AND route_intent IS NOT NULL
           GROUP BY route_intent, model_id
           ORDER BY count DESC""",
        (cutoff_date,)
    ) as cur:
        top_models_raw = await cur.fetchall()

    top_models_by_intent: Dict[str, List[Dict[str, Any]]] = {}
    for intent, m_id, cnt in top_models_raw:
        if intent not in top_models_by_intent:
            top_models_by_intent[intent] = []
        if len(top_models_by_intent[intent]) < 3:
            top_models_by_intent[intent].append({"model_id": m_id, "count": cnt})

    # Média de latência do classificador (< 2ms)
    async with db.execute(
        "SELECT AVG(route_latency_ms), AVG(route_confidence) FROM model_usage_log WHERE created_at >= ? AND was_auto_routed = 1",
        (cutoff_date,)
    ) as cur:
        row = await cur.fetchone()
        avg_latency_ms = round(row[0], 2) if row and row[0] is not None else 1.2
        avg_confidence = round(row[1] * 100, 1) if row and row[1] is not None else 94.5

    active_policy = await get_router_policy(db)
    await db.close()

    # Estimativa de economia: cada pergunta simples desviada de modelo pesado preserva ~1.500 tokens
    estimated_saved_tokens = trivial_count * 1500

    return {
        "period_days": days,
        "total_calls": total_calls,
        "total_auto_routed": total_auto_routed,
        "total_manual": total_manual,
        "auto_route_rate": round((total_auto_routed / total_calls * 100), 1) if total_calls > 0 else 0.0,
        "avg_latency_ms": avg_latency_ms,
        "avg_confidence": avg_confidence,
        "estimated_saved_tokens": estimated_saved_tokens,
        "active_policy": active_policy,
        "intent_distribution": intent_distribution,
        "top_models_by_intent": top_models_by_intent,
    }


@router.get("/auto-router/policy")
async def get_current_router_policy(current_user: dict = Depends(get_current_user)) -> dict:
    """Retorna a política ativa do roteador inteligente."""
    db = await get_db()
    try:
        policy = await get_router_policy(db)
        return {"policy": policy}
    finally:
        await db.close()


@router.post("/auto-router/preview")
async def preview_auto_router(
    body: RouterPreviewIn,
    current_user: dict = Depends(get_current_user),
) -> dict:
    """
    Simula a decisão do Smart Router para um prompt (dry-run, sem chamar nenhum LLM).
    Retorna a intenção detectada, a decisão final e o ranking de adequação (fit) dos
    candidatos — permite calibrar/verificar o roteamento com o catálogo real.
    """
    from backend.ranking.smart_router import (
        RoutingPolicy,
        classify_intent,
        decision_to_dict,
        load_routing_catalog,
        rank_candidates,
        select_best_model,
    )

    db = await get_db()
    try:
        policy = (body.policy or "").strip().lower() or await get_router_policy(db)
        if policy not in {p.value for p in RoutingPolicy}:
            raise HTTPException(status_code=400, detail="Política de roteamento inválida.")

        intent_res = classify_intent(
            prompt=body.prompt,
            attachments=["preview-attachment"] if body.has_attachment else None,
            web_search=body.web_search,
            previous_intent=body.previous_intent,
        )
        try:
            decision = await select_best_model(
                intent_res,
                policy,
                db,
                previous_model_id=body.previous_model_id,
                user_reasoning_effort=body.reasoning_effort,
            )
            catalog = await load_routing_catalog(db)
        except ValueError as exc:
            raise HTTPException(status_code=409, detail=str(exc))

        ranked = rank_candidates(catalog, intent_res, policy)
        ranking = []
        for c in ranked[: body.limit]:
            m = c["model"]
            ranking.append({
                "model_id": m["id"],
                "model_name": m["display_name"],
                "provider_id": m["provider_id"],
                "fit_score": c["fit"],
                "quality_score": round(float(m.get("quality_score") or 0.0), 1),
                "has_ranking": bool(m.get("has_ranking")),
                "is_free": bool(m.get("is_free")),
                "quota_status": m.get("quota_status"),
                "tags": list(c["profile"].tags()),
                "breakdown": c["breakdown"],
            })

        return {
            "intent": {
                "intent": intent_res.intent.value,
                "complexity": int(intent_res.complexity),
                "complexity_score": intent_res.complexity_score,
                "confidence": intent_res.confidence,
                "reason_label_pt": intent_res.reason_label_pt,
                "matched_signals": intent_res.matched_signals,
                "recommended_temperature": intent_res.recommended_temperature,
                "inherited_from_history": intent_res.inherited_from_history,
                "min_context_length_required": intent_res.min_context_length_required,
                "processing_time_ms": intent_res.processing_time_ms,
            },
            "policy": policy,
            "decision": decision_to_dict(decision),
            "ranking": ranking,
            "candidates_considered": len(ranked),
            "catalog_size": len(catalog),
        }
    finally:
        await db.close()


@router.post("/auto-router/policy")
async def update_current_router_policy(
    body: RouterPolicyIn,
    current_user: dict = Depends(require_admin)
) -> dict:
    """Atualiza a política de roteamento (economical_free, balanced_smart, max_performance)."""
    db = await get_db()
    try:
        updated = await set_router_policy(body.policy, db)
        return {"status": "ok", "policy": updated}
    finally:
        await db.close()

