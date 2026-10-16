# Fase 2 — Famílias Complementares

> **Dependência:** Fase 0 completa. Pode rodar em paralelo com Fase 1.
> Implementa as famílias de apoio: News, Translation, Geo e Fun.

---

## 🎯 Objetivo

Ampliar o repertório de dados reais do NexusLocal com notícias, tradução, geolocalização e curiosidades, usando o mesmo framework de failover da Fase 0.

---

## 📋 Tarefas

### T2.1 — Família News (Notícias)

**Diretório:** `backend/tools/families/news/`

#### T2.1.1 — Provider: GNews (Primário)

**Arquivo:** `backend/tools/families/news/gnews.py`

- [ ] Classe `GNewsProvider(ToolProvider)`
- [ ] Endpoint: `GET https://gnews.io/api/v4/search?q={query}&lang={lang}&token={key}`
- [ ] Requer key via `GNEWS_API_KEY` (free tier: 100 req/dia)
- [ ] Parâmetros: `query`, `lang` (pt), `max_results` (5), `topic` (opcional)
- [ ] Resposta normalizada:
  ```python
  {
      "articles": [
          {
              "title": "...",
              "description": "...",
              "url": "https://...",
              "source": "Folha de S.Paulo",
              "published_at": "2026-10-16T12:00:00Z",
              "image": "https://..."
          }
      ],
      "total_results": 42
  }
  ```
- [ ] Cache: 30 minutos
- [ ] Se key ausente → provider `disabled` automaticamente

**Critérios de Aceite:**
- [ ] Retorna notícias em pt-BR por padrão
- [ ] Filtro por tópico funciona (general, world, business, technology, sports)
- [ ] Sem key → failback transparente para próximo provider

#### T2.1.2 — Provider: Currents API (Fallback 1)

**Arquivo:** `backend/tools/families/news/currents.py`

- [ ] Classe `CurrentsProvider(ToolProvider)`
- [ ] Endpoint: `GET https://api.currentsapi.services/v1/search?keywords={q}&language={lang}&apiKey={key}`
- [ ] Requer key via `CURRENTS_API_KEY` (free tier: 600 req/dia)
- [ ] Normaliza para mesmo schema

#### T2.1.3 — Provider: DuckDuckGo News (Fallback 2)

**Arquivo:** `backend/tools/families/news/ddg_news.py`

- [ ] Classe `DDGNewsProvider(ToolProvider)`
- [ ] Reutiliza `ddgs` lib já instalada no projeto
- [ ] Usa método `ddgs.news()` em vez de `ddgs.text()`
- [ ] Sem API key, sem rate limit documentado
- [ ] Fallback final para quando GNews e Currents estão exaustos

#### T2.1.4 — Registro e Testes

- [ ] Registrar 3 providers com `fallback_order: 1, 2, 3`
- [ ] Teste: `backend/tests/test_tools_news.py`
  - [ ] Mock busca de notícias
  - [ ] Teste failover GNews (sem key) → DuckDuckGo
  - [ ] Teste cache 30min

---

### T2.2 — Família Translation (Tradução)

**Diretório:** `backend/tools/families/translation/`

#### T2.2.1 — Provider: LibreTranslate (Primário)

**Arquivo:** `backend/tools/families/translation/libretranslate.py`

- [ ] Classe `LibreTranslateProvider(ToolProvider)`
- [ ] Endpoint: `POST https://libretranslate.com/translate`
- [ ] Body: `{"q": "Hello", "source": "en", "target": "pt", "api_key": "..."}`
- [ ] Key via `LIBRETRANSLATE_API_KEY` (free tier disponível)
- [ ] Resposta normalizada:
  ```python
  {
      "original": "Hello, how are you?",
      "translated": "Olá, como vai você?",
      "source_lang": "en",
      "target_lang": "pt",
      "source": "LibreTranslate"
  }
  ```
- [ ] Cache: 30 dias (traduções são determinísticas)
- [ ] Detecção automática de idioma se `source` não fornecido

#### T2.2.2 — Provider: MyMemory (Fallback)

**Arquivo:** `backend/tools/families/translation/mymemory.py`

- [ ] Classe `MyMemoryProvider(ToolProvider)`
- [ ] Endpoint: `GET https://api.mymemory.translated.net/get?q={text}&langpair={src}|{tgt}`
- [ ] Sem API key
- [ ] Limite: 5000 chars/dia (free tier)
- [ ] Normaliza para mesmo schema

#### T2.2.3 — Registro e Testes

- [ ] Teste: `backend/tests/test_tools_translation.py`
  - [ ] Mock tradução en→pt
  - [ ] Mock failover LibreTranslate → MyMemory
  - [ ] Teste cache longo (30 dias)
  - [ ] Teste com texto > 5000 chars (deve truncar)

