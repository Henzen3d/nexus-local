"""backend/tools/families/weather/wttr.py — Provedor de clima wttr.in (Fallback 1).
"""
from __future__ import annotations

from typing import Any
import urllib.parse

from backend.logging_config import get_logger
from backend.tools.base import ToolProvider, ToolResult

logger = get_logger(__name__)


class WttrProvider(ToolProvider):
    provider_id = "wttr_in"
    family = "weather"
    base_url = "https://wttr.in"
    fallback_order = 2
    requires_key = False

    def cache_key(self, params: dict) -> str:
        city = (params.get("city") or "Sao Paulo").strip().lower()
        return self.make_deterministic_hash("weather:wttr", {"city": city})

    async def execute(self, params: dict) -> ToolResult:
        city = (params.get("city") or "São Paulo").strip()
        encoded_city = urllib.parse.quote(city)
        url = f"{self.base_url}/{encoded_city}?format=j1"

        try:
            resp = await self._http_get(url, timeout=8.0)
            if resp.status_code == 429:
                return ToolResult(
                    success=False,
                    data={},
                    provider_id=self.provider_id,
                    family=self.family,
                    error="wttr.in rate limit (HTTP 429)",
                )
            if resp.status_code != 200:
                return ToolResult(
                    success=False,
                    data={},
                    provider_id=self.provider_id,
                    family=self.family,
                    error=f"wttr.in HTTP {resp.status_code}",
                )

            body = resp.json()
            curr_cond = body.get("current_condition", [{}])[0]
            temp_c = float(curr_cond.get("temp_C", 0))
            humidity = int(curr_cond.get("humidity", 0))
            wind_km = float(curr_cond.get("windspeedKmph", 0))
            desc_list = curr_cond.get("lang_pt") or curr_cond.get("weatherDesc") or [{}]
            desc = desc_list[0].get("value", "Clima atual") if desc_list else "Clima atual"

            # Forecast
            weather_days = body.get("weather", [])
            forecast_list = []
            for w in weather_days[:3]:
                day_desc_list = w.get("hourly", [{}])[4].get("lang_pt") or w.get("hourly", [{}])[4].get("weatherDesc") or [{}]
                day_desc = day_desc_list[0].get("value", "") if day_desc_list else ""
                forecast_list.append({
                    "date": w.get("date"),
                    "temp_max": float(w.get("maxtempC", 0)),
                    "temp_min": float(w.get("mintempC", 0)),
                    "weather": day_desc,
                })

            normalized = {
                "location": city,
                "current": {
                    "temperature": temp_c,
                    "unit": "°C",
                    "weather_description": desc,
                    "humidity": humidity,
                    "wind_speed": wind_km,
                    "wind_unit": "km/h",
                },
                "forecast": forecast_list,
                "source": "wttr.in",
            }

            return ToolResult(
                success=True,
                data=normalized,
                provider_id=self.provider_id,
                family=self.family,
            )

        except Exception as e:
            logger.error("[WttrProvider] Erro ao consultar wttr.in: %s", e)
            return ToolResult(
                success=False,
                data={},
                provider_id=self.provider_id,
                family=self.family,
                error=str(e),
            )
