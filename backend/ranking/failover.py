"""
backend/ranking/failover.py
Núcleo do sistema de cascata de failover do NexusLocal.

Fluxo de resolução (chamado antes de cada request de chat):
  1. Verifica quota do modelo solicitado.
  2. Se disponível → retorna sem failover.
  3. Tier 1 → tenta irmãos da mesma família, em fallback_order crescente.
  4. Tier 2 → família inteira esgotada; tenta o melhor do ranking geral
             excluindo membros da mesma família.
  5. Se tudo estiver esgotado → levanta NoAvailableModelError.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Optional

import aiosqlite

from .quota import get_quota_status

logger = logging.getLogger("nexuslocal.ranking.failover")


class NoAvailableModelError(Exception):
    """Levantado quando nenhum modelo disponível pode ser encontrado."""
    pass


@dataclass
class ResolvedModel:
    """Resultado da resolução com ou sem failover."""
    model_id: str
    provider_id: str
    display_name: str
    was_failover: bool
    original_model_id: str
    failover_reason: Optional[str] = None  # 'rate_limit' | 'error' | None
    family_id: Optional[str] = None


async def _get_provider_id(model_id: str, db: aiosqlite.Connection) -> str:
    """Busca o provider_id de um modelo no banco."""
    async with db.execute(
        "SELECT provider_id FROM models WHERE id = ?", (model_id,)
    ) as cur:
        row = await cur.fetchone()
    if not row:
        raise ValueError(f"Modelo '{model_id}' não encontrado no banco.")
    return row[0]


async def _get_display_name(model_id: str, db: aiosqlite.Connection) -> str:
    """Busca o display_name de um modelo no banco."""
    async with db.execute(
        "SELECT display_name FROM models WHERE id = ?", (model_id,)
    ) as cur:
        row = await cur.fetchone()
    return row[0] if row else model_id


async def _get_family_for_model(
    model_id: str, db: aiosqlite.Connection
) -> Optional[tuple[str, list[tuple[str, str, int]]]]:
    """
    Retorna (family_id, [(model_id, provider_id, fallback_order), ...])
    ordenado por fallback_order ASC, ou None se o modelo não pertence a nenhuma família.
    """
    async with db.execute(
        "SELECT family_id FROM model_family_members WHERE model_id = ?",
        (model_id,)
    ) as cur:
        row = await cur.fetchone()

    if not row:
        return None

    family_id = row[0]

    # Busca todos os membros da família cujo modelo e provedor estejam habilitados
    async with db.execute(
        """
        SELECT mfm.model_id, m.provider_id, mfm.fallback_order
        FROM model_family_members mfm
        JOIN models m ON m.id = mfm.model_id
        JOIN providers p ON p.id = m.provider_id
        WHERE mfm.family_id = ? AND m.enabled = 1 AND p.enabled = 1
        ORDER BY mfm.fallback_order ASC
        """,
        (family_id,)
    ) as cur:
        members = await cur.fetchall()

    return family_id, [(r[0], r[1], r[2]) for r in members]


async def _get_next_best_ranked_model(
    db: aiosqlite.Connection,
    exclude_model_ids: list[str],
    exclude_family_ids: list[str],
) -> Optional[tuple[str, str, str]]:
    """
    Retorna (model_id, provider_id, display_name) do melhor modelo disponível
    no ranking geral, excluindo os modelos e famílias especificados.

    Tier 2: fallback para fora da família, baseado em nexuslocal_score.
    Garante que tanto o modelo (m.enabled = 1) quanto o provedor (p.enabled = 1) estejam ativos.
    """
    # Constrói lista de exclusão por família (model_ids dos membros das famílias excluídas)
    family_excluded_model_ids: list[str] = []
    for fid in exclude_family_ids:
        async with db.execute(
            "SELECT model_id FROM model_family_members WHERE family_id = ?", (fid,)
        ) as cur:
            rows = await cur.fetchall()
        family_excluded_model_ids.extend(r[0] for r in rows)

    all_excluded = set(exclude_model_ids) | set(family_excluded_model_ids)

    # Query: modelos e provedores habilitados com registro de ranking, não esgotados, não excluídos
    async with db.execute(
        """
        SELECT m.id, m.provider_id, m.display_name, r.nexuslocal_score
        FROM models m
        JOIN providers p ON p.id = m.provider_id
        JOIN model_rankings r ON r.model_id = m.id
        LEFT JOIN model_quota_status q ON q.model_id = m.id
        WHERE m.enabled = 1
          AND p.enabled = 1
          AND (q.status IS NULL OR q.status = 'available')
        ORDER BY r.nexuslocal_score DESC
        """
    ) as cur:
        rows = await cur.fetchall()

    from backend.ranking.token_bucket import token_bucket_manager
    candidate_fallback = None
    for row in rows:
        mid, pid, dname, _ = row
        if mid not in all_excluded:
            if token_bucket_manager.is_provider_available(pid):
                return mid, pid, dname
            elif candidate_fallback is None:
                candidate_fallback = (mid, pid, dname)

    return candidate_fallback


async def resolve_model_with_failover(
    requested_model_id: str,
    db: aiosqlite.Connection,
    failover_reason: str = "rate_limit",
    failover_enabled: bool = True,
    force_skip: bool = False,
    exclude_model_ids: Optional[list[str]] = None,
) -> ResolvedModel:
    """
    Resolve o modelo final a ser usado, com cascata de failover de 2 tiers.

    Args:
        requested_model_id: O modelo que o usuário/sistema solicitou.
        db: Conexão aberta com nexuslocal.db.
        failover_reason: Motivo do failover, se ocorrer ('rate_limit' | 'error').
        failover_enabled: Se False, não faz failover e levanta NoAvailableModelError
                          imediatamente se o modelo estiver esgotado.
        force_skip: Se True, ignora o status "available" do modelo e força o failover.
        exclude_model_ids: Lista de modelos já tentados ou throttled no mesmo turno.

    Returns:
        ResolvedModel com o modelo final (com ou sem failover).

    Raises:
        NoAvailableModelError: Se nenhum modelo disponível for encontrado.
    """
    if exclude_model_ids and requested_model_id in exclude_model_ids:
        force_skip = True

    # ── Verificação de integridade e ativação (modelo E provedor) ────────────
    async with db.execute(
        """
        SELECT m.enabled, p.enabled, m.provider_id, m.display_name
        FROM models m
        JOIN providers p ON p.id = m.provider_id
        WHERE m.id = ?
        """,
        (requested_model_id,),
    ) as cur:
        model_row = await cur.fetchone()

    provider_id = None
    display_name = None
    skip_reason = failover_reason

    if not model_row:
        if not failover_enabled:
            raise NoAvailableModelError(
                f"Modelo '{requested_model_id}' não encontrado no banco de dados."
            )
        force_skip = True
        skip_reason = "model_not_found"
    else:
        m_enabled, p_enabled, provider_id, display_name = model_row
        if not m_enabled or not p_enabled:
            force_skip = True
            skip_reason = "provider_disabled" if not p_enabled else "model_disabled"
            failover_reason = skip_reason

    # ── Verificação do modelo solicitado ─────────────────────────────────────
    quota = await get_quota_status(requested_model_id, db)

    if quota["status"] == "available" and not force_skip:
        # Verifica cota preemptiva ANTES de tentar a chamada real
        from backend.ranking.quota_tracker import get_quota_health, QuotaHealth
        health = await get_quota_health(requested_model_id, db)
        
        if health == QuotaHealth.NEAR_LIMIT:
            logger.warning(
                f"Modelo '{requested_model_id}' está NEAR_LIMIT (cota preemptiva quase esgotada). "
                f"Forçando desvio preventivo..."
            )
            return await resolve_model_with_failover(
                requested_model_id, 
                db, 
                failover_reason="preemptive_quota", 
                failover_enabled=failover_enabled, 
                force_skip=True,
                exclude_model_ids=exclude_model_ids,
            )

        # Caminho feliz — sem failover
        return ResolvedModel(
            model_id=requested_model_id,
            provider_id=provider_id,
            display_name=display_name,
            was_failover=False,
            original_model_id=requested_model_id,
        )

    # Modelo esgotado ou desabilitado — verificar se failover está habilitado
    if not failover_enabled:
        status_label = skip_reason if force_skip else quota["status"]
        raise NoAvailableModelError(
            f"Modelo '{requested_model_id}' está indisponível ({status_label}) e failover automático está desabilitado."
        )

    status_label = skip_reason if force_skip else quota["status"]
    logger.warning(
        f"Modelo '{requested_model_id}' está {status_label}. "
        f"Iniciando cascata de failover..."
    )

    # ── Tier 1 — Irmãos da mesma família ─────────────────────────────────────
    family_result = await _get_family_for_model(requested_model_id, db)
    family_id: Optional[str] = None

    if family_result:
        family_id, members = family_result
        logger.info(
            f"Tier 1: família '{family_id}' com {len(members)} membros. "
            f"Tentando irmãos em ordem de fallback..."
        )

        for member_model_id, member_provider_id, fallback_order in members:
            # Pula o modelo original ou modelos já excluídos
            if member_model_id == requested_model_id or (exclude_model_ids and member_model_id in exclude_model_ids):
                continue

            from backend.ranking.token_bucket import token_bucket_manager
            if not token_bucket_manager.is_provider_available(member_provider_id):
                continue

            member_quota = await get_quota_status(member_model_id, db)
            if member_quota["status"] == "available":
                display_name = await _get_display_name(member_model_id, db)
                logger.info(
                    f"✅ Tier 1 failover: '{requested_model_id}' → '{member_model_id}' "
                    f"(fallback_order={fallback_order})"
                )
                return ResolvedModel(
                    model_id=member_model_id,
                    provider_id=member_provider_id,
                    display_name=display_name,
                    was_failover=True,
                    original_model_id=requested_model_id,
                    failover_reason=failover_reason,
                    family_id=family_id,
                )

        logger.warning(
            f"Tier 1 esgotado: todos os membros da família '{family_id}' indisponíveis. "
            f"Avançando para Tier 2..."
        )
    else:
        logger.info(
            f"Modelo '{requested_model_id}' não pertence a nenhuma família. "
            f"Indo direto para Tier 2 (ranking geral)..."
        )

    # ── Tier 2 — Melhor modelo disponível no ranking geral ───────────────────
    all_excluded = list(set([requested_model_id] + (exclude_model_ids or [])))
    next_best = await _get_next_best_ranked_model(
        db=db,
        exclude_model_ids=all_excluded,
        exclude_family_ids=[family_id] if family_id else [],
    )

    if next_best:
        nb_model_id, nb_provider_id, nb_display_name = next_best
        logger.info(
            f"✅ Tier 2 failover: '{requested_model_id}' → '{nb_model_id}' "
            f"(melhor score disponível no ranking geral)"
        )
        return ResolvedModel(
            model_id=nb_model_id,
            provider_id=nb_provider_id,
            display_name=nb_display_name,
            was_failover=True,
            original_model_id=requested_model_id,
            failover_reason=failover_reason,
            family_id=None,
        )

    # ── Nenhum modelo disponível ──────────────────────────────────────────────
    raise NoAvailableModelError(
        f"Todos os modelos configurados estão indisponíveis. "
        f"Não foi possível realizar failover a partir de '{requested_model_id}'."
    )
