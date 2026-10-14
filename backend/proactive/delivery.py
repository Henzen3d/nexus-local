"""Entrega do insight — Fase 3 (F3.2): inline, toast, fila ``pending`` e retorno.

Máquina de estados de ``01-decisao-entrega-e-presenca.md`` §2.2:

* usuário **ativo na conversa de origem** ⇒ persiste a mensagem
  (``messages.kind='proactive'``) e envia ``proactive_insight`` com
  ``channel_hint='inline'``;
* usuário **ativo em outra conversa/tela** ⇒ persiste e envia com
  ``channel_hint='toast'`` (o cliente mostra toast com ação *Ver* + badge);
* **ausente** (idle/hidden/offline) ⇒ ``pending``: nada é persistido nem
  enviado; o insight continua ``ready`` (``channel=NULL``) até o retorno.

**Retorno** (:func:`flush_pending`, disparado pelo controller do WS quando a
presença transita para ``active``, um socket novo conecta ou o usuário troca de
conversa):

* abriu a **conversa de origem** ⇒ persiste com o prefixo de retorno
  ("Enquanto você estava fora…"), ``channel='pending_inline'`` e envia
  ``proactive_insight{channel_hint:'inline'}``;
* está na **tela inicial / outra conversa / outra tela** ⇒ envia
  ``proactive_pending{insights:[…]}`` (o cliente decide: cartão de retorno ou
  toast agrupado + badge); ``channel`` continua ``NULL`` até o usuário agir.

Invariantes: nunca interromper um turno em andamento (``service.is_turn_active``);
idempotência por ``delivered_message_id`` (a reivindicação é atômica — a
mensagem e o ``UPDATE … WHERE delivered_message_id IS NULL`` ficam na mesma
transação); máximo ``max_pending`` itens; vencidos (``expires_at``) nunca são
entregues.
"""
from __future__ import annotations

import asyncio
import json
import uuid
from dataclasses import dataclass
from typing import Any, Optional

from backend.logging_config import get_logger
from backend.proactive import presence

logger = get_logger(__name__)

WAIT_TURN_TIMEOUT_S = 20.0

INSIGHT_COLUMNS = (
    "id", "user_id", "conversation_id", "source_message_id", "delivered_message_id",
    "spawned_conversation_id",
    "topic", "topic_hash", "entities_json", "category", "confidence", "query", "status",
    "channel", "synthesized_text", "reason_line", "sources_json", "follow_ups_json",
    "language", "emotion", "error_code", "detector_model", "synth_model",
    "created_at", "ready_at", "delivered_at", "seen_at", "expires_at",
)

# §3.4 — "Ao vivo": "Fiquei curioso com *{topic}* e fui pesquisar: {resumo}. {gancho}"
LIVE_PREFIX = {
    "pt-BR": "Fiquei curioso com **{topic}** e fui pesquisar: ",
    "en-US": "I got curious about **{topic}** and looked it up: ",
    "es-ES": "Me dio curiosidad **{topic}** y fui a investigar: ",
}
# §3.4 — "No retorno (mesma conversa)"
RETURN_PREFIX = {
    "pt-BR": "Enquanto você estava fora, pesquisei sobre **{topic}**: ",
    "en-US": "While you were away, I looked into **{topic}**: ",
    "es-ES": "Mientras no estabas, investigué sobre **{topic}**: ",
}
# §3.4 — "Chat novo" (neutro quanto a gênero: "demonstrou interesse")
NEW_CHAT_PREFIX = {
    "pt-BR": "Oi! Na nossa conversa **«{origin_title}»** você demonstrou interesse por **{topic}**, então fui pesquisar: ",
    "en-US": "Hi! In our chat **«{origin_title}»** you seemed interested in **{topic}**, so I looked it up: ",
    "es-ES": "¡Hola! En nuestra conversación **«{origin_title}»** mostraste interés por **{topic}**, así que fui a investigar: ",
}
PREFIXES = {"live": LIVE_PREFIX, "return": RETURN_PREFIX, "new_chat": NEW_CHAT_PREFIX}

