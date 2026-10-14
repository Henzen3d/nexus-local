"""
backend/routers/ranking.py
FastAPI router do ranking de modelos.

- GET  /api/ranking               → lista classificada pelo NexusLocal Score, com provedor,
                                    tags do perfil e disponibilidade para o usuário atual.
                                    ``?scope=available`` (padrão) mostra só modelos utilizáveis;
                                    ``?scope=all`` inclui desabilitados/sem chave (marcados).
- GET/POST /api/ranking/weights   → pesos do score.
- POST /api/ranking/sync (admin)  → força a sincronização (qualidade + popularidade OpenRouter).
"""

from fastapi import APIRouter, Depends, HTTPException, Query
from typing import List

from backend.database import get_db
from backend.ranking.scorer import (
    RANKING_SCOPE_ALL,
    RANKING_SCOPE_AVAILABLE,
    ScoredModel,
    build_ranking_overview,
)
from backend.auth import get_current_user, require_admin

from pydantic import BaseModel

router = APIRouter(prefix="/api", tags=["Ranking"])

class RankingWeightsIn(BaseModel):
    weight_quality: float
    weight_popularity: float
    weight_usage: float
    max_expected_usage: int


@router.get("/ranking/weights")
async def get_ranking_weights(current_user: dict = Depends(get_current_user)):
    db = await get_db()
    try:
        from backend.ranking.scorer import load_ranking_weights
        return await load_ranking_weights(db)
    finally:
        await db.close()


@router.post("/ranking/weights")
async def update_ranking_weights(body: RankingWeightsIn, current_user: dict = Depends(require_admin)):
    # Validar que a soma dos pesos seja aproximadamente 1.0 (ou normalizar antes)
    total = body.weight_quality + body.weight_popularity + body.weight_usage
    if total <= 0:
        raise HTTPException(status_code=400, detail="A soma dos pesos deve ser maior que 0.")
    
    db = await get_db()
    try:
        # Insere ou atualiza cada valor de peso na tabela meta
        for k, v in [
            ("weight_quality", body.weight_quality / total),
            ("weight_popularity", body.weight_popularity / total),
            ("weight_usage", body.weight_usage / total),
            ("max_expected_usage", max(1, body.max_expected_usage))
        ]:
            await db.execute(
                "INSERT INTO meta (key, value) VALUES (?, ?) ON CONFLICT(key) DO UPDATE SET value = excluded.value",
                (k, str(v))
            )
        await db.commit()
        
        # Recalcula e persiste os scores após atualizar os pesos
        from backend.ranking.scorer import compute_all_scores, persist_scores
        scores = await compute_all_scores(db)
        await persist_scores(db, scores)
        
        return {"status": "ok", "message": "Pesos calibrados com sucesso."}
    finally:
        await db.close()


@router.get("/ranking", response_model=List[ScoredModel])
async def get_ranking(
    scope: str = Query(RANKING_SCOPE_AVAILABLE, pattern="^(available|all)$"),
    current_user: dict = Depends(get_current_user),
):
    """Retorna os modelos de chat com o NexusLocal Score calculado na hora.

    - ``scope=available`` (padrão): apenas modelos utilizáveis por este usuário
      (modelo e provedor habilitados, chave disponível) — a mesma regra do seletor.
    - ``scope=all``: todos os modelos de chat, com ``available``/``unavailable_reason``.
    - Modelos que não são de chat (embeddings, imagem, TTS…) nunca entram.
    - A lista é ordenada do maior para o menor ``nexuslocal_score``.
    """
    db = await get_db()
    try:
        scores = await build_ranking_overview(
            db, current_user.get("id"), RANKING_SCOPE_ALL if scope == RANKING_SCOPE_ALL else RANKING_SCOPE_AVAILABLE
        )
        return scores
    finally:
        await db.close()


@router.post("/ranking/sync")
async def trigger_ranking_sync(current_user: dict = Depends(require_admin)):
    """Força a sincronização do ranking (qualidade determinística + popularidade OpenRouter)."""
    from backend.ranking.sync import sync_rankings
    result = await sync_rankings()
    if result.get("status") == "error":
        raise HTTPException(status_code=502, detail=result.get("message") or "Falha ao sincronizar o ranking.")
    return result
