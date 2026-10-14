"""Orquestração do Assistente Proativo — Fase 2 (F2.2).

Ponto de entrada: :func:`schedule_proactive_check`, chamado no fim de cada
turno do chat (``routers/chat.py``). Ele **só agenda**: o porteiro léxico roda
inline (≈0,3 ms), as flags ``enabled_global``/``settings.enabled`` são lidas
com a conexão do turno e, se tudo passar, uma ``asyncio.Task`` guardada em
``_tasks`` executa :func:`run_pipeline` em segundo plano.

Pipeline: gate → classify → limites (SQL) → ``detected`` → ``researching`` →
pesquisa → síntese → ``ready`` → entrega (``delivery.deliver``). Cada etapa
atualiza ``status``/latências em ``proactive_insights``; qualquer exceção vira
``status='failed'`` + ``error_code`` e um ``warning`` no log — nunca chega ao
WebSocket do usuário.

Também mantém o registro de **turnos ativos** por conversa (``TurnGuard``),
usado pela entrega para não interromper uma resposta em andamento.
"""
from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Optional, Sequence

from backend.logging_config import get_logger
from backend.proactive import delivery, researcher, synthesizer
from backend.proactive.config import ProactiveConfig, UserSettings, get_user_settings, load_config
from backend.proactive.detector import (
    InterestSignal,
    classify_with_meta,
    evaluate,
    gate,
    normalize,
    resolve_detector_model,
)

logger = get_logger(__name__)

STATUS_STAGE = "proactive_status"

#: F5.2.1 — ``sources_json`` de insights ``dismissed`` fica só com as URLs
COMPACT_DISMISSED_AFTER_HOURS = 1


def log_stage(
    event: str,
    *,
    insight_id: Optional[str] = None,
    stage: str = "",
    latency_ms: Optional[float] = None,
    level: int = logging.INFO,
    **fields: Any,
) -> None:
    """Log estruturado por etapa (F5.2.3).

    Sempre com ``insight_id``/``stage``/``latency_ms`` em ``extra`` (e no texto,
    para o formatter padrão), **nunca** com o texto do usuário, o tópico ou a
    síntese — só identificadores, códigos e números.
    """
    extra = {
        "insight_id": insight_id,
        "stage": stage,
        "latency_ms": None if latency_ms is None else int(latency_ms),
        **{k: (round(v, 1) if isinstance(v, float) else v) for k, v in fields.items()},
    }
    parts = [f"{k}={v}" for k, v in extra.items() if v is not None]
    logger.log(level, "[Proactive] %s %s", event, " ".join(parts), extra={"proactive": extra})

# ─────────────────────────────────────────────────────────────────────────────
# Tasks em voo e turnos ativos
# ─────────────────────────────────────────────────────────────────────────────

_tasks: set[asyncio.Task] = set()
#: Pipelines em voo por usuário (F4.1.5 — "desligar cancela o que está rodando").
_user_tasks: dict[str, set[asyncio.Task]] = {}
_active_turns: dict[str, int] = {}
_turn_events: dict[str, asyncio.Event] = {}
_semaphores: dict[int, asyncio.Semaphore] = {}


def pending_tasks() -> int:
    return len(_tasks)


def user_task_count(user_id: str) -> int:
    return len([t for t in _user_tasks.get(user_id, ()) if not t.done()])


def track_task(coro: Any, *, name: str = "proactive", user_id: Optional[str] = None) -> asyncio.Task:
    """``create_task`` com referência guardada (nunca uma task solta — F2.2.5).

    ``user_id`` registra a task também por usuário, para :func:`cancel_user`.
    """
    task = asyncio.create_task(coro, name=name)
    _tasks.add(task)
    task.add_done_callback(_tasks.discard)
    if user_id:
        bucket = _user_tasks.setdefault(user_id, set())
        bucket.add(task)

        def _forget(t: asyncio.Task, *, _uid: str = user_id) -> None:
            remaining = _user_tasks.get(_uid)
            if remaining is not None:
                remaining.discard(t)
                if not remaining:
                    _user_tasks.pop(_uid, None)

        task.add_done_callback(_forget)
    return task


def cancel_user(user_id: str) -> int:
    """Cancela os pipelines em voo do usuário (F4.1.5). Devolve quantos foram cancelados."""
    count = 0
    for task in list(_user_tasks.get(user_id, ())):
        if not task.done():
            task.cancel()
            count += 1
    return count


def cancel_all() -> int:
    """Kill-switch (F4.4.4): cancela todos os pipelines em voo (não os flushes de retorno)."""
    count = 0
    for tasks in list(_user_tasks.values()):
        for task in list(tasks):
            if not task.done():
                task.cancel()
                count += 1
    return count


async def wait_tasks(timeout: float = 5.0) -> None:
    """Somente para testes: aguarda as tasks em voo terminarem."""
    pending = [t for t in _tasks if not t.done()]
    if pending:
        await asyncio.wait(pending, timeout=timeout)


CONNECT_FLUSH_DELAY_S = 3.0


