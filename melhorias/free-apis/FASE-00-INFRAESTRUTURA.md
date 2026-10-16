# Fase 0 — Infraestrutura Base

> **Pré-requisito para todas as demais fases.**
> Cria as tabelas, classes abstratas, sistema de cache e dispatcher central.

---

## 🎯 Objetivo

Construir o alicerce reutilizável que todas as famílias de ferramentas consumirão: ABC de provider, registro de famílias, failover automático, cache com TTL e dispatcher de chamadas.

---

## 📋 Tarefas

### T0.1 — Tabelas SQLite (`database.py`)

**Arquivo:** `backend/database.py` (dentro de `init_db()`)

#### Subtarefas:
- [ ] **T0.1.1** Criar tabela `tool_families`
  ```sql
  CREATE TABLE IF NOT EXISTS tool_families (
      id           TEXT PRIMARY KEY,      -- 'weather', 'currency', 'brasil', etc.
      display_name TEXT NOT NULL,         -- 'Clima', 'Câmbio', 'Brasil'
      description  TEXT,
      enabled      INTEGER DEFAULT 1,
      created_at   TEXT DEFAULT (datetime('now'))
  );
  ```
- [ ] **T0.1.2** Criar tabela `tool_providers`
  ```sql
  CREATE TABLE IF NOT EXISTS tool_providers (
      id            TEXT PRIMARY KEY,     -- 'open_meteo', 'wttr_in', etc.
      family_id     TEXT NOT NULL REFERENCES tool_families(id) ON DELETE CASCADE,
      display_name  TEXT NOT NULL,        -- 'Open-Meteo'
      base_url      TEXT NOT NULL,
      requires_key  INTEGER DEFAULT 0,
      env_key_name  TEXT,                 -- 'HG_BRASIL_KEY' (nome da var de env)
      fallback_order INTEGER NOT NULL,    -- 1 = primário, 2 = primeiro fallback
      enabled       INTEGER DEFAULT 1,
      created_at    TEXT DEFAULT (datetime('now')),
      UNIQUE(family_id, fallback_order)
  );
  CREATE INDEX IF NOT EXISTS idx_tool_providers_family 
      ON tool_providers(family_id, fallback_order);
  ```
- [ ] **T0.1.3** Criar tabela `tool_provider_quota`
  ```sql
  CREATE TABLE IF NOT EXISTS tool_provider_quota (
      provider_id         TEXT PRIMARY KEY REFERENCES tool_providers(id) ON DELETE CASCADE,
      status              TEXT DEFAULT 'available',  -- 'available' | 'degraded' | 'exhausted'
      consecutive_errors  INTEGER DEFAULT 0,
      exhausted_at        TEXT,
      estimated_reset_at  TEXT,
      last_error_message  TEXT
  );
  ```
- [ ] **T0.1.4** Criar tabela `tool_cache`
  ```sql
  CREATE TABLE IF NOT EXISTS tool_cache (
      cache_key   TEXT PRIMARY KEY,       -- sha256(family + provider + params)
      family      TEXT NOT NULL,
      provider    TEXT NOT NULL,
      response    TEXT NOT NULL,          -- JSON serializado
      created_at  TEXT NOT NULL,
      expires_at  TEXT NOT NULL,
      hit_count   INTEGER DEFAULT 0
  );
  CREATE INDEX IF NOT EXISTS idx_tool_cache_expires ON tool_cache(expires_at);
  CREATE INDEX IF NOT EXISTS idx_tool_cache_family ON tool_cache(family);
  ```
- [ ] **T0.1.5** Criar tabela `tool_usage_log`
  ```sql
  CREATE TABLE IF NOT EXISTS tool_usage_log (
      id              TEXT PRIMARY KEY,
      family          TEXT NOT NULL,
      provider_id     TEXT NOT NULL,
      user_id         TEXT,
      cache_hit       INTEGER DEFAULT 0,
      latency_ms      REAL,
      status          TEXT,               -- 'ok' | 'error' | 'fallback'
      error_message   TEXT,
      created_at      TEXT DEFAULT (datetime('now'))
  );
  CREATE INDEX IF NOT EXISTS idx_tool_usage_family ON tool_usage_log(family, created_at);
  ```
- [ ] **T0.1.6** Seed inicial das famílias e providers (dentro de `init_db()`)

#### Critérios de Aceite:
- [ ] `init_db()` cria todas as tabelas sem erro em banco limpo e existente
- [ ] Migração incremental com `try/except sqlite3.OperationalError`
- [ ] `PRAGMA integrity_check` passa após criação

---

### T0.2 — Classe Base `ToolProvider` (`backend/tools/base.py`)

#### Subtarefas:
- [ ] **T0.2.1** Definir `ToolResult` dataclass
  ```python
  @dataclass
  class ToolResult:
      success: bool
      data: dict | list | str
      provider_id: str
      family: str
      cached: bool = False
      latency_ms: float = 0.0
      error: str | None = None
  ```
- [ ] **T0.2.2** Definir ABC `ToolProvider`
  ```python
  class ToolProvider(ABC):
      provider_id: str
      family: str
      base_url: str
      timeout: float = 8.0
      
      @abstractmethod
      async def execute(self, params: dict) -> ToolResult:
          """Executa a chamada ao provedor externo."""
          ...
      
      @abstractmethod
      def cache_key(self, params: dict) -> str:
          """Gera chave de cache determinística para os params."""
          ...
      
      @property
      def ttl_seconds(self) -> int:
          """TTL do cache para esta família."""
          return DEFAULT_TTL.get(self.family, 900)
  ```
