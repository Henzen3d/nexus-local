# Fase 1 — Famílias Essenciais

> **Dependência:** Fase 0 completa.
> Implementa as 4 famílias de maior impacto: Weather, Currency, Brasil e Knowledge.

---

## 🎯 Objetivo

Dar ao NexusLocal a capacidade de responder perguntas sobre clima, câmbio, dados brasileiros e fatos verificáveis com dados reais, usando APIs gratuitas com failover automático.

---

## 📋 Tarefas

### T1.1 — Família Weather (Clima)

**Diretório:** `backend/tools/families/weather/`

#### T1.1.1 — Provider: Open-Meteo (Primário)

**Arquivo:** `backend/tools/families/weather/open_meteo.py`

- [ ] Classe `OpenMeteoProvider(ToolProvider)`
- [ ] Endpoint: `GET https://api.open-meteo.com/v1/forecast`
- [ ] Parâmetros suportados:
  - `city` → resolve para lat/lon via geocoding API do Open-Meteo
  - `days` → forecast_days (1-16)
  - `units` → `celsius` | `fahrenheit`
- [ ] Resposta normalizada:
  ```python
  {
      "location": "São Paulo, BR",
      "current": {
          "temperature": 22.5,
          "unit": "°C",
          "weather_code": 3,
          "weather_description": "Parcialmente nublado",
          "humidity": 65,
          "wind_speed": 12.3,
          "wind_unit": "km/h"
      },
      "forecast": [
          {"date": "2026-10-17", "temp_max": 28, "temp_min": 18, "weather": "Ensolarado"},
          ...
      ]
  }
  ```
- [ ] Cache key: `sha256(f"weather:open_meteo:{lat:.2f},{lon:.2f}:{days}")`
- [ ] TTL: 15 minutos
- [ ] Tratamento de erros: 429 → marca exausto, timeout → retry 1x

**Critérios de Aceite:**
- [ ] Retorna temperatura atual + previsão para cidades brasileiras e internacionais
- [ ] Geocoding resolve nomes em português ("São Paulo", "Rio de Janeiro")
- [ ] Cache hit evita chamada HTTP dupla em 15 min

#### T1.1.2 — Provider: wttr.in (Fallback 1)

**Arquivo:** `backend/tools/families/weather/wttr.py`

- [ ] Classe `WttrProvider(ToolProvider)`
- [ ] Endpoint: `GET https://wttr.in/{city}?format=j1`
- [ ] Normaliza resposta para o mesmo schema do Open-Meteo
- [ ] Sem API key necessária
- [ ] Menos preciso mas mais resiliente

#### T1.1.3 — Provider: HG Brasil Weather (Fallback 2)

**Arquivo:** `backend/tools/families/weather/hg_brasil.py`

- [ ] Classe `HGBrasilWeatherProvider(ToolProvider)`
- [ ] Endpoint: `GET https://api.hgbrasil.com/weather`
- [ ] Requer key via `HG_BRASIL_KEY` (free tier)
- [ ] Foco em cidades brasileiras
- [ ] Se key não configurada, provider marcado como `disabled`

#### T1.1.4 — Registro e Testes

- [ ] Registrar 3 providers no `registry.py` com `fallback_order: 1, 2, 3`
- [ ] Seed na tabela `tool_providers` via `init_db()`
- [ ] Teste: `backend/tests/test_tools_weather.py`
  - [ ] Mock HTTP para cada provider
  - [ ] Teste de failover (Open-Meteo retorna 429 → wttr.in responde)
  - [ ] Teste de cache hit
  - [ ] Teste com cidade inválida

---

### T1.2 — Família Currency (Câmbio)

**Diretório:** `backend/tools/families/currency/`

#### T1.2.1 — Provider: AwesomeAPI (Primário)

**Arquivo:** `backend/tools/families/currency/awesomeapi.py`

- [ ] Classe `AwesomeAPIProvider(ToolProvider)`
- [ ] Endpoints:
  - Cotação atual: `GET https://economia.awesomeapi.com.br/json/last/{from}-{to}`
  - Histórico: `GET https://economia.awesomeapi.com.br/json/daily/{from}-{to}/{days}`
- [ ] Parâmetros: `from_currency`, `to_currency`, `days` (opcional)
- [ ] Resposta normalizada:
  ```python
  {
      "from": "USD",
      "to": "BRL",
      "rate": 5.42,
      "variation": -0.15,
      "timestamp": "2026-10-16T12:00:00Z",
      "source": "AwesomeAPI"
  }
  ```
- [ ] Cache key: `sha256(f"currency:awesome:{from}:{to}")`
- [ ] TTL: 5 minutos

#### T1.2.2 — Provider: Frankfurter (Fallback)

**Arquivo:** `backend/tools/families/currency/frankfurter.py`

- [ ] Classe `FrankfurterProvider(ToolProvider)`
- [ ] Endpoint: `GET https://api.frankfurter.app/latest?from={from}&to={to}`
- [ ] Suporte a 30+ moedas (dados do ECB)
- [ ] Normaliza para mesmo schema

#### T1.2.3 — Registro e Testes

- [ ] Registrar 2 providers com `fallback_order: 1, 2`
- [ ] Teste: `backend/tests/test_tools_currency.py`
  - [ ] Mock cotação USD-BRL
  - [ ] Mock failover AwesomeAPI → Frankfurter
  - [ ] Teste cache 5min TTL

---