#: Status que ainda podem ser entregues no retorno.
PENDING_STATUSES = ("ready",)


@dataclass
class DeliveryOutcome:
    channel: Optional[str]          # inline | toast | pending_inline | new_chat | None (pendente)
    message_id: Optional[str] = None
    reason: str = ""

    @property
    def delivered(self) -> bool:
        return self.channel is not None


@dataclass
class PresenceContext:
    """Onde o usuário está no momento do retorno (vem do evento ``presence``)."""

    view: Optional[str] = None
    conversation_id: Optional[str] = None

    @property
    def in_chat(self) -> bool:
        return (self.view or "chat") == "chat"

    def is_in(self, conversation_id: str) -> bool:
        return self.in_chat and bool(self.conversation_id) and self.conversation_id == conversation_id


@dataclass
class FlushResult:
    delivered: list[str]            # insight ids persistidos inline (pending_inline)
    pending: list[str]              # insight ids anunciados em proactive_pending
    expired: int = 0

    @property
    def total(self) -> int:
        return len(self.delivered) + len(self.pending)


def _loads(raw: Any, default: Any) -> Any:
    if raw is None or raw == "":
        return default
    if isinstance(raw, (list, dict)):
        return raw
    try:
        return json.loads(raw)
    except (TypeError, ValueError):
        return default


def _language(insight: dict) -> str:
    lang = insight.get("language") or ""
    return lang if lang in LIVE_PREFIX else "pt-BR"


def build_message_content(insight: dict, *, mode: str = "live", origin_title: Optional[str] = None) -> str:
    """Conteúdo persistido da bolha: prefixo localizado + texto sintetizado.

    ``mode``: ``live`` (ao vivo), ``return`` (mesma conversa, no retorno) ou
    ``new_chat`` (1ª mensagem do chat iniciado por "Me conta aqui").
    """
    templates = PREFIXES.get(mode, LIVE_PREFIX)
    topic = (insight.get("topic") or "").strip()
    title = (origin_title or "").strip() or "…"
    prefix = templates[_language(insight)].format(topic=topic, origin_title=title)
    text = (insight.get("synthesized_text") or "").strip()
    return f"{prefix}{text}".strip()


def public_sources(insight: dict) -> list[dict[str, str]]:
    """``[{title, url, domain}]`` a partir de ``sources_json`` (contrato §3.2)."""
    out: list[dict[str, str]] = []
    for item in _loads(insight.get("sources_json"), []) or []:
        if not isinstance(item, dict) or not item.get("url"):
            continue
        url = str(item["url"])
        domain = str(item.get("domain") or "")
        if not domain:
            from backend.proactive.researcher import domain_of

            domain = domain_of(url)
        out.append({"title": str(item.get("title") or domain), "url": url, "domain": domain})
    return out


def build_insight_payload(insight: dict, *, message_id: Optional[str] = None, channel_hint: str = "inline") -> dict:
    """Evento ``proactive_insight`` (contrato §3.2)."""
    return {
        "type": "proactive_insight",
        "insight": insight_public_dict(insight, message_id=message_id),
        "channel_hint": channel_hint,
    }


def build_pending_payload(insights: list[dict]) -> dict:
    """Evento ``proactive_pending`` (contrato §3.2) — mesmo shape, ``status='ready'``, ≤ 3."""
    return {"type": "proactive_pending", "insights": [insight_public_dict(i) for i in insights]}


