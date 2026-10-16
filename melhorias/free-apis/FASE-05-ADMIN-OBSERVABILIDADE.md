# Fase 5 — Admin, Observabilidade & Auto-Sync

> **Dependência:** Fases 0–4 em qualquer estágio de completude.
> Painel administrativo, métricas, health checks e sincronização automática com o repositório public-apis.

---

## 🎯 Objetivo

Dar ao administrador visibilidade e controle total sobre o sistema de ferramentas: quais providers estão saudáveis, quais estão exaustos, taxa de cache hit, uso por usuário, e sincronização automática de novas APIs.

---

## 📋 Tarefas

### T5.1 — Painel Admin de Ferramentas (Frontend)

**Arquivo:** `frontend/src/components/admin/ToolsPanel.tsx`

#### Subtarefas:
- [ ] **T5.1.1** Criar componente `ToolsPanel.tsx`
  - Nova aba no painel admin: "🔧 Ferramentas"
  - Layout em grid: cards por família

- [ ] **T5.1.2** Card de família com status:
  ```
  ┌─────────────────────────────────────────────┐
  │ 🌤️ Weather                        ● Online │
  ├─────────────────────────────────────────────┤
  │ Provider        Status    Latência  Chamadas │
  │ ─────────────────────────────────────────── │
  │ Open-Meteo      ✅ OK      120ms     1,234  │
  │ wttr.in         ✅ OK      340ms       89   │
  │ HG Brasil       ⚠️ 429     —          12    │
  ├─────────────────────────────────────────────┤
  │ Cache hit: 78%  │  TTL: 15min  │  Total: 1335│
  └─────────────────────────────────────────────┘
  ```

- [ ] **T5.1.3** Toggle de enable/disable por provider
- [ ] **T5.1.4** Botão "🔄 Testar" que faz uma chamada de teste ao provider
- [ ] **T5.1.5** Botão "🗑️ Limpar Cache" por família
- [ ] **T5.1.6** Gráfico de uso das últimas 24h (sparkline ou mini bar chart)

#### Critérios de Aceite:
- [ ] Admin vê status real-time de todos os providers
- [ ] Pode habilitar/desabilitar providers individualmente
- [ ] Cache é limpável por família
- [ ] Design consistente com o painel admin existente

---

### T5.2 — Endpoints de Admin (`backend/routers/tools.py`)

#### Subtarefas:
- [ ] **T5.2.1** `GET /api/admin/tools/status`
  ```python
  # Retorna status de todas as famílias e providers
  {
      "families": [
          {
              "id": "weather",
              "display_name": "Clima",
              "enabled": true,
              "providers": [
                  {
                      "id": "open_meteo",
                      "display_name": "Open-Meteo",
                      "status": "available",
                      "consecutive_errors": 0,
                      "avg_latency_ms": 120.5,
                      "total_calls_24h": 1234,
                      "cache_hit_rate": 0.78
                  }
              ]
          }
      ],
      "global_stats": {
          "total_calls_24h": 5678,
          "cache_hit_rate": 0.72,
          "active_providers": 18,
          "exhausted_providers": 2
      }
  }
  ```

- [ ] **T5.2.2** `PUT /api/admin/tools/provider/{id}/toggle`
  - Habilita/desabilita um provider
  - Requer role=admin

- [ ] **T5.2.3** `POST /api/admin/tools/provider/{id}/test`
  - Executa uma chamada de teste ao provider
  - Retorna latência e resultado (ou erro)

- [ ] **T5.2.4** `DELETE /api/admin/tools/cache/{family}`
  - Limpa cache de uma família específica
  - Retorna quantidade de entradas removidas

- [ ] **T5.2.5** `GET /api/admin/tools/usage`
  - Uso por família nas últimas 24h/7d/30d
  - Breakdown por provider
  - Top 10 queries mais frequentes

