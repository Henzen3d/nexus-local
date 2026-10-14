"""Resolução do "modelo utilitário" (barato) compartilhada entre subsistemas.

Vários pipelines de bastidor (extrator de memória, detector proativo, etc.)
precisam de um modelo pequeno e barato, e não necessariamente do modelo que o
usuário escolheu para o chat. A cascata abaixo era privada de
``backend/memory.py`` (``_get_extractor_provider_and_model``) e foi extraída
para cá sem mudança de comportamento, ganhando apenas um degrau opcional de
override por chaves em ``meta`` (usado pelo detector proativo — Fase 4 permite
o admin escolher um modelo dedicado).

Cascata (primeiro que resolver vence):

1. ``override_meta_keys`` — par ``(provider_key, model_key)`` em ``meta``
   (ex.: ``proactive_detector_provider_id`` / ``proactive_detector_model_id``).
2. Extrator de memória dedicado — ``meta.memory_extractor_provider_id`` /
   ``meta.memory_extractor_model_id``.
3. Enhancer — tabela ``enhancer_config`` (normalmente um modelo pequeno).
4. Provedor/modelo do próprio chat (último recurso).

Cada degrau só é aceito se ``get_provider``/``get_model_name`` resolverem sem
erro (provedor habilitado, chave válida, modelo cadastrado); caso contrário a
cascata segue para o próximo degrau, exatamente como antes.
"""
from __future__ import annotations

from typing import Any, Optional, Tuple

import aiosqlite

from backend.providers.registry import get_model_name, get_provider

SOURCE_OVERRIDE = "override"
SOURCE_MEMORY_EXTRACTOR = "memory_extractor"
SOURCE_ENHANCER = "enhancer"
SOURCE_CHAT_FALLBACK = "chat_fallback"


async def read_meta(db: aiosqlite.Connection, key: str) -> Optional[str]:
    """Lê ``meta.value`` (string sem espaços nas pontas) ou ``None``."""
    try:
        async with db.execute("SELECT value FROM meta WHERE key = ?", (key,)) as cur:
            row = await cur.fetchone()
            return row[0].strip() if row and row[0] else None
    except Exception:
        return None


async def _try_resolve(
    db: aiosqlite.Connection,
    provider_id: Optional[str],
    model_id: Optional[str],
    user_id: Optional[str],
) -> Optional[Tuple[Any, str]]:
    if not provider_id or not model_id:
        return None
    try:
        provider = await get_provider(provider_id, db, user_id=user_id)
        model_name = await get_model_name(model_id, db)
        return provider, model_name
    except Exception:
        return None


async def resolve_utility_model(
    db: aiosqlite.Connection,
    user_id: Optional[str],
    fallback_provider_id: str,
    fallback_model_id: str,
    *,
    override_meta_keys: Optional[Tuple[str, str]] = None,
) -> Tuple[Any, str, str]:
    """Devolve ``(provider, model_name, source)`` seguindo a cascata do módulo.

    ``source`` é um rótulo estável para logs/métricas: ``"override"``,
    ``"memory_extractor"``, ``"enhancer"`` ou ``"chat_fallback"``.

    O último degrau propaga exceções de ``get_provider``/``get_model_name``
    (mesmo comportamento histórico do extrator de memória): se nem o modelo do
    chat resolver, o chamador decide o que fazer.
    """
    # 1. Override explícito (ex.: modelo dedicado do detector proativo)
    if override_meta_keys:
        prov_key, model_key = override_meta_keys
        resolved = await _try_resolve(
            db, await read_meta(db, prov_key), await read_meta(db, model_key), user_id
        )
        if resolved:
            return resolved[0], resolved[1], SOURCE_OVERRIDE

    # 2. Extrator de memória dedicado (meta)
    resolved = await _try_resolve(
        db,
        await read_meta(db, "memory_extractor_provider_id"),
        await read_meta(db, "memory_extractor_model_id"),
        user_id,
    )
    if resolved:
        return resolved[0], resolved[1], SOURCE_MEMORY_EXTRACTOR

    # 3. Enhancer (tabela enhancer_config — não é meta)
    try:
        async with db.execute(
            "SELECT enhancer_provider_id, enhancer_model_id FROM enhancer_config WHERE id = 1"
        ) as cur:
            row = await cur.fetchone()
    except Exception:
        row = None
    if row and row[0] and row[1]:
        resolved = await _try_resolve(db, row[0], row[1], user_id)
        if resolved:
            return resolved[0], resolved[1], SOURCE_ENHANCER

    # 4. Último recurso: mesmo provedor/modelo do chat (erros propagam)
    provider = await get_provider(fallback_provider_id, db, user_id=user_id)
    model_name = await get_model_name(fallback_model_id, db)
    return provider, model_name, SOURCE_CHAT_FALLBACK