def insight_public_dict(insight: dict, *, message_id: Optional[str] = None) -> dict:
    """Shape público do insight (sem campos internos), reutilizado pelo GET da conversa e por ``/pending``."""
    origin = None
    if insight.get("spawned_conversation_id") or insight.get("origin_title") is not None:
        origin = {
            "conversation_id": insight["conversation_id"],
            "title": insight.get("origin_title") or "",
        }
    return {
        "id": insight["id"],
        "conversation_id": insight["conversation_id"],
        "message_id": message_id or insight.get("delivered_message_id"),
        "topic": insight.get("topic") or "",
        "category": insight.get("category") or "other",
        "text": insight.get("synthesized_text") or "",
        "reason_line": insight.get("reason_line") or "",
        "sources": public_sources(insight),
        "follow_ups": [f for f in (_loads(insight.get("follow_ups_json"), []) or []) if isinstance(f, str)],
        "status": insight.get("status"),
        "channel": insight.get("channel"),
        "language": insight.get("language"),
        "expires_at": insight.get("expires_at"),
        "created_at": insight.get("created_at"),
        "ready_at": insight.get("ready_at"),
        "spawned_conversation_id": insight.get("spawned_conversation_id"),
        "origin": origin,
    }


async def load_insight(db: Any, insight_id: str) -> Optional[dict]:
    async with db.execute(
        f"SELECT {', '.join(INSIGHT_COLUMNS)} FROM proactive_insights WHERE id = ?",
        (insight_id,),
    ) as cur:
        row = await cur.fetchone()
    if not row:
        return None
    return dict(zip(INSIGHT_COLUMNS, row))


async def load_pending(db: Any, user_id: str, *, limit: int = 3) -> list[dict]:
    """Insights ``ready`` não entregues do usuário (mais antigos primeiro), já sem os vencidos."""
    async with db.execute(
        f"""SELECT {', '.join(INSIGHT_COLUMNS)} FROM proactive_insights
            WHERE user_id = ? AND status = 'ready' AND delivered_message_id IS NULL
              AND (expires_at IS NULL OR expires_at >= datetime('now'))
            ORDER BY COALESCE(ready_at, created_at) ASC, rowid ASC
            LIMIT ?""",
        (user_id, max(0, int(limit))),
    ) as cur:
        rows = await cur.fetchall()
    return [dict(zip(INSIGHT_COLUMNS, r)) for r in rows]


async def attach_origin_titles(db: Any, insights: list[dict]) -> list[dict]:
    """Preenche ``origin_title`` (título da conversa de origem) para o payload público."""
    ids = {i["conversation_id"] for i in insights if i.get("conversation_id")}
    if not ids:
        return insights
    placeholders = ",".join("?" for _ in ids)
    async with db.execute(
        f"SELECT id, title FROM conversations WHERE id IN ({placeholders})", tuple(ids)
    ) as cur:
        titles = {r[0]: r[1] for r in await cur.fetchall()}
    for i in insights:
        i.setdefault("origin_title", titles.get(i["conversation_id"]) or "")
    return insights


# ─────────────────────────────────────────────────────────────────────────────
# Persistência atômica (F2.5.2 + F2.5.6 / F3.6.6)
# ─────────────────────────────────────────────────────────────────────────────

_user_locks: dict[str, asyncio.Lock] = {}


def _lock_for(user_id: str) -> asyncio.Lock:
    lock = _user_locks.get(user_id)
    if lock is None:
        lock = _user_locks[user_id] = asyncio.Lock()
    return lock


def _model_labels(insight: dict) -> tuple[Optional[str], Optional[str]]:
    model_label = insight.get("synth_model") or None
    provider_label = model_label.split("/")[0] if model_label and "/" in model_label else None
    return model_label, provider_label


async def persist_proactive_message(
    db: Any,
    insight: dict,
    *,
    mode: str = "live",
    conversation_id: Optional[str] = None,
    origin_title: Optional[str] = None,
    commit: bool = True,
) -> str:
    """Mensagem do assistente ``kind='proactive'`` + ``updated_at`` (sem mexer no título)."""
    message_id = str(uuid.uuid4())
    target_conv = conversation_id or insight["conversation_id"]
    model_label, provider_label = _model_labels(insight)
    await db.execute(
        """INSERT INTO messages (id, conversation_id, role, content, model_id, provider, kind, proactive_insight_id)
           VALUES (?, ?, 'assistant', ?, ?, ?, 'proactive', ?)""",
        (message_id, target_conv, build_message_content(insight, mode=mode, origin_title=origin_title),
         model_label, provider_label, insight["id"]),
    )
    await db.execute(
        "UPDATE conversations SET updated_at = datetime('now') WHERE id = ?",
        (target_conv,),
    )
    if commit:
        await db.commit()
    return message_id


