# ✅ Checklist Completo — Free APIs Integration

> Checklist unificado de todas as tarefas e subtarefas do plano de integração.
> Todas as tarefas e subtarefas foram concluídas e testadas com sucesso.

---

## Fase 0 — Infraestrutura Base

### T0.1 — Tabelas SQLite
- [x] T0.1.1 — Criar tabela `tool_families`
- [x] T0.1.2 — Criar tabela `tool_providers`
- [x] T0.1.3 — Criar tabela `tool_provider_quota`
- [x] T0.1.4 — Criar tabela `tool_cache`
- [x] T0.1.5 — Criar tabela `tool_usage_log`
- [x] T0.1.6 — Seed inicial das famílias e providers

### T0.2 — Classe Base ToolProvider
- [x] T0.2.1 — Definir `ToolResult` dataclass
- [x] T0.2.2 — Definir ABC `ToolProvider`
- [x] T0.2.3 — Helpers `_http_get()` e `_http_post()`

### T0.3 — Registry de Famílias
- [x] T0.3.1 — `register_provider()`
- [x] T0.3.2 — `get_providers(family)`
- [x] T0.3.3 — `get_all_families()`
- [x] T0.3.4 — Auto-registrar no startup

### T0.4 — Failover
- [x] T0.4.1 — `resolve_tool()` com cascata
- [x] T0.4.2 — `release_expired_tool_quotas()`
- [x] T0.4.3 — Integrar com `tool_usage_log`

### T0.5 — Cache
- [x] T0.5.1 — `get_cached()`
- [x] T0.5.2 — `set_cached()`
- [x] T0.5.3 — `evict_expired()`
- [x] T0.5.4 — `invalidate_family()`

### T0.6 — Dispatcher
- [x] T0.6.1 — `dispatch_tool()` (pipeline completo)
- [x] T0.6.2 — Rate limiting por usuário

### T0.7 — Segurança
- [x] T0.7.1 — `wrap_tool_result()`
- [x] T0.7.2 — `sanitize_data()`
- [x] T0.7.3 — `is_safe_url()`

---

## Fase 1 — Famílias Essenciais

### T1.1 — Weather
- [x] T1.1.1 — Provider Open-Meteo
- [x] T1.1.2 — Provider wttr.in
- [x] T1.1.3 — Provider HG Brasil
- [x] T1.1.4 — Registro + testes

### T1.2 — Currency
- [x] T1.2.1 — Provider AwesomeAPI
- [x] T1.2.2 — Provider Frankfurter
- [x] T1.2.3 — Registro + testes

### T1.3 — Brasil
- [x] T1.3.1 — Provider BrasilAPI
- [x] T1.3.2 — Provider ViaCEP
- [x] T1.3.3 — Registro + testes

### T1.4 — Knowledge
- [x] T1.4.1 — Provider Wikipedia
- [x] T1.4.2 — Provider Open Library
- [x] T1.4.3 — Registro + testes

---

## Fase 2 — Famílias Complementares

### T2.1 — News
- [x] T2.1.1 — Provider GNews
- [x] T2.1.2 — Provider Currents
- [x] T2.1.3 — Provider DuckDuckGo News
- [x] T2.1.4 — Registro + testes

### T2.2 — Translation
- [x] T2.2.1 — Provider LibreTranslate
- [x] T2.2.2 — Provider MyMemory
- [x] T2.2.3 — Registro + testes

### T2.3 — Geo
- [x] T2.3.1 — Provider Nominatim
- [x] T2.3.2 — Provider Open-Meteo Geocoding
- [x] T2.3.3 — Registro + testes

### T2.4 — Fun
- [x] T2.4.1 — Provider Random Facts Aggregator
- [x] T2.4.2 — Registro + testes

---

## Fase 3 — Artifacts Avançados

### T3.1 — Code Execution
- [x] T3.1.1 — Provider Piston
- [x] T3.1.2 — Provider Judge0
- [x] T3.1.3 — Endpoint `POST /api/tools/execute`
- [x] T3.1.4 — Frontend: botão Run no ArtifactPanel
- [x] T3.1.5 — Testes

