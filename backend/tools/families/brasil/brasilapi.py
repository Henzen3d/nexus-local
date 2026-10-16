"""backend/tools/families/brasil/brasilapi.py — Provedor BrasilAPI (Primário para dados públicos brasileiros).
"""
from __future__ import annotations

import re
from typing import Any

from backend.logging_config import get_logger
from backend.tools.base import ToolProvider, ToolResult

logger = get_logger(__name__)


class BrasilAPIProvider(ToolProvider):
    provider_id = "brasilapi"
    family = "brasil"
    base_url = "https://brasilapi.com.br/api"
    fallback_order = 1
    requires_key = False

    def cache_key(self, params: dict) -> str:
        q_type = (params.get("type") or "cep").strip().lower()
        val = str(params.get("value") or params.get("cep") or params.get("cnpj") or params.get("ddd") or "").strip()
        clean_val = re.sub(r"[^\w]", "", val)
        return self.make_deterministic_hash("brasil:api", {"type": q_type, "val": clean_val})

    async def execute(self, params: dict) -> ToolResult:
        query_type = (params.get("type") or "").strip().lower()
        raw_val = str(params.get("value") or "").strip()

        # Inferência automática de tipo se não informado explicitamente
        if not query_type:
            if params.get("cep"):
                query_type = "cep"
                raw_val = str(params["cep"])
            elif params.get("cnpj"):
                query_type = "cnpj"
                raw_val = str(params["cnpj"])
            elif params.get("ddd"):
                query_type = "ddd"
                raw_val = str(params["ddd"])
            elif params.get("year") or params.get("feriados"):
                query_type = "feriados"
                raw_val = str(params.get("year") or params.get("feriados"))
            else:
                query_type = "cep"

        clean_digits = re.sub(r"\D", "", raw_val)

        try:
            if query_type == "cep":
                if len(clean_digits) != 8:
                    return ToolResult(
                        success=False,
                        data={},
                        provider_id=self.provider_id,
                        family=self.family,
                        error=f"CEP inválido: '{raw_val}'. Deve conter 8 dígitos.",
                    )
                url = f"{self.base_url}/cep/v2/{clean_digits}"
                resp = await self._http_get(url, timeout=8.0)
                if resp.status_code == 404:
                    return ToolResult(
                        success=False,
                        data={},
                        provider_id=self.provider_id,
                        family=self.family,
                        error=f"CEP '{clean_digits}' não encontrado",
                    )
                if resp.status_code != 200:
                    return ToolResult(
                        success=False,
                        data={},
                        provider_id=self.provider_id,
                        family=self.family,
                        error=f"BrasilAPI HTTP {resp.status_code}",
                    )

                body = resp.json()
                normalized = {
                    "type": "cep",
                    "cep": body.get("cep"),
                    "street": body.get("street"),
                    "neighborhood": body.get("neighborhood"),
                    "city": body.get("city"),
                    "state": body.get("state"),
                    "service": body.get("service"),
                    "location": body.get("location", {}),
                    "source": "BrasilAPI (v2)",
                }
                return ToolResult(success=True, data=normalized, provider_id=self.provider_id, family=self.family)

            elif query_type == "cnpj":
                if len(clean_digits) != 14:
                    return ToolResult(
                        success=False,
                        data={},
                        provider_id=self.provider_id,
                        family=self.family,
                        error=f"CNPJ inválido: '{raw_val}'. Deve conter 14 dígitos.",
                    )
                url = f"{self.base_url}/cnpj/v1/{clean_digits}"
                resp = await self._http_get(url, timeout=10.0)
                if resp.status_code != 200:
                    return ToolResult(
                        success=False,
                        data={},
                        provider_id=self.provider_id,
                        family=self.family,
                        error=f"BrasilAPI CNPJ HTTP {resp.status_code}",
                    )

                body = resp.json()
                normalized = {
                    "type": "cnpj",
                    "cnpj": body.get("cnpj"),
                    "razao_social": body.get("razao_social"),
                    "nome_fantasia": body.get("nome_fantasia"),
                    "situacao_cadastral": body.get("descricao_situacao_cadastral"),
                    "cnae_fiscal_descricao": body.get("cnae_fiscal_descricao"),
                    "data_inicio_atividade": body.get("data_inicio_atividade"),
                    "uf": body.get("uf"),
                    "municipio": body.get("municipio"),
                    "bairro": body.get("bairro"),
                    "logradouro": body.get("logradouro"),
                    "numero": body.get("numero"),
                    "cep": body.get("cep"),
                    "source": "BrasilAPI",
                }
                return ToolResult(success=True, data=normalized, provider_id=self.provider_id, family=self.family)

            elif query_type == "ddd":
                ddd_val = clean_digits[:2]
                url = f"{self.base_url}/ddd/v1/{ddd_val}"
                resp = await self._http_get(url, timeout=8.0)
                if resp.status_code != 200:
                    return ToolResult(
                        success=False,
                        data={},
                        provider_id=self.provider_id,
                        family=self.family,
                        error=f"BrasilAPI DDD HTTP {resp.status_code}",
                    )
                body = resp.json()
                normalized = {
                    "type": "ddd",
                    "ddd": ddd_val,
                    "state": body.get("state"),
                    "cities": body.get("cities", [])[:15],
                    "total_cities": len(body.get("cities", [])),
                    "source": "BrasilAPI",
                }
                return ToolResult(success=True, data=normalized, provider_id=self.provider_id, family=self.family)

            elif query_type == "feriados":
                year = clean_digits if len(clean_digits) == 4 else "2026"
                url = f"{self.base_url}/feriados/v1/{year}"
                resp = await self._http_get(url, timeout=8.0)
                if resp.status_code != 200:
                    return ToolResult(
                        success=False,
                        data={},
                        provider_id=self.provider_id,
                        family=self.family,
                        error=f"BrasilAPI Feriados HTTP {resp.status_code}",
                    )
                body = resp.json()
                normalized = {
                    "type": "feriados",
                    "year": int(year),
                    "holidays": body,
                    "source": "BrasilAPI",
                }
                return ToolResult(success=True, data=normalized, provider_id=self.provider_id, family=self.family)

            else:
                return ToolResult(
                    success=False,
                    data={},
                    provider_id=self.provider_id,
                    family=self.family,
                    error=f"Tipo de consulta Brasil não suportado: '{query_type}'",
                )

        except Exception as e:
            logger.error("[BrasilAPIProvider] Erro ao consultar BrasilAPI: %s", e)
            return ToolResult(
                success=False,
                data={},
                provider_id=self.provider_id,
                family=self.family,
                error=str(e),
            )
