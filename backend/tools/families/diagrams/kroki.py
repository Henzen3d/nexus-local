"""backend/tools/families/diagrams/kroki.py — Provedor Kroki para renderização universal de diagramas (Primário).
"""
from __future__ import annotations

import httpx
from typing import Any

from backend.logging_config import get_logger
from backend.tools.base import ToolProvider, ToolResult
from backend.tools.security import sanitize_svg

logger = get_logger(__name__)

SUPPORTED_DIAGRAM_TYPES = {
    "mermaid",
    "plantuml",
    "d2",
    "graphviz",
    "dot",
    "ditaa",
    "c4plantuml",
    "excalidraw",
    "nomnoml",
    "actdiag",
    "blockdiag",
    "seqdiag",
    "nwdiag",
    "wavedrom",
}


class KrokiProvider(ToolProvider):
    provider_id = "kroki"
    family = "diagrams"
    base_url = "https://kroki.io"
    fallback_order = 1
    requires_key = False

    def cache_key(self, params: dict) -> str:
        dtype = (params.get("type") or "mermaid").strip().lower()
        src = (params.get("source") or params.get("code") or "").strip()
        return self.make_deterministic_hash("diagrams:kroki", {"type": dtype, "src": src})

    @property
    def ttl_seconds(self) -> int:
        return 3600  # 1 hora

    async def execute(self, params: dict) -> ToolResult:
        raw_type = (params.get("type") or "mermaid").strip().lower()
        dtype = "graphviz" if raw_type == "dot" else raw_type

        source_code = (params.get("source") or params.get("code") or "").strip()
        if not source_code:
            return ToolResult(
                success=False,
                data={},
                provider_id=self.provider_id,
                family=self.family,
                error="Nenhum código de diagrama fornecido",
            )

        if dtype not in SUPPORTED_DIAGRAM_TYPES:
            # Fallback para mermaid se tipo desconhecido
            dtype = "mermaid"

        url = f"{self.base_url}/{dtype}/svg"
        headers = {
            "Content-Type": "text/plain; charset=utf-8",
            "Accept": "image/svg+xml",
        }

        try:
            # Envia o texto plano do diagrama no corpo da requisição POST
            resp = await self._http_post(url, content=source_code.encode("utf-8"), headers=headers, timeout=12.0)

            if resp.status_code == 400:
                err_text = resp.text[:300]
                return ToolResult(
                    success=False,
                    data={},
                    provider_id=self.provider_id,
                    family=self.family,
                    error=f"Erro de sintaxe no diagrama {dtype}: {err_text}",
                )
            if resp.status_code == 429:
                return ToolResult(
                    success=False,
                    data={},
                    provider_id=self.provider_id,
                    family=self.family,
                    error="Kroki rate limit (HTTP 429)",
                )
            if resp.status_code != 200:
                return ToolResult(
                    success=False,
                    data={},
                    provider_id=self.provider_id,
                    family=self.family,
                    error=f"Kroki HTTP {resp.status_code}: {resp.text[:200]}",
                )

            svg_raw = resp.text
            clean_svg = sanitize_svg(svg_raw)

            normalized = {
                "diagram_type": dtype,
                "svg": clean_svg,
                "source": "Kroki",
            }

            return ToolResult(
                success=True,
                data=normalized,
                provider_id=self.provider_id,
                family=self.family,
            )

        except Exception as e:
            logger.error("[KrokiProvider] Erro ao renderizar diagrama: %s", e)
            return ToolResult(
                success=False,
                data={},
                provider_id=self.provider_id,
                family=self.family,
                error=str(e),
            )
