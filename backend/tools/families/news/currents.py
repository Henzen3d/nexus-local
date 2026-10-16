"""backend/tools/families/news/currents.py — Provedor de notícias Currents API (Fallback 1).
"""
from __future__ import annotations

import os
from typing import Any

from backend.logging_config import get_logger
from backend.tools.base import ToolProvider, ToolResult

logger = get_logger(__name__)


class CurrentsProvider(ToolProvider):
    provider_id = "currents"
    family = "news"
    base_url = "https://api.currentsapi.services/v1"
    fallback_order = 2
    requires_key = True
    env_key_name = "CURRENTS_API_KEY"

    def cache_key(self, params: dict) -> str:
        q = (params.get("query") or params.get("q") or "brasil").strip().lower()
        lang = (params.get("lang") or "pt").strip().lower()
        return self.make_deterministic_hash("news:currents", {"q": q, "lang": lang})

    async def execute(self, params: dict) -> ToolResult:
        api_key = self.get_api_key()
        if not api_key:
            return ToolResult(
                success=False,
                data={},
                provider_id=self.provider_id,
                family=self.family,
                error="CURRENTS_API_KEY não configurada",
            )

        query = (params.get("query") or params.get("q") or "notícias").strip()
        lang = (params.get("lang") or "pt").strip().lower()
        url = f"{self.base_url}/search"
        query_params = {
            "keywords": query,
            "language": lang,
            "apiKey": api_key,
        }

        try:
            resp = await self._http_get(url, params=query_params, timeout=8.0)
            if resp.status_code == 429:
                return ToolResult(
                    success=False,
                    data={},
                    provider_id=self.provider_id,
                    family=self.family,
                    error="Currents rate limit (HTTP 429)",
                )
            if resp.status_code != 200:
                return ToolResult(
                    success=False,
                    data={},
                    provider_id=self.provider_id,
                    family=self.family,
                    error=f"Currents HTTP {resp.status_code}",
                )

            body = resp.json()
            raw_news = body.get("news", [])
            articles = []
            for n in raw_news[:5]:
                articles.append({
                    "title": n.get("title"),
                    "description": n.get("description"),
                    "url": n.get("url"),
                    "source": n.get("author") or "Currents API",
                    "published_at": n.get("published"),
                    "image": n.get("image"),
                })

            normalized = {
                "query": query,
                "total_results": len(articles),
                "articles": articles,
                "source": "Currents API",
            }

            return ToolResult(
                success=True,
                data=normalized,
                provider_id=self.provider_id,
                family=self.family,
            )

        except Exception as e:
            logger.error("[CurrentsProvider] Erro ao consultar Currents: %s", e)
            return ToolResult(
                success=False,
                data={},
                provider_id=self.provider_id,
                family=self.family,
                error=str(e),
            )
