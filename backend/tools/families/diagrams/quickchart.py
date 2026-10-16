"""backend/tools/families/diagrams/quickchart.py — Provedor QuickChart para renderização de gráficos Chart.js em SVG/PNG.
"""
from __future__ import annotations

import json
from typing import Any

from backend.logging_config import get_logger
from backend.tools.base import ToolProvider, ToolResult
from backend.tools.security import sanitize_svg

logger = get_logger(__name__)


class QuickChartProvider(ToolProvider):
    provider_id = "quickchart"
    family = "diagrams"
    base_url = "https://quickchart.io"
    fallback_order = 2
    requires_key = False

    def cache_key(self, params: dict) -> str:
        chart = str(params.get("chart") or params.get("source") or params.get("config") or "").strip()
        return self.make_deterministic_hash("diagrams:quickchart", {"c": chart})

    @property
    def ttl_seconds(self) -> int:
        return 3600  # 1 hora

    async def execute(self, params: dict) -> ToolResult:
        chart_input = params.get("chart") or params.get("source") or params.get("config")
        if not chart_input:
            return ToolResult(
                success=False,
                data={},
                provider_id=self.provider_id,
                family=self.family,
                error="Configuração de gráfico não fornecida para QuickChart",
            )

        # Se for string JSON, faz parse
        chart_obj = chart_input
        if isinstance(chart_input, str):
            try:
                chart_obj = json.loads(chart_input)
            except Exception:
                # Se não for JSON válido, tenta encapsular como configuração básica
                chart_obj = {
                    "type": "bar",
                    "data": {
                        "labels": ["Item 1", "Item 2", "Item 3"],
                        "datasets": [{"label": "Dados", "data": [12, 19, 3]}],
                    },
                }

        width = int(params.get("width", 600))
        height = int(params.get("height", 380))

        payload = {
            "chart": chart_obj,
            "width": width,
            "height": height,
            "format": "svg",
            "backgroundColor": "transparent",
        }

        url = f"{self.base_url}/chart"
        try:
            resp = await self._http_post(url, json_data=payload, timeout=12.0)
            if resp.status_code != 200:
                return ToolResult(
                    success=False,
                    data={},
                    provider_id=self.provider_id,
                    family=self.family,
                    error=f"QuickChart HTTP {resp.status_code}: {resp.text[:200]}",
                )

            svg_raw = resp.text
            clean_svg = sanitize_svg(svg_raw)

            normalized = {
                "diagram_type": "chart",
                "svg": clean_svg,
                "source": "QuickChart",
            }

            return ToolResult(
                success=True,
                data=normalized,
                provider_id=self.provider_id,
                family=self.family,
            )

        except Exception as e:
            logger.error("[QuickChartProvider] Erro ao renderizar gráfico: %s", e)
            return ToolResult(
                success=False,
                data={},
                provider_id=self.provider_id,
                family=self.family,
                error=str(e),
            )
