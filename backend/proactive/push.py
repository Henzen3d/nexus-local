"""Web Push no PWA — Fase 6 (F6.1 / F6.2).

Gerencia chaves VAPID (geração automática persistida em ``meta`` ou lida de env),
tabela ``push_subscriptions``, envio assíncrono via ``pywebpush`` e poda de
inscrições inválidas (HTTP 410 Gone / 404 ou 5 falhas consecutivas).
"""
from __future__ import annotations

import asyncio
import json
import os
import re
from datetime import datetime, timezone
from typing import Any, Optional

from cryptography.hazmat.primitives import serialization
import py_vapid
from py_vapid.utils import b64urlencode
import pywebpush

from backend.logging_config import get_logger
from backend.proactive.config import get_user_settings

logger = get_logger(__name__)

DEFAULT_VAPID_SUBJECT = "mailto:admin@nexuslocal.internal"


async def ensure_vapid_keys(db: Any) -> tuple[str, bytes, str]:
    """Retorna (public_key_b64, private_key_pem_bytes, subject).
    
    Ordem de prioridade:
    1. Variáveis de ambiente VAPID_PUBLIC_KEY, VAPID_PRIVATE_KEY, VAPID_SUBJECT.
    2. Registros na tabela meta (vapid_public_key, vapid_private_key_pem, vapid_subject).
    3. Geração automática transparente, salva em meta para persistir entre reinicializações.
    """
    env_pub = os.getenv("VAPID_PUBLIC_KEY")
    env_priv = os.getenv("VAPID_PRIVATE_KEY")
    env_sub = os.getenv("VAPID_SUBJECT", DEFAULT_VAPID_SUBJECT)

    if env_pub and env_priv:
        priv_bytes = env_priv.encode("utf-8") if isinstance(env_priv, str) else env_priv
        return env_pub.strip(), priv_bytes, env_sub

    # Verificar meta
    db_pub, db_priv, db_sub = None, None, None
    try:
        async with db.execute(
            "SELECT key, value FROM meta WHERE key IN ('vapid_public_key', 'vapid_private_key_pem', 'vapid_subject')"
        ) as cur:
            rows = await cur.fetchall()
            kv = {r[0]: r[1] for r in rows}
            db_pub = kv.get("vapid_public_key")
            db_priv = kv.get("vapid_private_key_pem")
            db_sub = kv.get("vapid_subject")
    except Exception as exc:
        logger.debug("[Push] meta não disponível: %s", exc)

    if db_pub and db_priv:
        return db_pub.strip(), db_priv.encode("utf-8"), db_sub or DEFAULT_VAPID_SUBJECT

    # Gerar par VAPID novo
    logger.info("[Push] Gerando novo par de chaves VAPID...")
    vapid = py_vapid.Vapid()
    vapid.generate_keys()
    priv_pem = vapid.private_pem()  # bytes
    raw_pub = vapid.public_key.public_bytes(
        encoding=serialization.Encoding.X962,
        format=serialization.PublicFormat.UncompressedPoint,
    )
    pub_b64 = b64urlencode(raw_pub)
    subject = env_sub or DEFAULT_VAPID_SUBJECT

    try:
        await db.execute(
            "INSERT OR REPLACE INTO meta (key, value) VALUES ('vapid_public_key', ?)",
            (pub_b64,),
        )
        await db.execute(
            "INSERT OR REPLACE INTO meta (key, value) VALUES ('vapid_private_key_pem', ?)",
            (priv_pem.decode("utf-8"),),
        )
        await db.execute(
            "INSERT OR REPLACE INTO meta (key, value) VALUES ('vapid_subject', ?)",
            (subject,),
        )
        await db.commit()
        logger.info("[Push] Novo par VAPID salvo na tabela meta.")
    except Exception as exc:
        logger.warning("[Push] Falha ao persistir chaves VAPID em meta: %s", exc)

    return pub_b64, priv_pem, subject