def schedule_return_flush(
    user_id: str,
    ws: Any,
    context: Any = None,
    *,
    delay: float = 0.0,
    skip_if_reported: bool = False,
) -> asyncio.Task:
    """F3.1.4: "voltou" ⇒ tenta entregar pendências sem bloquear o loop do WS.

    ``skip_if_reported`` (usado na conexão): se, passado ``delay``, o cliente já
    enviou seu primeiro ``presence`` — que por si só dispara o flush com o
    contexto certo — este flush de segurança é dispensado (sem duplicar
    ``proactive_pending``). Clientes antigos, que nunca reportam, recebem a
    pendência pelo caminho de segurança.
    """
    from backend.proactive import delivery, presence

    async def _run() -> None:
        try:
            if delay > 0:
                await asyncio.sleep(delay)
            if skip_if_reported:
                sock = presence.get_socket(user_id, ws)
                if sock is None or sock.reported:
                    return
            await delivery.flush_pending(user_id, ws, context)
        except asyncio.CancelledError:
            raise
        except Exception as exc:  # nunca derruba o socket do usuário
            logger.warning("[Proactive] flush_pending falhou (user=%s): %s", user_id, exc)

    return track_task(_run(), name=f"proactive-return:{user_id[:8]}")


def mark_turn_started(conversation_id: str) -> None:
    if not conversation_id:
        return
    _active_turns[conversation_id] = _active_turns.get(conversation_id, 0) + 1
    event = _turn_events.get(conversation_id)
    if event is not None:
        event.clear()


def mark_turn_finished(conversation_id: str) -> None:
    if not conversation_id:
        return
    remaining = _active_turns.get(conversation_id, 0) - 1
    if remaining <= 0:
        _active_turns.pop(conversation_id, None)
        event = _turn_events.pop(conversation_id, None)
        if event is not None:
            event.set()
    else:
        _active_turns[conversation_id] = remaining


def is_turn_active(conversation_id: str) -> bool:
    return _active_turns.get(conversation_id, 0) > 0


async def wait_turn_end(conversation_id: str, timeout: float = 20.0) -> bool:
    """Aguarda o fim do turno em andamento; ``True`` se a conversa ficou livre."""
    if not is_turn_active(conversation_id):
        return True
    event = _turn_events.setdefault(conversation_id, asyncio.Event())
    try:
        await asyncio.wait_for(event.wait(), timeout=timeout)
    except asyncio.TimeoutError:
        return not is_turn_active(conversation_id)
    return True


class TurnGuard:
    """Marca o turno de uma conversa como ativo entre ``start`` e ``finish``."""

    __slots__ = ("conversation_id",)

    def __init__(self) -> None:
        self.conversation_id: Optional[str] = None

    def start(self, conversation_id: str) -> None:
        if self.conversation_id == conversation_id:
            return
        self.finish()
        if conversation_id:
            mark_turn_started(conversation_id)
            self.conversation_id = conversation_id

    def finish(self) -> None:
        if self.conversation_id:
            mark_turn_finished(self.conversation_id)
            self.conversation_id = None


def _semaphore_for(concurrency: int) -> asyncio.Semaphore:
    concurrency = max(1, int(concurrency or 1))
    sem = _semaphores.get(concurrency)
    if sem is None:
        sem = asyncio.Semaphore(concurrency)
        _semaphores[concurrency] = sem
    return sem


def reset_runtime_state() -> None:
    """Somente para testes: limpa turnos, semáforos e tasks registradas."""
    _active_turns.clear()
    _turn_events.clear()
    _semaphores.clear()
    _tasks.clear()
    _user_tasks.clear()


# ─────────────────────────────────────────────────────────────────────────────
# topic_hash e limites (F2.2.3)
# ─────────────────────────────────────────────────────────────────────────────

def compute_topic_hash(topic: str, entities: Sequence[str] = ()) -> str:
    """``sha256(normalize(topic + entities))[:16]`` — entidades ordenadas, sem repetição."""
    ents = sorted({normalize(e) for e in (entities or []) if normalize(e)})
    base = " ".join([normalize(topic or ""), *ents]).strip()
    return hashlib.sha256(base.encode("utf-8")).hexdigest()[:16]


@dataclass
class LimitCheck:
    allowed: bool
    reason: str = "ok"
    counts: dict[str, int] = field(default_factory=dict)


async def _count(db: Any, sql: str, params: tuple) -> int:
    async with db.execute(sql, params) as cur:
        row = await cur.fetchone()
    return int(row[0] or 0) if row else 0


async def is_topic_blocked(db: Any, user_id: str, topic_hash: str) -> bool:
    return await _count(
        db, "SELECT COUNT(*) FROM proactive_topic_blocklist WHERE user_id = ? AND topic_hash = ?",
        (user_id, topic_hash),
    ) > 0