async def claim_and_persist(
    db: Any,
    insight: dict,
    *,
    channel: str,
    mode: str,
    conversation_id: Optional[str] = None,
    origin_title: Optional[str] = None,
) -> Optional[str]:
    """Insere a mensagem e reivindica o insight **na mesma transação**.

    Devolve o ``message_id`` ou ``None`` se outro processo/aba já entregou
    (``delivered_message_id`` deixou de ser ``NULL``) — nesse caso a mensagem
    inserida é desfeita pelo ``rollback``.
    """
    async with _lock_for(insight["user_id"]):
        try:
            message_id = await persist_proactive_message(
                db, insight, mode=mode, conversation_id=conversation_id,
                origin_title=origin_title, commit=False,
            )
            cur = await db.execute(
                """UPDATE proactive_insights
                    SET status = 'delivered', channel = ?, delivered_message_id = ?,
                        delivered_at = datetime('now')
                    WHERE id = ? AND delivered_message_id IS NULL
                      AND status IN ('ready', 'delivered')""",
                (channel, message_id, insight["id"]),
            )
            if (cur.rowcount or 0) != 1:
                await db.rollback()
                return None
            await db.commit()
            return message_id
        except Exception:
            try:
                await db.rollback()
            except Exception:
                pass
            raise


async def _notify(user_id: str, payload: dict, ws: Any = None) -> None:
    if ws is not None:
        await ws.send_json(payload)
        return
    from backend.routers.chat import notify_user_sockets

    await notify_user_sockets(user_id, payload)


# ─────────────────────────────────────────────────────────────────────────────
# Decisão e entrega ao vivo (F2.5 / F3.2.1)
# ─────────────────────────────────────────────────────────────────────────────

def decide(insight: dict) -> str:
    """``inline`` | ``toast`` | ``pending`` conforme a presença atual (§2.2)."""
    user_id = insight["user_id"]
    if not presence.has_active_socket(user_id):
        return "pending"
    if presence.is_active_in_conversation(user_id, insight["conversation_id"]):
        return "inline"
    return "toast"


def _is_expired(insight: dict) -> bool:
    """``expires_at`` é gravado em UTC (mesma base de ``datetime('now')`` no SQLite)."""
    exp = insight.get("expires_at")
    if not exp:
        return False
    from datetime import datetime, timezone

    try:
        when = datetime.fromisoformat(str(exp).replace("Z", "").replace("T", " "))
    except ValueError:
        return False
    return when < datetime.now(timezone.utc).replace(tzinfo=None)


async def deliver(insight: dict, db: Any, *, wait_turn_timeout: float = WAIT_TURN_TIMEOUT_S) -> DeliveryOutcome:
    """Decide e executa a entrega ao vivo. Idempotente (F2.5.6)."""
    from backend.proactive import service

    if insight.get("delivered_message_id"):
        return DeliveryOutcome(insight.get("channel") or "inline", insight["delivered_message_id"], "already_delivered")
    if insight.get("status") not in ("ready", "delivered"):
        return DeliveryOutcome(None, None, f"status_{insight.get('status')}")
    if _is_expired(insight):
        await db.execute(
            "UPDATE proactive_insights SET status = 'expired' WHERE id = ? AND status = 'ready'", (insight["id"],)
        )
        await db.commit()
        return DeliveryOutcome(None, None, "expired")

    user_id = insight["user_id"]
    conversation_id = insight["conversation_id"]

    channel = decide(insight)
    if channel == "pending":
        return DeliveryOutcome(None, None, "absent")

    # Não interromper um turno em andamento na conversa de origem (F2.5.4)
    if service.is_turn_active(conversation_id):
        freed = await service.wait_turn_end(conversation_id, timeout=wait_turn_timeout)
        if not freed:
            return DeliveryOutcome(None, None, "turn_busy")
        channel = decide(insight)
        if channel == "pending":
            return DeliveryOutcome(None, None, "absent")

    message_id = await claim_and_persist(db, insight, channel=channel, mode="live")
    if message_id is None:
        return DeliveryOutcome(None, None, "already_delivered")
    insight = {**insight, "status": "delivered", "channel": channel, "delivered_message_id": message_id}

    try:
        await _notify(user_id, build_insight_payload(insight, message_id=message_id, channel_hint=channel))
    except Exception as exc:  # mensagem já persistida; o cliente a verá ao recarregar
        logger.warning("[Proactive] falha ao notificar socket (insight=%s): %s", insight["id"], exc)
        return DeliveryOutcome(channel, message_id, "notify_failed")
    return DeliveryOutcome(channel, message_id, "delivered")