---

### T2.3 — Família Geo (Geolocalização)

**Diretório:** `backend/tools/families/geo/`

#### T2.3.1 — Provider: Nominatim/OSM (Primário)

**Arquivo:** `backend/tools/families/geo/nominatim.py`

- [ ] Classe `NominatimProvider(ToolProvider)`
- [ ] Endpoints:
  - Geocoding: `GET https://nominatim.openstreetmap.org/search?q={query}&format=json`
  - Reverse: `GET https://nominatim.openstreetmap.org/reverse?lat={lat}&lon={lon}&format=json`
- [ ] **IMPORTANTE:** Rate limit de 1 req/s — implementar throttle interno
- [ ] Header obrigatório: `User-Agent: NexusLocal/1.0 (contact@email.com)`
- [ ] Resposta normalizada:
  ```python
  {
      "display_name": "São Paulo, SP, Brasil",
      "lat": -23.5505,
      "lon": -46.6333,
      "type": "city",
      "importance": 0.85
  }
  ```
- [ ] Cache: 7 dias (coordenadas são estáticas)

#### T2.3.2 — Provider: Open-Meteo Geocoding (Fallback)

**Arquivo:** `backend/tools/families/geo/open_meteo_geo.py`

- [ ] Classe `OpenMeteoGeoProvider(ToolProvider)`
- [ ] Endpoint: `GET https://geocoding-api.open-meteo.com/v1/search?name={query}`
- [ ] Complementar ao weather — usa mesma infraestrutura
- [ ] Normaliza para mesmo schema

#### T2.3.3 — Registro e Testes

- [ ] Teste: `backend/tests/test_tools_geo.py`
  - [ ] Mock geocoding
  - [ ] Teste throttle (1 req/s)
  - [ ] Teste cache 7 dias

---

### T2.4 — Família Fun (Curiosidades)

**Diretório:** `backend/tools/families/fun/`

#### T2.4.1 — Provider: Random Facts / Aggregator

**Arquivo:** `backend/tools/families/fun/random_facts.py`

- [ ] Classe `RandomFactsProvider(ToolProvider)`
- [ ] APIs agregadas (uma classe, múltiplos endpoints):
  - Fatos: `GET https://uselessfacts.jsph.pl/api/v2/facts/random`
  - Dogs: `GET https://dog.ceo/api/breeds/image/random`
  - Cats: `GET https://api.thecatapi.com/v1/images/search`
  - Advice: `GET https://api.adviceslip.com/advice`
- [ ] Parâmetro: `type` → `fact` | `dog` | `cat` | `advice`
- [ ] Cache: **0** (sem cache — dados aleatórios devem ser frescos)
- [ ] Resposta normalizada por tipo

#### T2.4.2 — Registro e Testes

- [ ] Teste: `backend/tests/test_tools_fun.py`
  - [ ] Mock cada endpoint
  - [ ] Verificar que NÃO cacheia

---

## 📁 Arquivos Criados

| Arquivo | Descrição |
|---|---|
| `backend/tools/families/news/__init__.py` | Package init |
| `backend/tools/families/news/gnews.py` | Provider GNews |
| `backend/tools/families/news/currents.py` | Provider Currents |
| `backend/tools/families/news/ddg_news.py` | Provider DuckDuckGo News |
| `backend/tools/families/translation/__init__.py` | Package init |
| `backend/tools/families/translation/libretranslate.py` | Provider LibreTranslate |
| `backend/tools/families/translation/mymemory.py` | Provider MyMemory |
| `backend/tools/families/geo/__init__.py` | Package init |
| `backend/tools/families/geo/nominatim.py` | Provider Nominatim |
| `backend/tools/families/geo/open_meteo_geo.py` | Provider Open-Meteo Geo |
| `backend/tools/families/fun/__init__.py` | Package init |
| `backend/tools/families/fun/random_facts.py` | Provider Random Facts |
| `backend/tests/test_tools_news.py` | Testes news |
| `backend/tests/test_tools_translation.py` | Testes translation |
| `backend/tests/test_tools_geo.py` | Testes geo |
| `backend/tests/test_tools_fun.py` | Testes fun |

---

## ⏱️ Estimativa

| Subtarefa | Tempo |
|---|---|
| T2.1 News (3 providers + testes) | 2.5h |
| T2.2 Translation (2 providers + testes) | 2h |
| T2.3 Geo (2 providers + testes) | 1.5h |
| T2.4 Fun (1 provider + testes) | 1h |
| **Total** | **~7h** |