async def get_vapid_public_key(db: Any) -> str:
    """Retorna apenas a chave pública em formato base64url para envio ao frontend."""
    pub_b64, _, _ = await ensure_vapid_keys(db)
    return pub_b64


async def save_subscription(
    db: Any,
    user_id: str,
    endpoint: str,
    p256dh: str,
    auth: str,
    user_agent: Optional[str] = None,
) -> int:
    """Registra ou atualiza uma inscrição Web Push para o usuário."""
    await db.execute(
        """
        INSERT INTO push_subscriptions (user_id, endpoint, p256dh, auth, user_agent, created_at, failures)
        VALUES (?, ?, ?, ?, ?, datetime('now'), 0)
        ON CONFLICT(endpoint) DO UPDATE SET
            user_id = excluded.user_id,
            p256dh = excluded.p256dh,
            auth = excluded.auth,
            user_agent = excluded.user_agent,
            failures = 0
        """,
        (user_id, endpoint, p256dh, auth, user_agent),
    )
    await db.commit()
    async with db.execute("SELECT id FROM push_subscriptions WHERE endpoint = ?", (endpoint,)) as cur:
        row = await cur.fetchone()
        return row[0] if row else 0


async def remove_subscription(db: Any, user_id: str, endpoint: str) -> bool:
    """Remove uma inscrição Web Push (pertencente ao próprio usuário)."""
    cur = await db.execute(
        "DELETE FROM push_subscriptions WHERE user_id = ? AND endpoint = ?",
        (user_id, endpoint),
    )
    await db.commit()
    return (cur.rowcount or 0) > 0


_HHMM = re.compile(r"^([01]\d|2[0-3]):[0-5]\d$")


def is_in_quiet_hours(quiet_hours: Optional[dict[str, str]], now_dt: Optional[datetime] = None) -> bool:
    """Verifica se o momento atual está dentro da faixa de horário silencioso."""
    if not quiet_hours or not isinstance(quiet_hours, dict):
        return False
    start_str = quiet_hours.get("start")
    end_str = quiet_hours.get("end")
    if not start_str or not end_str or not _HHMM.match(start_str) or not _HHMM.match(end_str):
        return False

    dt = now_dt or datetime.now()
    now_hm = dt.strftime("%H:%M")

    if start_str <= end_str:
        return start_str <= now_hm < end_str
    else:  # Cruza a meia-noite (ex.: 22:00 até 08:00)
        return now_hm >= start_str or now_hm < end_str


def _dispatch_single_push(
    sub_info: dict,
    payload_str: str,
    priv_pem: bytes,
    claims: dict,
    timeout: float = 8.0,
) -> int:
    """Envia uma notificação Web Push de forma síncrona (executada em threadpool)."""
    try:
        response = pywebpush.webpush(
            subscription_info=sub_info,
            data=payload_str,
            vapid_private_key=priv_pem.decode("utf-8"),
            vapid_claims=claims,
            timeout=timeout,
        )
        status_code = getattr(response, "status_code", 201)
        return int(status_code)
    except pywebpush.WebPushException as ex:
        if ex.response is not None:
            return int(ex.response.status_code)
        logger.warning("[Push] WebPushException sem response: %s", ex)
        return 500
    except Exception as ex:
        logger.warning("[Push] Erro inesperado em webpush: %s", ex)
        return 500


