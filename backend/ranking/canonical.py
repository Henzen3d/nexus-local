"""
backend/ranking/canonical.py
Normalização Canônica de Modelos e Matching de Famílias para NexusLocal / Multi+.

Especificação do Golden Prompt v3.0 (Seções 5.1 e A2):
- IDs Canônicos sem prefixos de provedores duplicados/compostos e sem sufixos (:free, :nitro).
- Suporte a modelos reais:
    nvidia/nvidia/nemotron-3-ultra-550b-a55b -> nemotron-3-ultra-550b-a55b
    openrouter/nvidia/nemotron-3-ultra-550b-a55b:free -> nemotron-3-ultra-550b-a55b
    gemini/gemini-2.5-pro -> gemini-2.5-pro
    models/gemini-2.5-pro -> gemini-2.5-pro
    longcat/LongCat-2.5-Preview -> longcat-2.5-preview
    openrouter/google/gemma-4-31b-it:free -> gemma-4-31b-it
- Lookup unificado de famílias (Tier 1) via correspondência exata, canônica ou por radical de família.
- Cooldown persistido no escopo de modelo e propagação para escopo canônico cross-provider
  quando 2 ou mais provedores falharem com 0 tokens.
"""

from __future__ import annotations

import re
from datetime import datetime, timezone, timedelta
from typing import Optional, List, Tuple
import aiosqlite

from backend.logging_config import get_logger

logger = get_logger("nexuslocal.ranking.canonical")

KNOWN_PREFIXES = {
    "openrouter", "nvidia", "gemini", "cloudflare", "siliconflow",
    "groq", "cerebras", "zai", "ollama", "huggingface", "sambanova",
    "longcat", "freetheai", "llm7", "deepseek", "qwen", "openai",
    "together", "mistral", "cohere", "zenmux", "bynara", "local",
    "lmstudio", "models", "google", "meta-llama", "deepseek-ai",
    "moonshotai", "meta", "aisingapore", "ibm-granite", "nousresearch",
    "defog", "microsoft", "nv-mistralai", "x-ai", "fta", "kai", "ocz",
    "anthropic", "vertex", "bedrock", "deepinfra"
}

KNOWN_FAMILIES = [
    "deepseek-r1",
    "deepseek-v3",
    "deepseek",
    "nemotron",
    "gemini",
    "llama-3.3-70b",
    "llama-3.1",
    "llama-3",
    "llama",
    "qwen-2.5",
    "qwen",
    "gemma",
    "claude",
    "gpt-4o",
    "gpt-4",
    "gpt",
    "mistral",
    "phi",
    "command-r",
    "longcat",
]


def canonical_model_id(model_id: str) -> str:
    """
    Normaliza o ID do modelo removendo sufixos (como ':free', ':nitro', ':latest') e
    prefixos de provedores/organizações (simples ou duplicados como 'openrouter/nvidia/', 'nvidia/nvidia/'),
    retornando um identificador canônico em minúsculas para comparação cross-provider
    e matching de famílias no Tier 1 e Tier 2.
    """
    if not model_id:
        return ""

    cand = model_id.strip()

    # 1. Remove sufixos como ':free', ':nitro', ':latest'
    lower_cand = cand.lower()
    if lower_cand.endswith(":free"):
        cand = cand[:-5]
    elif lower_cand.endswith(":nitro"):
        cand = cand[:-6]
    elif lower_cand.endswith(":latest"):
        cand = cand[:-7]

    parts = [p for p in cand.split("/") if p]

    # 2. Remove prefixos conhecidos de provedores e organizações no início
    while len(parts) > 1 and parts[0].lower() in KNOWN_PREFIXES:
        parts.pop(0)

    # 3. Remove duplicações consecutivas (ex: 'nvidia/nvidia/...')
    while len(parts) > 1 and parts[0].lower() == parts[1].lower():
        parts.pop(0)

    result = "/".join(parts) if parts else cand
    return result.lower().strip()


def extract_family_from_canonical(canon_id: str) -> Optional[str]:
    """
    Extrai o identificador base de família a partir de um ID canônico.
    Exemplos:
        'gemini-2.5-pro' -> 'gemini'
        'nemotron-3-ultra-550b-a55b' -> 'nemotron'
        'deepseek-r1-distill-llama-70b' -> 'deepseek-r1'
        'llama-3.3-70b' -> 'llama-3.3-70b'
        'longcat-2.5-preview' -> 'longcat'
    """
    if not canon_id:
        return None
    canon = canon_id.lower().strip()
    for fam in KNOWN_FAMILIES:
        if (
            canon == fam
            or canon.startswith(f"{fam}-")
            or canon.startswith(f"{fam}_")
            or canon.startswith(f"{fam}/")
            or (f"-{fam}-" in canon)
            or (canon.endswith(f"-{fam}"))
        ):
            return fam
    return None


async def apply_zero_token_cooldown(
    failed_model_id: str,
    db: aiosqlite.Connection,
    retry_after: int = 600,
) -> None:
    """
    Registra cooldown de 0 tokens no modelo e verifica se outro provedor do mesmo
    modelo canônico também falhou recentemente. Se 2 ou mais provedores falharem,
    propaga o cooldown no escopo canônico para todos os provedores daquele modelo.
    """
    from backend.ranking.quota import mark_model_exhausted

    # 1. Aplica cooldown no modelo específico
    await mark_model_exhausted(
        failed_model_id,
        db,
        retry_after=retry_after,
        error_msg="Silent failure: 0 tokens returned",
    )

    canon_id = canonical_model_id(failed_model_id)
    if not canon_id:
        return

    # 2. Busca todos os modelos cadastrados no banco que compartilham este mesmo canonical_model_id
    async with db.execute("SELECT id, provider_id FROM models WHERE enabled = 1") as cur:
        all_models = await cur.fetchall()

    same_canon_models = [
        mid for mid, _ in all_models
        if canonical_model_id(mid) == canon_id and mid != failed_model_id
    ]

    if not same_canon_models:
        return

    # 3. Verifica se algum outro modelo desse canonical já está em cooldown por falha silenciosa
    now_iso = datetime.now(timezone.utc).isoformat()
    placeholders = ",".join("?" for _ in same_canon_models)
    query = f"""
        SELECT model_id FROM model_quota_status
        WHERE model_id IN ({placeholders})
          AND status = 'exhausted'
          AND estimated_reset_at > ?
          AND (last_error_message LIKE '%0 tokens%' OR last_error_message LIKE '%Silent failure%')
    """
    async with db.execute(query, tuple(same_canon_models + [now_iso])) as cur:
        failed_siblings = await cur.fetchall()

    if failed_siblings:
        # Pelo menos 2 provedores do mesmo modelo canônico falharam!
        # Propaga cooldown no escopo canônico para todos os modelos irmãos
        logger.warning(
            "[canonical_cooldown] Múltiplos provedores do modelo canônico '%s' falharam com 0 tokens. "
            "Propagando quarentena temporária (%ds) para todos os provedores variantes: %s",
            canon_id,
            retry_after,
            same_canon_models,
        )
        for sib in same_canon_models:
            await mark_model_exhausted(
                sib,
                db,
                retry_after=retry_after,
                error_msg=f"Canonical cooldown: multiple providers failed with 0 tokens ({canon_id})",
            )