async def check_limits(
    db: Any,
    user_id: str,
    conversation_id: str,
    topic_hash: str,
    config: ProactiveConfig,
) -> LimitCheck:
    """Limites em SQL (sobrevivem a restart): blocklist, 3/h/conversa, 10/dia/usuário, cooldown 24 h."""
    counts: dict[str, int] = {}
    if await is_topic_blocked(db, user_id, topic_hash):
        return LimitCheck(False, "topic_blocked", counts)

    counts["conv_hour"] = await _count(
        db,
        """SELECT COUNT(*) FROM proactive_insights
           WHERE conversation_id = ? AND status <> 'failed'
             AND created_at > datetime('now', '-1 hour')""",
        (conversation_id,),
    )
    if counts["conv_hour"] >= config.max_per_hour_conv:
        return LimitCheck(False, "limit_conv_hour", counts)

    counts["user_day"] = await _count(
        db,
        """SELECT COUNT(*) FROM proactive_insights
           WHERE user_id = ? AND status <> 'failed'
             AND created_at > datetime('now', '-1 day')""",
        (user_id,),
    )
    if counts["user_day"] >= config.max_per_day_user:
        return LimitCheck(False, "limit_user_day", counts)

    counts["topic_recent"] = await _count(
        db,
        """SELECT COUNT(*) FROM proactive_insights
           WHERE user_id = ? AND topic_hash = ? AND status <> 'failed'
             AND created_at > datetime('now', ?)""",
        (user_id, topic_hash, f"-{int(config.topic_cooldown_hours)} hours"),
    )
    if counts["topic_recent"] > 0:
        return LimitCheck(False, "topic_cooldown", counts)

    return LimitCheck(True, "ok", counts)


async def enforce_pending_limit(
    db: Any, user_id: str, max_pending: int, *, keep_id: Optional[str] = None
) -> list[str]:
    """Garante ≤ ``max_pending`` insights ``ready`` por usuário expirando os mais antigos.

    ``keep_id`` (o insight recém-pronto) nunca é expirado por esta regra.
    Devolve os ids expirados.
    """
    max_pending = max(0, int(max_pending))
    async with db.execute(
        """SELECT id FROM proactive_insights
           WHERE user_id = ? AND status = 'ready'
           ORDER BY created_at ASC, rowid ASC""",
        (user_id,),
    ) as cur:
        rows = [r[0] for r in await cur.fetchall()]
    excess = len(rows) - max_pending
    if excess <= 0:
        return []
    expired: list[str] = []
    for insight_id in rows:
        if len(expired) >= excess:
            break
        if insight_id == keep_id:
            continue
        expired.append(insight_id)
    for insight_id in expired:
        await db.execute(
            "UPDATE proactive_insights SET status = 'expired' WHERE id = ? AND status = 'ready'",
            (insight_id,),
        )
    if expired:
        await db.commit()
    return expired


async def expire_overdue(db: Any, user_id: Optional[str] = None) -> int:
    """Marca como ``expired`` os insights ``ready`` com ``expires_at`` vencido."""
    sql = """UPDATE proactive_insights SET status = 'expired'
             WHERE status = 'ready' AND expires_at IS NOT NULL AND expires_at < datetime('now')"""
    params: tuple = ()
    if user_id:
        sql += " AND user_id = ?"
        params = (user_id,)
    cur = await db.execute(sql, params)
    changed = cur.rowcount or 0
    await db.commit()
    return changed


async def expire_pending(db: Any, user_id: Optional[str], error_code: str) -> int:
    """Expira tudo o que ainda não foi entregue (``detected|researching|ready``) com
    ``error_code`` explicativo — histórico já entregue é preservado."""
    sql = """UPDATE proactive_insights SET status = 'expired', error_code = ?
             WHERE status IN ('detected', 'researching', 'ready')"""
    params: list = [error_code[:80]]
    if user_id:
        sql += " AND user_id = ?"
        params.append(user_id)
    cur = await db.execute(sql, tuple(params))
    changed = cur.rowcount or 0
    await db.commit()
    return changed


async def disable_user(db: Any, user_id: str) -> dict[str, int]:
    """F4.1.5 — ``enabled=false``: cancela pipelines em voo e expira pendentes
    (``error_code='user_disabled'``). Mensagens já entregues continuam no histórico."""
    cancelled = cancel_user(user_id)
    if cancelled:
        await asyncio.sleep(0)  # deixa os cancelamentos gravarem ``failed:cancelled``
    expired = await expire_pending(db, user_id, "user_disabled")
    return {"cancelled": cancelled, "expired": expired}


async def apply_kill_switch(db: Any) -> dict[str, int]:
    """F4.4.4 — ``enabled_global=false``: cancela tudo e expira pendentes de todos
    (``error_code='global_disabled'``)."""
    cancelled = cancel_all()
    if cancelled:
        await asyncio.sleep(0)
    expired = await expire_pending(db, None, "global_disabled")
    return {"cancelled": cancelled, "expired": expired}


STUCK_AFTER_MINUTES = 5
PURGE_AFTER_DAYS = 30
TERMINAL_STATUSES = ("seen", "dismissed", "blocked", "expired", "failed")


