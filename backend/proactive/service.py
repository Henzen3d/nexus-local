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

# ─────────────────────────────────────────────────────────────────────────────
# Tasks em voo e turnos ativos
# ─────────────────────────────────────────────────────────────────────────────

_tasks: set[asyncio.Task] = set()
_active_turns: dict[str, int] = {}
_turn_events: dict[str, asyncio.Event] = {}
_semaphores: dict[int, asyncio.Semaphore] = {}


def pending_tasks() -> int:
    return len(_tasks)


def track_task(coro: Any, *, name: str = "proactive") -> asyncio.Task:
    """``create_task`` com referência guardada (nunca uma task solta — F2.2.5)."""
    task = asyncio.create_task(coro, name=name)
    _tasks.add(task)
    task.add_done_callback(_tasks.discard)
    return task


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
            WHERE status IN ({placeholders}) AND created_at < datetime('now', ?)""",
        (*TERMINAL_STATUSES, f"-{PURGE_AFTER_DAYS} days"),
    )
    purged = cur.rowcount or 0
    await db.commit()
    if expired or stuck or purged:
        logger.info("[Proactive] housekeeping: expired=%d stuck=%d purged=%d", expired, stuck, purged)
    return {"expired": expired, "stuck": stuck, "purged": purged}


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
        f"UPDATE proactive_insights SET {assignments} WHERE id = ?",
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
                logger.warning("[Proactive] pipeline excedeu %.0fs (conv=%s)", config.total_timeout_s, conversation_id)
                return PipelineResult("failed", "timeout", insight_id=holder.insight_id, status="failed")
    except Exception as exc:
        await _fail_insight(db, holder.insight_id, f"error:{type(exc).__name__}")
        logger.warning("[Proactive] pipeline falhou (conv=%s): %s", conversation_id, exc)
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
        logger.info("[Proactive] pesquisa sem resultado (%s) para %r", code, signal.topic)
        return PipelineResult("research", code, insight_id=insight_id, status="failed", signal=signal)

    # ── 4. Síntese ──────────────────────────────────────────────────────
    await _notify_status(user_id, conversation_id, "synthesizing")
    try:
        synth_provider, synth_model, synth_source = await synthesizer.resolve_synth_model(
            db, user_id, provider_id, model_id, config
        )
    except synthesizer.NoSynthModel:
        await _fail_insight(db, insight_id, "no_synth_model")
        return PipelineResult("synth", "no_synth_model", insight_id=insight_id, status="failed", signal=signal)
    except Exception as exc:
        await _fail_insight(db, insight_id, f"synth_model:{type(exc).__name__}")
        return PipelineResult("synth", "synth_model_error", insight_id=insight_id, status="failed", signal=signal)

    synthesis = await synthesizer.synthesize(
        signal, research.sources, provider=synth_provider, model_name=synth_model,
        user_message=user_message, timeout=config.synth_timeout_s, now=now, model_source=synth_source,
    )
    synth_label = await synthesizer.model_label(db, synth_source, synth_model, model_id)
    if not synthesis.ok:
        await _update_insight(db, insight_id, synth_model=synth_label, latency_synth_ms=int(synthesis.latency_ms))
        await _fail_insight(db, insight_id, synthesis.error or "synth_parse")
        return PipelineResult("synth", synthesis.error or "synth_parse", insight_id=insight_id,
                              status="failed", signal=signal)

    expires_at = synthesizer.compute_expires_at(signal.category, event_date=synthesis.event_date)
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
        expires_at=expires_at,
        ready_at=datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S"),  # mesma base de datetime('now')
    )
    expired = await enforce_pending_limit(db, user_id, config.max_pending, keep_id=insight_id)
    if expired:
        logger.info("[Proactive] %d insight(s) pendente(s) expirado(s) por limite", len(expired))

    # ── 5. Entrega ──────────────────────────────────────────────────────
    insight_row = await delivery.load_insight(db, insight_id)
    if insight_row is None:
        return PipelineResult("ready", "ready", insight_id=insight_id, status="ready", signal=signal)
    outcome = await delivery.deliver(insight_row, db)
    if outcome.channel:
        return PipelineResult("delivered", outcome.reason or "delivered", insight_id=insight_id,
                              status="delivered", channel=outcome.channel,
                              message_id=outcome.message_id, signal=signal)
    return PipelineResult("ready", outcome.reason or "pending", insight_id=insight_id, status="ready", signal=signal)


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
    )