- [ ] **T5.2.6** `POST /api/admin/tools/sync-public-apis`
  - Trigger manual do sync com public-apis/public-apis
  - Retorna relatório de novas APIs descobertas

#### Critérios de Aceite:
- [ ] Todos os endpoints requerem autenticação admin
- [ ] Rate limit nos endpoints de admin (30 req/min)
- [ ] Respostas incluem cache_hit_rate calculado

---

### T5.3 — Health Check de Ferramentas

#### Subtarefas:
- [ ] **T5.3.1** Adicionar tools ao endpoint `/health` existente:
  ```python
  # Em backend/main.py ou backend/routers/health.py
  {
      "status": "healthy",
      "database": "ok",
      "tools": {
          "status": "degraded",  # "healthy" | "degraded" | "unhealthy"
          "families_healthy": 8,
          "families_degraded": 1,  # pelo menos 1 provider exausto
          "families_down": 0,      # todos providers exaustos
          "last_check": "2026-10-16T12:00:00Z"
      }
  }
  ```

- [ ] **T5.3.2** Background health check a cada 5 minutos:
  - Testa 1 provider aleatório de cada família
  - Atualiza status na tabela `tool_provider_quota`
  - Se família inteira está down → warning no log

- [ ] **T5.3.3** Alertas no painel admin se tool está degraded/down

#### Critérios de Aceite:
- [ ] Health endpoint inclui status de ferramentas
- [ ] Background check não sobrecarrega APIs (1 req por família a cada 5 min)
- [ ] Admin recebe visual warning para providers exaustos

---

### T5.4 — Auto-Sync com public-apis/public-apis

**Arquivo:** `backend/tools/sync_public_apis.py`

#### Subtarefas:
- [ ] **T5.4.1** Criar tabela `public_apis_registry`:
  ```sql
  CREATE TABLE IF NOT EXISTS public_apis_registry (
      id          TEXT PRIMARY KEY,           -- hash(api_name + url)
      api_name    TEXT NOT NULL,
      description TEXT,
      auth        TEXT,                       -- '' | 'apiKey' | 'OAuth'
      https       INTEGER DEFAULT 1,
      cors        TEXT,                       -- 'yes' | 'no' | 'unknown'
      category    TEXT,
      url         TEXT NOT NULL,
      discovered_at TEXT DEFAULT (datetime('now')),
      relevance   TEXT DEFAULT 'unknown',     -- 'high' | 'medium' | 'low' | 'unknown'
      integrated  INTEGER DEFAULT 0           -- 1 se já integrado como tool_provider
  );
  ```

- [ ] **T5.4.2** Implementar parser do README.md do repositório:
  ```python
  async def parse_public_apis_readme(content: str) -> list[dict]:
      """Parseia tabela markdown do README.md em lista de APIs."""
      # Formato: | API | Description | Auth | HTTPS | CORS | Link |
      # Filtrar por categorias de interesse
      ...
  ```

- [ ] **T5.4.3** Implementar classificador de relevância:
  ```python
  RELEVANCE_KEYWORDS = {
      "high": ["weather", "currency", "exchange", "geocoding", "news", 
               "translate", "wikipedia", "code", "diagram"],
      "medium": ["books", "animals", "facts", "quotes", "jokes",
                 "calendar", "holidays"],
      "low": ["anime", "games", "sports", "music", "food"]
  }
  
  def classify_relevance(api: dict) -> str:
      """Classifica relevância da API para o NexusLocal."""
      ...
  ```

- [ ] **T5.4.4** Background job semanal:
  ```python
  # Em backend/main.py
  @app.on_event("startup")
  async def schedule_public_apis_sync():
      # Roda a cada 7 dias
      asyncio.create_task(periodic_public_apis_sync(interval_hours=168))
  ```

- [ ] **T5.4.5** Relatório de sync no admin:
  ```python
  {
      "last_synced": "2026-10-16T00:00:00Z",
      "total_apis": 1400,
      "high_relevance": 45,
      "medium_relevance": 120,
      "new_since_last_sync": 3,
      "already_integrated": 12
  }
  ```