async def run_housekeeping(db: Any) -> dict[str, int]:
    """F3.2.7: expira vencidos, falha pipelines travados e apaga terminais antigos.

    * ``ready`` com ``expires_at < now`` ⇒ ``expired``;
    * ``detected|researching`` há mais de 5 min ⇒ ``failed:stuck`` (processo
      reiniciado no meio do pipeline);
    * terminais (``seen|dismissed|blocked|expired|failed``) com mais de 30 dias
      ⇒ apagados (retenção do plano; a blocklist é tabela própria e permanece).
    """
    expired = await expire_overdue(db)
    cur = await db.execute(
        """UPDATE proactive_insights SET status = 'failed', error_code = 'stuck'
           WHERE status IN ('detected', 'researching')
             AND created_at < datetime('now', ?)""",
        (f"-{STUCK_AFTER_MINUTES} minutes",),
    )
    stuck = cur.rowcount or 0
    placeholders = ",".join("?" for _ in TERMINAL_STATUSES)
    cur = await db.execute(
        f"""DELETE FROM proactive_insights
            WHERE status IN ({placeholders}) AND created_at < datetime('now', ?)""",  # nosec B608 — SQL montado só com constantes do código; valores sempre parametrizados
        (*TERMINAL_STATUSES, f"-{PURGE_AFTER_DAYS} days"),
    )
    purged = cur.rowcount or 0
    await db.commit()
    compacted = await compact_dismissed_sources(db)
    if expired or stuck or purged or compacted:
        log_stage("housekeeping", stage="housekeeping", expired=expired, stuck=stuck, purged=purged,
                  compacted=compacted)
    return {"expired": expired, "stuck": stuck, "purged": purged, "compacted": compacted}


async def compact_dismissed_sources(db: Any, *, after_hours: int = COMPACT_DISMISSED_AFTER_HOURS) -> int:
    """F5.2.1: insights ``dismissed`` guardam só as URLs das fontes (sem título,
    trecho nem texto lido) — o usuário já disse que não quer; o que fica serve
    apenas para auditoria/ranking. Idempotente: linhas já compactas são puladas."""
    async with db.execute(
        """SELECT id, sources_json FROM proactive_insights
           WHERE status = 'dismissed' AND sources_json IS NOT NULL AND sources_json <> ''
             AND created_at < datetime('now', ?)""",
        (f"-{after_hours} hours",),
    ) as cur:
        rows = await cur.fetchall()
    compacted = 0
    for insight_id, raw in rows:
        try:
            sources = json.loads(raw)
        except (TypeError, ValueError):
            sources = []
        if not isinstance(sources, list):
            sources = []
        urls = [{"url": str(item.get("url") or "")} for item in sources
                if isinstance(item, dict) and item.get("url")]
        if all(isinstance(item, dict) and set(item.keys()) == {"url"} for item in sources) and len(urls) == len(sources):
            continue  # já compacto
        await db.execute(
            "UPDATE proactive_insights SET sources_json = ? WHERE id = ?",
            (json.dumps(urls, ensure_ascii=False), insight_id),
        )
        compacted += 1
    if compacted:
        await db.commit()
    return compacted


async def recover_interrupted(db: Any) -> int:
    """F5.2.2: no boot, insights ``detected|researching`` de antes do restart
    nunca vão terminar (as tasks morreram com o processo) ⇒ ``failed:restart``.
    Padrão de ``recover_interrupted_dreams``."""
    cur = await db.execute(
        """UPDATE proactive_insights SET status = 'failed', error_code = 'restart'
           WHERE status IN ('detected', 'researching')"""
    )
    recovered = cur.rowcount or 0
    await db.commit()
    if recovered:
        log_stage("recovered_after_restart", stage="startup", level=logging.WARNING, recovered=recovered)
    return recovered


# ─────────────────────────────────────────────────────────────────────────────
# Persistência do insight
# ─────────────────────────────────────────────────────────────────────────────

async def _insert_insight(
    db: Any,
    *,
    user_id: str,
    conversation_id: str,
    source_message_id: Optional[str],
    signal: InterestSignal,
    topic_hash: str,
    detector_model: str,
    latency_detect_ms: float,
    created_at: Optional[str] = None,
) -> str:
    insight_id = str(uuid.uuid4())
    await db.execute(
        """INSERT INTO proactive_insights
               (id, user_id, conversation_id, source_message_id, topic, topic_hash, entities_json,
                category, confidence, query, status, language, emotion, detector_model,
                latency_detect_ms, created_at)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'detected', ?, ?, ?, ?, COALESCE(?, datetime('now')))""",
        (
            insight_id, user_id, conversation_id, source_message_id,
            (signal.topic or signal.suggested_query or "")[:200], topic_hash,
            json.dumps(list(signal.entities or []), ensure_ascii=False),
            signal.category or "other", float(signal.interest or 0.0), signal.suggested_query or None,
            signal.language or None, signal.emotion or None, detector_model or None,
            int(latency_detect_ms), created_at,
        ),
    )
    await db.commit()
    return insight_id


async def _update_insight(db: Any, insight_id: str, **fields: Any) -> None:
    if not fields:
        return
    assignments = ", ".join(f"{key} = ?" for key in fields)
    await db.execute(
        f"UPDATE proactive_insights SET {assignments} WHERE id = ?",  # nosec B608 — SQL montado só com constantes do código; valores sempre parametrizados
        (*fields.values(), insight_id),
    )
    await db.commit()


async def _fail_insight(db: Any, insight_id: Optional[str], code: str) -> None:
    if not insight_id:
        return
    try:
        await _update_insight(db, insight_id, status="failed", error_code=code[:80])
    except Exception as exc:  # pragma: no cover — melhor esforço
        logger.debug("[Proactive] não foi possível marcar falha %s: %s", insight_id, exc)


