"""
backend/ranking/scorer.py
Motor de cálculo do NexusLocal Score.

Fórmula:
    score = (quality * 0.5) + (popularity_norm * 0.3) + (usage_norm * 0.2)

onde:
    popularity_norm = 100 - min(popularity_rank, 100)   # rank 1 → 99 pts
    usage_norm      = min(usage_count / MAX_USAGE * 100, 100)
"""

import logging
import aiosqlite
from dataclasses import dataclass, field
from typing import List, Optional

logger = logging.getLogger("nexuslocal.ranking.scorer")

# Uso interno máximo esperado para normalização (tunável via config futura)
MAX_EXPECTED_USAGE: int = 500

# Pesos do NexusLocal Score (somam 1.0)
WEIGHT_QUALITY: float = 0.5
WEIGHT_POPULARITY: float = 0.3
WEIGHT_USAGE: float = 0.2


@dataclass
class ScoredModel:
    """Resultado do cálculo de score para um modelo."""
    model_id: str
    quality_score: float
    popularity_rank: Optional[int]
    internal_usage_count: int
    nexuslocal_score: float
    # Breakdown detalhado para exibição em tooltip (Fase 4.4)
    quality_contribution: float
    popularity_contribution: float
    usage_contribution: float
    popularity_normalized: float
    usage_normalized: float
    source: str = "hybrid"


def calculate_nexuslocal_score(
    quality_score: float,
    popularity_rank: Optional[int],
    internal_usage_count: int,
    max_usage: int = MAX_EXPECTED_USAGE,
    weight_quality: float = WEIGHT_QUALITY,
    weight_popularity: float = WEIGHT_POPULARITY,
    weight_usage: float = WEIGHT_USAGE,
) -> dict:
    """
    Calcula o NexusLocal Score combinando três sinais com pesos fixos.

    Args:
        quality_score: Pontuação de qualidade 0-100 (benchmark, curadoria ou llm-stats).
        popularity_rank: Posição no OpenRouter por volume de uso (1 = mais popular).
                         None significa sem dados — recebe nota neutra (50).
        internal_usage_count: Quantidade de usos registrados internamente para esse modelo.
        max_usage: Valor máximo esperado de uso para normalização (default: 500).

    Returns:
        Dicionário com score final e breakdown.
    """
    # Normalização de qualidade — já deve estar 0-100 mas clampamos para garantia
    q = max(0.0, min(float(quality_score), 100.0))

    # Normalização de popularidade:
    # rank 1 → 99, rank 100 → 0, sem rank → neutro 50
    if popularity_rank is not None:
        p_norm = 100.0 - min(float(popularity_rank), 100.0)
    else:
        p_norm = 50.0

    # Normalização de uso interno — escala linear com teto em max_usage
    safe_max = max(max_usage, 1)
    u_norm = min(float(internal_usage_count) / safe_max * 100.0, 100.0)

    q_contrib = q * weight_quality
    p_contrib = p_norm * weight_popularity
    u_contrib = u_norm * weight_usage

    final_score = q_contrib + p_contrib + u_contrib

    return {
        "nexuslocal_score": round(final_score, 4),
        "quality_contribution": round(q_contrib, 4),
        "popularity_contribution": round(p_contrib, 4),
        "usage_contribution": round(u_contrib, 4),
        "popularity_normalized": round(p_norm, 4),
        "usage_normalized": round(u_norm, 4),
    }


async def aggregate_internal_usage(db: aiosqlite.Connection) -> dict:
    """
    Agrega a contagem de uso interno por model_id a partir de model_usage_log.

    Returns:
        Dict[model_id, int] — número de vezes que cada modelo foi usado.
    """
    usage: dict = {}
    try:
        async with db.execute(
            "SELECT model_id, COUNT(*) AS cnt FROM model_usage_log GROUP BY model_id"
        ) as cursor:
            async for row in cursor:
                usage[row[0]] = row[1]
    except Exception as e:
        logger.warning(f"Erro ao agregar uso interno: {e}")
    return usage