# ─────────────────────────────────────────────────────────────────────────────
# Retorno (F3.2.3 / F3.2.5)
# ─────────────────────────────────────────────────────────────────────────────

async def flush_pending(
    user_id: str,
    ws: Any = None,
    context: Optional[PresenceContext] = None,
    *,
    db: Any = None,
    max_pending: Optional[int] = None,
) -> FlushResult:
    """Entrega pendências no retorno do usuário.

    * expira vencidos; carrega ``ready`` restantes (≤ ``max_pending``);
    * item cuja conversa de origem está aberta no socket ⇒ ``pending_inline``
      (mensagem com prefixo de retorno + ``proactive_insight`` para todos os
      sockets do usuário — multi-aba recebe o mesmo ``message_id``);
    * demais ⇒ um único ``proactive_pending`` para o socket que voltou
      (ou para todos, quando ``ws`` é ``None``).
    """
    from backend.proactive import service
    from backend.proactive.config import load_config

    own_db = db is None
    if own_db:
        from backend.database import get_db

        db = await get_db()
    try:
        config = await load_config(db)
        limit = int(max_pending if max_pending is not None else config.max_pending)
        expired = await service.expire_overdue(db, user_id)
        pending = await load_pending(db, user_id, limit=limit)
        if not pending:
            return FlushResult([], [], expired)
        await attach_origin_titles(db, pending)
        ctx = context or PresenceContext()

        delivered: list[str] = []
        remaining: list[dict] = []
        for insight in pending:
            if ctx.is_in(insight["conversation_id"]):
                if service.is_turn_active(insight["conversation_id"]):
                    freed = await service.wait_turn_end(insight["conversation_id"], timeout=WAIT_TURN_TIMEOUT_S)
                    if not freed:
                        remaining.append(insight)
                        continue
                message_id = await claim_and_persist(db, insight, channel="pending_inline", mode="return")
                if message_id is None:
                    continue  # outra aba/processo já entregou
                delivered.append(insight["id"])
                payload = build_insight_payload(
                    {**insight, "status": "delivered", "channel": "pending_inline"},
                    message_id=message_id, channel_hint="inline",
                )
                try:
                    await _notify(user_id, payload)
                except Exception as exc:
                    logger.warning("[Proactive] falha ao notificar retorno (insight=%s): %s", insight["id"], exc)
            else:
                remaining.append(insight)

        if remaining:
            try:
                await _notify(user_id, build_pending_payload(remaining), ws=ws)
            except Exception as exc:
                logger.warning("[Proactive] falha ao enviar proactive_pending (user=%s): %s", user_id, exc)
        return FlushResult(delivered, [i["id"] for i in remaining], expired)
    finally:
        if own_db:
            await db.close()


