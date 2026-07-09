"""
backend/routers/ranking.py
FastAPI router que expõe o endpoint GET /api/ranking.
Retorna a lista de modelos classificada pelo NexusLocal Score calculado.
"""

from fastapi import APIRouter, Depends, HTTPException
from typing import List

from backend.database import get_db
from backend.ranking.scorer import compute_all_scores, ScoredModel

from pydantic import BaseModel

router = APIRouter(prefix="/api", tags=["Ranking"])

class RankingWeightsIn(BaseModel):
    weight_quality: float
    weight_popularity: float
    weight_usage: float
    max_expected_usage: int


@router.get("/ranking/weights")
async def get_ranking_weights():
    db = await get_db()
    try:
        from backend.ranking.scorer import load_ranking_weights
        return await load_ranking_weights(db)
    finally:
        await db.close()


@router.post("/ranking/weights")
async def update_ranking_weights(body: RankingWeightsIn):
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
async def get_ranking():
    """Retorna a lista de modelos com scores já calculados.
    
    - Se ainda não houver scores, executa o cálculo imediatamente.
    - A lista é ordenada do maior para o menor `nexuslocal_score`.
    """
    db = await get_db()
    try:
        scores = await compute_all_scores(db)
        if not scores:
            raise HTTPException(status_code=404, detail="Nenhum ranking encontrado.")
        return scores
    finally:
        await db.close()
