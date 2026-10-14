"""Presença do usuário — Fase 3 (F3.1), compatível com a API mínima da F2.

Estrutura em memória por processo: ``user_id → UserPresence(sockets: {id(ws): SocketPresence})``.
O cliente envia ``{type:"presence", state, conversation_id, view}`` (contrato
``01-decisao-entrega-e-presenca.md`` §3.1); ping/pong renovam ``last_seen_at``;
socket fechado ⇒ removido (``offline`` quando não resta nenhum).

Regras (§2.1 / §2.4 do contrato):

* ``effective_state(user)`` = **melhor** estado entre os sockets
  (``active > idle > hidden``), ``offline`` sem socket;
* socket sem ``touch`` há mais de ``STALE_AFTER_S`` (2 × intervalo de ping) é
  tratado como ``hidden`` — cliente congelado sem fechar o socket (F3.1.3);
* **"voltou"** = transição ``idle|hidden|offline → active`` de um socket, socket
  novo, ou troca de conversa enquanto ``active`` (F3.1.4 / F3.2.5). O
  ``Transition`` devolvido por :func:`update` diz se a entrega pendente deve
  ser tentada (``should_flush``); quem agenda é o controller do WS.

Um socket que nunca reportou presença conta como ``active`` sem conversa
(compatibilidade com clientes antigos ⇒ toast).
"""
from __future__ import annotations

import time
from collections import deque
from dataclasses import dataclass, field
from typing import Any, Optional

VALID_STATES = ("active", "idle", "hidden")
#: Ordem de "qualidade" do estado — o melhor socket define o estado do usuário.
STATE_RANK = {"active": 3, "idle": 2, "hidden": 1, "offline": 0}
#: Intervalo de keepalive (cliente e servidor usam 25 s); 2× + folga.
PING_INTERVAL_S = 25.0
STALE_AFTER_S = 2 * PING_INTERVAL_S + 5.0


@dataclass
class SocketPresence:
    """Estado reportado por **um** socket."""

    state: str = "active"
    conversation_id: Optional[str] = None
    view: Optional[str] = None
    last_seen_at: float = field(default_factory=time.monotonic)
    updated_at: float = field(default_factory=time.monotonic)
    #: ``False`` até o cliente enviar o primeiro evento ``presence`` deste socket.
    reported: bool = False

    def is_stale(self, now: Optional[float] = None) -> bool:
        now = time.monotonic() if now is None else now
        return (now - self.last_seen_at) > STALE_AFTER_S

    def effective_state(self, now: Optional[float] = None) -> str:
        """``hidden`` se o socket parou de dar sinal de vida (F3.1.3)."""
        if self.is_stale(now):
            return "hidden"
        return self.state

    @property
    def is_active(self) -> bool:
        return self.effective_state() == "active"

    def to_dict(self) -> dict[str, Any]:
        return {"state": self.state, "conversation_id": self.conversation_id, "view": self.view}


# Compatibilidade com o nome usado na F2.
PresenceState = SocketPresence


@dataclass
class UserPresence:
    user_id: str
    sockets: dict[int, SocketPresence] = field(default_factory=dict)

    def effective_state(self, now: Optional[float] = None) -> str:
        best = "offline"
        for sock in self.sockets.values():
            state = sock.effective_state(now)
            if STATE_RANK[state] > STATE_RANK[best]:
                best = state
        return best


@dataclass
class Transition:
    """Resultado de :func:`update`/:func:`register` — decide se há "retorno"."""

    socket: SocketPresence
    previous_state: str                     # estado efetivo do socket antes ('offline' = socket novo)
    previous_conversation_id: Optional[str]
    user_previous_state: str                # estado efetivo do usuário antes
    user_state: str                         # estado efetivo do usuário depois

    @property
    def returned(self) -> bool:
        """``idle|hidden|offline → active`` neste socket (inclui socket novo)."""
        return self.socket.effective_state() == "active" and self.previous_state != "active"

    @property
    def conversation_changed(self) -> bool:
        return (
            self.socket.effective_state() == "active"
            and self.socket.conversation_id != self.previous_conversation_id
        )

    @property
    def should_flush(self) -> bool:
        return self.returned or self.conversation_changed

    @property
    def kind(self) -> str:
        if self.previous_state == "offline":
            return "connect"
        if self.returned:
            return "return"
        if self.conversation_changed:
            return "conversation"
        return "none"


_presence: dict[str, UserPresence] = {}
_transitions: deque[tuple[float, str, str]] = deque(maxlen=5000)  # (monotonic, user_id, kind)


def _key(ws: Any) -> int:
    return id(ws)


