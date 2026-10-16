"""backend/tools/families/weather/open_meteo.py — Provedor de clima Open-Meteo (Primário).
"""
from __future__ import annotations

from typing import Any, Optional
import httpx

from backend.logging_config import get_logger
from backend.tools.base import ToolProvider, ToolResult

logger = get_logger(__name__)

# Mapeamento oficial de códigos WMO (World Meteorological Organization) para português
WMO_WEATHER_CODES = {
    0: "Céu limpo",
    1: "Predominantemente ensolarado",
    2: "Parcialmente nublado",
    3: "Nublado",
    45: "Nevoeiro",
    48: "Nevoeiro com geada",
    51: "Garoa leve",
    53: "Garoa moderada",
    55: "Garoa densa",
    56: "Garoa congelante leve",
    57: "Garoa congelante densa",
    61: "Chuva fraca",
    62: "Chuva moderada",
    63: "Chuva forte",
    65: "Chuva torrencial",
    66: "Chuva congelante leve",
    67: "Chuva congelante pesada",
    71: "Queda de neve leve",
    73: "Queda de neve moderada",
    75: "Queda de neve pesada",
    77: "Granizo fino",
    80: "Pancadas de chuva leves",
    81: "Pancadas de chuva moderadas",
    82: "Pancadas de chuva violentas",
    85: "Nevasca fraca",
    86: "Nevasca pesada",
    95: "Tempestade com trovoadas",
    96: "Tempestade com granizo leve",
    99: "Tempestade com granizo pesado",
}


class OpenMeteoProvider(ToolProvider):
    provider_id = "open_meteo"
    family = "weather"
    base_url = "https://api.open-meteo.com/v1"
    fallback_order = 1
    requires_key = False

    def cache_key(self, params: dict) -> str:
        city = (params.get("city") or "Sao Paulo").strip().lower()
        days = params.get("days", 3)
        return self.make_deterministic_hash("weather:open_meteo", {"city": city, "days": days})

    async def _resolve_coordinates(self, city: str) -> Optional[dict]:
        """Resolve nome de cidade em lat/lon usando a geocoding API do Open-Meteo."""
        geo_url = "https://geocoding-api.open-meteo.com/v1/search"
        resp = await self._http_get(
            geo_url,
            params={"name": city, "count": 1, "language": "pt", "format": "json"},
            timeout=5.0,
        )
        if resp.status_code != 200:
            return None
        data = resp.json()
        results = data.get("results")
        if not results:
            return None
        first = results[0]
        return {
            "name": first.get("name"),
            "admin1": first.get("admin1"),
            "country": first.get("country"),
            "latitude": first.get("latitude"),
            "longitude": first.get("longitude"),
        }

    async def execute(self, params: dict) -> ToolResult:
        city = (params.get("city") or "").strip()
        if not city:
            city = "São Paulo"

        days = int(params.get("days", 3))
        days = max(1, min(16, days))

        try:
            # 1. Geocodificação
            loc = await self._resolve_coordinates(city)
            if not loc:
                return ToolResult(
                    success=False,
                    data={},
                    provider_id=self.provider_id,
                    family=self.family,
                    error=f"Localização não encontrada: '{city}'",
                )

            lat = loc["latitude"]
            lon = loc["longitude"]
            loc_label = f"{loc['name']}"
            if loc.get("admin1"):
                loc_label += f", {loc['admin1']}"
            if loc.get("country"):
                loc_label += f" - {loc['country']}"

            # 2. Previsão
            forecast_url = f"{self.base_url}/forecast"
            forecast_params = {
                "latitude": lat,
                "longitude": lon,
                "current": "temperature_2m,relative_humidity_2m,weather_code,wind_speed_10m",
                "daily": "weather_code,temperature_2m_max,temperature_2m_min",
                "forecast_days": days,
                "timezone": "auto",
            }

            resp = await self._http_get(forecast_url, params=forecast_params)
            if resp.status_code == 429:
                return ToolResult(
                    success=False,
                    data={},
                    provider_id=self.provider_id,
                    family=self.family,
                    error="Open-Meteo rate limit (HTTP 429)",
                )
            if resp.status_code != 200:
                return ToolResult(
                    success=False,
                    data={},
                    provider_id=self.provider_id,
                    family=self.family,
                    error=f"Open-Meteo HTTP {resp.status_code}: {resp.text[:200]}",
                )

            body = resp.json()
            curr = body.get("current", {})
            w_code = curr.get("weather_code", 0)
            w_desc = WMO_WEATHER_CODES.get(w_code, "Variável")

            daily = body.get("daily", {})
            dates = daily.get("time", [])
            max_temps = daily.get("temperature_2m_max", [])
            min_temps = daily.get("temperature_2m_min", [])
            daily_codes = daily.get("weather_code", [])

            forecast_list = []
            for i in range(len(dates)):
                c_code = daily_codes[i] if i < len(daily_codes) else 0
                forecast_list.append({
                    "date": dates[i],
                    "temp_max": max_temps[i] if i < len(max_temps) else None,
                    "temp_min": min_temps[i] if i < len(min_temps) else None,
                    "weather": WMO_WEATHER_CODES.get(c_code, "Variável"),
                })

            normalized = {
                "location": loc_label,
                "current": {
                    "temperature": curr.get("temperature_2m"),
                    "unit": "°C",
                    "weather_code": w_code,
                    "weather_description": w_desc,
                    "humidity": curr.get("relative_humidity_2m"),
                    "wind_speed": curr.get("wind_speed_10m"),
                    "wind_unit": "km/h",
                },
                "forecast": forecast_list,
                "source": "Open-Meteo",
            }

            return ToolResult(
                success=True,
                data=normalized,
                provider_id=self.provider_id,
                family=self.family,
            )

        except Exception as e:
            logger.error("[OpenMeteoProvider] Erro ao consultar clima: %s", e)
            return ToolResult(
                success=False,
                data={},
                provider_id=self.provider_id,
                family=self.family,
                error=str(e),
            )