async def pending_for_api(db: Any, user_id: str, *, max_pending: Optional[int] = None) -> list[dict]:
    """``GET /api/proactive/pending`` (F3.2.4): mesmo conteúdo do flush, com expiração aplicada."""
    from backend.proactive import service
    from backend.proactive.config import load_config

    config = await load_config(db)
    limit = int(max_pending if max_pending is not None else config.max_pending)
    await service.expire_overdue(db, user_id)
    pending = await load_pending(db, user_id, limit=limit)
    await attach_origin_titles(db, pending)
    return [insight_public_dict(i) for i in pending]


# ─────────────────────────────────────────────────────────────────────────────
# "Me conta aqui" (F3.3)
# ─────────────────────────────────────────────────────────────────────────────

NEW_CHAT_TITLE_MAX = 60


def new_chat_title(topic: str) -> str:
    title = " ".join((topic or "").split()).strip() or "✦"
    if len(title) > NEW_CHAT_TITLE_MAX:
        title = title[: NEW_CHAT_TITLE_MAX - 1].rstrip() + "…"
    return title[:1].upper() + title[1:]


async def expand_new_chat(db: Any, insight: dict) -> dict:
    """Cria a conversa iniciada pela IA a partir do insight (idempotente).

    Devolve ``{conversation_id, message_id, title, created}``. Se o insight já
    gerou uma conversa, devolve a existente (``created=False``).
    """
    if insight.get("spawned_conversation_id"):
        async with db.execute(
            "SELECT id FROM messages WHERE conversation_id = ? AND proactive_insight_id = ? ORDER BY created_at ASC LIMIT 1",
            (insight["spawned_conversation_id"], insight["id"]),
        ) as cur:
            row = await cur.fetchone()
        async with db.execute(
            "SELECT title FROM conversations WHERE id = ?", (insight["spawned_conversation_id"],)
        ) as cur:
            trow = await cur.fetchone()
        return {
            "conversation_id": insight["spawned_conversation_id"],
            "message_id": row[0] if row else None,
            "title": trow[0] if trow else "",
            "created": False,
        }

    async with db.execute(
        "SELECT title, model_id, provider_id FROM conversations WHERE id = ? AND user_id = ?",
        (insight["conversation_id"], insight["user_id"]),
    ) as cur:
        origin = await cur.fetchone()
    origin_title = (origin[0] if origin else "") or ""
    model_id = origin[1] if origin else None
    provider_id = origin[2] if origin else None

    async with _lock_for(insight["user_id"]):
        new_conv_id = str(uuid.uuid4())
        title = new_chat_title(insight.get("topic") or "")
        try:
            await db.execute(
                """INSERT INTO conversations (id, user_id, title, model_id, provider_id, origin_insight_id)
                   VALUES (?, ?, ?, ?, ?, ?)""",
                (new_conv_id, insight["user_id"], title, model_id, provider_id, insight["id"]),
            )
            message_id = await persist_proactive_message(
                db, insight, mode="new_chat", conversation_id=new_conv_id,
                origin_title=origin_title, commit=False,
            )
            # Se ainda não havia sido entregue, esta é a entrega (status/channel/delivered_*).
            cur = await db.execute(
                """UPDATE proactive_insights
                   SET spawned_conversation_id = ?,
                       status = CASE WHEN status = 'ready' THEN 'delivered' ELSE status END,
                       channel = COALESCE(channel, 'new_chat'),
                       delivered_message_id = COALESCE(delivered_message_id, ?),
                       delivered_at = COALESCE(delivered_at, datetime('now'))
                   WHERE id = ? AND spawned_conversation_id IS NULL""",
                (new_conv_id, message_id, insight["id"]),
            )
            if (cur.rowcount or 0) != 1:
                await db.rollback()
                fresh = await load_insight(db, insight["id"])
                if fresh and fresh.get("spawned_conversation_id"):
                    return await expand_new_chat(db, fresh)
                raise RuntimeError("expand_conflict")
            await db.commit()
        except Exception:
            try:
                await db.rollback()
            except Exception:
                pass
            raise
    return {"conversation_id": new_conv_id, "message_id": message_id, "title": title, "created": True}
