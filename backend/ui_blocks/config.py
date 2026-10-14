"""Configuração em runtime do Intelligent UI (singleton, ``id = 1``).

Ordem de precedência, da maior para a menor:

1. Linha na tabela ``intelligent_ui_config`` — gravada pelo painel admin
   (``POST /api/intelligent-ui/config``).
2. Variáveis de ambiente ``INTELLIGENT_UI_ENABLED``, ``INTELLIGENT_UI_IMAGE_HOSTS``
   e ``INTELLIGENT_UI_ALLOW_PRIVATE_HTTP`` (``.env``).
3. Padrão: desligado, sem hosts, sem HTTP privado.

Enquanto ninguém salvar pelo painel, o ``.env`` continua mandando — a tabela só
ganha linha no primeiro ``update``. Isso mantém o comportamento documentado em
``melhorias/intelligent-ui/00-visao-e-spec.md`` ("ausente significa falso").
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass, field
from typing import Any, Optional

import aiosqlite

_TRUE_VALUES = ("true", "1", "yes", "on")
_HOST_REGEX = re.compile(r"^(?=.{1,253}$)(?:[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?)(?:\.[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?)*$")
MAX_IMAGE_HOSTS = 32


def _env_bool(name: str, default: bool = False) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in _TRUE_VALUES


def normalize_hosts(value: Any) -> list[str]:
    """Normaliza a lista de hosts confiáveis para imagens.

    Aceita string separada por vírgula/espaço/quebra de linha ou lista. Remove
    esquema, caminho, porta e userinfo; descarta o que não for hostname válido;
    elimina duplicados preservando a ordem. Limita a ``MAX_IMAGE_HOSTS``.
    """
    if value is None:
        return []
    if isinstance(value, str):
        parts = re.split(r"[,\s]+", value)
    elif isinstance(value, (list, tuple, set)):
        parts = [str(p) for p in value]
    else:
        return []

    out: list[str] = []
    seen: set[str] = set()
    for raw in parts:
        host = raw.strip().lower()
        if not host:
            continue
        host = re.sub(r"^[a-z][a-z0-9+.-]*://", "", host)  # esquema
        host = host.split("@")[-1]  # userinfo
        host = host.split("/")[0].split("?")[0].split("#")[0]  # caminho/query
        if host.startswith("[") and "]" in host:  # IPv6 literal
            host = host[1 : host.index("]")]
        else:
            host = host.split(":")[0]  # porta
        host = host.rstrip(".")
        if not host or host in seen:
            continue
        if not _HOST_REGEX.match(host) and not re.match(r"^[0-9a-f:.]+$", host):
            continue
        seen.add(host)
        out.append(host)
        if len(out) >= MAX_IMAGE_HOSTS:
            break
    return out


@dataclass
class IntelligentUiConfig:
    enabled: bool = False
    image_hosts: list[str] = field(default_factory=list)
    allow_private_http: bool = False
    source: str = "default"  # "db" | "env" | "default"
    updated_at: Optional[str] = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "enabled": bool(self.enabled),
            "image_hosts": list(self.image_hosts),
            "allow_private_http": bool(self.allow_private_http),
            "source": self.source,
            "updated_at": self.updated_at,
        }


def config_from_env() -> IntelligentUiConfig:
    """Configuração derivada só do ambiente (fallback quando a tabela está vazia)."""
    has_any = any(
        os.getenv(n) is not None
        for n in ("INTELLIGENT_UI_ENABLED", "INTELLIGENT_UI_IMAGE_HOSTS", "INTELLIGENT_UI_ALLOW_PRIVATE_HTTP")
    )
    return IntelligentUiConfig(
        enabled=_env_bool("INTELLIGENT_UI_ENABLED", False),
        image_hosts=normalize_hosts(os.getenv("INTELLIGENT_UI_IMAGE_HOSTS", "")),
        allow_private_http=_env_bool("INTELLIGENT_UI_ALLOW_PRIVATE_HTTP", False),
        source="env" if has_any else "default",
    )


async def ensure_table(db: aiosqlite.Connection) -> None:
    """Cria a tabela singleton se ainda não existir (idempotente)."""
    await db.execute(
        """
        CREATE TABLE IF NOT EXISTS intelligent_ui_config (
            id                 INTEGER PRIMARY KEY CHECK (id = 1),
            enabled            INTEGER NOT NULL DEFAULT 0,
            image_hosts        TEXT    NOT NULL DEFAULT '',
            allow_private_http INTEGER NOT NULL DEFAULT 0,
            updated_at         TEXT    DEFAULT (datetime('now'))
        )
        """
    )


async def get_intelligent_ui_config(db: Optional[aiosqlite.Connection] = None) -> IntelligentUiConfig:
    """Lê a configuração efetiva: linha da tabela, senão ambiente."""
    should_close = False
    if db is None:
        from backend.database import get_db

        db = await get_db()
        should_close = True
    try:
        try:
            async with db.execute(
                "SELECT enabled, image_hosts, allow_private_http, updated_at FROM intelligent_ui_config WHERE id = 1"
            ) as cur:
                row = await cur.fetchone()
        except aiosqlite.OperationalError:
            row = None  # tabela ainda não migrada
        if row is not None:
            return IntelligentUiConfig(
                enabled=bool(row[0]),
                image_hosts=normalize_hosts(row[1] or ""),
                allow_private_http=bool(row[2]),
                source="db",
                updated_at=row[3],
            )
    finally:
        if should_close:
            await db.close()
    return config_from_env()


async def update_intelligent_ui_config(db: aiosqlite.Connection, updates: dict[str, Any]) -> IntelligentUiConfig:
    """Grava os campos informados (merge sobre a configuração efetiva atual)."""
    current = await get_intelligent_ui_config(db)
    enabled = current.enabled
    image_hosts = list(current.image_hosts)
    allow_private_http = current.allow_private_http

    if "enabled" in updates and updates["enabled"] is not None:
        enabled = bool(updates["enabled"])
    if "image_hosts" in updates and updates["image_hosts"] is not None:
        image_hosts = normalize_hosts(updates["image_hosts"])
    if "allow_private_http" in updates and updates["allow_private_http"] is not None:
        allow_private_http = bool(updates["allow_private_http"])

    await ensure_table(db)
    await db.execute(
        """
        INSERT INTO intelligent_ui_config (id, enabled, image_hosts, allow_private_http, updated_at)
        VALUES (1, ?, ?, ?, datetime('now'))
        ON CONFLICT(id) DO UPDATE SET
            enabled = excluded.enabled,
            image_hosts = excluded.image_hosts,
            allow_private_http = excluded.allow_private_http,
            updated_at = excluded.updated_at
        """,
        (1 if enabled else 0, ",".join(image_hosts), 1 if allow_private_http else 0),
    )
    await db.commit()
    return await get_intelligent_ui_config(db)
