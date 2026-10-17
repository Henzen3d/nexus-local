"""backend/tests/test_tools_families.py — Testes dos provedores de ferramentas das famílias.
"""
from __future__ import annotations

import pytest
from backend import database as dbmod
from backend.tools.base import ToolResult
from backend.tools.families.weather.open_meteo import OpenMeteoProvider
from backend.tools.families.currency.awesomeapi import AwesomeAPIProvider
from backend.tools.families.brasil.brasilapi import BrasilAPIProvider
from backend.tools.families.knowledge.wikipedia import WikipediaProvider
from backend.tools.families.code_exec.piston import PistonProvider
from backend.tools.families.diagrams.kroki import KrokiProvider


@pytest.mark.asyncio
async def test_open_meteo_cache_key():
    p = OpenMeteoProvider()
    k1 = p.cache_key({"city": "São Paulo", "days": 3})
    k2 = p.cache_key({"city": "são paulo", "days": 3})
    assert k1 == k2, "Cache key deve ser determinística e insensível a maiúsculas na cidade"


@pytest.mark.asyncio
async def test_awesomeapi_cache_key():
    p = AwesomeAPIProvider()
    k1 = p.cache_key({"from": "USD", "to": "BRL"})
    k2 = p.cache_key({"from": "usd", "to": "brl"})
    assert k1 == k2


@pytest.mark.asyncio
async def test_brasilapi_cache_key():
    p = BrasilAPIProvider()
    k1 = p.cache_key({"type": "cep", "value": "01001-000"})
    k2 = p.cache_key({"type": "cep", "value": "01001000"})
    assert k1 == k2, "Cache key de CEP deve normalizar traços"


@pytest.mark.asyncio
async def test_wikipedia_cache_key():
    p = WikipediaProvider()
    k1 = p.cache_key({"query": "Alan Turing", "lang": "pt"})
    k2 = p.cache_key({"query": "alan turing", "lang": "pt"})
    assert k1 == k2


@pytest.mark.asyncio
async def test_piston_code_execution_mock(monkeypatch):
    p = PistonProvider()

    class FakeResponse:
        status_code = 200

        def json(self):
            return {
                "language": "python",
                "version": "3.10.0",
                "run": {
                    "stdout": "42\n",
                    "stderr": "",
                    "code": 0,
                    "output": "42\n",
                },
            }

    async def fake_http_post(url, json_data=None, content=None, headers=None, timeout=None):
        return FakeResponse()

    monkeypatch.setattr(p, "_http_post", fake_http_post)

    result = await p.execute({"language": "python", "code": "print(42)"})
    assert result.success is True
    assert result.data["stdout"] == "42\n"
    assert result.data["exit_code"] == 0
    assert result.data["language"] == "python"


@pytest.mark.asyncio
async def test_kroki_diagram_mock(monkeypatch):
    p = KrokiProvider()

    class FakeSvgResponse:
        status_code = 200
        text = "<svg viewBox='0 0 100 100'><circle cx='50' cy='50' r='40'/></svg>"

    async def fake_http_post(url, *args, **kwargs):
        return FakeSvgResponse()

    monkeypatch.setattr(p, "_http_post", fake_http_post)

    result = await p.execute({"type": "mermaid", "source": "graph TD; A-->B;"})
    assert result.success is True
    assert "<svg" in result.data["svg"]
    assert result.data["diagram_type"] == "mermaid"


def test_detect_mermaid_as_diagram_artifact():
    from backend.orchestration.artifacts import detect_artifacts

    content = """
Aqui está o diagrama:
```mermaid
%% arquivo: fluxo-autenticacao-jwt.mmd
sequenceDiagram
    participant C as Cliente
    participant G as API Gateway
    C->>G: POST /auth/login
```
Espero que ajude!
"""
    arts = detect_artifacts(content)
    assert len(arts) == 1
    assert arts[0]["type"] == "diagram"
    assert arts[0]["title"] == "fluxo-autenticacao-jwt.mmd"
    assert "sequenceDiagram" in arts[0]["content"]