#### Critérios de Aceite:
- [ ] Sync roda automaticamente 1x por semana
- [ ] Parser extrai corretamente das tabelas markdown
- [ ] APIs com Auth vazia ou "apiKey" são destacadas
- [ ] Admin pode ver APIs descobertas e marcar como integradas
- [ ] Sync não falha se repositório estiver temporariamente indisponível

---

### T5.5 — Métricas e Observabilidade

#### Subtarefas:
- [ ] **T5.5.1** Dashboard de métricas no admin:
  - Total de tool calls (24h, 7d, 30d)
  - Cache hit rate por família
  - Latência média por provider
  - Failover rate (% de chamadas que precisaram de fallback)
  - Top 10 queries mais frequentes
  - Errors por provider

- [ ] **T5.5.2** Logging estruturado:
  ```python
  logger.info(
      "[Tool] %s via %s | cache=%s | latency=%dms | status=%s",
      family, provider_id, cached, latency_ms, status
  )
  ```

- [ ] **T5.5.3** Widget de ferramentas no Dashboard principal:
  - Mini card no dashboard existente mostrando:
    - "🔧 Ferramentas Ativas: 18/20"
    - "📊 Cache Hit: 72%"
    - "⚠️ 2 providers exaustos"

#### Critérios de Aceite:
- [ ] Métricas calculadas a partir de `tool_usage_log`
- [ ] Dashboard atualiza em real-time (polling 30s)
- [ ] Widget no dashboard principal é discreto e informativo

---

### T5.6 — Configuração via Admin Panel

#### Subtarefas:
- [ ] **T5.6.1** Seção "Tool Settings" no admin:
  - Toggle global de ferramentas (enable/disable all)
  - TTL por família (editável)
  - Rate limit por usuário (editável)
  - Auto-detection (enable/disable)
  - API keys para providers que precisam (GNews, Currents, etc.)

- [ ] **T5.6.2** Persistência em `meta` table ou `admin_settings`:
  ```sql
  -- Formato chave-valor em meta
  INSERT INTO meta (key, value) VALUES ('tool_global_enabled', 'true');
  INSERT INTO meta (key, value) VALUES ('tool_weather_ttl', '900');
  INSERT INTO meta (key, value) VALUES ('tool_rate_limit_per_user', '10');
  ```

- [ ] **T5.6.3** Hot-reload de configuração:
  - Mudanças no admin aplicam imediatamente sem restart
  - Invalidação de cache quando TTL muda

#### Critérios de Aceite:
- [ ] Admin pode configurar sem editar .env
- [ ] Hot-reload funciona sem restart do backend
- [ ] Configurações persistem entre deploys

---

## 📁 Arquivos Criados/Modificados

| Arquivo | Ação |
|---|---|
| `frontend/src/components/admin/ToolsPanel.tsx` | Criado |
| `frontend/src/components/admin/ToolCard.tsx` | Criado |
| `frontend/src/components/admin/ToolUsageChart.tsx` | Criado |
| `backend/routers/tools.py` | Modificado — endpoints de admin |
| `backend/tools/sync_public_apis.py` | Criado |
| `backend/main.py` | Modificado — background jobs |
| `backend/database.py` | Modificado — tabela public_apis_registry |
| I18n: `pt-BR.json`, `en-US.json`, `es-ES.json` | Modificados — novas strings |

---

## ⏱️ Estimativa

| Subtarefa | Tempo |
|---|---|
| T5.1 Admin Panel Frontend | 4h |
| T5.2 Admin Endpoints | 3h |
| T5.3 Health Check | 2h |
| T5.4 Auto-Sync | 3h |
| T5.5 Métricas | 2h |
| T5.6 Configuração | 2h |
| Testes e I18n | 2h |
| **Total** | **~18h** |
