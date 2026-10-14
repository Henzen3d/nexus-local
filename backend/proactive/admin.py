"""Consultas do painel (F4): estatísticas do usuário, blocklist, logs anonimizados
e métricas globais do admin.

Regra de ouro (F4.4.2): **nenhuma** consulta daqui devolve o texto da mensagem
do usuário nem ``synthesized_text`` — só rótulos curtos, status, modelos e
latências.
"""
from __future__ import annotations

import math
from typing import Any, Optional

from backend.logging_config import get_logger

logger = get_logger(__name__)

TOPIC_LABEL_MAX = 60
LOGS_MAX_LIMIT = 200
STATS_WINDOWS = {"24h": "-1 day", "7d": "-7 days"}
ALL_STATUSES = ("detected", "researching", "ready", "delivered", "seen", "dismissed", "blocked", "expired", "failed")


def short_label(text: Optional[str], limit: int = TOPIC_LABEL_MAX) -> str:
    """Rótulo curto do tópico (nunca o texto da mensagem)."""
    clean = " ".join((text or "").split())
    return clean if len(clean) <= limit else clean[: limit - 1].rstrip() + "…"


def percentile(values: list[float], pct: float) -> Optional[float]:
    """Percentil por interpolação linear (``None`` sem amostras)."""
    data = sorted(v for v in values if v is not None)
    if not data:
        return None
    if len(data) == 1:
        return float(data[0])
    rank = (len(data) - 1) * (pct / 100.0)
    low, high = math.floor(rank), math.ceil(rank)
    if low == high:
        return float(data[int(rank)])
    return float(data[low] + (data[high] - data[low]) * (rank - low))


# ─────────────────────────────────────────────────────────────────────────────
# Usuário
# ─────────────────────────────────────────────────────────────────────────────

async def user_stats(db: Any, user_id: str) -> dict[str, int]:
    """Mini-estatística do painel do usuário (F4.1.1 / F4.3.1)."""
    async with db.execute(
        """SELECT
               COUNT(*),
               SUM(CASE WHEN delivered_at IS NOT NULL THEN 1 ELSE 0 END),
               SUM(CASE WHEN know_more_at IS NOT NULL THEN 1 ELSE 0 END),
               SUM(CASE WHEN status = 'blocked' THEN 1 ELSE 0 END)
           FROM proactive_insights
           WHERE user_id = ? AND created_at >= datetime('now', '-30 days')""",
        (user_id,),
    ) as cur:
        row = await cur.fetchone()
    total, delivered, know_more, blocked = (row or (0, 0, 0, 0))
    return {
        "insights_30d": int(total or 0),
        "delivered_30d": int(delivered or 0),
        "know_more_30d": int(know_more or 0),
        "blocked_30d": int(blocked or 0),
    }


async def conversation_count(db: Any, user_id: str) -> int:
    async with db.execute("SELECT COUNT(*) FROM conversations WHERE user_id = ?", (user_id,)) as cur:
        row = await cur.fetchone()
    return int(row[0] or 0) if row else 0


async def list_blocked_topics(db: Any, user_id: str) -> list[dict[str, Any]]:
    async with db.execute(
        """SELECT topic_hash, topic_label, created_at FROM proactive_topic_blocklist
           WHERE user_id = ? ORDER BY created_at DESC, topic_hash""",
        (user_id,),
    ) as cur:
        rows = await cur.fetchall()
    return [
        {"topic_hash": r[0], "topic_label": short_label(r[1]) or r[0][:12], "created_at": r[2]}
        for r in rows
    ]


async def unblock_topic(db: Any, user_id: str, topic_hash: str) -> dict[str, Any]:
    """``DELETE /blocklist/{hash}`` (F4.1.3) — também reabre as bolhas bloqueadas
    daquele tópico (``blocked`` → ``seen``) para o "Desfazer" restaurar a UI."""
    cur = await db.execute(
        "DELETE FROM proactive_topic_blocklist WHERE user_id = ? AND topic_hash = ?",
        (user_id, topic_hash),
    )
    removed = (cur.rowcount or 0) > 0
    async with db.execute(
        "SELECT id FROM proactive_insights WHERE user_id = ? AND topic_hash = ? AND status = 'blocked'",
        (user_id, topic_hash),
    ) as sel:
        restored = [r[0] for r in await sel.fetchall()]
    if restored:
        await db.execute(
            "UPDATE proactive_insights SET status = 'seen' WHERE user_id = ? AND topic_hash = ? AND status = 'blocked'",
            (user_id, topic_hash),
        )
    await db.commit()
    return {"removed": removed, "restored_insight_ids": restored}


# ─────────────────────────────────────────────────────────────────────────────
# Admin — logs anonimizados e métricas
# ─────────────────────────────────────────────────────────────────────────────

LOG_COLUMNS = (
    "id", "created_at", "username", "category", "topic", "confidence", "status", "channel",
    "latency_detect_ms", "latency_research_ms", "latency_synth_ms",
    "detector_model", "synth_model", "error_code",
)


