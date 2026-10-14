"""Presença mínima do usuário — Fase 2 (F2.5/F2.6.2).

Estrutura em memória por processo: ``user_id → {id(ws): PresenceState}``. O
cliente envia ``{type:"presence", state, conversation_id, view}`` ao trocar de
conversa/aba (contrato em ``01-decisao-entrega-e-presenca.md`` §3.1). Socket
fechado ⇒ entrada removida (``offline``).

Regras usadas pela entrega na F2:

* **presente na conversa** = algum socket ``active`` com
  ``conversation_id`` igual ao da conversa de origem ⇒ bolha inline;
* **presente em outro lugar** = algum socket ``active`` ⇒ toast + badge;
* caso contrário (``idle``/``hidden``/sem socket) ⇒ nada é enviado; o insight
  fica ``ready`` para a fila de retorno da F3.

Um socket que nunca reportou presença conta como ``active`` sem conversa
(compatibilidade com clientes antigos ⇒ toast).
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any, Optional

VALID_STATES = ("active", "idle", "hidden")


@dataclass
class PresenceState:
    state: str = "active"
    conversation_id: Optional[str] = None
    view: Optional[str] = None
    last_seen_at: float = field(default_factory=time.monotonic)
    updated_at: float = field(default_factory=time.monotonic)

    @property
    def is_active(self) -> bool:
        return self.state == "active"

    def to_dict(self) -> dict[str, Any]:
        return {"state": self.state, "conversation_id": self.conversation_id, "view": self.view}


_presence: dict[str, dict[int, PresenceState]] = {}


def _key(ws: Any) -> int:
    return id(ws)


def register(user_id: str, ws: Any) -> PresenceState:
    """Novo socket: começa ``active`` sem conversa (até o cliente reportar)."""
    state = PresenceState()
    _presence.setdefault(user_id, {})[_key(ws)] = state
    return state


def remove(user_id: str, ws: Any) -> None:
    sockets = _presence.get(user_id)
    if not sockets:
        return
    sockets.pop(_key(ws), None)
    if not sockets:
        _presence.pop(user_id, None)


def update(
    user_id: str,
    ws: Any,
    *,
    state: Any = None,
    conversation_id: Any = None,
    view: Any = None,
) -> PresenceState:
    """Aplica um evento ``presence`` do cliente (campos inválidos são ignorados)."""
    sockets = _presence.setdefault(user_id, {})
    current = sockets.get(_key(ws))
    if current is None:
        current = PresenceState()
        sockets[_key(ws)] = current
    if isinstance(state, str) and state in VALID_STATES:
        current.state = state
    if conversation_id is None or conversation_id == "":
        current.conversation_id = None
    elif isinstance(conversation_id, str) and len(conversation_id) <= 64:
        current.conversation_id = conversation_id
    if isinstance(view, str) and len(view) <= 32:
        current.view = view
    now = time.monotonic()
    current.updated_at = now
    current.last_seen_at = now
    return current


def touch(user_id: str, ws: Any) -> None:
    """Renova ``last_seen_at`` (chamado a cada ping/pong)."""
    current = _presence.get(user_id, {}).get(_key(ws))
    if current is not None:
        current.last_seen_at = time.monotonic()


def snapshot(user_id: str) -> list[PresenceState]:
    return list(_presence.get(user_id, {}).values())


def has_active_socket(user_id: str) -> bool:
    return any(s.is_active for s in snapshot(user_id))


def is_active_in_conversation(user_id: str, conversation_id: str) -> bool:
    return any(
        s.is_active and s.conversation_id == conversation_id for s in snapshot(user_id)
    )


def reset() -> None:
    """Somente para testes."""
    _presence.clear()