async def send_push_notification(db: Any, user_id: str, payload: dict) -> int:
    """Envia o payload para todas as inscrições ativas do usuário.
    
    Remove inscrições com HTTP 404/410 (Gone) ou mais de 5 falhas consecutivas.
    """
    async with db.execute(
        "SELECT id, endpoint, p256dh, auth, failures FROM push_subscriptions WHERE user_id = ?",
        (user_id,),
    ) as cur:
        subscriptions = await cur.fetchall()

    if not subscriptions:
        return 0

    pub_b64, priv_pem, subject = await ensure_vapid_keys(db)
    claims = {"sub": subject}
    payload_str = json.dumps(payload, ensure_ascii=False)

    success_count = 0
    loop = asyncio.get_running_loop()

    for sub_id, endpoint, p256dh, auth, failures in subscriptions:
        sub_info = {
            "endpoint": endpoint,
            "keys": {
                "p256dh": p256dh,
                "auth": auth,
            },
        }

        # Executa pywebpush em threadpool para não travar o loop de eventos
        status = await loop.run_in_executor(
            None,
            _dispatch_single_push,
            sub_info,
            payload_str,
            priv_pem,
            claims,
        )

        if 200 <= status < 300:
            success_count += 1
            await db.execute(
                "UPDATE push_subscriptions SET last_success_at = datetime('now'), failures = 0 WHERE id = ?",
                (sub_id,),
            )
        elif status in (404, 410):
            logger.info("[Push] Inscrição expirada (HTTP %d). Removendo id=%s", status, sub_id)
            await db.execute("DELETE FROM push_subscriptions WHERE id = ?", (sub_id,))
        else:
            new_failures = failures + 1
            logger.warning("[Push] Falha ao enviar para id=%s (status %d, falha %d)", sub_id, status, new_failures)
            if new_failures >= 5:
                logger.info("[Push] Inscrição atingiu limite de 5 falhas. Removendo id=%s", sub_id)
                await db.execute("DELETE FROM push_subscriptions WHERE id = ?", (sub_id,))
            else:
                await db.execute(
                    "UPDATE push_subscriptions SET failures = ? WHERE id = ?",
                    (new_failures, sub_id),
                )

    await db.commit()
    return success_count


async def maybe_send_proactive_push(db: Any, insight: dict) -> bool:
    """Avalia regras de entrega (F6.1.5 e F6.1.6) e envia notificação push se apropriado."""
    user_id = insight.get("user_id")
    if not user_id:
        return False

    settings = await get_user_settings(db, user_id)
    if not settings.enabled or not settings.push_enabled:
        return False

    if is_in_quiet_hours(settings.quiet_hours):
        logger.debug("[Push] Usuário %s em horário silencioso, push ignorado.", user_id)
        return False

    # F6.1.6 — Não enviar push se faltar < 2h para expirar
    expires_at = insight.get("expires_at")
    if expires_at:
        try:
            exp = datetime.fromisoformat(str(expires_at).replace("Z", "").replace("T", " "))
            remaining_s = (exp - datetime.now(timezone.utc).replace(tzinfo=None)).total_seconds()
            if remaining_s < 7200:  # < 2 horas
                logger.debug("[Push] Insight %s vence em menos de 2h, push ignorado.", insight.get("id"))
                return False
        except Exception:
            pass

    # Agrupamento (F6.1.5): se houver > 1 pendente em 15 min
    async with db.execute(
        """
        SELECT COUNT(*) FROM proactive_insights
        WHERE user_id = ? AND status = 'ready' AND delivered_message_id IS NULL
          AND ready_at >= datetime('now', '-15 minutes')
        """,
        (user_id,),
    ) as cur:
        row = await cur.fetchone()
        recent_pending_count = row[0] if row else 1

    topic = (insight.get("topic") or "").strip()
    if recent_pending_count > 1:
        body = f"{recent_pending_count} novidades esperando você"
    else:
        body = f"✦ Pesquisei sobre {topic}"

    payload = {
        "title": "NexusLocal",
        "body": body,
        "url": f"/?insight={insight.get('id', '')}",
        "insight_id": insight.get("id"),
    }

    try:
        sent = await send_push_notification(db, user_id, payload)
        logger.info("[Push] Notificação disparada para %s (sucessos=%d)", user_id, sent)
        return sent > 0
    except Exception as exc:
        logger.warning("[Push] Erro ao disparar push para %s: %s", user_id, exc)
        return False
