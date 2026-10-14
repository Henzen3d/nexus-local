"""
backend/ranking/sync.py
Sincronização dos dados brutos do ranking (``model_rankings``) e recálculo dos scores.

Para CADA modelo cadastrado em ``models``:
- ``quality_score``   → determinístico: curadoria local (``model_rankings.json``) ou
  heurística de família/geração (``backend/ranking/model_profile.py``), a mesma base do
  Roteador Inteligente. Nunca aleatório.
- ``popularity_rank`` → posição no OpenRouter (``sort=most-popular``) casada por nome
  normalizado entre provedores; ``NULL`` quando o modelo não está listado.
- ``source``          → ``curated`` | ``heuristic``.

Pontos de entrada:
- ``sync_rankings()``             → job completo (com rede), usado no boot, a cada 24 h e
  por ``POST /api/ranking/sync``.
- ``seed_missing_rankings(db)``   → só modelos sem linha (sem rede), chamado após o sync
  de modelos de um provedor.
- ``migrate_legacy_rankings(db)`` → troca linhas antigas (``auto-seed`` aleatórias,
  ``hybrid``/``manual`` da curadoria 2024-25) pela base determinística (migração única).
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any, Dict, Optional, Sequence, Tuple

import aiosqlite

from backend.ranking.scorer import compute_all_scores, persist_scores
from backend.ranking.sources import (
    SOURCE_CURATED,
    SOURCE_LEGACY_RANDOM,
    OpenRouterRankingSource,
    StaticRegistrySource,
    build_popularity_index,
    match_popularity,
    model_key_for,
    resolve_quality,
)

logger = logging.getLogger("nexuslocal.ranking.sync")

# Lock simples para evitar execuções de sincronização concorrentes
_sync_lock = asyncio.Lock()

# Fontes antigas que devem ser substituídas pela base determinística.
LEGACY_SOURCES: Tuple[str, ...] = (SOURCE_LEGACY_RANDOM, "hybrid", "manual", "openrouter", "llm-stats")

_MODEL_ROWS_SQL = (
    "SELECT m.id, m.name, m.provider_id, m.reasoning_control, COALESCE(m.supports_vision, 0) "
    "FROM models m"
)

_UPSERT_SQL = """
    INSERT INTO model_rankings (model_id, quality_score, popularity_rank, source, updated_at)
    VALUES (?, ?, ?, ?, datetime('now'))
    ON CONFLICT(model_id) DO UPDATE SET
        quality_score   = excluded.quality_score,
        popularity_rank = excluded.popularity_rank,
        source          = excluded.source,
        updated_at      = datetime('now')