async def load_ranking_weights(db: aiosqlite.Connection) -> dict:
    """
    Carrega os pesos e o uso esperado do banco de dados (tabela meta).
    Se não existirem, retorna os valores padrão.
    """
    weights = {
        "weight_quality": WEIGHT_QUALITY,
        "weight_popularity": WEIGHT_POPULARITY,
        "weight_usage": WEIGHT_USAGE,
        "max_expected_usage": MAX_EXPECTED_USAGE
    }
    try:
        async with db.execute(
            "SELECT key, value FROM meta WHERE key IN ('weight_quality', 'weight_popularity', 'weight_usage', 'max_expected_usage')"
        ) as cur:
            async for row in cur:
                try:
                    k, v = row[0], row[1]
                    if k == "max_expected_usage":
                        weights[k] = int(float(v))
                    else:
                        weights[k] = float(v)
                except ValueError:
                    pass
    except Exception as e:
        logger.warning(f"Erro ao carregar pesos de meta: {e}")
    return weights


async def compute_all_scores(db: aiosqlite.Connection) -> List[ScoredModel]:
    """
    Lê todos os registros de model_rankings, obtém o uso interno e recalcula
    o NexusLocal Score para cada modelo.

    Args:
        db: Conexão aberta com nexuslocal.db.

    Returns:
        Lista de ScoredModel ordenada do maior para o menor score.
    """
    usage_map = await aggregate_internal_usage(db)
    weights = await load_ranking_weights(db)

    ranked: List[ScoredModel] = []

    try:
        async with db.execute(
            "SELECT model_id, quality_score, popularity_rank, source FROM model_rankings"
        ) as cursor:
            rows = await cursor.fetchall()
    except Exception as e:
        logger.error(f"Erro ao ler model_rankings: {e}")
        return []

    for row in rows:
        model_id, quality_score, popularity_rank, source = row
        usage_count = usage_map.get(model_id, 0)

        breakdown = calculate_nexuslocal_score(
            quality_score=quality_score or 0.0,
            popularity_rank=popularity_rank,
            internal_usage_count=usage_count,
            max_usage=weights["max_expected_usage"],
            weight_quality=weights["weight_quality"],
            weight_popularity=weights["weight_popularity"],
            weight_usage=weights["weight_usage"],
        )

        ranked.append(
            ScoredModel(
                model_id=model_id,
                quality_score=quality_score or 0.0,
                popularity_rank=popularity_rank,
                internal_usage_count=usage_count,
                nexuslocal_score=breakdown["nexuslocal_score"],
                quality_contribution=breakdown["quality_contribution"],
                popularity_contribution=breakdown["popularity_contribution"],
                usage_contribution=breakdown["usage_contribution"],
                popularity_normalized=breakdown["popularity_normalized"],
                usage_normalized=breakdown["usage_normalized"],
                source=source or "manual",
            )
        )

    ranked.sort(key=lambda m: m.nexuslocal_score, reverse=True)
    logger.info(f"Scores calculados para {len(ranked)} modelos.")
    return ranked


async def persist_scores(db: aiosqlite.Connection, scored: List[ScoredModel]) -> int:
    """
    Persiste os scores calculados de volta na tabela model_rankings.

    Args:
        db: Conexão aberta com nexuslocal.db.
        scored: Lista retornada por compute_all_scores().

    Returns:
        Número de linhas atualizadas.
    """
    updated = 0
    for s in scored:
        try:
            await db.execute(
                """
                UPDATE model_rankings
                SET nexuslocal_score = ?,
                    updated_at       = datetime('now')
                WHERE model_id = ?
                """,
                (s.nexuslocal_score, s.model_id),
            )
            updated += 1
        except Exception as e:
            logger.error(f"Erro ao persistir score de {s.model_id}: {e}")

    await db.commit()
    logger.info(f"{updated} scores persistidos na tabela model_rankings.")
    return updated
