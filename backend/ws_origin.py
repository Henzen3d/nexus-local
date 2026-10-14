"""Checagem de ``Origin`` no handshake do WebSocket (plano 12 §6, Intelligent UI).

Navegador sempre manda ``Origin`` ao abrir um WebSocket, e o WebSocket não obedece
CORS: qualquer site aberto na mesma máquina poderia tentar falar com ``/ws/chat``
(cross-site WebSocket hijacking). O token JWT na query já impede o uso sem
credencial; esta checagem é a segunda camada, a mesma que o ``security.spec.ts``
do AnswerUI testa.

Regra:

- sem ``Origin`` (cliente que não é navegador: testes, scripts) → passa;
- ``Origin`` cujo ``host[:porta]`` é o mesmo do cabeçalho ``Host`` → passa
  (produção atrás do nginx e dev pelo proxy do Vite caem aqui);
- ``Origin`` na lista ``ALLOWED_ORIGINS`` (a mesma do CORS) → passa
  (dev com ``VITE_WS_URL`` apontando direto para o backend);
- qualquer outra coisa, inclusive ``Origin: null`` → recusado antes do ``accept``.
"""

from __future__ import annotations

import os
from typing import Iterable
from urllib.parse import urlsplit

DEFAULT_DEV_ORIGINS = ("http://localhost:5173", "http://127.0.0.1:5173")

_DEFAULT_PORTS = {"http": "80", "https": "443", "ws": "80", "wss": "443"}


def allowed_origins_from_env() -> list[str]:
    """``ALLOWED_ORIGINS`` do ``.env`` (separado por vírgula) ou os padrões de dev.

    Usada pelo CORS em ``backend/main.py`` e pelo WebSocket: uma lista só.
    """
    raw = os.getenv("ALLOWED_ORIGINS", "")
    origins = [o.strip().rstrip("/") for o in raw.split(",") if o.strip()]
    return origins or list(DEFAULT_DEV_ORIGINS)


def _netloc(origin: str) -> str | None:
    """``host[:porta]`` em minúsculas, sem a porta padrão do esquema; None se não for URL."""
    try:
        parts = urlsplit(origin.strip())
    except ValueError:
        return None
    scheme = (parts.scheme or "").lower()
    host = (parts.hostname or "").lower()
    if not scheme or not host:
        return None
    port = parts.port
    if port is None or str(port) == _DEFAULT_PORTS.get(scheme):
        return host
    return f"{host}:{port}"


def _host_netloc(host_header: str) -> str:
    """Normaliza o cabeçalho ``Host`` como ``_netloc`` (sem ``:80``/``:443``)."""
    host = host_header.strip().lower()
    for default in (":80", ":443"):
        if host.endswith(default):
            return host[: -len(default)]
    return host


def is_origin_allowed(
    origin: str | None,
    host: str | None,
    allowed_origins: Iterable[str] | None = None,
) -> bool:
    """Decide se o ``Origin`` do handshake pode abrir o WebSocket."""
    if origin is None or not origin.strip():
        return True
    origin_netloc = _netloc(origin)
    if origin_netloc is None:  # "null", lixo, esquema sem host
        return False
    if host and origin_netloc == _host_netloc(host):
        return True
    allowed = allowed_origins if allowed_origins is not None else allowed_origins_from_env()
    origin_lower = origin.strip().rstrip("/").lower()
    for candidate in allowed:
        if candidate.strip().rstrip("/").lower() == origin_lower:
            return True
    return False
