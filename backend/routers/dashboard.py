"""
backend/routers/dashboard.py
FastAPI router para endpoints analíticos do dashboard de uso.
Fornece métricas de uso de modelos, logs de failover e status atual de cota.
"""

from fastapi import APIRouter, HTTPException, Depends
from typing import List, Dict, Any
from datetime import datetime, timezone, timedelta

from backend.database import get_db
from backend.auth import require_admin

router = APIRouter(prefix="/api/dashboard", tags=["dashboard"])

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
