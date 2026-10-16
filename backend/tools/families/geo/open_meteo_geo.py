"""backend/tools/families/geo/open_meteo_geo.py — Provedor Open-Meteo Geocoding (Fallback rápido sem rate limits estritos).
"""
from __future__ import annotations

from typing import Any

from backend.logging_config import get_logger
from backend.tools.base import ToolProvider, ToolResult

logger = get_logger(__name__)


class OpenMeteoGeoProvider(ToolProvider):
    provider_id = "open_meteo_geo"
    family = "geo"
    base_url = "https://geocoding-api.open-meteo.com/v1"
    fallback_order = 2
    requires_key = False

    def cache_key(self, params: dict) -> str:
        q = (params.get("query") or params.get("q") or params.get("address") or "").strip().lower()
        return self.make_deterministic_hash("geo:open_meteo", {"q": q})

    async def execute(self, params: dict) -> ToolResult:
        query = (params.get("query") or params.get("q") or params.get("address") or "").strip()
        if not query:
            return ToolResult(
                success=False,
                data={},
                provider_id=self.provider_id,
                family=self.family,
                error="Parâmetro 'query' é obrigatório para geocodificação",
            )

        url = f"{self.base_url}/search"
        query_params = {
            "name": query,
            "count": 1,
            "language": "pt",
            "format": "json",
        }

        try:
            resp = await self._http_get(url, params=query_params, timeout=8.0)
            if resp.status_code != 200:
                return ToolResult(
                    success=False,
                    data={},
                    provider_id=self.provider_id,
                    family=self.family,
                    error=f"Open-Meteo Geo HTTP {resp.status_code}",
                )

            body = resp.json()
            results = body.get("results", [])
            if not results:
                return ToolResult(
                    success=False,
                    data={},
                    provider_id=self.provider_id,
                    family=self.family,
                    error=f"Localização '{query}' não encontrada no Open-Meteo Geocoding",
                )

            top = results[0]
            loc_label = top.get("name", "")
            if top.get("admin1"):
                loc_label += f", {top['admin1']}"
            if top.get("country"):
                loc_label += f" - {top['country']}"

            normalized = {
                "display_name": loc_label,
                "lat": float(top.get("latitude", 0.0)),
                "lon": float(top.get("longitude", 0.0)),
                "type": "city",
                "importance": 0.8,
                "country": top.get("country"),
                "admin1": top.get("admin1"),
                "source": "Open-Meteo Geocoding",
            }

            return ToolResult(
                success=True,
                data=normalized,
                provider_id=self.provider_id,
                family=self.family,
            )

        except Exception as e:
            logger.error("[OpenMeteoGeoProvider] Erro ao consultar geolocalização: %s", e)
            return ToolResult(
                success=False,
                data={},
                provider_id=self.provider_id,
                family=self.family,
                error=str(e),
            )