def _record(user_id: str, kind: str) -> None:
    if kind != "none":
        _transitions.append((time.monotonic(), user_id, kind))


def register(user_id: str, ws: Any) -> Transition:
    """Novo socket: começa ``active`` sem conversa (até o cliente reportar)."""
    user = _presence.setdefault(user_id, UserPresence(user_id))
    previous_user_state = user.effective_state()
    sock = SocketPresence()
    user.sockets[_key(ws)] = sock
    tr = Transition(sock, "offline", None, previous_user_state, user.effective_state())
    _record(user_id, tr.kind)
    return tr


def remove(user_id: str, ws: Any) -> None:
    user = _presence.get(user_id)
    if not user:
        return
    user.sockets.pop(_key(ws), None)
    if not user.sockets:
        _presence.pop(user_id, None)


def update(
    user_id: str,
    ws: Any,
    *,
    state: Any = None,
    conversation_id: Any = None,
    view: Any = None,
) -> Transition:
    """Aplica um evento ``presence`` do cliente (campos inválidos são ignorados)."""
    user = _presence.setdefault(user_id, UserPresence(user_id))
    now = time.monotonic()
    previous_user_state = user.effective_state(now)
    current = user.sockets.get(_key(ws))
    if current is None:
        current = SocketPresence()
        user.sockets[_key(ws)] = current
        previous_state = "offline"
    elif not current.reported:
        # Socket recém-conectado: o 1º relato é a "chegada" (equivale a offline → active)
        previous_state = "offline"
    else:
        previous_state = current.effective_state(now)
    previous_conversation = current.conversation_id
    current.reported = True

    if isinstance(state, str) and state in VALID_STATES:
        current.state = state
    if conversation_id is None or conversation_id == "":
        current.conversation_id = None
    elif isinstance(conversation_id, str) and len(conversation_id) <= 64:
        current.conversation_id = conversation_id
    if isinstance(view, str) and len(view) <= 32:
        current.view = view
    current.updated_at = now
    current.last_seen_at = now

    tr = Transition(current, previous_state, previous_conversation, previous_user_state, user.effective_state(now))
    _record(user_id, tr.kind)
    return tr


def touch(user_id: str, ws: Any) -> Optional[Transition]:
    """Renova ``last_seen_at`` (ping/pong). Devolve ``Transition`` se o socket
    estava *stale* e voltou a dar sinal (conta como retorno)."""
    user = _presence.get(user_id)
    if not user:
        return None
    current = user.sockets.get(_key(ws))
    if current is None:
        return None
    now = time.monotonic()
    previous_user_state = user.effective_state(now)
    previous_state = current.effective_state(now)
    current.last_seen_at = now
    if previous_state == "hidden" and current.state == "active":
        tr = Transition(current, previous_state, current.conversation_id, previous_user_state, user.effective_state(now))
        _record(user_id, tr.kind)
        return tr
    return None


def snapshot(user_id: str) -> list[SocketPresence]:
    user = _presence.get(user_id)
    return list(user.sockets.values()) if user else []


def get_socket(user_id: str, ws: Any) -> Optional[SocketPresence]:
    user = _presence.get(user_id)
    return user.sockets.get(_key(ws)) if user else None


def effective_state(user_id: str) -> str:
    user = _presence.get(user_id)
    return user.effective_state() if user else "offline"


def has_active_socket(user_id: str) -> bool:
    return effective_state(user_id) == "active"


def is_active_in_conversation(user_id: str, conversation_id: str) -> bool:
    return any(
        s.is_active and s.conversation_id == conversation_id for s in snapshot(user_id)
    )


def active_conversation_sockets(user_id: str) -> list[SocketPresence]:
    return [s for s in snapshot(user_id) if s.is_active]


def stats(window_s: float = 3600.0) -> dict[str, Any]:
    """Métricas simples para o dashboard admin (F3.1.5)."""
    now = time.monotonic()
    users_active = sum(1 for u in _presence.values() if u.effective_state(now) == "active")
    sockets = sum(len(u.sockets) for u in _presence.values())
    cutoff = now - window_s
    recent = [t for t in _transitions if t[0] >= cutoff]
    by_kind: dict[str, int] = {}
    for _, _, kind in recent:
        by_kind[kind] = by_kind.get(kind, 0) + 1
    return {
        "users_online": len(_presence),
        "users_active": users_active,
        "sockets": sockets,
        "transitions_last_hour": len(recent),
        "transitions_by_kind": by_kind,
    }


def reset() -> None:
    """Somente para testes."""
    _presence.clear()
    _transitions.clear()
