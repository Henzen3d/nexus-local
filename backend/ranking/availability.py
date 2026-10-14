"""
backend/ranking/availability.py
Regra única de "modelo utilizável por este usuário", compartilhada entre o seletor
de modelos (``GET /api/models``) e o ranking (``GET /api/ranking``).

Um modelo é utilizável quando:
- ``models.enabled = 1`` e ``providers.enabled = 1``;
- há chave utilizável: pessoal (``user_api_keys``), provedor gratuito compartilhado
  (OrcaRouter, Bynara), Ollama local, ou provedor gratuito com chave global;
- se ``free_registry_hide_unconfirmed`` estiver ativo, modelos de provedores gratuitos
  precisam estar com ``confirmed_free = 1``.

A consulta precisa ter os aliases ``p`` (providers) e ``k`` (user_api_keys do usuário).
"""

from __future__ import annotations

import aiosqlite

# Provedores cuja chave é compartilhada/dispensável (mesma lista de admin.py e registry.py).
SHARED_KEY_PROVIDERS = ("ollama", "orcarouter", "bynara", "freetheai", "llm7")

USABLE_KEY_CONDITION_SQL = """(
            (k.api_key IS NOT NULL AND TRIM(k.api_key) != '') OR
            p.id IN ('ollama', 'orcarouter', 'bynara', 'freetheai', 'llm7') OR
            (p.is_free = 1 AND p.api_key IS NOT NULL AND TRIM(p.api_key) != '') OR
            (p.is_local = 1)
        )"""

REASON_PROVIDER_DISABLED = "provider_disabled"
REASON_MODEL_DISABLED = "model_disabled"
REASON_MISSING_KEY = "missing_key"
REASON_UNCONFIRMED_FREE = "unconfirmed_free"


async def load_hide_unconfirmed_flag(db: aiosqlite.Connection) -> bool:
    """Lê ``free_registry_hide_unconfirmed`` da tabela meta (padrão: True)."""
    try:
        async with db.execute(
            "SELECT value FROM meta WHERE key = 'free_registry_hide_unconfirmed'"
        ) as cur:
            row = await cur.fetchone()
        return (row[0] == "true") if row else True
    except Exception:
        return True


def unavailability_reason(
    *,
    model_enabled: int,
    provider_enabled: int,
    has_usable_key: int,
    provider_is_free: int,
    confirmed_free: int,
    hide_unconfirmed: bool,
) -> str | None:
    """Motivo pelo qual o modelo não aparece no seletor (``None`` = utilizável)."""
    if not int(provider_enabled or 0):
        return REASON_PROVIDER_DISABLED
    if not int(model_enabled or 0):
        return REASON_MODEL_DISABLED
    if not int(has_usable_key or 0):
        return REASON_MISSING_KEY
    if hide_unconfirmed and int(provider_is_free or 0) and not int(confirmed_free or 0):
        return REASON_UNCONFIRMED_FREE
    return None