async def _load_context(db: Any, conversation_id: str, user_msg_id: Optional[str], limit: int = 3) -> list[dict]:
    """Últimas ``limit`` mensagens **anteriores** à do usuário (sem proativas)."""
    try:
        if user_msg_id:
            sql = """SELECT role, content FROM messages
                     WHERE conversation_id = ? AND id <> ?
                       AND COALESCE(kind, 'normal') <> 'proactive'
                       AND created_at <= (SELECT created_at FROM messages WHERE id = ?)
                     ORDER BY created_at DESC LIMIT ?"""
            params: tuple = (conversation_id, user_msg_id, user_msg_id, limit)
        else:
            sql = """SELECT role, content FROM messages
                     WHERE conversation_id = ? AND COALESCE(kind, 'normal') <> 'proactive'
                     ORDER BY created_at DESC LIMIT ?"""
            params = (conversation_id, limit)
        async with db.execute(sql, params) as cur:
            rows = await cur.fetchall()
    except Exception as exc:
        logger.debug("[Proactive] contexto indisponível: %s", exc)
        return []
    return [{"role": r[0], "content": r[1]} for r in reversed(rows)]


async def _notify_status(user_id: str, conversation_id: str, stage: str) -> None:
    try:
        from backend.routers.chat import notify_user_sockets

        await notify_user_sockets(
            user_id, {"type": STATUS_STAGE, "conversation_id": conversation_id, "stage": stage}
        )
    except Exception as exc:  # pragma: no cover — nunca derruba o pipeline
        logger.debug("[Proactive] status não enviado: %s", exc)


# ─────────────────────────────────────────────────────────────────────────────
# Pipeline (F2.2.6)
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class PipelineResult:
    stage: str                 # gate|classify|limits|research|synth|ready|delivered|failed|skipped
    reason: str = ""
    insight_id: Optional[str] = None
    status: Optional[str] = None
    channel: Optional[str] = None
    message_id: Optional[str] = None
    signal: Optional[InterestSignal] = None

    @property
    def created(self) -> bool:
        return self.insight_id is not None


async def run_pipeline(
    user_id: str,
    conversation_id: str,
    user_msg_id: Optional[str],
    user_message: str,
    *,
    web_search_used: bool = False,
    model_id: Optional[str] = None,
    provider_id: Optional[str] = None,
    context_msgs: Optional[Sequence[Any]] = None,
    config: Optional[ProactiveConfig] = None,
    settings: Optional[UserSettings] = None,
    db: Any = None,
    now: Optional[datetime] = None,
) -> PipelineResult:
    """Executa o pipeline completo para uma mensagem. Nunca levanta exceção."""
    from backend.database import get_db

    own_db = db is None
    if own_db:
        db = await get_db()
    holder = _IdHolder()
    try:
        gate_result = gate(user_message, web_search_used=web_search_used)
        if not gate_result.passed:
            return PipelineResult("gate", gate_result.reason)

        config = config or await load_config(db)
        if not config.enabled_global:
            return PipelineResult("skipped", "disabled_global")
        settings = settings or await get_user_settings(db, user_id)
        if not settings.enabled:
            return PipelineResult("skipped", "disabled_user")

        sem = _semaphore_for(config.concurrency)
        async with sem:
            try:
                return await asyncio.wait_for(
                    _run_stages(
                        db, user_id, conversation_id, user_msg_id, user_message,
                        gate_language=gate_result.language, config=config, settings=settings,
                        model_id=model_id, provider_id=provider_id, context_msgs=context_msgs,
                        now=now, holder=holder,
                    ),
                    timeout=config.total_timeout_s,
                )
            except asyncio.TimeoutError:
                await _fail_insight(db, holder.insight_id, "timeout")
                log_stage("pipeline_timeout", insight_id=holder.insight_id, stage="pipeline",
                          latency_ms=config.total_timeout_s * 1000, level=logging.WARNING,
                          conversation_id=conversation_id, error_code="timeout")
                return PipelineResult("failed", "timeout", insight_id=holder.insight_id, status="failed")
    except asyncio.CancelledError:
        # Desligado pelo usuário/admin no meio do caminho (F4.1.5 / F4.4.4)
        await _fail_insight(db, holder.insight_id, "cancelled")
        log_stage("pipeline_cancelled", insight_id=holder.insight_id, stage="pipeline",
                  conversation_id=conversation_id, error_code="cancelled")
        raise
    except Exception as exc:
        await _fail_insight(db, holder.insight_id, f"error:{type(exc).__name__}")
        log_stage("pipeline_error", insight_id=holder.insight_id, stage="pipeline", level=logging.WARNING,
                  conversation_id=conversation_id, error_code=f"error:{type(exc).__name__}")
        return PipelineResult("failed", f"error:{type(exc).__name__}", insight_id=holder.insight_id, status="failed")
    finally:
        if own_db:
            try:
                await db.close()
            except Exception:
                pass


class _IdHolder:
    """Guarda o id do insight criado dentro de ``_run_stages``.

    ``asyncio.wait_for`` cancela a corrotina interna no timeout, então o id
    precisa viver fora dela para o ``status='failed'`` ser gravado.
    """

    __slots__ = ("insight_id",)

    def __init__(self) -> None:
        self.insight_id: Optional[str] = None

    def set(self, insight_id: str) -> None:
        self.insight_id = insight_id


