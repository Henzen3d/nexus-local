"""backend/tools/families/weather/hg_brasil.py — Provedor de clima HG Brasil (Fallback 2 com chave opcional).
"""
from __future__ import annotations

from typing import Any
import os

from backend.logging_config import get_logger
from backend.tools.base import ToolProvider, ToolResult

logger = get_logger(__name__)


class HGBrasilWeatherProvider(ToolProvider):
    provider_id = "hg_brasil_weather"
    family = "weather"
    base_url = "https://api.hgbrasil.com/weather"
    fallback_order = 3
    requires_key = True
    env_key_name = "HG_BRASIL_KEY"

    def cache_key(self, params: dict) -> str:
        city = (params.get("city") or "Sao Paulo").strip().lower()
        return self.make_deterministic_hash("weather:hg_brasil", {"city": city})

    async def execute(self, params: dict) -> ToolResult:
        api_key = self.get_api_key()
        if not api_key:
            return ToolResult(
                success=False,
                data={},
                provider_id=self.provider_id,
                family=self.family,
                error="HG_BRASIL_KEY não configurada",
            )

        city = (params.get("city") or "São Paulo").strip()
        query_params = {
            "key": api_key,
            "city_name": city,
            "format": "json",
        }

        try:
            resp = await self._http_get(self.base_url, params=query_params)
            if resp.status_code == 429:
                return ToolResult(
                    success=False,
                    data={},
                    provider_id=self.provider_id,
                    family=self.family,
                    error="HG Brasil rate limit (HTTP 429)",
                )
            if resp.status_code != 200:
                return ToolResult(
                    success=False,
                    data={},
                    provider_id=self.provider_id,
                    family=self.family,
                    error=f"HG Brasil HTTP {resp.status_code}",
                )

            body = resp.json()
            results = body.get("results", {})
            if not results:
                return ToolResult(
                    success=False,
                    data={},
                    provider_id=self.provider_id,
                    family=self.family,
                    error="Dados não encontrados na HG Brasil",
                )

            forecast_list = []
            for f in results.get("forecast", [])[:3]:
                forecast_list.append({
                    "date": f.get("date"),
                    "temp_max": f.get("max"),
                    "temp_min": f.get("min"),
                    "weather": f.get("description"),
                })

            normalized = {
                "location": f"{results.get('city_name', city)}",
                "current": {
                    "temperature": results.get("temp"),
                    "unit": "°C",
                    "weather_description": results.get("description"),
                    "humidity": results.get("humidity"),
                    "wind_speed": results.get("wind_speedy"),
                },
                "forecast": forecast_list,
                "source": "HG Brasil Clima",
            }

            return ToolResult(
                success=True,
                data=normalized,
                provider_id=self.provider_id,
                family=self.family,
            )

        except Exception as e:
            logger.error("[HGBrasilWeatherProvider] Erro ao consultar HG Brasil: %s", e)
            return ToolResult(
                success=False,
                data={},
                provider_id=self.provider_id,
                family=self.family,
                error=str(e),
            )