"""


def _invalidate_router_cache() -> None:
    try:
        from backend.ranking.smart_router import invalidate_model_cache
        invalidate_model_cache()
    except Exception:
        pass


async def _fetch_model_rows(db: aiosqlite.Connection, where: str = "", params: Sequence[Any] = ()) -> list:
    async with db.execute(f"{_MODEL_ROWS_SQL} {where}", tuple(params)) as cur:
        return await cur.fetchall()


async def _upsert_rows(
    db: aiosqlite.Connection,
    rows: list,
    curated_index: Dict[str, Dict],
    popularity_index: Optional[Dict[str, int]],
    existing_popularity: Optional[Dict[str, Optional[int]]] = None,
) -> Dict[str, int]:
    """Grava qualidade/popularidade determinísticas para ``rows`` (sem commit)."""
    stats = {"models": 0, "curated": 0, "heuristic": 0, "matched_popularity": 0}
    for model_id, name, provider_id, reasoning_control, supports_vision in rows:
        quality, source = resolve_quality(
            model_id, name, provider_id, reasoning_control, int(supports_vision or 0), curated_index
        )
        key = model_key_for(model_id, name)
        if popularity_index is not None:
            pop = match_popularity(key, popularity_index)
            if pop is None and source == SOURCE_CURATED:
                pop = curated_index.get(key, {}).get("popularity_rank")
        elif existing_popularity is not None:
            # Sem dados novos do OpenRouter: preserva a última posição conhecida.
            pop = existing_popularity.get(model_id)
        else:
            pop = None
        await db.execute(_UPSERT_SQL, (model_id, quality, pop, source))
        stats["models"] += 1
        stats[source] = stats.get(source, 0) + 1
        if pop is not None:
            stats["matched_popularity"] += 1
    return stats


async def seed_missing_rankings(db: aiosqlite.Connection) -> int:
    """Cria linhas determinísticas (qualidade heurística/curada, sem popularidade) para
    modelos ainda sem registro em ``model_rankings``. Não acessa a rede e não faz commit."""
    rows = await _fetch_model_rows(db, "WHERE m.id NOT IN (SELECT model_id FROM model_rankings)")
    if not rows:
        return 0
    curated_index = StaticRegistrySource().load_index()
    stats = await _upsert_rows(db, rows, curated_index, popularity_index=None)
    logger.info("Ranking: %d modelos novos semeados (heurística determinística).", stats["models"])
    return stats["models"]


async def migrate_legacy_rankings(db: aiosqlite.Connection, recompute: bool = True) -> int:
    """Substitui linhas de fontes legadas (aleatórias ``auto-seed`` e curadoria 2024-25)
    pela base determinística atual. Idempotente: na segunda execução não há linhas legadas.

    Também semeia modelos sem linha. Faz commit quando ``recompute`` é True.
    """
    placeholders = ",".join("?" for _ in LEGACY_SOURCES)
    rows = await _fetch_model_rows(
        db,
        f"JOIN model_rankings r ON r.model_id = m.id WHERE r.source IN ({placeholders}) OR r.source IS NULL",
        LEGACY_SOURCES,
    )
    curated_index = StaticRegistrySource().load_index()
    migrated = 0
    if rows:
        stats = await _upsert_rows(db, rows, curated_index, popularity_index=None)
        migrated = stats["models"]
        logger.info(
            "Ranking: %d registros legados (aleatórios/curadoria antiga) substituídos pela base determinística.",
            migrated,
        )
    seeded = await seed_missing_rankings(db)
    if recompute and (migrated or seeded):
        scored = await compute_all_scores(db)
        await persist_scores(db, scored)  # faz commit
        _invalidate_router_cache()
    return migrated + seeded


async def sync_rankings(
    db: Optional[aiosqlite.Connection] = None,
    fetch_popularity: bool = True,
    openrouter_source: Optional[OpenRouterRankingSource] = None,
) -> Dict[str, Any]:
    """
    Executa o fluxo completo de sincronização e cálculo de scores:
    1. Qualidade determinística (curadoria local > heurística do perfil) para todos os modelos.
    2. Popularidade dinâmica do OpenRouter casada por nome normalizado (opcional).
    3. Upsert em ``model_rankings`` e recálculo/persistência do NexusLocal Score.

    ``db`` pode ser injetado (testes); por padrão abre a conexão via ``get_db``.
    Retorna um dicionário com estatísticas sobre a sincronização realizada.
    """
    if _sync_lock.locked():
        logger.warning("Uma sincronização de rankings já está em andamento.")
        return {"status": "ignored", "message": "Sincronização já em execução"}

    async with _sync_lock:
        logger.info("Iniciando sincronização de rankings...")
        own_db = db is None
        try:
            curated_index = StaticRegistrySource().load_index()
            popularity_index: Optional[Dict[str, int]] = None
            openrouter_models = 0
            if fetch_popularity:
                src = openrouter_source or OpenRouterRankingSource()
                ranks = await src.fetch_popularity_ranks()
                openrouter_models = len(ranks)
                if ranks:
                    popularity_index = build_popularity_index(ranks)
                else:
                    logger.warning("OpenRouter indisponível: popularidade anterior será preservada.")

            if own_db:
                from backend.database import get_db
                db = await get_db()
            assert db is not None
            try:
                rows = await _fetch_model_rows(db)
                existing_pop: Dict[str, Optional[int]] = {}
                async with db.execute(
                    "SELECT model_id, popularity_rank, source FROM model_rankings"
                ) as cur:
                    async for mid, pop, source in cur:
                        # Popularidade aleatória legada nunca é preservada.
                        existing_pop[mid] = None if source == SOURCE_LEGACY_RANDOM else pop

                stats = await _upsert_rows(db, rows, curated_index, popularity_index, existing_pop)
                await db.commit()

                scored_models = await compute_all_scores(db)
                persist_count = await persist_scores(db, scored_models)
                _invalidate_router_cache()

                logger.info(
                    "Ranking sincronizado: %d modelos (%d curados, %d heurísticos), %d com popularidade OpenRouter.",
                    stats["models"], stats.get("curated", 0), stats.get("heuristic", 0), stats["matched_popularity"],
                )
                return {
                    "status": "success",
                    "models": stats["models"],
                    "curated": stats.get("curated", 0),
                    "heuristic": stats.get("heuristic", 0),
                    "matched_popularity": stats["matched_popularity"],
                    "openrouter_models": openrouter_models,
                    "popularity_refreshed": popularity_index is not None,
                    "updated_scores": persist_count,
                }
            finally:
                if own_db:
                    await db.close()

        except Exception as e:
            logger.error(f"Erro durante a sincronização de rankings: {e}", exc_info=True)
            return {"status": "error", "message": str(e)}


async def start_periodic_sync_job(interval_hours: float = 24.0, initial_delay_s: float = 0.0):
    """
    Loop de background de sincronização periódica (24h padrão).
    ``initial_delay_s`` deixa o boot (sync de provedores, warm-ups) terminar antes.
    """
    logger.info(f"Loop periódico de sincronização iniciado (intervalo: {interval_hours} horas)")
    if initial_delay_s > 0:
        await asyncio.sleep(initial_delay_s)
    while True:
        try:
            await sync_rankings()
        except Exception as e:
            logger.error(f"Falha não tratada no job de sync de rankings: {e}")

        # Converte horas para segundos e aguarda
        await asyncio.sleep(interval_hours * 3600)