async def _run_stages(
    db: Any,
    user_id: str,
    conversation_id: str,
    user_msg_id: Optional[str],
    user_message: str,
    *,
    gate_language: str,
    config: ProactiveConfig,
    settings: UserSettings,
    model_id: Optional[str],
    provider_id: Optional[str],
    context_msgs: Optional[Sequence[Any]],
    now: Optional[datetime],
    holder: _IdHolder,
) -> PipelineResult:
    # ── 1. Classificador ────────────────────────────────────────────────
    started = time.perf_counter()
    try:
        provider, model_name, source = await resolve_detector_model(
            db, user_id, provider_id or "", model_id or ""
        )
    except Exception as exc:
        logger.debug("[Proactive] sem modelo para o detector: %s", exc)
        return PipelineResult("classify", "no_detector_model")
    if context_msgs is None:
        context_msgs = await _load_context(db, conversation_id, user_msg_id)
    signal, meta = await classify_with_meta(
        user_message, context_msgs, provider=provider, model_name=model_name,
        language_hint=gate_language if gate_language != "unknown" else None, now=now,
    )
    decision = evaluate(signal, settings.sensitivity)
    if not decision.accepted:
        return PipelineResult("classify", decision.reason, signal=signal)
    if signal.category not in settings.categories:
        return PipelineResult("classify", "category_disabled", signal=signal)
    latency_detect_ms = (time.perf_counter() - started) * 1000
    detector_label = f"{source}:{model_name}"
    tokens_in = meta.prompt_chars // 4
    tokens_out = meta.response_chars // 4

    # ── 2. Limites ──────────────────────────────────────────────────────
    topic_hash = compute_topic_hash(signal.topic, signal.entities)
    limits = await check_limits(db, user_id, conversation_id, topic_hash, config)
    if not limits.allowed:
        return PipelineResult("limits", limits.reason, signal=signal)

    insight_id = await _insert_insight(
        db, user_id=user_id, conversation_id=conversation_id, source_message_id=user_msg_id,
        signal=signal, topic_hash=topic_hash, detector_model=detector_label,
        latency_detect_ms=latency_detect_ms,
    )
    holder.set(insight_id)
    await _update_insight(db, insight_id, tokens_in=tokens_in, tokens_out=tokens_out)
    log_stage("detected", insight_id=insight_id, stage="detect", latency_ms=latency_detect_ms,
              category=signal.category, confidence=round(float(signal.interest or 0.0), 2),
              detector=detector_label)

    # ── 3. Pesquisa ─────────────────────────────────────────────────────
    await _update_insight(db, insight_id, status="researching")
    await _notify_status(user_id, conversation_id, "researching")
    research = await researcher.research(
        signal, db, topic_hash=topic_hash, timeout=config.research_timeout_s, now=now
    )
    await _update_insight(
        db, insight_id, latency_research_ms=int(research.elapsed_ms), query=research.query or signal.suggested_query
    )
    if not research.ok:
        code = research.error or "no_results"
        await _fail_insight(db, insight_id, code)
        log_stage("research_failed", insight_id=insight_id, stage="research", latency_ms=research.elapsed_ms,
                  level=logging.WARNING, error_code=code)
        return PipelineResult("research", code, insight_id=insight_id, status="failed", signal=signal)
    log_stage("researched", insight_id=insight_id, stage="research", latency_ms=research.elapsed_ms,
              sources=len(research.sources), cache_hit=research.cache_hit)

    # ── 4. Síntese ──────────────────────────────────────────────────────
    await _notify_status(user_id, conversation_id, "synthesizing")
    try:
        synth_provider, synth_model, synth_source = await synthesizer.resolve_synth_model(
            db, user_id, provider_id, model_id, config
        )
    except synthesizer.NoSynthModel:
        await _fail_insight(db, insight_id, "no_synth_model")
        log_stage("synth_failed", insight_id=insight_id, stage="synth", level=logging.WARNING,
                  error_code="no_synth_model")
        return PipelineResult("synth", "no_synth_model", insight_id=insight_id, status="failed", signal=signal)
    except Exception as exc:
        await _fail_insight(db, insight_id, f"synth_model:{type(exc).__name__}")
        log_stage("synth_failed", insight_id=insight_id, stage="synth", level=logging.WARNING,
                  error_code=f"synth_model:{type(exc).__name__}")
        return PipelineResult("synth", "synth_model_error", insight_id=insight_id, status="failed", signal=signal)

    synthesis = await synthesizer.synthesize(
        signal, research.sources, provider=synth_provider, model_name=synth_model,
        user_message=user_message, timeout=config.synth_timeout_s, now=now, model_source=synth_source,
    )
    synth_label = await synthesizer.model_label(db, synth_source, synth_model, model_id)
    tokens_in += synthesis.prompt_chars // 4
    tokens_out += synthesis.response_chars // 4
    await _record_benchmark(
        detector_label, synth_label, success=synthesis.ok,
        latency_ms=latency_detect_ms + research.elapsed_ms + synthesis.latency_ms,
        tokens_in=tokens_in, tokens_out=tokens_out,
        phases={"detect": latency_detect_ms, "research": research.elapsed_ms, "synth": synthesis.latency_ms},
        error=synthesis.error,
    )
    if not synthesis.ok:
        await _update_insight(db, insight_id, synth_model=synth_label, latency_synth_ms=int(synthesis.latency_ms),
                              tokens_in=tokens_in, tokens_out=tokens_out)
        await _fail_insight(db, insight_id, synthesis.error or "synth_parse")
        log_stage("synth_failed", insight_id=insight_id, stage="synth", latency_ms=synthesis.latency_ms,
                  level=logging.WARNING, error_code=synthesis.error or "synth_parse")
        return PipelineResult("synth", synthesis.error or "synth_parse", insight_id=insight_id,
                              status="failed", signal=signal)

    expires_at = synthesizer.compute_expires_at(
        signal.category, event_date=synthesis.event_date,
        news_hours=config.expiry_news_hours, default_days=config.expiry_default_days,
    )
    sources_payload = research.sources
    if synthesis.used_source_urls:
        # Mantém a ordem original, mas prioriza as fontes realmente usadas
        used = set(synthesis.used_source_urls)
        sources_payload = [s for s in research.sources if s.url in used] + [
            s for s in research.sources if s.url not in used
        ]
    await _update_insight(
        db, insight_id,
        status="ready",
        synthesized_text=synthesis.text,
        reason_line=synthesis.reason_line,
        sources_json=json.dumps([s.to_dict() for s in sources_payload], ensure_ascii=False),
        follow_ups_json=json.dumps(synthesis.follow_ups, ensure_ascii=False),
        synth_model=synth_label,
        latency_synth_ms=int(synthesis.latency_ms),
        tokens_in=tokens_in,
        tokens_out=tokens_out,
        expires_at=expires_at,
        ready_at=datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S"),  # mesma base de datetime('now')
    )
    log_stage("ready", insight_id=insight_id, stage="synth", latency_ms=synthesis.latency_ms,
              total_ms=latency_detect_ms + research.elapsed_ms + synthesis.latency_ms,
              tokens_in=tokens_in, tokens_out=tokens_out, synth=synth_label)
    expired = await enforce_pending_limit(db, user_id, config.max_pending, keep_id=insight_id)
    if expired:
        log_stage("pending_limit", insight_id=insight_id, stage="deliver", expired=len(expired))

    # ── 5. Entrega ──────────────────────────────────────────────────────
    insight_row = await delivery.load_insight(db, insight_id)
    if insight_row is None:
        return PipelineResult("ready", "ready", insight_id=insight_id, status="ready", signal=signal)
    outcome = await delivery.deliver(insight_row, db)
    log_stage("delivery", insight_id=insight_id, stage="deliver", channel=outcome.channel or "pending",
              reason=outcome.reason or None)
    if outcome.channel:
        return PipelineResult("delivered", outcome.reason or "delivered", insight_id=insight_id,
                              status="delivered", channel=outcome.channel,
                              message_id=outcome.message_id, signal=signal)
    return PipelineResult("ready", outcome.reason or "pending", insight_id=insight_id, status="ready", signal=signal)


