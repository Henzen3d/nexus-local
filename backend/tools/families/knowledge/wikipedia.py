"""backend/tools/families/knowledge/wikipedia.py — Provedor Wikipedia (Resumo enciclopédico e fatos verificáveis).
"""
from __future__ import annotations

import urllib.parse
from typing import Any, Optional

from backend.logging_config import get_logger
from backend.tools.base import ToolProvider, ToolResult

logger = get_logger(__name__)


class WikipediaProvider(ToolProvider):
    provider_id = "wikipedia"
    family = "knowledge"
    base_url = "https://wikipedia.org"
    fallback_order = 1
    requires_key = False

    def cache_key(self, params: dict) -> str:
        q = (params.get("query") or params.get("q") or "").strip().lower()
        lang = (params.get("lang") or "pt").strip().lower()
        return self.make_deterministic_hash("knowledge:wiki", {"q": q, "lang": lang})

    async def execute(self, params: dict) -> ToolResult:
        query = (params.get("query") or params.get("q") or "").strip()
        lang = (params.get("lang") or "pt").strip().lower()

        if not query:
            return ToolResult(
                success=False,
                data={},
                provider_id=self.provider_id,
                family=self.family,
                error="Parâmetro 'query' é obrigatório para busca na Wikipedia",
            )

        try:
            # 1. Tenta obter o summary diretamente do título
            encoded_title = urllib.parse.quote(query.replace(" ", "_"))
            summary_url = f"https://{lang}.wikipedia.org/api/rest_v1/page/summary/{encoded_title}"

            resp = await self._http_get(summary_url, timeout=7.0)
            if resp.status_code == 200:
                body = resp.json()
                if body.get("type") not in ("disambiguation", "no-extract"):
                    normalized = {
                        "title": body.get("title"),
                        "description": body.get("description"),
                        "extract": body.get("extract"),
                        "url": body.get("content_urls", {}).get("desktop", {}).get("page"),
                        "thumbnail": body.get("thumbnail", {}).get("source"),
                        "source": f"Wikipedia ({lang})",
                    }
                    return ToolResult(
                        success=True,
                        data=normalized,
                        provider_id=self.provider_id,
                        family=self.family,
                    )

            # 2. Se falhar ou for ambíguo, faz busca para encontrar o artigo mais relevante
            search_url = f"https://{lang}.wikipedia.org/w/api.php"
            search_params = {
                "action": "query",
                "list": "search",
                "srsearch": query,
                "format": "json",
                "srlimit": 1,
            }

            s_resp = await self._http_get(search_url, params=search_params, timeout=7.0)
            if s_resp.status_code == 200:
                s_body = s_resp.json()
                search_results = s_body.get("query", {}).get("search", [])
                if search_results:
                    top_title = search_results[0].get("title")
                    enc_top = urllib.parse.quote(top_title.replace(" ", "_"))
                    top_summary_url = f"https://{lang}.wikipedia.org/api/rest_v1/page/summary/{enc_top}"
                    top_resp = await self._http_get(top_summary_url, timeout=7.0)
                    if top_resp.status_code == 200:
                        b = top_resp.json()
                        normalized = {
                            "title": b.get("title"),
                            "description": b.get("description"),
                            "extract": b.get("extract"),
                            "url": b.get("content_urls", {}).get("desktop", {}).get("page"),
                            "thumbnail": b.get("thumbnail", {}).get("source"),
                            "source": f"Wikipedia ({lang})",
                        }
                        return ToolResult(
                            success=True,
                            data=normalized,
                            provider_id=self.provider_id,
                            family=self.family,
                        )

            return ToolResult(
                success=False,
                data={},
                provider_id=self.provider_id,
                family=self.family,
                error=f"Nenhum artigo enciclopédico encontrado na Wikipedia ({lang}) para '{query}'",
            )

        except Exception as e:
            logger.error("[WikipediaProvider] Erro ao consultar Wikipedia: %s", e)
            return ToolResult(
                success=False,
                data={},
                provider_id=self.provider_id,
                family=self.family,
                error=str(e),
            )