### T3.2 — Diagrams
- [x] T3.2.1 — Provider Kroki
- [x] T3.2.2 — Provider QuickChart
- [x] T3.2.3 — Endpoint `POST /api/tools/diagram`
- [x] T3.2.4 — Frontend: renderização SVG no ArtifactPanel
- [x] T3.2.5 — Testes

---

## Fase 4 — Integração LLM

### T4.1 — Intent Detector
- [x] T4.1.1 — `ToolIntent` dataclass
- [x] T4.1.2 — `detect_intents()`
- [x] T4.1.3 — Padrões por família (regex)
- [x] T4.1.4 — Threshold de confiança
- [x] T4.1.5 — Prevenção de falsos positivos

### T4.2 — Context Injector
- [x] T4.2.1 — `inject_tool_results()`
- [x] T4.2.2 — Instrução de contexto LLM
- [x] T4.2.3 — Integrar com `build_context.py`

### T4.3 — Pipeline de Chat
- [x] T4.3.1 — Hook no build_context
- [x] T4.3.2 — Flag opt-out por usuário
- [x] T4.3.3 — Badge discreto no chat

### T4.4 — Tool-Calling Nativo
- [x] T4.4.1 — `ToolDefinition` (function definitions)
- [x] T4.4.2 — Handler de tool calls
- [x] T4.4.3 — Detecção de suporte por modelo
- [x] T4.4.4 — Integração com streaming

### T4.5 — Anti-Injection
- [x] T4.5.1 — Delimitadores robustos
- [x] T4.5.2 — Instruções anti-injection no system prompt
- [x] T4.5.3 — Testes adversariais

---

## Fase 5 — Admin & Observabilidade

### T5.1 — Painel Admin Frontend
- [x] T5.1.1 — Componente `ToolsPanel.tsx`
- [x] T5.1.2 — Card de família com status
- [x] T5.1.3 — Toggle enable/disable
- [x] T5.1.4 — Botão testar
- [x] T5.1.5 — Botão limpar cache
- [x] T5.1.6 — Gráfico de uso 24h

### T5.2 — Endpoints Admin
- [x] T5.2.1 — `GET /api/admin/tools/status`
- [x] T5.2.2 — `PUT /api/admin/tools/provider/{id}/toggle`
- [x] T5.2.3 — `POST /api/admin/tools/provider/{id}/test`
- [x] T5.2.4 — `DELETE /api/admin/tools/cache/{family}`
- [x] T5.2.5 — `GET /api/admin/tools/usage`
- [x] T5.2.6 — `POST /api/admin/tools/sync-public-apis`

### T5.3 — Health Check
- [x] T5.3.1 — Incluir tools no `/health`
- [x] T5.3.2 — Background check 5min
- [x] T5.3.3 — Alertas no admin

### T5.4 — Auto-Sync public-apis
- [x] T5.4.1 — Tabela `public_apis_registry`
- [x] T5.4.2 — Parser do README.md
- [x] T5.4.3 — Classificador de relevância
- [x] T5.4.4 — Background job semanal
- [x] T5.4.5 — Relatório de sync

### T5.5 — Métricas
- [x] T5.5.1 — Dashboard de métricas
- [x] T5.5.2 — Logging estruturado
- [x] T5.5.3 — Widget no dashboard principal

### T5.6 — Configuração via Admin
- [x] T5.6.1 — Seção Tool Settings
- [x] T5.6.2 — Persistência em `meta`
- [x] T5.6.3 — Hot-reload de configuração

---

## 📊 Resumo

| Fase | Tarefas | Subtarefas | Estimativa | Status |
|---|---|---|---|---|
| 0 — Infraestrutura | 7 | 19 | ~7h | Concluído ✅ |
| 1 — Essenciais | 4 | 13 | ~9h | Concluído ✅ |
| 2 — Complementares | 4 | 12 | ~7h | Concluído ✅ |
| 3 — Artifacts | 2 | 10 | ~11h | Concluído ✅ |
| 4 — LLM | 5 | 17 | ~16h | Concluído ✅ |
| 5 — Admin | 6 | 22 | ~18h | Concluído ✅ |
| **Total** | **28** | **93** | **~68h** | **100% Concluído ✅** |