async def list_logs(
    db: Any,
    *,
    limit: int = 50,
    offset: int = 0,
    status: Optional[str] = None,
) -> dict[str, Any]:
    """F4.4.2 — linhas anonimizadas, mais recentes primeiro."""
    limit = max(1, min(int(limit or 50), LOGS_MAX_LIMIT))
    offset = max(0, int(offset or 0))
    where = ""
    params: list[Any] = []
    if status:
        if status not in ALL_STATUSES:
            return {"rows": [], "total": 0, "limit": limit, "offset": offset, "status": status}
        where = "WHERE i.status = ?"
        params.append(status)
    async with db.execute(f"SELECT COUNT(*) FROM proactive_insights i {where}", tuple(params)) as cur:
        total = int((await cur.fetchone())[0] or 0)
    async with db.execute(
        f"""SELECT i.id, i.created_at, u.username, i.category, i.topic, i.confidence, i.status, i.channel,
                   i.latency_detect_ms, i.latency_research_ms, i.latency_synth_ms,
                   i.detector_model, i.synth_model, i.error_code
            FROM proactive_insights i
            LEFT JOIN users u ON u.id = i.user_id
            {where}
            ORDER BY i.created_at DESC, i.rowid DESC
            LIMIT ? OFFSET ?""",
        (*params, limit, offset),
    ) as cur:
        rows = await cur.fetchall()
    out = []
    for r in rows:
        item = dict(zip(LOG_COLUMNS, r))
        item["topic"] = short_label(item.get("topic"))
        item["username"] = item.get("username") or "—"
        item["confidence"] = round(float(item["confidence"]), 2) if item.get("confidence") is not None else None
        out.append(item)
    return {"rows": out, "total": total, "limit": limit, "offset": offset, "status": status}


async def _window_counts(db: Any, modifier: str) -> dict[str, Any]:
    by_status = {s: 0 for s in ALL_STATUSES}
    async with db.execute(
        "SELECT status, COUNT(*) FROM proactive_insights WHERE created_at >= datetime('now', ?) GROUP BY status",
        (modifier,),
    ) as cur:
        for status, count in await cur.fetchall():
            if status in by_status:
                by_status[status] = int(count or 0)
    async with db.execute(
        """SELECT
               SUM(CASE WHEN delivered_at IS NOT NULL THEN 1 ELSE 0 END),
               SUM(CASE WHEN know_more_at IS NOT NULL THEN 1 ELSE 0 END),
               SUM(CASE WHEN status = 'blocked' THEN 1 ELSE 0 END),
               SUM(CASE WHEN status = 'dismissed' THEN 1 ELSE 0 END),
               COUNT(DISTINCT user_id)
           FROM proactive_insights WHERE created_at >= datetime('now', ?)""",
        (modifier,),
    ) as cur:
        delivered, know_more, blocked, dismissed, users = await cur.fetchone()
    delivered = int(delivered or 0)
    total = sum(by_status.values())
    return {
        "total": total,
        "by_status": by_status,
        "delivered": delivered,
        "know_more": int(know_more or 0),
        "blocked": int(blocked or 0),
        "dismissed": int(dismissed or 0),
        "users": int(users or 0),
        "know_more_rate": round(int(know_more or 0) / delivered, 3) if delivered else None,
        "blocked_rate": round(int(blocked or 0) / delivered, 3) if delivered else None,
        "failure_rate": round(by_status["failed"] / total, 3) if total else None,
    }


async def admin_stats(db: Any) -> dict[str, Any]:
    """F4.4.3 — contadores por status (24 h / 7 d), taxas e p95 das latências."""
    windows = {name: await _window_counts(db, modifier) for name, modifier in STATS_WINDOWS.items()}

    async with db.execute(
        """SELECT latency_detect_ms, latency_research_ms, latency_synth_ms
           FROM proactive_insights
           WHERE created_at >= datetime('now', '-7 days')
             AND (latency_detect_ms IS NOT NULL OR latency_research_ms IS NOT NULL OR latency_synth_ms IS NOT NULL)
           ORDER BY created_at DESC LIMIT 5000"""
    ) as cur:
        rows = await cur.fetchall()
    detect = [float(r[0]) for r in rows if r[0] is not None]
    research = [float(r[1]) for r in rows if r[1] is not None]
    synth = [float(r[2]) for r in rows if r[2] is not None]
    totals = [sum(v for v in r if v is not None) for r in rows if any(v is not None for v in r)]
    latency = {
        "samples": len(rows),
        "detect_p50_ms": percentile(detect, 50),
        "detect_p95_ms": percentile(detect, 95),
        "research_p50_ms": percentile(research, 50),
        "research_p95_ms": percentile(research, 95),
        "synth_p50_ms": percentile(synth, 50),
        "synth_p95_ms": percentile(synth, 95),
        "total_p95_ms": percentile(totals, 95),
    }

    async with db.execute("SELECT COUNT(*) FROM proactive_user_settings WHERE enabled = 1") as cur:
        users_enabled = int((await cur.fetchone())[0] or 0)
    async with db.execute("SELECT COUNT(*) FROM proactive_insights WHERE status = 'ready'") as cur:
        pending_now = int((await cur.fetchone())[0] or 0)
    async with db.execute("SELECT COUNT(*) FROM proactive_topic_blocklist") as cur:
        blocklist_size = int((await cur.fetchone())[0] or 0)

    try:
        from backend.proactive import presence, service

        runtime = {
            "tasks_in_flight": service.pending_tasks(),
            "presence": presence.stats(),
        }
    except Exception:  # pragma: no cover — métricas de runtime são best-effort
        runtime = {"tasks_in_flight": 0, "presence": {}}

    return {
        "windows": windows,
        "latency": latency,
        "users_enabled": users_enabled,
        "pending_now": pending_now,
        "blocklist_size": blocklist_size,
        "runtime": runtime,
    }
