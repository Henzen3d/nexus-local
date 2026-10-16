# 🏗️ Arquitetura — Free APIs Integration

> Diagrama detalhado da arquitetura do sistema de ferramentas com APIs públicas gratuitas.

---

## Visão Geral do Sistema

```
┌─────────────────────────────────────────────────────────────────────────┐
│                           FRONTEND                                      │
│                                                                         │
│  ┌──────────────┐  ┌──────────────────┐  ┌───────────────────────────┐  │
│  │   ChatPanel   │  │  ArtifactPanel   │  │     Admin ToolsPanel      │  │
│  │              │  │                  │  │                           │  │
│  │ Tool badge   │  │ ▶ Run (Piston)   │  │ Family cards + status    │  │
│  │ "🔧 Clima"   │  │ 📊 Diagram (Kroki)│ │ Enable/Disable toggles  │  │
│  │              │  │ 📋 JSX sandbox   │  │ Cache management         │  │
│  └──────┬───────┘  └────────┬─────────┘  └───────────┬───────────────┘  │
│         │                   │                         │                  │
└─────────┼───────────────────┼─────────────────────────┼──────────────────┘
          │                   │                         │
          ▼                   ▼                         ▼
┌─────────────────────────────────────────────────────────────────────────┐
│                          BACKEND (FastAPI)                               │
│                                                                         │
│  ┌────────────────────────────────────────────────────────────────────┐  │
│  │                     API Layer (routers/)                           │  │
│  │  POST /api/chat ──► intent detect ──► tool dispatch ──► LLM       │  │
│  │  POST /api/tools/execute ─────────────────► code_exec family      │  │
│  │  POST /api/tools/diagram ─────────────────► diagrams family       │  │
│  │  GET  /api/admin/tools/status ────────────► status aggregation    │  │
│  └────────────────────────┬───────────────────────────────────────────┘  │
│                           │                                              │
│  ┌────────────────────────▼───────────────────────────────────────────┐  │
│  │                   Tool Dispatcher (tools/dispatcher.py)            │  │
│  │                                                                    │  │
│  │  1. Cache check (tool_cache)                                       │  │
│  │  2. Resolve provider (failover cascade)                            │  │
│  │  3. Execute HTTP call                                              │  │
│  │  4. Sanitize result (security.py)                                  │  │
│  │  5. Cache store                                                    │  │
│  │  6. Log to tool_usage_log                                          │  │
│  │  7. Return ToolResult                                              │  │
│  └──┬─────────┬─────────┬─────────┬─────────┬─────────┬──────────────┘  │
│     │         │         │         │         │         │                  │
│  ┌──▼──┐  ┌──▼──┐  ┌──▼──┐  ┌──▼──┐  ┌──▼──┐  ┌──▼──┐               │
│  │Cache│  │Fail │  │Regis│  │Secur│  │Inten│  │Conte│               │
│  │.py  │  │over │  │try  │  │ity  │  │t    │  │xt   │               │
│  │     │  │.py  │  │.py  │  │.py  │  │.py  │  │Inj. │               │
│  └─────┘  └─────┘  └─────┘  └─────┘  └─────┘  └─────┘               │
│                                                                         │
│  ┌────────────────────────────────────────────────────────────────────┐  │
│  │                   Tool Families (tools/families/)                  │  │
│  │                                                                    │  │
│  │  ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────┐             │  │
│  │  │ Weather  │ │ Currency │ │ Brasil   │ │Knowledge │             │  │
│  │  │          │ │          │ │          │ │          │             │  │
│  │  │OpenMeteo │ │AwesomeAPI│ │BrasilAPI │ │Wikipedia │             │  │
│  │  │ wttr.in  │ │Frankfurtr│ │ViaCEP    │ │OpenLibry │             │  │
│  │  │HG Brasil │ │          │ │          │ │          │             │  │
│  │  └──────────┘ └──────────┘ └──────────┘ └──────────┘             │  │
│  │                                                                    │  │
│  │  ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────┐             │  │
│  │  │  News    │ │Translat° │ │   Geo    │ │   Fun    │             │  │
│  │  │          │ │          │ │          │ │          │             │  │
│  │  │ GNews    │ │LibreTrns │ │Nominatim │ │Facts/Dog │             │  │
│  │  │ Currents │ │MyMemory  │ │OM Geocode│ │Cat/Advice│             │  │
│  │  │ DDG News │ │          │ │          │ │          │             │  │
│  │  └──────────┘ └──────────┘ └──────────┘ └──────────┘             │  │
│  │                                                                    │  │
│  │  ┌──────────┐ ┌──────────┐                                        │  │
│  │  │Code Exec │ │ Diagrams │  ← Fase 3: Artifacts Avançados        │  │
│  │  │          │ │          │                                        │  │
│  │  │ Piston   │ │ Kroki    │                                        │  │
│  │  │ Judge0   │ │QuickChart│                                        │  │
│  │  └──────────┘ └──────────┘                                        │  │
│  └────────────────────────────────────────────────────────────────────┘  │
│                                                                         │
│  ┌────────────────────────────────────────────────────────────────────┐  │
│  │                     SQLite (nexuslocal.db)                         │  │
│  │                                                                    │  │
│  │  ┌─────────────────┐  ┌───────────────────┐  ┌─────────────────┐  │  │
│  │  │  tool_families   │  │  tool_providers    │  │tool_provider    │  │  │
│  │  │                 │  │                   │  │  _quota          │  │  │
│  │  │ id              │  │ id                │  │                 │  │  │
│  │  │ display_name    │◄─│ family_id (FK)    │  │ provider_id(FK) │  │  │
│  │  │ enabled         │  │ fallback_order    │  │ status          │  │  │
│  │  └─────────────────┘  │ base_url          │  │ consecutive_err │  │  │
│  │                       │ requires_key      │  │ exhausted_at    │  │  │
│  │                       │ enabled           │  │ est_reset_at    │  │  │
│  │                       └───────────────────┘  └─────────────────┘  │  │
│  │                                                                    │  │
│  │  ┌─────────────────┐  ┌───────────────────┐  ┌─────────────────┐  │  │
│  │  │   tool_cache     │  │  tool_usage_log   │  │public_apis      │  │  │
│  │  │                 │  │                   │  │  _registry       │  │  │
│  │  │ cache_key (PK)  │  │ id               │  │                 │  │  │
│  │  │ family          │  │ family           │  │ api_name        │  │  │
│  │  │ provider        │  │ provider_id      │  │ category        │  │  │
│  │  │ response (JSON) │  │ user_id          │  │ auth            │  │  │
│  │  │ expires_at      │  │ cache_hit        │  │ relevance       │  │  │
│  │  │ hit_count       │  │ latency_ms       │  │ integrated      │  │  │
│  │  └─────────────────┘  │ status           │  └─────────────────┘  │  │
│  │                       └───────────────────┘                       │  │
│  └────────────────────────────────────────────────────────────────────┘  │
│                                                                         │
│  ┌────────────────────────────────────────────────────────────────────┐  │
│  │                    Background Jobs (main.py)                       │  │
│  │                                                                    │  │
│  │  ⏰ release_expired_tool_quotas()     → cada 5 min                │  │
│  │  ⏰ evict_expired_cache()             → cada 15 min               │  │
│  │  ⏰ health_check_tools()             → cada 5 min                │  │
│  │  ⏰ sync_public_apis_registry()      → cada 7 dias               │  │
│  └────────────────────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────────────────┘
```

