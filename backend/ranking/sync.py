"""
backend/ranking/sync.py
Job de sincronização e atualização de rankings periódicos ou manuais.
Combina fontes externas (OpenRouter) com o curador local (model_rankings.json)
e uso interno para recalcular os scores e atualizar as tabelas do DB.
"""

import logging
import asyncio
from typing import Dict, List, Any
import aiosqlite

from backend.database import get_db
from backend.ranking.sources import StaticRegistrySource, OpenRouterRankingSource
from backend.ranking.scorer import compute_all_scores, persist_scores

logger = logging.getLogger("nexuslocal.ranking.sync")

# Lock simples para evitar execuções de sincronização concorrentes
_sync_lock = asyncio.Lock()

async def sync_rankings() -> Dict[str, Any]:
    """
    Executa o fluxo completo de sincronização e cálculo de scores:
    1. Busca a popularidade dinâmica do OpenRouter + qualidade do JSON local.
    2. Insere/atualiza os dados brutos na tabela model_rankings.
    3. Agrega estatísticas de uso interno e roda o Scorer.
    4. Atualiza a coluna nexuslocal_score na tabela model_rankings.
    
    Retorna um dicionário com estatísticas sobre a sincronização realizada.
    """
    if _sync_lock.locked():
        logger.warning("Uma sincronização de rankings já está em andamento.")
        return {"status": "ignored", "message": "Sincronização já em execução"}

    async with _sync_lock:
        logger.info("Iniciando sincronização periódica de rankings...")
        
        static_src = StaticRegistrySource()
        or_src = OpenRouterRankingSource(static_src)
        
        try:
            # 1. Fetch de dados das fontes externas/locais combinados
            entries = await or_src.fetch()
            logger.info(f"Obtidas {len(entries)} entradas de rankings para processar.")
            
            db = await get_db()
            try:
                # 2. Atualizar dados brutos (quality_score e popularity_rank) no DB
                # Apenas atualizamos registros de modelos que já estão cadastrados na tabela models
                # para respeitar a integridade referencial.
                updated_entries_count = 0
                for entry in entries:
                    model_id = entry["model_id"]
                    
                    # Verifica se o modelo existe na tabela principal 'models'
                    # Se model_id for genérico (como 'deepseek-r1'), procuramos correspondências
                    # que tenham model_id contendo essa chave (ex: 'openrouter/deepseek-r1')
                    async with db.execute(
                        "SELECT id FROM models WHERE id = ? OR id LIKE ?",
                        (model_id, f"%/{model_id}%")
                    ) as cursor:
                        matched_models = [row[0] for row in await cursor.fetchall()]

                    for matched_id in matched_models:
                        # Insere ou substitui na tabela model_rankings
                        # Se já existir, atualiza os campos mantendo o resto intacto
                        await db.execute(
                            """
                            INSERT INTO model_rankings (model_id, quality_score, popularity_rank, source, updated_at)
                            VALUES (?, ?, ?, ?, datetime('now'))
                            ON CONFLICT(model_id) DO UPDATE SET
                                quality_score = excluded.quality_score,
                                popularity_rank = excluded.popularity_rank,
                                source = excluded.source,
                                updated_at = datetime('now')
                            """,
                            (
                                matched_id,
                                entry["quality_score"],
                                entry["popularity_rank"],
                                "hybrid"
                            )
                        )
                        updated_entries_count += 1
                
                await db.commit()
                logger.info(f"Dados brutos inseridos/atualizados para {updated_entries_count} ids de modelos.")

                # 3. Executar o cálculo do NexusLocal Score para todos os modelos no ranking
                scored_models = await compute_all_scores(db)
                
                # 4. Salvar os novos scores calculados
                persist_count = await persist_scores(db, scored_models)

                return {
                    "status": "success",
                    "processed_entries": len(entries),
                    "mapped_models": updated_entries_count,
                    "updated_scores": persist_count
                }
            finally:
                await db.close()
                
        except Exception as e:
            logger.error(f"Erro durante a sincronização de rankings: {e}", exc_info=True)
            return {"status": "error", "message": str(e)}


async def start_periodic_sync_job(interval_hours: float = 24.0):
    """
    Loop de background de sincronização periódica (24h padrão).
    """
    logger.info(f"Loop periódico de sincronização iniciado (intervalo: {interval_hours} horas)")
    while True:
        try:
            await sync_rankings()
        except Exception as e:
            logger.error(f"Falha não tratada no job de sync de rankings: {e}")
        
        # Converte horas para segundos e aguarda
        await asyncio.sleep(interval_hours * 3600)
