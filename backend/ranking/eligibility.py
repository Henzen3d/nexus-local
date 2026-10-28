"""
backend/ranking/eligibility.py
Gate de Elegibilidade Explícito (Filtro Duro antes do Ranking).

Implementa a seção 6.1 do Golden Prompt v3.0:
Um candidato (provider, model) é INELEGÍVEL se qualquer item for verdadeiro:
1. Breaker OPEN, ou quarentena ativa de escopo (402/auth);
2. Cooldown ativo para (provider, model) ou para o canonical_model_id;
3. Modelo desativado / MODEL_DEPRECATED ou provedor desativado;
4. Semáforo de admissão cheio (concorrência por modelo e por provedor);
5. Saturação de quota >= 0.95 (exceto probe canary);
6. Já falhou nesta cascata com o mesmo canônico (exceto último recurso).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Optional, Set, Dict, Any, List
import aiosqlite

from backend.logging_config import get_logger
from backend.ranking.canonical import canonical_model_id
from backend.ranking.token_bucket import token_bucket_manager
from backend.ranking.admission import admission_controller

logger = get_logger(__name__)


@dataclass
class EligibilityResult:
    """Resultado da avaliação de elegibilidade do candidato."""
    eligible: bool
    reason: Optional[str] = None

    def __bool__(self) -> bool:
        return self.eligible


async def check_candidate_eligibility(
    model_id: str,
    provider_id: str,
    db: aiosqlite.Connection,
    *,
    user_id: Optional[str] = None,
    excluded_model_ids: Optional[Set[str]] = None,
    excluded_canonicals: Optional[Set[str]] = None,
    is_canary_probe: bool = False,
    allow_same_canonical_last_resort: bool = False,
    cached_quota_status: Optional[Dict[str, Any]] = None,
) -> EligibilityResult:
    """
    Avalia os 6 critérios de inelegibilidade dura para um candidato (provider, model).
    O score de qualidade NUNCA sobrepõe este filtro.
    """
    now_iso = datetime.now(timezone.utc).isoformat()
    cid = canonical_model_id(model_id)

    # 1. Modelos já excluídos nesta cascata
    if excluded_model_ids and model_id in excluded_model_ids:
        return EligibilityResult(False, "already_attempted_in_cascade")

    # 2. Mesmo canônico já falho nesta cascata (exceto último recurso)
    if excluded_canonicals and cid in excluded_canonicals:
        if not allow_same_canonical_last_resort:
            return EligibilityResult(False, "same_canonical_already_failed")

    # 3. Semáforo de Admissão (Concorrência por modelo e provedor)
    if not admission_controller.is_admission_available(model_id, provider_id):
        return EligibilityResult(False, "admission_concurrency_saturated")

    # 4. Token Bucket / Breaker do provedor
    if not token_bucket_manager.is_provider_available(provider_id):
        return EligibilityResult(False, "provider_circuit_breaker_open")

    # 5. Consulta ativações e status no banco
    import sqlite3
    try:
        async with db.execute("""
            SELECT COALESCE(ums.enabled, m.enabled), COALESCE(ups.enabled, p.enabled),
                   COALESCE(q.status, 'available'),
                   q.estimated_reset_at,
                   q.known_rpm, q.known_rpd,
                   q.current_minute_count, q.current_day_count
            FROM models m
            JOIN providers p ON p.id = m.provider_id
            LEFT JOIN user_provider_settings ups ON ups.provider_id = p.id AND ups.user_id = ?
            LEFT JOIN user_model_settings ums ON ums.model_id = m.id AND ums.user_id = ?
            LEFT JOIN model_quota_status q ON q.model_id = m.id
            WHERE m.id = ? AND p.id = ?
        """, (user_id, user_id, model_id, provider_id)) as cur:
            row = await cur.fetchone()
    except sqlite3.OperationalError:
        # Se falhou, tenta sem user_provider_settings mas com known_rpm (ex: testes em memória com schema mínimo)
        try:
            async with db.execute("""
                SELECT m.enabled, p.enabled,
                       COALESCE(q.status, 'available'),
                       q.estimated_reset_at,
                       q.known_rpm, q.known_rpd,
                       q.current_minute_count, q.current_day_count
                FROM models m
                JOIN providers p ON p.id = m.provider_id
                LEFT JOIN model_quota_status q ON q.model_id = m.id
                WHERE m.id = ? AND p.id = ?
            """, (model_id, provider_id)) as cur:
                row = await cur.fetchone()
        except sqlite3.OperationalError:
            # Fallback para schemas antigos onde known_rpm/rpd ainda não existiam
            async with db.execute("""
                SELECT m.enabled, p.enabled,
                       COALESCE(q.status, 'available'),
                       q.estimated_reset_at,
                       NULL, NULL, NULL, NULL
                FROM models m
                JOIN providers p ON p.id = m.provider_id
                LEFT JOIN model_quota_status q ON q.model_id = m.id
                WHERE m.id = ? AND p.id = ?
            """, (model_id, provider_id)) as cur:
                row = await cur.fetchone()

    if not row:
        return EligibilityResult(False, "candidate_not_found")

    m_enabled, p_enabled, q_status, reset_at, known_rpm, known_rpd, min_count, day_count = row

    # Modelo ou Provedor Desativado / MODEL_DEPRECATED
    if not m_enabled:
        return EligibilityResult(False, "model_disabled_or_deprecated")
    if not p_enabled:
        return EligibilityResult(False, "provider_disabled")

    # Breaker OPEN ou Quarentena ativa (status 'open', 'quarantine', 'exhausted', 'cooldown')
    if q_status in ("open", "quarantine"):
        return EligibilityResult(False, f"circuit_breaker_{q_status}")

    # Cooldown ativo para o modelo específico
    if q_status in ("exhausted", "cooldown"):
        if reset_at is None or reset_at > now_iso:
            return EligibilityResult(False, "model_cooldown_active")

    # Cooldown ativo no escopo do CANONICAL_MODEL_ID
    # Se qualquer variante do mesmo canônico estiver em cooldown ativo com reset futuro
    async with db.execute("""
        SELECT q.model_id, q.status, q.estimated_reset_at
        FROM model_quota_status q
        WHERE q.status IN ('exhausted', 'cooldown', 'quarantine', 'open')
          AND (q.estimated_reset_at IS NULL OR q.estimated_reset_at > ?)
    """, (now_iso,)) as cur:
        blocked_rows = await cur.fetchall()

    for b_mid, b_status, _ in blocked_rows:
        if canonical_model_id(b_mid) == cid:
            return EligibilityResult(False, f"canonical_cooldown_active_via_{b_mid}")

    # Saturação de cota >= 0.95 (exceto probe canary)
    if not is_canary_probe:
        if known_rpm and known_rpm > 0:
            if ((min_count or 0) / known_rpm) >= 0.95:
                return EligibilityResult(False, "quota_saturated_rpm")
        if known_rpd and known_rpd > 0:
            if ((day_count or 0) / known_rpd) >= 0.95:
                return EligibilityResult(False, "quota_saturated_rpd")

    return EligibilityResult(True, None)


def is_candidate_eligible_in_memory(
    candidate: Dict[str, Any],
    *,
    excluded_model_ids: Optional[Set[str]] = None,
    excluded_canonicals: Optional[Set[str]] = None,
    blocked_canonicals: Optional[Set[str]] = None,
    is_canary_probe: bool = False,
    allow_same_canonical_last_resort: bool = False,
) -> EligibilityResult:
    """
    Avaliação síncrona de elegibilidade dura baseada no dicionário em RAM (JEV Model Cache).
    Usada dentro de loops de ranking e filtros rápidos sem I/O.
    """
    mid = candidate.get("id", "")
    pid = candidate.get("provider_id", "")
    cid = canonical_model_id(mid)

    if excluded_model_ids and mid in excluded_model_ids:
        return EligibilityResult(False, "already_attempted_in_cascade")

    if excluded_canonicals and cid in excluded_canonicals:
        if not allow_same_canonical_last_resort:
            return EligibilityResult(False, "same_canonical_already_failed")

    if blocked_canonicals and cid in blocked_canonicals:
        return EligibilityResult(False, "canonical_cooldown_active")

    # Semáforo de admissão
    if not admission_controller.is_admission_available(mid, pid):
        return EligibilityResult(False, "admission_concurrency_saturated")

    # Provedor disponível no Token Bucket
    if not token_bucket_manager.is_provider_available(pid):
        return EligibilityResult(False, "provider_circuit_breaker_open")

    # Status de cota / breaker em RAM
    status = candidate.get("quota_status", "available")
    if status in ("exhausted", "cooldown", "open", "quarantine"):
        return EligibilityResult(False, f"model_status_{status}")

    return EligibilityResult(True, None)