---

## Fluxo de uma Chamada de Ferramenta

```
User Message
    │
    ▼
┌─────────────────────┐
│  Intent Detection    │  < 2ms (regex)
│  "clima em SP"       │
│  → weather, city=SP  │
└─────────┬───────────┘
          │
          ▼
┌─────────────────────┐     ┌──────────────┐
│  Cache Lookup        │────►│ Cache HIT?   │
│  sha256(weather:     │     │              │
│  open_meteo:SP:3)    │     │  Yes → Return│
└─────────┬───────────┘     └──────────────┘
          │ No
          ▼
┌─────────────────────┐
│  Provider Resolution │
│                     │
│  1. Open-Meteo      │─── available? ──► Execute
│     └── 429/timeout │                      │
│                     │                      ▼
│  2. wttr.in         │─── available? ──► Execute
│     └── 429/timeout │                      │
│                     │                      ▼
│  3. HG Brasil       │─── available? ──► Execute
│     └── all failed  │
│                     │
│  → NoToolAvailable  │
└─────────┬───────────┘
          │
          ▼
┌─────────────────────┐
│  Sanitize Result     │
│  - Strip HTML        │
│  - Remove suspects   │
│  - Truncate 4096     │
│  - Wrap in tags      │
└─────────┬───────────┘
          │
          ▼
┌─────────────────────┐
│  Store Cache         │
│  TTL = 15 min        │
└─────────┬───────────┘
          │
          ▼
┌─────────────────────┐
│  Log Usage           │
│  family, provider,   │
│  latency, status     │
└─────────┬───────────┘
          │
          ▼
┌─────────────────────┐
│  Inject in Context   │
│  <tool_result>       │
│    {...data...}      │
│  </tool_result>      │
└─────────┬───────────┘
          │
          ▼
      LLM Response
     (with real data)
```