async def _record_benchmark(
    detector_label: str,
    synth_label: str,
    *,
    success: bool,
    latency_ms: float,
    tokens_in: int,
    tokens_out: int,
    phases: dict[str, float],
    error: str = "",
) -> None:
    """F5.2.4: custo/latência no ``task_benchmark_manager`` (em memória, não bloqueia)."""
    try:
        from backend.metrics import task_benchmark_manager

        provider_id, _, model_id = (synth_label or detector_label or "").partition("/")
        await task_benchmark_manager.record_task_async(
            task_type="proactive",
            latency_ms=latency_ms,
            model_id=model_id or synth_label or detector_label,
            provider_id=provider_id or "proactive",
            success=success,
            calls_made=2,
            tokens_input=tokens_in,
            tokens_output=tokens_out,
            errors=[error] if error else None,
            phase_latencies={k: round(v, 1) for k, v in phases.items()},
            persist_to_disk=False,
        )
    except Exception as exc:  # pragma: no cover — telemetria nunca derruba o pipeline
        logger.debug("[Proactive] benchmark não registrado: %s", exc)


# ─────────────────────────────────────────────────────────────────────────────
# Agendamento (F2.2.5)
# ─────────────────────────────────────────────────────────────────────────────

async def schedule_proactive_check(
    db: Any,
    user_id: str,
    conversation_id: str,
    user_msg_id: Optional[str],
    user_message: str,
    *,
    web_search_used: bool = False,
    model_id: Optional[str] = None,
    provider_id: Optional[str] = None,
) -> Optional[asyncio.Task]:
    """Agenda a verificação proativa para a mensagem do usuário.

    Barato por construção: porteiro léxico inline, duas leituras (config com
    cache de 60 s + settings do usuário) e ``create_task`` guardada em
    ``_tasks`` (``add_done_callback(discard)``). Devolve a task ou ``None``.
    """
    if not user_id or not conversation_id or not user_message:
        return None
    try:
        gate_result = gate(user_message, web_search_used=web_search_used)
        if not gate_result.passed:
            return None
        config = await load_config(db)
        if not config.enabled_global:
            return None
        settings = await get_user_settings(db, user_id)
        if not settings.enabled:
            return None
    except Exception as exc:
        logger.debug("[Proactive] agendamento abortado: %s", exc)
        return None

    return track_task(
        run_pipeline(
            user_id, conversation_id, user_msg_id, user_message,
            web_search_used=web_search_used, model_id=model_id, provider_id=provider_id,
            config=config, settings=settings,
        ),
        name=f"proactive:{conversation_id[:8]}",
        user_id=user_id,
    )


