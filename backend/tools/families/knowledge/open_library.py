"""backend/tools/families/knowledge/open_library.py — Provedor Open Library (Fallback para livros, autores e obras literárias).
"""
from __future__ import annotations

from typing import Any

from backend.logging_config import get_logger
from backend.tools.base import ToolProvider, ToolResult

logger = get_logger(__name__)


class OpenLibraryProvider(ToolProvider):
    provider_id = "open_library"
    family = "knowledge"
    base_url = "https://openlibrary.org"
    fallback_order = 2
    requires_key = False

    def cache_key(self, params: dict) -> str:
        q = (params.get("query") or params.get("q") or "").strip().lower()
        return self.make_deterministic_hash("knowledge:openlib", {"q": q})

    async def execute(self, params: dict) -> ToolResult:
        query = (params.get("query") or params.get("q") or "").strip()
        if not query:
            return ToolResult(
                success=False,
                data={},
                provider_id=self.provider_id,
                family=self.family,
                error="Parâmetro 'query' é obrigatório para Open Library",
            )

        url = f"{self.base_url}/search.json"
        query_params = {"q": query, "limit": 3}

        try:
            resp = await self._http_get(url, params=query_params, timeout=8.0)
            if resp.status_code != 200:
                return ToolResult(
                    success=False,
                    data={},
                    provider_id=self.provider_id,
                    family=self.family,
                    error=f"Open Library HTTP {resp.status_code}",
                )

            body = resp.json()
            docs = body.get("docs", [])
            if not docs:
                return ToolResult(
                    success=False,
                    data={},
                    provider_id=self.provider_id,
                    family=self.family,
                    error=f"Nenhum livro ou autor encontrado para '{query}'",
                )

            books = []
            for doc in docs[:3]:
                books.append({
                    "title": doc.get("title"),
                    "author_name": doc.get("author_name", []),
                    "first_publish_year": doc.get("first_publish_year"),
                    "isbn": doc.get("isbn", [])[:3],
                    "publisher": doc.get("publisher", [])[:2],
                })

            normalized = {
                "query": query,
                "total_found": body.get("numFound", len(books)),
                "books": books,
                "source": "Open Library",
            }

            return ToolResult(
                success=True,
                data=normalized,
                provider_id=self.provider_id,
                family=self.family,
            )

        except Exception as e:
            logger.error("[OpenLibraryProvider] Erro ao consultar Open Library: %s", e)
            return ToolResult(
                success=False,
                data={},
                provider_id=self.provider_id,
                family=self.family,
                error=str(e),
            )
