"""backend/tools/families/news/ddg_news.py — Provedor DuckDuckGo News (Fallback 2 sem necessidade de chave).
"""
from __future__ import annotations

import asyncio
from typing import Any

from backend.logging_config import get_logger
from backend.tools.base import ToolProvider, ToolResult

logger = get_logger(__name__)


class DDGNewsProvider(ToolProvider):
    provider_id = "ddg_news"
    family = "news"
    base_url = "https://duckduckgo.com"
    fallback_order = 3
    requires_key = False

    def cache_key(self, params: dict) -> str:
        q = (params.get("query") or params.get("q") or "brasil").strip().lower()
        return self.make_deterministic_hash("news:ddg", {"q": q})

    async def execute(self, params: dict) -> ToolResult:
        query = (params.get("query") or params.get("q") or "notícias do dia").strip()
        max_results = min(int(params.get("max_results", 5)), 10)

        def _fetch_news():
            try:
                from ddgs import DDGS
                with DDGS() as ddgs:
                    # news() busca especificamente feeds de notícias
                    try:
                        return list(ddgs.news(query, max_results=max_results))
                    except Exception:
                        # Fallback para text() se news() falhar
                        return list(ddgs.text(f"notícias {query}", max_results=max_results))
            except Exception as e:
                logger.error("[DDGNewsProvider] Erro no DDGS: %s", e)
                return []

        try:
            loop = asyncio.get_running_loop()
            raw_items = await asyncio.wait_for(
                loop.run_in_executor(None, _fetch_news),
                timeout=8.0,
            )

            if not raw_items:
                return ToolResult(
                    success=False,
                    data={},
                    provider_id=self.provider_id,
                    family=self.family,
                    error=f"Nenhuma notícia encontrada no DuckDuckGo para '{query}'",
                )

            articles = []
            for item in raw_items:
                articles.append({
                    "title": item.get("title"),
                    "description": item.get("body"),
                    "url": item.get("url") or item.get("href"),
                    "source": item.get("source") or "DuckDuckGo News",
                    "published_at": item.get("date"),
                    "image": item.get("image"),
                })

            normalized = {
                "query": query,
                "total_results": len(articles),
                "articles": articles,
                "source": "DuckDuckGo News",
            }

            return ToolResult(
                success=True,
                data=normalized,
                provider_id=self.provider_id,
                family=self.family,
            )

        except asyncio.TimeoutError:
            return ToolResult(
                success=False,
                data={},
                provider_id=self.provider_id,
                family=self.family,
                error="Timeout ao buscar notícias no DuckDuckGo",
            )
        except Exception as e:
            logger.error("[DDGNewsProvider] Erro inesperado: %s", e)
            return ToolResult(
                success=False,
                data={},
                provider_id=self.provider_id,
                family=self.family,
                error=str(e),
            )
