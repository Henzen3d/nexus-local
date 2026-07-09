import httpx
import json
import logging
from pathlib import Path
from typing import Dict, List, Optional, TypedDict

logger = logging.getLogger("nexuslocal.ranking.sources")

class RankingEntry(TypedDict):
    model_id: str
    quality_score: float
    popularity_rank: Optional[int]

class StaticRegistrySource:
    def __init__(self, file_path: Optional[Path] = None):
        if file_path is None:
            self.file_path = Path(__file__).resolve().parents[1] / "data" / "model_rankings.json"
        else:
            self.file_path = file_path

    def load(self) -> Dict[str, Dict]:
        """Reads and returns the local curation of model rankings."""
        if not self.file_path.exists():
            logger.warning(f"Static rankings file not found at {self.file_path}")
            return {}
        try:
            with open(self.file_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            return data.get("rankings", {})
        except Exception as e:
            logger.error(f"Error loading static rankings: {e}")
            return {}

class OpenRouterRankingSource:
    def __init__(self, static_source: StaticRegistrySource):
        self.static_source = static_source
        self.api_url = "https://openrouter.ai/api/v1/models"

    async def fetch_popularity_ranks(self) -> Dict[str, int]:
        """Fetches models from OpenRouter ordered by popularity and maps their ranks."""
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.get(self.api_url, params={"sort": "most-popular"})
                if response.status_code == 200:
                    data = response.json()
                    models_list = data.get("data", [])
                    ranks = {}
                    for idx, model in enumerate(models_list):
                        model_id = model.get("id")
                        if model_id:
                            ranks[model_id] = idx + 1
                    return ranks
                else:
                    logger.warning(f"OpenRouter returned status code {response.status_code}")
        except Exception as e:
            logger.error(f"Error fetching rankings from OpenRouter: {e}")
        return {}

    async def fetch(self) -> List[RankingEntry]:
        """
        Combines static quality scores from model_rankings.json with dynamic OpenRouter popularity ranks.
        """
        static_rankings = self.static_source.load()
        popularity_ranks = await self.fetch_popularity_ranks()
        entries: List[RankingEntry] = []

        # We will map each static key (like 'deepseek-r1') to any openrouter model id containing that key
        # And construct a ranking entry for it.
        for key, val in static_rankings.items():
            quality = val.get("quality_score", 0.0)
            pop_rank = val.get("popularity_rank")  # Default from JSON

            # Try to find a dynamic rank match in the OpenRouter models list
            matched_dynamic_ranks = []
            for or_id, rank in popularity_ranks.items():
                if key in or_id:
                    matched_dynamic_ranks.append(rank)
            
            if matched_dynamic_ranks:
                # Use the best popularity rank found among matches
                pop_rank = min(matched_dynamic_ranks)

            # We create a generic entry with the family key. The scorer will resolve this against actual DB models.
            entries.append({
                "model_id": key,
                "quality_score": quality,
                "popularity_rank": pop_rank
            })

        return entries
