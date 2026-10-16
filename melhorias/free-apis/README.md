# 🌐 Free Public APIs — Plano de Integração

> **Objetivo:** Transformar o NexusLocal em um hub inteligente que consulta dados reais do mundo externo (clima, câmbio, notícias, CEP, tradução, execução de código, diagramas e fatos verificáveis) usando exclusivamente APIs públicas gratuitas, com failover automático entre provedores e cache inteligente.

---

## 📋 Índice

1. [Visão Geral da Arquitetura](#visão-geral-da-arquitetura)
2. [Inventário de APIs por Família](#inventário-de-apis-por-família)
3. [Fases de Implementação](#fases-de-implementação)
4. [Estrutura de Diretórios](#estrutura-de-diretórios)
5. [Infraestrutura Existente Reutilizada](#infraestrutura-existente-reutilizada)
6. [Segurança & Prompt Injection](#segurança--prompt-injection)
7. [Cache com TTL por Tipo](#cache-com-ttl-por-tipo)
8. [Auto-Sync com public-apis/public-apis](#auto-sync-com-public-apispublic-apis)
9. [Variáveis de Ambiente](#variáveis-de-ambiente)
10. [Roteiro de Testes](#roteiro-de-testes)
11. [Execução & Deploy](#execução--deploy)

---

## Visão Geral da Arquitetura

```
┌──────────────────────────────────────────────────────────────┐
│                        LLM / Chat                            │
│  "Qual a temperatura em SP?" → detecta intent=weather        │
└──────────────┬───────────────────────────────────────────────┘
               │ tool_call(weather, {city: "São Paulo"})
               ▼
┌──────────────────────────────────────────────────────────────┐
│               backend/tools/dispatcher.py                    │
│  resolve_tool(family="weather") → tenta Open-Meteo           │
│    → 429? marca exausto, tenta wttr.in → tenta HG Brasil    │
└──────────┬──────────────┬──────────────┬─────────────────────┘
           │              │              │
     ┌─────▼─────┐ ┌─────▼─────┐ ┌─────▼──────┐
     │ Open-Meteo │ │  wttr.in  │ │ HG Brasil  │
     │  (prio 1)  │ │  (prio 2) │ │ (prio 3)   │
     └────────────┘ └───────────┘ └────────────┘
           │
     ┌─────▼─────────────────────────────┐
     │  tool_cache (SQLite, TTL 15min)   │
     └───────────────────────────────────┘
```

### Princípios Fundamentais

| Princípio | Descrição |
|---|---|
| **Famílias com Failover** | Cada tipo de dado (weather, news, currency…) é uma "família de ferramentas". Se o provedor primário falha (429/timeout), o próximo é tentado automaticamente — espelhando `model_families` + `model_family_members` + `model_quota_status`. |
| **Cache com TTL** | Respostas são cacheadas em SQLite com TTL configurável por tipo (weather 15min, currency 5min, CEP semanas). Evita chamadas repetitivas e economiza cota. |
| **Segurança** | Dados retornados por ferramentas entram no contexto como bloco delimitado (`<tool_result>…</tool_result>`), nunca como instrução. Previne prompt injection via dados externos. |
| **Zero Chaves** | Todas as APIs selecionadas são 100% gratuitas e não requerem API key (ou oferecem tier free generoso). |

---

## Inventário de APIs por Família

### Família: Weather (Clima)

| Provedor | URL Base | Auth | Rate Limit | Notas |
|---|---|---|---|---|
| **Open-Meteo** | `api.open-meteo.com` | Nenhuma | 10k/dia | Previsão 16 dias, dados históricos |
| **wttr.in** | `wttr.in` | Nenhuma | Sem limite documentado | Formato texto/JSON simples |
| **HG Brasil Weather** | `api.hgbrasil.com/weather` | Key free | 1 req/2s | Foco Brasil, dados de cidades BR |

### Família: News (Notícias)

| Provedor | URL Base | Auth | Rate Limit | Notas |
|---|---|---|---|---|
| **GNews** | `gnews.io/api/v4` | Key free | 100/dia | Multi-idioma, filtros por tópico |
| **Currents API** | `api.currentsapi.services` | Key free | 600/dia | Suporta pt-BR |
| **DuckDuckGo** (fallback) | Via `ddgs` lib | Nenhuma | ~50/min | Já integrado no NexusLocal |

### Família: Currency (Câmbio)

| Provedor | URL Base | Auth | Rate Limit | Notas |
|---|---|---|---|---|
| **AwesomeAPI** | `economia.awesomeapi.com.br` | Nenhuma | Sem limite | Câmbio BRL, histórico |
| **Frankfurter** | `api.frankfurter.app` | Nenhuma | Sem limite | ECB rates, 30+ moedas |

### Família: Brasil (CEP/CNPJ)

| Provedor | URL Base | Auth | Rate Limit | Notas |
|---|---|---|---|---|
| **BrasilAPI** | `brasilapi.com.br/api` | Nenhuma | Sem limite doc | CEP, CNPJ, DDD, bancos, feriados |
| **ViaCEP** | `viacep.com.br/ws` | Nenhuma | Sem limite doc | Apenas CEP |

### Família: Translation (Tradução)

| Provedor | URL Base | Auth | Rate Limit | Notas |
|---|---|---|---|---|
| **LibreTranslate** | `libretranslate.com` | API key free | Variável | Self-host possível |
| **MyMemory** | `api.mymemory.translated.net` | Nenhuma | 5000 chars/dia | Tradução humana contribuída |

### Família: Code Execution (Execução de Código)

| Provedor | URL Base | Auth | Rate Limit | Notas |
|---|---|---|---|---|
| **Piston** | `emkc.org/api/v2/piston` | Nenhuma | 5/s | 70+ linguagens, self-host possível |
| **Judge0 CE** | `judge0-ce.p.rapidapi.com` | RapidAPI free | 50/dia | Compilação + execução |

### Família: Diagrams (Diagramas)

| Provedor | URL Base | Auth | Rate Limit | Notas |
|---|---|---|---|---|
| **Kroki** | `kroki.io` | Nenhuma | Sem limite doc | Mermaid, PlantUML, D2, 20+ formatos |
| **QuickChart** | `quickchart.io` | Nenhuma | 500/mês free | Chart.js renderizado como PNG |

### Família: Knowledge (Conhecimento Verificável)

| Provedor | URL Base | Auth | Rate Limit | Notas |
|---|---|---|---|---|
| **Wikipedia** | `{lang}.wikipedia.org/api/rest_v1` | Nenhuma | 200/s | Resumos, busca, imagens |
| **Wikimedia** | `commons.wikimedia.org/w/api.php` | Nenhuma | 200/s | Imagens CC livres |
| **Open Library** | `openlibrary.org/api` | Nenhuma | Sem limite doc | Livros, autores, capas |

### Família: Geo (Geolocalização)

| Provedor | URL Base | Auth | Rate Limit | Notas |
|---|---|---|---|---|
| **Nominatim (OSM)** | `nominatim.openstreetmap.org` | Nenhuma | 1/s | Geocoding, reverse geocoding |
| **Open-Meteo Geocoding** | `geocoding-api.open-meteo.com` | Nenhuma | 10k/dia | Complemento do weather |

### Família: Fun / Curiosidades

| Provedor | URL Base | Auth | Rate Limit | Notas |
|---|---|---|---|---|
| **Useless Facts** | `uselessfacts.jsph.pl` | Nenhuma | Ilimitado | Fatos curiosos aleatórios |
| **Dog/Cat API** | `dog.ceo/api`, `thecatapi.com` | Nenhuma | Ilimitado | Imagens aleatórias de pets |
| **Advice Slip** | `api.adviceslip.com` | Nenhuma | Ilimitado | Conselhos aleatórios |

---

## Fases de Implementação

> 📄 Documentação detalhada de cada fase está nos arquivos `FASE-*.md` nesta pasta.

| Fase | Nome | Escopo | Arquivos Detalhados |
|---|---|---|---|
| **0** | Infraestrutura Base | Tabelas, base classes, cache, dispatcher | [FASE-00-INFRAESTRUTURA.md](./FASE-00-INFRAESTRUTURA.md) |
| **1** | Famílias Essenciais | Weather, Currency, Brasil, Knowledge | [FASE-01-FAMILIAS-ESSENCIAIS.md](./FASE-01-FAMILIAS-ESSENCIAIS.md) |
| **2** | Famílias Complementares | News, Translation, Geo, Fun | [FASE-02-FAMILIAS-COMPLEMENTARES.md](./FASE-02-FAMILIAS-COMPLEMENTARES.md) |
| **3** | Artifacts Avançados | Piston/Judge0, Kroki/QuickChart no painel | [FASE-03-ARTIFACTS-AVANCADOS.md](./FASE-03-ARTIFACTS-AVANCADOS.md) |
| **4** | Integração LLM | Tool-calling, intent detection, anti-injection | [FASE-04-INTEGRACAO-LLM.md](./FASE-04-INTEGRACAO-LLM.md) |
| **5** | Admin & Observabilidade | Painel, métricas, health, auto-sync repo | [FASE-05-ADMIN-OBSERVABILIDADE.md](./FASE-05-ADMIN-OBSERVABILIDADE.md) |

### Diagrama de Dependências

```
Fase 0 ─────────► Fase 1 ─────────► Fase 2
   │                  │                  │
   │                  ▼                  │
   │              Fase 4 ◄──────────────┘
   │                  │
   ▼                  ▼
Fase 3            Fase 5
```

---

## Estrutura de Diretórios

```
backend/
├── tools/                       ← NOVO: módulo de ferramentas
│   ├── __init__.py
│   ├── base.py                  ← ToolProvider ABC, ToolResult dataclass
│   ├── registry.py              ← Registro de famílias e providers
│   ├── failover.py              ← Lógica de cascata (espelha ranking/failover.py)
│   ├── cache.py                 ← Cache SQLite com TTL por tipo
│   ├── dispatcher.py            ← Orquestrador: intent → família → resultado
│   ├── security.py              ← Sanitização anti-injection
│   ├── families/                ← Uma subpasta por família
│   │   ├── __init__.py
│   │   ├── weather/
│   │   │   ├── __init__.py
│   │   │   ├── open_meteo.py
│   │   │   ├── wttr.py
│   │   │   └── hg_brasil.py
│   │   ├── currency/
│   │   │   ├── __init__.py
│   │   │   ├── awesomeapi.py
│   │   │   └── frankfurter.py
│   │   ├── brasil/
│   │   │   ├── __init__.py
│   │   │   ├── brasilapi.py
│   │   │   └── viacep.py
│   │   ├── knowledge/
│   │   │   ├── __init__.py
│   │   │   ├── wikipedia.py
│   │   │   └── open_library.py
│   │   ├── news/
│   │   │   ├── __init__.py
│   │   │   ├── gnews.py
│   │   │   └── currents.py
│   │   ├── translation/
│   │   │   ├── __init__.py
│   │   │   ├── libretranslate.py
│   │   │   └── mymemory.py
│   │   ├── geo/
│   │   │   ├── __init__.py
│   │   │   └── nominatim.py
│   │   ├── code_exec/
│   │   │   ├── __init__.py
│   │   │   ├── piston.py
│   │   │   └── judge0.py
│   │   ├── diagrams/
│   │   │   ├── __init__.py
│   │   │   ├── kroki.py
│   │   │   └── quickchart.py
│   │   └── fun/
│   │       ├── __init__.py
│   │       └── random_facts.py
│   └── sync_public_apis.py      ← Auto-sync com github.com/public-apis/public-apis
│
├── routers/
│   └── tools.py                 ← NOVO: endpoints REST para admin/health de ferramentas
│
└── tests/
    └── test_tools_*.py          ← Testes por família (banco temporário!)
```

---

## Infraestrutura Existente Reutilizada

O NexusLocal já possui infraestrutura madura que será **espelhada** (não duplicada) para as ferramentas:

### 1. Padrão de Quotas (`backend/ranking/quota.py`)

A tabela `model_quota_status` e as funções `mark_model_exhausted()`, `mark_model_success()`, `release_expired_quotas()` serão o modelo exato para a nova tabela `tool_provider_quota`.

```python
# Existente para modelos:
await mark_model_exhausted("gpt-4o", db, retry_after=3600)

# Novo para ferramentas (mesma API):
await mark_tool_exhausted("open_meteo", db, retry_after=900)
```

### 2. Padrão de Famílias (`model_families` + `model_family_members`)

Cada ferramenta terá famílias (`tool_families`) com membros ordenados por `fallback_order`, exatamente como modelos LLM.

### 3. Free Registry Sync (`backend/free_registry/sync.py`)

O mecanismo de sync com o awesome-free-llm-apis será replicado para o repositório `public-apis/public-apis`, usando o mesmo padrão de `is_registry_stale()` + `clear_and_reload_registry()`.

### 4. Web Search Providers (`backend/web_search/providers.py`)

Os providers de busca web (Brave, DuckDuckGo) seguem o padrão `async def search()` com fallback que será generalizado para todas as famílias de ferramentas.

---

## Segurança & Prompt Injection

### Problema
APIs externas podem retornar dados manipulados que, se injetados diretamente no contexto do LLM, poderiam alterar o comportamento do modelo.

### Solução

```python
# backend/tools/security.py

def wrap_tool_result(tool_name: str, raw_data: dict) -> str:
    """Encapsula o resultado da ferramenta em delimitadores seguros."""
    sanitized = sanitize_data(raw_data)
    return (
        f"<tool_result tool=\"{tool_name}\" timestamp=\"{utcnow()}\">\n"
        f"{json.dumps(sanitized, ensure_ascii=False)}\n"
        f"</tool_result>"
    )

def sanitize_data(data: dict) -> dict:
    """Remove padrões perigosos de dados externos."""
    # 1. Strip tags HTML/script
    # 2. Trunca strings > MAX_FIELD_LENGTH
    # 3. Remove campos suspeitos (ex: "system_prompt", "instructions")
    # 4. Escapa caracteres de controle Unicode
    ...
```

### Regras
- Resultados de ferramentas **NUNCA** entram como `role: system`
- Sempre encapsulados como `role: tool` ou dentro de `<tool_result>` no user message
- Campo `source_url` é validado com `is_safe_public_url()` (já existe no proactive)
- Tamanho máximo de resultado: 4096 chars (trunca com `[…truncated]`)

---

## Cache com TTL por Tipo

| Família | TTL Padrão | Justificativa |
|---|---|---|
| Weather | 15 min | Dados mudam frequentemente mas não a cada segundo |
| Currency | 5 min | Mercado é dinâmico mas não precisa de real-time |
| News | 30 min | Notícias não mudam tão rápido |
| Brasil (CEP) | 7 dias | CEPs raramente mudam |
| Brasil (CNPJ) | 24 horas | Dados cadastrais são relativamente estáticos |
| Translation | 30 dias | Traduções são determinísticas |
| Knowledge | 24 horas | Artigos Wikipedia mudam raramente |
| Geo | 7 dias | Coordenadas geográficas são estáticas |
| Code Exec | 0 (sem cache) | Cada execução pode ter resultado diferente |
| Diagrams | 1 hora | Mesmo input = mesmo diagrama |
| Fun | 0 (sem cache) | Dados aleatórios devem ser sempre frescos |

### Implementação

```sql
CREATE TABLE IF NOT EXISTS tool_cache (
    cache_key    TEXT PRIMARY KEY,  -- sha256(family + provider + params_json)
    family       TEXT NOT NULL,
    provider     TEXT NOT NULL,
    response     TEXT NOT NULL,     -- JSON serializado
    created_at   TEXT NOT NULL,
    expires_at   TEXT NOT NULL,     -- created_at + TTL
    hit_count    INTEGER DEFAULT 0
);

CREATE INDEX IF NOT EXISTS idx_tool_cache_expires ON tool_cache(expires_at);
CREATE INDEX IF NOT EXISTS idx_tool_cache_family ON tool_cache(family);
```

---

## Auto-Sync com public-apis/public-apis

### Objetivo
Periodicamente consultar o repositório [public-apis/public-apis](https://github.com/public-apis/public-apis) para descobrir novas APIs gratuitas relevantes.

### Implementação

```python
# backend/tools/sync_public_apis.py

GITHUB_RAW = "https://raw.githubusercontent.com/public-apis/public-apis/master/README.md"
CATEGORIES_OF_INTEREST = [
    "Weather", "Currency Exchange", "Geocoding", "News",
    "Science & Math", "Books", "Animals", "Open Data"
]

async def sync_public_apis_registry(db):
    """
    1. Faz GET no README.md raw do repositório
    2. Parseia a tabela markdown por categoria
    3. Filtra por Auth == '' ou Auth == 'apiKey' (free tier)
    4. Grava/atualiza na tabela public_apis_registry
    5. Marca timestamp no meta
    """
    ...
```

### Frequência
- **Background job** no `main.py`, similar ao `sync_free_registry`
- Intervalo: 1x por semana (APIs públicas mudam lentamente)
- Tabela `meta` com chave `public_apis_last_synced`

---

## Variáveis de Ambiente

```env
# ── Tool Families ────────────────────────────────────────────
TOOL_CACHE_ENABLED=true                  # Habilitar cache global
TOOL_CACHE_DEFAULT_TTL_SECONDS=900       # TTL padrão (15min)
TOOL_MAX_RETRIES=3                       # Tentativas antes de exaustão
TOOL_TIMEOUT_SECONDS=8                   # Timeout por chamada HTTP
TOOL_MAX_RESULT_CHARS=4096               # Trunca resultado acima disso

# ── Provedores com API Key Free ──────────────────────────────
GNEWS_API_KEY=                           # gnews.io free tier
CURRENTS_API_KEY=                        # currentsapi.services free tier
HG_BRASIL_KEY=                           # hgbrasil.com free tier
JUDGE0_RAPIDAPI_KEY=                     # rapidapi.com free tier (opcional)
LIBRETRANSLATE_API_KEY=                  # libretranslate.com free tier

# ── Sync ─────────────────────────────────────────────────────
PUBLIC_APIS_SYNC_ENABLED=true            # Auto-sync semanal
PUBLIC_APIS_SYNC_INTERVAL_HOURS=168      # 7 dias
```

---

## Roteiro de Testes

> ⚠️ **REGRA FÉRREA:** Todos os testes rodam em banco temporário (`tempfile.mkstemp`), NUNCA no `nexuslocal.db` ao vivo.

### Testes Unitários (por família)

```bash
# Da raiz do projeto:
.venv/Scripts/python -m pytest backend/tests/test_tools_weather.py -v
.venv/Scripts/python -m pytest backend/tests/test_tools_currency.py -v
.venv/Scripts/python -m pytest backend/tests/test_tools_brasil.py -v
# ... etc

# Todos os testes de ferramentas:
.venv/Scripts/python -m pytest backend/tests/test_tools_*.py -v
```

### Testes de Integração (failover)

```bash
.venv/Scripts/python -m pytest backend/tests/test_tools_failover.py -v
```

### Testes de Cache

```bash
.venv/Scripts/python -m pytest backend/tests/test_tools_cache.py -v
```

### Padrão de Fixture

```python
# backend/tests/conftest.py (já existente — adicionar fixtures de tools)

@pytest.fixture
async def tools_db(tmp_path):
    """Banco temporário com schema de ferramentas."""
    db_path = tmp_path / "test_tools.db"
    db = await aiosqlite.connect(str(db_path))
    await init_tool_tables(db)
    yield db
    await db.close()
```

---

## Execução & Deploy

### Desenvolvimento Local

```bash
# 1. Ativar venv
.venv\Scripts\activate     # Windows
source .venv/bin/activate   # Linux/Mac

# 2. Instalar dependências novas (se houver)
pip install -r backend/requirements.txt

# 3. Rodar backend com hot-reload
uvicorn backend.main:app --reload --port 8000

# 4. Rodar testes
python -m pytest backend/tests/test_tools_*.py -v
```

### Deploy em Produção (Docker)

Seguir o pipeline oficial do `AGENTS.md`:

```bash
# 1. Backup & integridade
sqlite3 backend/nexuslocal.db "PRAGMA integrity_check;"
cp backend/nexuslocal.db "backend/nexuslocal_backup_$(date +%Y%m%d_%H%M%S).db"

# 2. Pull
git pull origin main

# 3. Rebuild
docker compose build --no-cache backend frontend

# 4. Restart
docker compose up -d --force-recreate backend frontend

# 5. Health check
docker compose ps
docker exec nexus_backend python -c "import urllib.request; print(urllib.request.urlopen('http://localhost:8000/health').read().decode())"
```

### Migração de Schema

As novas tabelas (`tool_families`, `tool_provider_quota`, `tool_cache`, `public_apis_registry`) seguem o padrão incremental com `try/except sqlite3.OperationalError` dentro de `init_db()` em `database.py`, conforme regra do `AGENTS.md`.

---

## Documentos Relacionados

| Documento | Descrição |
|---|---|
| [FASE-00-INFRAESTRUTURA.md](./FASE-00-INFRAESTRUTURA.md) | Tabelas, classes base, cache, dispatcher |
| [FASE-01-FAMILIAS-ESSENCIAIS.md](./FASE-01-FAMILIAS-ESSENCIAIS.md) | Weather, Currency, Brasil, Knowledge |
| [FASE-02-FAMILIAS-COMPLEMENTARES.md](./FASE-02-FAMILIAS-COMPLEMENTARES.md) | News, Translation, Geo, Fun |
| [FASE-03-ARTIFACTS-AVANCADOS.md](./FASE-03-ARTIFACTS-AVANCADOS.md) | Piston/Judge0, Kroki/QuickChart |
| [FASE-04-INTEGRACAO-LLM.md](./FASE-04-INTEGRACAO-LLM.md) | Tool-calling, intent detection |
| [FASE-05-ADMIN-OBSERVABILIDADE.md](./FASE-05-ADMIN-OBSERVABILIDADE.md) | Painel admin, métricas, auto-sync |
| [CHECKLIST.md](./CHECKLIST.md) | Checklist completo de todas as tarefas |
| [ARCHITECTURE.md](./ARCHITECTURE.md) | Diagrama de arquitetura detalhado |