---

## Relação com Arquitetura Existente

```
                    EXISTENTE                          NOVO
              ┌─────────────────────┐          ┌─────────────────────┐
              │  model_families     │          │  tool_families      │
              │  model_family_      │  espelha │  tool_providers     │
              │    members          │ ───────► │  (com fallback_     │
              │  model_quota_status │          │    order)           │
              │                     │          │  tool_provider_     │
              │  ranking/quota.py   │          │    quota            │
              │  ranking/failover.py│          │  tools/failover.py  │
              └─────────────────────┘          └─────────────────────┘

              ┌─────────────────────┐          ┌─────────────────────┐
              │  free_registry/     │  espelha │  sync_public_       │
              │    sync.py          │ ───────► │    apis.py          │
              │    fetcher.py       │          │  public_apis_       │
              │    matcher.py       │          │    registry         │
              └─────────────────────┘          └─────────────────────┘

              ┌─────────────────────┐          ┌─────────────────────┐
              │  web_search/        │  espelha │  tools/families/    │
              │    providers.py     │ ───────► │    weather/         │
              │  BraveSearchProvider│          │    currency/        │
              │  DuckDuckGoProvider │          │    brasil/          │
              └─────────────────────┘          └─────────────────────┘
```

---

## Tabelas de Dados — ER Simplificado

```
tool_families          tool_providers         tool_provider_quota
┌──────────────┐      ┌──────────────────┐   ┌──────────────────┐
│ id (PK)      │◄─┐   │ id (PK)          │──►│ provider_id (PK) │
│ display_name │  └───│ family_id (FK)   │   │ status           │
│ enabled      │      │ display_name     │   │ consecutive_err  │
│ description  │      │ base_url         │   │ exhausted_at     │
└──────────────┘      │ fallback_order   │   │ est_reset_at     │
                      │ requires_key     │   │ last_error_msg   │
                      │ env_key_name     │   └──────────────────┘
                      │ enabled          │
                      └──────────────────┘

tool_cache                    tool_usage_log
┌──────────────────────┐     ┌──────────────────────┐
│ cache_key (PK)       │     │ id (PK)              │
│ family               │     │ family               │
│ provider             │     │ provider_id          │
│ response (JSON)      │     │ user_id              │
│ created_at           │     │ cache_hit            │
│ expires_at           │     │ latency_ms           │
│ hit_count            │     │ status               │
└──────────────────────┘     │ error_message        │
                             │ created_at           │
                             └──────────────────────┘

public_apis_registry
┌──────────────────────┐
│ id (PK)              │
│ api_name             │
│ description          │
│ auth                 │
│ category             │
│ url                  │
│ relevance            │
│ integrated           │
│ discovered_at        │
└──────────────────────┘
```
