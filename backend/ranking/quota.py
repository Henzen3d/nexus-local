import aiosqlite
from datetime import datetime, timedelta, timezone

from backend.logging_config import get_logger
logger = get_logger(__name__)

async def get_quota_status(model_id: str, db: aiosqlite.Connection) -> dict:
    """Retorna o status de cota de um modelo."""
    async with db.execute(
        "SELECT status, consecutive_errors, exhausted_at, estimated_reset_at, last_error_message "
        "FROM model_quota_status WHERE model_id = ?",
        (model_id,)
    ) as cur:
        row = await cur.fetchone()
        
    if not row:
        return {
            "status": "available",
            "consecutive_errors": 0,
            "exhausted_at": None,
            "estimated_reset_at": None,
            "last_error_message": None
        }
        
    return {
        "status": row[0],
        "consecutive_errors": row[1],
        "exhausted_at": row[2],
        "estimated_reset_at": row[3],
        "last_error_message": row[4]
    }

def is_quota_exhausted_error(error_msg: str | None) -> bool:
    """
    Detecta se uma mensagem de erro ou código HTTP indica que a cota/limite de uso
    do modelo foi atingida (ex: HTTP 402, usage limit reached, quota exceeded, too_many_requests).
    """
    if not error_msg:
        return False
    msg_lower = error_msg.lower()

    # 1. Menção a HTTP 402 (ex: LongCat "Provider error 402" ou status code 402)
    has_402 = (
        "402" in msg_lower
        and any(ctx in msg_lower for ctx in ("error", "status", "code", "http", "api", "provider"))
    )
    if has_402:
        return True

    # 2. Gatilhos de limite de uso e cota esgotada
    quota_triggers = [
        "usage limit reached",
        "usage limit",
        "limit reached",
        "quota_exceeded",
        "quota exceeded",
        "exceeded your current quota",
        "resource has been exhausted",
        "daily limit reached",
        "monthly limit reached",
        "rate limit reached",
    ]
    if any(trigger in msg_lower for trigger in quota_triggers):
        return True

    # 3. too_many_requests acompanhado de rate_limit_error ou usage
    if "too_many_requests" in msg_lower and any(kw in msg_lower for kw in ("rate_limit", "limit", "usage")):
        return True

    return False


async def mark_model_exhausted(
    model_id: str, 
    db: aiosqlite.Connection,
    retry_after: int | None = None,
    error_msg: str | None = None
) -> None:
    """
    Marca um modelo como esgotado (status='exhausted').
    Calcula a estimativa de reset com base no retry_after ou um fallback.
    Se o erro for de cota/limite de uso (ex: HTTP 402 / usage limit), aplica backoff mínimo de 1 hora.
    """
    now = datetime.now(timezone.utc)
    
    if is_quota_exhausted_error(error_msg):
        retry_after = max(retry_after or 0, 3600)

    if retry_after is not None and retry_after > 0:
        reset_time = now + timedelta(seconds=retry_after)
    else:
        # Heurística padrão: se não enviar Retry-After, tentamos novamente em 1 hora
        reset_time = now + timedelta(hours=1)
        
    now_str = now.isoformat()
    reset_str = reset_time.isoformat()
    
    await db.execute(
        """
        INSERT INTO model_quota_status 
        (model_id, status, consecutive_errors, exhausted_at, estimated_reset_at, last_error_message)
        VALUES (?, 'exhausted', 1, ?, ?, ?)
        ON CONFLICT(model_id) DO UPDATE SET
            status = 'exhausted',
            consecutive_errors = consecutive_errors + 1,
            exhausted_at = excluded.exhausted_at,
            estimated_reset_at = excluded.estimated_reset_at,
            last_error_message = excluded.last_error_message
        """,
        (model_id, now_str, reset_str, error_msg)
    )
    await db.commit()
    try:
        from backend.ranking.smart_router import invalidate_model_cache
        invalidate_model_cache()
    except Exception:
        pass
    logger.warning("⚠️ Quota exhausted for model %s. Reset estimated at %s", model_id, reset_str)


async def mark_model_success(model_id: str, db: aiosqlite.Connection) -> None:
    """
    Marca que a chamada para o modelo foi bem-sucedida, resetando erros.
    """
    await db.execute(
        """
        INSERT INTO model_quota_status 
        (model_id, status, consecutive_errors)
        VALUES (?, 'available', 0)
        ON CONFLICT(model_id) DO UPDATE SET
            status = 'available',
            consecutive_errors = 0,
            exhausted_at = NULL,
            estimated_reset_at = NULL,
            last_error_message = NULL
        """,
        (model_id,)
    )
    await db.commit()


async def release_expired_quotas(db: aiosqlite.Connection) -> int:
    """
    Verifica se existem modelos 'exhausted' ou 'degraded' cujo
    tempo de reset estimado já passou, e os libera para 'available'.
    Retorna o número de modelos liberados.
    """
    now = datetime.now(timezone.utc).isoformat()
    
    async with db.execute(
        """
        SELECT model_id FROM model_quota_status
        WHERE status != 'available' 
          AND estimated_reset_at IS NOT NULL 
          AND estimated_reset_at <= ?
        """,
        (now,)
    ) as cur:
        rows = await cur.fetchall()
        
    if not rows:
        return 0
        
    model_ids = [row[0] for row in rows]
    
    placeholders = ",".join("?" for _ in model_ids)
    
    await db.execute(
        f"""
        UPDATE model_quota_status
        SET status = 'available', 
            consecutive_errors = 0,
            exhausted_at = NULL,
            estimated_reset_at = NULL
        WHERE model_id IN ({placeholders})
        """,
        model_ids
    )
    await db.commit()
    try:
        from backend.ranking.smart_router import invalidate_model_cache
        invalidate_model_cache()
    except Exception:
        pass

    logger.info("🔄 Released expired quotas for %s models: %s", len(model_ids), model_ids)
    return len(model_ids)
