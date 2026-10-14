"""Entrega do insight — Fase 2 (F2.5): inline ou toast, só com presença.

Regras desta fase (``01-decisao-entrega-e-presenca.md`` §2.2, versão F2):

* usuário **ativo na conversa de origem** ⇒ persiste a mensagem
  (``messages.kind='proactive'``) e envia ``proactive_insight`` com
  ``channel_hint='inline'``;
* usuário **ativo em outra conversa/tela** ⇒ persiste e envia com
  ``channel_hint='toast'`` (o cliente mostra toast com ação *Ver* + badge);
* **sem socket ativo** (idle/hidden/offline) ⇒ nada é persistido nem enviado;
  o insight continua ``ready`` e a F3 cuida do retorno (prefixo "Enquanto você
  estava fora…").

Guarda de "não interromper": se houver turno em andamento na conversa
(``service.is_turn_active``), aguarda o fim antes de persistir/enviar. A guarda
de digitação (3 s) é do cliente.
"""
from __future__ import annotations

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
# §3.4 — "No retorno (mesma conversa)" — usado pela F3, já disponível para o prefixo correto.
RETURN_PREFIX = {
    "pt-BR": "Enquanto você estava fora, pesquisei sobre **{topic}**: ",
    "en-US": "While you were away, I looked into **{topic}**: ",
    "es-ES": "Mientras no estabas, investigué sobre **{topic}**: ",
}


@dataclass
class DeliveryOutcome:
    channel: Optional[str]          # inline | toast | None (pendente)
    message_id: Optional[str] = None
    reason: str = ""

    @property
    def delivered(self) -> bool:
        return self.channel is not None


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


def build_message_content(insight: dict, *, mode: str = "live") -> str:
    """Conteúdo persistido da bolha: prefixo localizado + texto sintetizado."""
    templates = RETURN_PREFIX if mode == "return" else LIVE_PREFIX
    prefix = templates[_language(insight)].format(topic=(insight.get("topic") or "").strip())
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


def insight_public_dict(insight: dict, *, message_id: Optional[str] = None) -> dict:
    """Shape público do insight (sem campos internos), reutilizado pelo GET da conversa."""
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
        "language": insight.get("language"),
        "expires_at": insight.get("expires_at"),
        "created_at": insight.get("created_at"),
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


async def persist_proactive_message(db: Any, insight: dict, *, mode: str = "live") -> str:
    """F2.5.2: mensagem do assistente ``kind='proactive'`` + ``updated_at`` (sem mexer no título)."""
    message_id = str(uuid.uuid4())
    model_label = insight.get("synth_model") or None
    provider_label = model_label.split("/")[0] if model_label and "/" in model_label else None
    await db.execute(
        """INSERT INTO messages (id, conversation_id, role, content, model_id, provider, kind, proactive_insight_id)
           VALUES (?, ?, 'assistant', ?, ?, ?, 'proactive', ?)""",
        (message_id, insight["conversation_id"], build_message_content(insight, mode=mode),
         model_label, provider_label, insight["id"]),
    )
    await db.execute(
        "UPDATE conversations SET updated_at = datetime('now') WHERE id = ?",
        (insight["conversation_id"],),
    )
    await db.commit()
    return message_id


async def _notify(user_id: str, payload: dict) -> None:
    from backend.routers.chat import notify_user_sockets

    await notify_user_sockets(user_id, payload)


async def deliver(insight: dict, db: Any, *, wait_turn_timeout: float = WAIT_TURN_TIMEOUT_S) -> DeliveryOutcome:
    """Decide e executa a entrega (versão F2). Idempotente (F2.5.6)."""
    from backend.proactive import service

    if insight.get("delivered_message_id"):
        return DeliveryOutcome(insight.get("channel") or "inline", insight["delivered_message_id"], "already_delivered")
    if insight.get("status") not in ("ready", "delivered"):
        return DeliveryOutcome(None, None, f"status_{insight.get('status')}")

    user_id = insight["user_id"]
    conversation_id = insight["conversation_id"]

    if not presence.has_active_socket(user_id):
        return DeliveryOutcome(None, None, "absent")

    # Não interromper um turno em andamento na conversa de origem (F2.5.4)
    if service.is_turn_active(conversation_id):
        freed = await service.wait_turn_end(conversation_id, timeout=wait_turn_timeout)
        if not freed:
            return DeliveryOutcome(None, None, "turn_busy")
        if not presence.has_active_socket(user_id):
            return DeliveryOutcome(None, None, "absent")

    channel = "inline" if presence.is_active_in_conversation(user_id, conversation_id) else "toast"

    message_id = await persist_proactive_message(db, insight, mode="live")
    await db.execute(
        """UPDATE proactive_insights
           SET status = 'delivered', channel = ?, delivered_message_id = ?, delivered_at = datetime('now')
           WHERE id = ? AND delivered_message_id IS NULL""",
        (channel, message_id, insight["id"]),
    )
    await db.commit()
    insight = {**insight, "status": "delivered", "channel": channel, "delivered_message_id": message_id}

    try:
        await _notify(user_id, build_insight_payload(insight, message_id=message_id, channel_hint=channel))
    except Exception as exc:  # mensagem já persistida; o cliente a verá ao recarregar
        logger.warning("[Proactive] falha ao notificar socket (insight=%s): %s", insight["id"], exc)
        return DeliveryOutcome(channel, message_id, "notify_failed")
    return DeliveryOutcome(channel, message_id, "delivered")
