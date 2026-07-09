"""
Teste da subtarefa 3.4 — Cálculo do NexusLocal Score com dados reais.
Roda o scorer contra o nexuslocal.db e imprime o ranking completo.
"""
import asyncio
import sys
from pathlib import Path

# Garante que o root do projeto está no path para importar backend.*
ROOT = Path(__file__).resolve().parents[2]  # ../../  -> Multi+
sys.path.insert(0, str(ROOT))

from backend.database import DB_PATH
from backend.ranking.scorer import compute_all_scores, persist_scores
import aiosqlite


async def run():
    print(f"DB: {DB_PATH}\n")
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row

        # Verifica quantos modelos existem no ranking bruto
        async with db.execute("SELECT COUNT(*) FROM model_rankings") as cur:
            total_raw = (await cur.fetchone())[0]
        print(f"Registros em model_rankings: {total_raw}")

        # Verifica uso interno acumulado
        try:
            async with db.execute("SELECT COUNT(*) FROM model_usage_log") as cur:
                total_usage = (await cur.fetchone())[0]
            print(f"Registros em model_usage_log: {total_usage}")
        except Exception:
            print("model_usage_log vazia ou inexistente (uso interno = 0 para todos)")
            total_usage = 0

        print("\n--- Calculando NexusLocal Scores ---\n")
        scored = await compute_all_scores(db)

        if not scored:
            print("AVISO: nenhum modelo retornado. Verifique se model_rankings está populada.")
            return

        print(f"{'Posição':<8} {'Model ID':<40} {'Score':>8}  {'Quality':>8}  {'Pop.Rank':>9}  {'Uso':>6}")
        print("-" * 95)
        for i, s in enumerate(scored, 1):
            pop = s.popularity_rank if s.popularity_rank is not None else "—"
            print(
                f"#{i:<7} {s.model_id:<40} {s.nexuslocal_score:>8.2f}  "
                f"{s.quality_score:>8.1f}  {str(pop):>9}  {s.internal_usage_count:>6}"
            )

        print(f"\nTotal de modelos ranqueados: {len(scored)}")

        # Persiste os scores recalculados no DB
        updated = await persist_scores(db, scored)
        print(f"Scores persistidos na tabela model_rankings: {updated}")


asyncio.run(run())