async def manual_investigate(
    user_id: str,
    prompt: str,
    *,
    category: Optional[str] = "news",
    conversation_id: Optional[str] = None,
    db: Any = None,
) -> tuple[str, str]:
    """F7.2.4 — Disparo manual de investigação proativa (Hub).

    Cria ou reutiliza a conversa, insere insight em 'researching',
    executa pesquisa e síntese em background via track_task,
    e entrega via WebSocket/delivery.
    Devolve (insight_id, conversation_id).
    """
    own_db = db is None
    if own_db:
        from backend.database import get_db

        db = await get_db()
    try:
        conv_id = conversation_id
        if not conv_id:
            conv_id = str(uuid.uuid4())
            title = f"✦ {prompt[:40].strip()}"
            await db.execute(
                "INSERT INTO conversations (id, user_id, title, created_at, updated_at) VALUES (?, ?, ?, datetime('now'), datetime('now'))",
                (conv_id, user_id, title),
            )
            await db.commit()

        config = await load_config(db)
        signal = InterestSignal(
            interest=1.0,
            topic=prompt[:80].strip(),
            category=category or "news",
            suggested_query=prompt.strip(),
            reason="Investigação manual solicitada pelo usuário no Hub.",
            entities=[],
            language="pt-BR",
        )
        topic_hash = compute_topic_hash(signal.topic, signal.entities)
        insight_id = await _insert_insight(
            db,
            user_id=user_id,
            conversation_id=conv_id,
            source_message_id=None,
            signal=signal,
            topic_hash=topic_hash,
            detector_model="manual:hub",
            latency_detect_ms=0,
        )

        async def _execute_manual_investigation():
            from backend.database import get_db

            task_db = await get_db()
            try:
                await _update_insight(task_db, insight_id, status="researching")
                await _notify_status(user_id, conv_id, "researching")
                research = await researcher.research(
                    signal, task_db, topic_hash=topic_hash, timeout=config.research_timeout_s, now=datetime.now()
                )
                await _update_insight(
                    task_db, insight_id, latency_research_ms=int(research.elapsed_ms), query=research.query or signal.suggested_query
                )
                if not research.ok:
                    code = research.error or "no_results"
                    await _fail_insight(task_db, insight_id, code)
                    return

                await _notify_status(user_id, conv_id, "synthesizing")
                try:
                    synth_provider, synth_model, synth_source = await synthesizer.resolve_synth_model(
                        task_db, user_id, None, None, config
                    )
                except Exception as exc:
                    await _fail_insight(task_db, insight_id, f"synth_model:{type(exc).__name__}")
                    return

                synthesis = await synthesizer.synthesize(
                    signal, research.sources, provider=synth_provider, model_name=synth_model,
                    user_message=prompt, timeout=config.synth_timeout_s, now=datetime.now(), model_source=synth_source,
                )
                synth_label = await synthesizer.model_label(task_db, synth_source, synth_model, None)
                if not synthesis.ok:
                    await _fail_insight(task_db, insight_id, synthesis.error or "synth_parse")
                    return

                expires_at = synthesizer.compute_expires_at(
                    signal.category, event_date=synthesis.event_date,
                    news_hours=config.expiry_news_hours, default_days=config.expiry_default_days,
                )
                sources_payload = research.sources
                if synthesis.used_source_urls:
                    used = set(synthesis.used_source_urls)
                    sources_payload = [s for s in research.sources if s.url in used] + [
                        s for s in research.sources if s.url not in used
                    ]
                await _update_insight(
                    task_db, insight_id,
                    status="ready",
                    synthesized_text=synthesis.text,
                    reason_line=synthesis.reason_line,
                    sources_json=json.dumps([s.to_dict() for s in sources_payload], ensure_ascii=False),
                    follow_ups_json=json.dumps(synthesis.follow_ups, ensure_ascii=False),
                    synth_model=synth_label,
                    latency_synth_ms=int(synthesis.latency_ms),
                    expires_at=expires_at,
                    ready_at=datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S"),
                )
                await enforce_pending_limit(task_db, user_id, config.max_pending, keep_id=insight_id)

                insight_row = await delivery.load_insight(task_db, insight_id)
                if insight_row:
                    await delivery.deliver(insight_row, task_db)
            except Exception as exc:
                logger.warning("[Proactive] erro na investigação manual %s: %s", insight_id, exc)
                try:
                    await _fail_insight(task_db, insight_id, f"error:{type(exc).__name__}")
                except Exception:
                    pass
            finally:
                await task_db.close()

        track_task(
            _execute_manual_investigation(),
            name=f"manual:{insight_id[:8]}",
            user_id=user_id,
        )
        return insight_id, conv_id
    finally:
        if own_db:
            await db.close()
