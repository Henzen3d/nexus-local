"""backend/tools/families/news/gnews.py — Provedor de notícias GNews (Primário).
"""
from __future__ import annotations

import os
from typing import Any

from backend.logging_config import get_logger
from backend.tools.base import ToolProvider, ToolResult

logger = get_logger(__name__)


class GNewsProvider(ToolProvider):
    provider_id = "gnews"
    family = "news"
    base_url = "https://gnews.io/api/v4"
    fallback_order = 1
    requires_key = True
    env_key_name = "GNEWS_API_KEY"

    def cache_key(self, params: dict) -> str:
        q = (params.get("query") or params.get("q") or "brasil").strip().lower()
        lang = (params.get("lang") or "pt").strip().lower()
        return self.make_deterministic_hash("news:gnews", {"q": q, "lang": lang})

    async def execute(self, params: dict) -> ToolResult:
        api_key = self.get_api_key()
        if not api_key:
            return ToolResult(
                success=False,
                data={},
                provider_id=self.provider_id,
                family=self.family,
                error="GNEWS_API_KEY não configurada",
            )

        query = (params.get("query") or params.get("q") or "notícias").strip()
        lang = (params.get("lang") or "pt").strip().lower()
        max_results = min(int(params.get("max_results", 5)), 10)

        url = f"{self.base_url}/search"
        query_params = {
            "q": query,
            "lang": lang,
            "max": max_results,
            "apikey": api_key,
        }

        try:
            resp = await self._http_get(url, params=query_params, timeout=8.0)
            if resp.status_code == 429:
                return ToolResult(
                    success=False,
                    data={},
                    provider_id=self.provider_id,
                    family=self.family,
                    error="GNews rate limit (HTTP 429)",
                )
            if resp.status_code != 200:
                return ToolResult(
                    success=False,
                    data={},
                    provider_id=self.provider_id,
                    family=self.family,
                    error=f"GNews HTTP {resp.status_code}",
                )

            body = resp.json()
            articles_raw = body.get("articles", [])
            articles = []
            for a in articles_raw:
                articles.append({
                    "title": a.get("title"),
                    "description": a.get("description"),
                    "url": a.get("url"),
                    "source": a.get("source", {}).get("name", "GNews"),
                    "published_at": a.get("publishedAt"),
                    "image": a.get("image"),
                })

            normalized = {
                "query": query,
                "total_results": body.get("totalArticles", len(articles)),
                "articles": articles,
                "source": "GNews",
            }

            return ToolResult(
                success=True,
                data=normalized,
                provider_id=self.provider_id,
                family=self.family,
            )

        except Exception as e:
            logger.error("[GNewsProvider] Erro ao consultar notícias: %s", e)
            return ToolResult(
                success=False,
                data={},
                provider_id=self.provider_id,
                family=self.family,
                error=str(e),
            )
