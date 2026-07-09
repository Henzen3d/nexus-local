from enum import Enum

class QuotaHealth(Enum):
    SAFE = "safe"
    NEAR_LIMIT = "near_limit"
    UNKNOWN = "unknown"

async def record_request(model_id: str, db):
    """
    Chamado após CADA chamada bem-sucedida ao provider.
    Incrementa os contadores da janela atual.
    """
    await db.execute("""
        UPDATE model_quota_status
        SET current_minute_count = current_minute_count + 1,
            current_day_count    = current_day_count + 1
        WHERE model_id = ?
    """, (model_id,))
    await db.commit()

async def get_quota_health(model_id: str, db, threshold: float = 0.85) -> QuotaHealth:
    """
    Retorna 'safe', 'near_limit' ou 'unknown' (quando não há known_rpm/rpd —
    caso 'unparseable', cai no comportamento reativo já existente).
    """
    async with db.execute("""
        SELECT known_rpm, known_rpd, current_minute_count, current_day_count 
        FROM model_quota_status 
        WHERE model_id = ?
    """, (model_id,)) as cur:
        status_row = await cur.fetchone()
        
    if not status_row:
        return QuotaHealth.UNKNOWN
        
    known_rpm, known_rpd, current_minute_count, current_day_count = status_row
    
    if known_rpm is None and known_rpd is None:
        return QuotaHealth.UNKNOWN  # sem dados — comportamento reativo padrão
        
    # Tratamento para contadores que podem ser None (caso a linha acabou de ser inserida)
    current_minute_count = current_minute_count or 0
    current_day_count = current_day_count or 0
        
    minute_ratio = current_minute_count / known_rpm if known_rpm else 0
    day_ratio    = current_day_count / known_rpd if known_rpd else 0
    
    if minute_ratio >= threshold or day_ratio >= threshold:
        return QuotaHealth.NEAR_LIMIT
        
    return QuotaHealth.SAFE

async def reset_minute_windows(db):
    """
    Reseta a contagem de minutos. Deve rodar a cada 60 segundos.
    """
    await db.execute("UPDATE model_quota_status SET current_minute_count = 0")
    await db.commit()

async def reset_day_windows(db):
    """
    Reseta a contagem diária. Deve rodar à meia-noite (UTC).
    """
    await db.execute("UPDATE model_quota_status SET current_day_count = 0")
    await db.commit()