### T1.3 — Família Brasil (CEP/CNPJ)

**Diretório:** `backend/tools/families/brasil/`

#### T1.3.1 — Provider: BrasilAPI (Primário)

**Arquivo:** `backend/tools/families/brasil/brasilapi.py`

- [ ] Classe `BrasilAPIProvider(ToolProvider)`
- [ ] Endpoints:
  - CEP: `GET https://brasilapi.com.br/api/cep/v2/{cep}`
  - CNPJ: `GET https://brasilapi.com.br/api/cnpj/v1/{cnpj}`
  - DDD: `GET https://brasilapi.com.br/api/ddd/v1/{ddd}`
  - Feriados: `GET https://brasilapi.com.br/api/feriados/v3/{year}`
  - Bancos: `GET https://brasilapi.com.br/api/banks/v1`
- [ ] Parâmetros: `type` (cep/cnpj/ddd/feriados/bancos) + valor
- [ ] Resposta normalizada por tipo
- [ ] Cache: CEP 7 dias, CNPJ 24h, Feriados 30 dias

#### T1.3.2 — Provider: ViaCEP (Fallback para CEP)

**Arquivo:** `backend/tools/families/brasil/viacep.py`

- [ ] Classe `ViaCEPProvider(ToolProvider)`
- [ ] Endpoint: `GET https://viacep.com.br/ws/{cep}/json/`
- [ ] Apenas para tipo `cep`
- [ ] Normaliza para mesmo schema do BrasilAPI

#### T1.3.3 — Registro e Testes

- [ ] Registrar providers
- [ ] Teste: `backend/tests/test_tools_brasil.py`
  - [ ] Mock CEP válido e inválido
  - [ ] Mock CNPJ
  - [ ] Failover BrasilAPI → ViaCEP para CEPs

---

### T1.4 — Família Knowledge (Conhecimento Verificável)

**Diretório:** `backend/tools/families/knowledge/`

#### T1.4.1 — Provider: Wikipedia (Primário)

**Arquivo:** `backend/tools/families/knowledge/wikipedia.py`

- [ ] Classe `WikipediaProvider(ToolProvider)`
- [ ] Endpoints:
  - Resumo: `GET https://{lang}.wikipedia.org/api/rest_v1/page/summary/{title}`
  - Busca: `GET https://{lang}.wikipedia.org/w/api.php?action=query&list=search&srsearch={q}`
- [ ] Parâmetros: `query`, `lang` (padrão: pt)
- [ ] Resposta normalizada:
  ```python
  {
      "title": "São Paulo",
      "extract": "São Paulo é um município brasileiro...",
      "url": "https://pt.wikipedia.org/wiki/São_Paulo",
      "thumbnail": "https://...",
      "source": "Wikipedia (pt)"
  }
  ```
- [ ] Cache: 24 horas
- [ ] Anti-alucinação: resumos curtos e verificáveis para contexto do LLM

#### T1.4.2 — Provider: Open Library (Fallback para livros)

**Arquivo:** `backend/tools/families/knowledge/open_library.py`

- [ ] Classe `OpenLibraryProvider(ToolProvider)`
- [ ] Endpoints:
  - Busca: `GET https://openlibrary.org/search.json?q={query}`
  - Livro: `GET https://openlibrary.org/works/{id}.json`
- [ ] Para queries sobre livros, autores, ISBNs

#### T1.4.3 — Registro e Testes

- [ ] Registrar providers
- [ ] Teste: `backend/tests/test_tools_knowledge.py`
  - [ ] Mock busca Wikipedia em pt-BR
  - [ ] Mock summary com thumbnail
  - [ ] Teste de truncamento (artigos longos)

---

## 📁 Arquivos Criados

| Arquivo | Descrição |
|---|---|
| `backend/tools/families/__init__.py` | Package init |
| `backend/tools/families/weather/__init__.py` | Package init |
| `backend/tools/families/weather/open_meteo.py` | Provider Open-Meteo |
| `backend/tools/families/weather/wttr.py` | Provider wttr.in |
| `backend/tools/families/weather/hg_brasil.py` | Provider HG Brasil |
| `backend/tools/families/currency/__init__.py` | Package init |
| `backend/tools/families/currency/awesomeapi.py` | Provider AwesomeAPI |
| `backend/tools/families/currency/frankfurter.py` | Provider Frankfurter |
| `backend/tools/families/brasil/__init__.py` | Package init |
| `backend/tools/families/brasil/brasilapi.py` | Provider BrasilAPI |
| `backend/tools/families/brasil/viacep.py` | Provider ViaCEP |
| `backend/tools/families/knowledge/__init__.py` | Package init |
| `backend/tools/families/knowledge/wikipedia.py` | Provider Wikipedia |
| `backend/tools/families/knowledge/open_library.py` | Provider Open Library |
| `backend/tests/test_tools_weather.py` | Testes weather |
| `backend/tests/test_tools_currency.py` | Testes currency |
| `backend/tests/test_tools_brasil.py` | Testes brasil |
| `backend/tests/test_tools_knowledge.py` | Testes knowledge |

---

## ⏱️ Estimativa

| Subtarefa | Tempo |
|---|---|
| T1.1 Weather (3 providers + testes) | 3h |
| T1.2 Currency (2 providers + testes) | 2h |
| T1.3 Brasil (2 providers + testes) | 2h |
| T1.4 Knowledge (2 providers + testes) | 2h |
| **Total** | **~9h** |
