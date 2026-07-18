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

async def mark_model_exhausted(
    model_id: str, 
    db: aiosqlite.Connection,
    retry_after: int | None = None,
    error_msg: str | None = None
) -> None:
    """
    Marca um modelo como esgotado (status='exhausted').
    Calcula a estimativa de reset com base no retry_after ou um fallback.
    """
    now = datetime.now(timezone.utc)
    
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
    
    logger.info("🔄 Released expired quotas for %s models: %s", len(model_ids), model_ids)
    return len(model_ids)