- [ ] **T0.2.3** Implementar helper `_http_get()` e `_http_post()` no base com retry, timeout e tratamento de 429

#### Critérios de Aceite:
- [ ] ABC importável sem erros
- [ ] `ToolResult` serializável para JSON
- [ ] Helpers HTTP usam `httpx.AsyncClient` com timeout configurável

---

### T0.3 — Registry de Famílias (`backend/tools/registry.py`)

#### Subtarefas:
- [ ] **T0.3.1** Implementar `register_provider(provider: ToolProvider)`
- [ ] **T0.3.2** Implementar `get_providers(family: str) -> list[ToolProvider]` (ordenado por `fallback_order`)
- [ ] **T0.3.3** Implementar `get_all_families() -> list[str]`
- [ ] **T0.3.4** Auto-registrar provedores no startup (`main.py`)

#### Critérios de Aceite:
- [ ] Registry carrega providers na ordem correta
- [ ] Providers desabilitados (no DB) não são registrados
- [ ] Thread-safe (singleton com lock)

---

### T0.4 — Failover (`backend/tools/failover.py`)

#### Subtarefas:
- [ ] **T0.4.1** Implementar `resolve_tool(family: str, params: dict, db) -> ToolResult`
  - Itera providers da família em ordem de fallback
  - Se provider está `exhausted` no `tool_provider_quota`, pula
  - Se chamada falha (429/timeout/erro), marca `exhausted` e tenta o próximo
  - Se sucesso, marca `available` e retorna
- [ ] **T0.4.2** Implementar `release_expired_tool_quotas(db)` (cron job)
- [ ] **T0.4.3** Integrar com `tool_usage_log` para rastreamento

#### Critérios de Aceite:
- [ ] Failover transparente: mesmo input, resultado do primeiro provider disponível
- [ ] Exaustão com cooldown respeita `estimated_reset_at`
- [ ] Log de uso registra provider utilizado e se houve fallback

---

### T0.5 — Cache (`backend/tools/cache.py`)

#### Subtarefas:
- [ ] **T0.5.1** Implementar `get_cached(cache_key: str, db) -> ToolResult | None`
- [ ] **T0.5.2** Implementar `set_cached(cache_key: str, result: ToolResult, ttl: int, db)`
- [ ] **T0.5.3** Implementar `evict_expired(db) -> int` (limpeza periódica)
- [ ] **T0.5.4** Implementar `invalidate_family(family: str, db)` (flush manual)

#### Critérios de Aceite:
- [ ] Cache hit retorna resultado sem chamada HTTP
- [ ] TTL expirado = cache miss
- [ ] `hit_count` incrementa corretamente
- [ ] Eviction job remove entradas expiradas

---

### T0.6 — Dispatcher (`backend/tools/dispatcher.py`)

#### Subtarefas:
- [ ] **T0.6.1** Implementar `dispatch_tool(family: str, params: dict, user_id: str, db) -> ToolResult`
  - Verifica cache primeiro
  - Se miss, chama `resolve_tool()` (que faz failover)
  - Grava no cache e no usage_log
  - Retorna `ToolResult` encapsulado com `security.wrap_tool_result()`
- [ ] **T0.6.2** Implementar rate limiting por usuário (evita abuso)

#### Critérios de Aceite:
- [ ] Pipeline completo: cache → failover → sanitize → result
- [ ] Rate limit por usuário (10 tool calls/min padrão)
- [ ] Log completo com latência e cache_hit

---

### T0.7 — Segurança (`backend/tools/security.py`)

#### Subtarefas:
- [ ] **T0.7.1** Implementar `wrap_tool_result(tool_name, raw_data) -> str`
- [ ] **T0.7.2** Implementar `sanitize_data(data) -> dict`
  - Strip HTML/script tags
  - Trunca campos longos
  - Remove campos suspeitos ("system_prompt", "instructions", "ignore_above")
  - Escapa caracteres de controle Unicode
- [ ] **T0.7.3** Implementar `is_safe_url(url: str) -> bool` (reutiliza `is_safe_public_url` do proactive)

#### Critérios de Aceite:
- [ ] XSS/injection patterns são removidos
- [ ] Dados truncados ficam legíveis
- [ ] URLs privadas (localhost, 10.x, 192.168.x) são rejeitadas

---

## 📁 Arquivos Criados/Modificados

| Arquivo | Ação |
|---|---|
| `backend/database.py` | Modificado — novas tabelas em `init_db()` |
| `backend/tools/__init__.py` | Criado |
| `backend/tools/base.py` | Criado |
| `backend/tools/registry.py` | Criado |
| `backend/tools/failover.py` | Criado |
| `backend/tools/cache.py` | Criado |
| `backend/tools/dispatcher.py` | Criado |
| `backend/tools/security.py` | Criado |
| `backend/main.py` | Modificado — registrar providers no startup |

---

## ⏱️ Estimativa

| Subtarefa | Tempo |
|---|---|
| T0.1 Tabelas | 1h |
| T0.2 Base class | 1h |
| T0.3 Registry | 30min |
| T0.4 Failover | 1.5h |
| T0.5 Cache | 1h |
| T0.6 Dispatcher | 1h |
| T0.7 Segurança | 1h |
| **Total** | **~7h** |
