"""backend/tools/failover.py — Mecanismo de failover em cascata e cotas para ferramentas.
"""
from __future__ import annotations

import time
from datetime import datetime, timedelta, timezone
from typing import Optional
import aiosqlite

from backend.logging_config import get_logger
from backend.tools.base import ToolProvider, ToolResult
from backend.tools.registry import ToolRegistry, get_providers

logger = get_logger(__name__)


async def get_tool_provider_quota_status(provider_id: str, db: aiosqlite.Connection) -> dict:
    """Retorna o status de cota/saúde de um provedor de ferramenta."""
    async with db.execute(
        "SELECT status, consecutive_errors, exhausted_at, estimated_reset_at, last_error_message "
        "FROM tool_provider_quota WHERE provider_id = ?",
        (provider_id,)
    ) as cur:
        row = await cur.fetchone()

    if not row:
        return {
            "status": "available",
            "consecutive_errors": 0,
            "exhausted_at": None,
            "estimated_reset_at": None,
            "last_error_message": None,
        }

    return {
        "status": row[0] or "available",
        "consecutive_errors": row[1] or 0,
        "exhausted_at": row[2],
        "estimated_reset_at": row[3],
        "last_error_message": row[4],
    }


async def mark_tool_provider_exhausted(
    provider_id: str,
    db: aiosqlite.Connection,
    retry_after: Optional[int] = None,
    error_msg: Optional[str] = None,
) -> None:
    """Marca um provedor como exausto ('exhausted') com tempo estimado de reset."""
    now = datetime.now(timezone.utc)
    if retry_after is not None and retry_after > 0:
        reset_time = now + timedelta(seconds=retry_after)
    else:
        # Padrão: 30 minutos de cooldown para ferramentas gratuitas
        reset_time = now + timedelta(minutes=30)

    now_str = now.isoformat()
    reset_str = reset_time.isoformat()

    try:
        await db.execute(
            """
            INSERT INTO tool_provider_quota
            (provider_id, status, consecutive_errors, exhausted_at, estimated_reset_at, last_error_message)
            VALUES (?, 'exhausted', 1, ?, ?, ?)
            ON CONFLICT(provider_id) DO UPDATE SET
                status = 'exhausted',
                consecutive_errors = consecutive_errors + 1,
                exhausted_at = excluded.exhausted_at,
                estimated_reset_at = excluded.estimated_reset_at,
                last_error_message = excluded.last_error_message
            """,
            (provider_id, now_str, reset_str, (error_msg or "")[:500])
        )
        await db.commit()
        logger.warning("[ToolFailover] Provedor %s marcado como exausto até %s: %s", provider_id, reset_str, error_msg)
    except Exception as e:
        logger.warning("[ToolFailover] Não foi possível atualizar quota para %s: %s", provider_id, e)


async def mark_tool_provider_success(provider_id: str, db: aiosqlite.Connection) -> None:
    """Reseta status de erro do provedor após execução bem-sucedida."""
    try:
        await db.execute(
            """
            INSERT INTO tool_provider_quota
            (provider_id, status, consecutive_errors)
            VALUES (?, 'available', 0)
            ON CONFLICT(provider_id) DO UPDATE SET
                status = 'available',
                consecutive_errors = 0,
                exhausted_at = NULL,
                estimated_reset_at = NULL,
                last_error_message = NULL
            """,
            (provider_id,)
        )
        await db.commit()
    except Exception as e:
        logger.warning("[ToolFailover] Não foi possível atualizar quota de sucesso para %s: %s", provider_id, e)


async def release_expired_tool_quotas(db: aiosqlite.Connection) -> int:
    """Reabilita provedores cujo tempo de exaustão já expirou."""
    now = datetime.now(timezone.utc).isoformat()
    async with db.execute(
        """
        SELECT provider_id FROM tool_provider_quota
        WHERE status != 'available'
          AND estimated_reset_at IS NOT NULL
          AND estimated_reset_at <= ?
        """,
        (now,)
    ) as cur:
        rows = await cur.fetchall()

    if not rows:
        return 0

    provider_ids = [r[0] for r in rows]
    placeholders = ",".join("?" for _ in provider_ids)
    await db.execute(
        f"""
        UPDATE tool_provider_quota
        SET status = 'available',
            consecutive_errors = 0,
            exhausted_at = NULL,
            estimated_reset_at = NULL,
            last_error_message = NULL
        WHERE provider_id IN ({placeholders})
        """,
        provider_ids
    )
    await db.commit()
    logger.info("[ToolFailover] Reabilitados %d provedores de ferramentas com cotas resetadas", len(provider_ids))
    return len(provider_ids)


async def resolve_tool(
    family: str,
    params: dict,
    db: aiosqlite.Connection,
) -> ToolResult:
    """Itera provedores da família em ordem de fallback_order.

    Se o provedor estiver exausto ou desabilitado, pula.
    Se a chamada falhar, marca como exausto e tenta o próximo.
    Retorna o primeiro ToolResult com sucesso ou o último com erro.
    """
    providers = get_providers(family)
    if not providers:
        return ToolResult(
            success=False,
            data={},
            provider_id="none",
            family=family,
            error=f"Nenhum provedor registrado para a família '{family}'",
        )

    now = datetime.now(timezone.utc).isoformat()
    errors_acc: list[str] = []

    for provider in providers:
        # 1. Verifica se está habilitado e configurado (ex: chave de API presente)
        if not provider.is_configured():
            logger.debug("[ToolFailover] Pulando %s (não configurado ou desabilitado)", provider.provider_id)
            continue

        # 2. Verifica cota no banco
        q_status = await get_tool_provider_quota_status(provider.provider_id, db)
        if q_status["status"] == "exhausted":
            reset_at = q_status["estimated_reset_at"]
            if reset_at and reset_at > now:
                logger.debug("[ToolFailover] Provedor %s está exausto até %s", provider.provider_id, reset_at)
                continue

        # 3. Executa a chamada
        t_start = time.perf_counter()
        try:
            result = await provider.execute(params)
            elapsed_ms = (time.perf_counter() - t_start) * 1000.0
            result.latency_ms = elapsed_ms

            if result.success:
                await mark_tool_provider_success(provider.provider_id, db)
                return result
            else:
                err = result.error or "Falha desconhecida"
                errors_acc.append(f"{provider.provider_id}: {err}")
                await mark_tool_provider_exhausted(provider.provider_id, db, error_msg=err)
                logger.warning("[ToolFailover] Provedor %s falhou: %s. Tentando próximo...", provider.provider_id, err)

        except Exception as exc:
            elapsed_ms = (time.perf_counter() - t_start) * 1000.0
            err_msg = str(exc)
            errors_acc.append(f"{provider.provider_id}: {err_msg}")
            await mark_tool_provider_exhausted(provider.provider_id, db, error_msg=err_msg)
            logger.warning("[ToolFailover] Exceção em %s (%s). Tentando próximo...", provider.provider_id, exc)

    # Se todos falharem:
    combined_err = "; ".join(errors_acc) if errors_acc else "Todos os provedores indisponíveis"
    return ToolResult(
        success=False,
        data={},
        provider_id="none",
        family=family,
        error=f"Todos os provedores da família '{family}' falharam: {combined_err}",
    )
