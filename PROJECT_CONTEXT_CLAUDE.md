# 🧠 NexusLocal — Arquitetura Central, Orquestração e Contexto Técnico

Este documento consolida a arquitetura central, fluxo de execução, adaptadores de IA, esquema de banco de dados e contratos de tipos do **NexusLocal**. Ele foi estruturado para servir de contexto técnico completo para IAs, desenvolvedores e projetos no Claude.

---

## 1. Visão Geral da Arquitetura

O **NexusLocal** é uma plataforma de chat e assistência IA de alta performance construída sobre a filosofia **local-first**:
* **Backend:** Python 3.11+, FastAPI, WebSockets bidirecionais assíncronos, SQLite WAL (`aiosqlite`) e FastEmbed para embeddings locais leves.
* **Frontend:** React 18, TypeScript, Vite, Vanilla CSS com design system de alto padrão (editorial cream + coral brand, temas Light/Dark), PWA offline-ready.
* **Paradigma de Execução:** Local-first e privacidade total. Toda a inteligência de orquestração, cache semântico, memória adaptativa e RAG ocorre na máquina local, comunicando-se via HTTP/SSE com provedores de IA gratuitos e remotos (Groq, Gemini, OpenRouter, Cloudflare, Ollama, etc.).

---

## 2. Orquestração de APIs, Streaming e Tratamento de Erro 429

O fluxo de mensagens é orquestrado em tempo real através de WebSockets e uma esteira modular de resolução.

### A. Ponto de Entrada (WebSocket)
* **Arquivo:** [`backend/routers/chat.py`](file:///j:/Arquivos%20Osmar/Multi+/backend/routers/chat.py)
* **Endpoint:** `@router.websocket("/ws/chat")`
* **Responsabilidades:**
  1. Autenticação JWT via query param (`token`).
  2. Gerenciamento de keep-alive (`ping`/`pong` a cada 25s).
  3. Despacho assíncrono para montagem de contexto (`backend/orchestration/build_context.py`), resolução de busca web e anexos.
  4. Execução do gerador de resposta através de `resolve_and_stream()`.
  5. Pós-processamento: detecção automática de artefatos (`artifacts.py`), salvamento no banco e disparo em segundo plano do extrator de memória adaptativa.

### B. Resolução de Requisições e Cascata de Failover
* **Arquivo:** [`backend/orchestration/resolve_request.py`](file:///j:/Arquivos%20Osmar/Multi+/backend/orchestration/resolve_request.py)
* **Função Central:** `stream_from_llm()` / `resolve_and_stream()`
* **Fluxo de Failover e Tratamento de Rate Limit (HTTP 429):**
  1. **Tentativas de Failover:** O sistema executa um loop de até `_MAX_FAILOVER_ATTEMPTS = 3`.
  2. **Resolução de Modelo:** Chama `resolve_model_with_failover(model_id, db)` (`backend/ranking/resolver.py`). Se o modelo primário estiver esgotado, busca o melhor substituto ativo da mesma família.
  3. **Notificação ao Frontend:** Se houver failover, o WebSocket emite `{ "type": "failover_notice", "original_model": ..., "fallback_model": ..., "reason": "rate_limit" }`.
  4. **Captura do Erro 429:**
     ```python
     except RateLimitError as e:
         await mark_model_exhausted(current_model_id, db, e.retry_after, str(e))
         if attempt == _MAX_FAILOVER_ATTEMPTS:
             await ws.send_json({"type": "error", "message": "Limite de tentativas de failover excedido."})
         else:
             continue  # Salta imediatamente para o próximo modelo disponível na família
     ```
  5. **Vision Relay Fallback:** Se um modelo recusar imagens anexadas com erro de visão, o interceptor detecta a recusa e aciona dinamicamente o *Vision Relay* (descreve a imagem usando um modelo com suporte a visão e substitui no histórico sem travar o chat).

### C. Sistema de Ranking, Famílias e Quotas
* **Arquivos:**
  * [`backend/ranking/resolver.py`](file:///j:/Arquivos%20Osmar/Multi+/backend/ranking/resolver.py): Algoritmo de resolução inteligente por prioridade de família (`model_family_members`).
  * [`backend/ranking/exhaustion.py`](file:///j:/Arquivos%20Osmar/Multi+/backend/ranking/exhaustion.py): Gestão de cooldown e expiração de modelos esgotados (`mark_model_exhausted`, `is_model_exhausted`).
  * [`backend/ranking/quota_tracker.py`](file:///j:/Arquivos%20Osmar/Multi+/backend/ranking/quota_tracker.py): Rastreio de volume de requisições por modelo.

---

## 3. Clientes e Adaptadores de Provedores de IA

A camada de conectividade normaliza a comunicação de streaming e autenticação de dezenas de provedores sob uma interface assíncrona única.

* **Arquivos:**
  * [`backend/providers/base.py`](file:///j:/Arquivos%20Osmar/Multi+/backend/providers/base.py)
  * [`backend/providers/registry.py`](file:///j:/Arquivos%20Osmar/Multi+/backend/providers/registry.py)

### Hierarquia de Classes

```
BaseProvider (ABC)
 ├── OpenAICompatProvider  --> Groq, OpenRouter, Cerebras, SambaNova, SiliconFlow, NVIDIA NIM, DeepSeek, Ollama (/v1)
 ├── GeminiProvider        --> Google Gemini API nativa (com Context Caching)
 └── CloudflareProvider    --> Cloudflare Workers AI nativo (/accounts/{id}/ai/run/{model})
```

### Contrato Base (`BaseProvider`)
```python
class BaseProvider(ABC):
    def __init__(self, api_key: str, base_url: str):
        self.api_key = api_key
        self.base_url = base_url.rstrip("/")

    @abstractmethod
    async def stream_chat(
        self,
        model: str,
        messages: List[Dict[str, str]],
        temperature: float = 0.7,
        max_tokens: int = 4096,
    ) -> AsyncIterator[str]:
        ...
```

### Destaques dos Adaptadores

1. **`RateLimitError`:**
   ```python
   class RateLimitError(Exception):
       def __init__(self, retry_after: int | None = None, provider: str | None = None):
           self.retry_after = retry_after
           self.provider = provider
   ```
2. **`OpenAICompatProvider`:**
   * Utiliza cliente `httpx.AsyncClient(timeout=120.0)` com streaming SSE.
   * Converte status `429` capturando o header `Retry-After`.
   * **Parser de Pensamento / Raciocínio Profundo:** Extrai campos como `reasoning_content` (DeepSeek/OpenAI) e estruturas aninhadas da Mistral, formatando automaticamente blocos `<think>...</think>` para renderização elegante no frontend.
3. **`GeminiProvider`:**
   * Conexão direta com `https://generativelanguage.googleapis.com/v1beta`.
   * **Context Caching Automático:** Para conversas longas ou projetos, gera cache em `/cachedContents` com TTL de 10 minutos (reduzindo latência e economizando cotas de tokens).
4. **`registry.py -> get_provider(provider_id, db, user_id)`:**
   * Fábrica central de instâncias.
   * Busca chaves globais ou isoladas por usuário (`user_api_keys`).
   * Garante isolamento estrito em contas familiares.

---

## 4. Esquema de Banco de Dados Local (SQLite DDL)

* **Arquivo:** [`backend/database.py`](file:///j:/Arquivos%20Osmar/Multi+/backend/database.py)
* **Modo:** SQLite em modo `WAL` (`PRAGMA journal_mode=WAL; PRAGMA foreign_keys=ON;`).

### Principais Tabelas e Relacionamentos

```sql
-- 1. Conversas e Mensagens
CREATE TABLE IF NOT EXISTS conversations (
    id           TEXT PRIMARY KEY,
    user_id      TEXT REFERENCES users(id) ON DELETE CASCADE,
    title        TEXT DEFAULT 'Nova conversa',
    model_id     TEXT,
    provider_id  TEXT,
    is_favorite  INTEGER DEFAULT 0,
    favorited_at TEXT DEFAULT NULL,
    project_id   TEXT REFERENCES projects(id) ON DELETE SET NULL,
    created_at   TEXT DEFAULT (datetime('now')),
    updated_at   TEXT DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS messages (
    id              TEXT PRIMARY KEY,
    conversation_id TEXT NOT NULL REFERENCES conversations(id) ON DELETE CASCADE,
    role            TEXT NOT NULL CHECK(role IN ('user','assistant','system')),
    content         TEXT NOT NULL,
    model_id        TEXT,
    provider        TEXT,
    created_at      TEXT DEFAULT (datetime('now'))
);

-- 2. Provedores e Modelos
CREATE TABLE IF NOT EXISTS providers (
    id              TEXT PRIMARY KEY,
    name            TEXT NOT NULL,
    base_url        TEXT NOT NULL,
    api_key         TEXT DEFAULT '',
    enabled         INTEGER DEFAULT 1,
    is_free         INTEGER DEFAULT 0,
    share_admin_key INTEGER DEFAULT 0,
    created_at      TEXT DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS models (
    id             TEXT PRIMARY KEY,
    provider_id    TEXT NOT NULL REFERENCES providers(id) ON DELETE CASCADE,
    name           TEXT NOT NULL,
    display_name   TEXT NOT NULL,
    context_length INTEGER DEFAULT 8192,
    context_source TEXT DEFAULT 'default',
    confirmed_free INTEGER DEFAULT 0,
    supports_vision INTEGER DEFAULT 0,
    enabled        INTEGER DEFAULT 1
);

-- 3. Famílias de Modelos e Failover
CREATE TABLE IF NOT EXISTS model_families (
    id             TEXT PRIMARY KEY,
    name           TEXT NOT NULL,
    description    TEXT DEFAULT '',
    is_active      INTEGER DEFAULT 1,
    created_at     TEXT DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS model_family_members (
    id             TEXT PRIMARY KEY,
    family_id      TEXT NOT NULL REFERENCES model_families(id) ON DELETE CASCADE,
    model_id       TEXT NOT NULL REFERENCES models(id) ON DELETE CASCADE,
    fallback_order INTEGER NOT NULL,
    UNIQUE(family_id, model_id)
);

CREATE TABLE IF NOT EXISTS model_quota_status (
    model_id            TEXT PRIMARY KEY REFERENCES models(id) ON DELETE CASCADE,
    status              TEXT DEFAULT 'available',  -- 'available' | 'degraded' | 'exhausted'
    consecutive_errors  INTEGER DEFAULT 0,
    exhausted_at        TEXT,
    estimated_reset_at  TEXT,
    last_error_message  TEXT
);

-- 4. Memória Adaptativa e Consolidação (Dream Memory)
CREATE TABLE IF NOT EXISTS user_memory (
    id               TEXT PRIMARY KEY,
    user_id          TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    category         TEXT NOT NULL,
    fact             TEXT NOT NULL,
    fact_key         TEXT,
    is_active        INTEGER DEFAULT 1,
    is_pinned        INTEGER DEFAULT 0,
    status           TEXT DEFAULT 'active' CHECK(status IN ('active', 'merged', 'superseded', 'archived')),
    superseded_by_id TEXT REFERENCES user_memory(id) ON DELETE SET NULL,
    source_dream_id  TEXT REFERENCES dream_logs(id) ON DELETE SET NULL,
    consolidated_at  TEXT DEFAULT NULL,
    version          INTEGER DEFAULT 1,
    confidence       REAL DEFAULT 1.0,
    embedding        BLOB,
    created_at       TEXT DEFAULT (datetime('now')),
    updated_at       TEXT DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS memory_snapshots (
    id             TEXT PRIMARY KEY,
    user_id        TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    trigger_type   TEXT NOT NULL,
    facts_count    INTEGER NOT NULL,
    snapshot_json  TEXT NOT NULL,
    snapshot_hash  TEXT NOT NULL,
    is_compressed  INTEGER DEFAULT 0,
    created_at     TEXT DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS dream_logs (
    id                 TEXT PRIMARY KEY,
    user_id            TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    snapshot_id        TEXT REFERENCES memory_snapshots(id) ON DELETE SET NULL,
    provider_id        TEXT NOT NULL,
    model_id           TEXT NOT NULL,
    facts_before       INTEGER NOT NULL,
    facts_after        INTEGER NOT NULL,
    facts_merged       INTEGER DEFAULT 0,
    facts_superseded   INTEGER DEFAULT 0,
    facts_created      INTEGER DEFAULT 0,
    duration_ms        INTEGER DEFAULT 0,
    status             TEXT NOT NULL,
    summary_notes      TEXT,
    error_message      TEXT,
    created_at         TEXT DEFAULT (datetime('now'))
);

-- 5. Cache Semântico e Exato
CREATE TABLE IF NOT EXISTS cache_exact (
    id          TEXT PRIMARY KEY,
    hash        TEXT NOT NULL,
    model_id    TEXT NOT NULL,
    response    TEXT NOT NULL,
    token_est   INTEGER DEFAULT 0,
    hits        INTEGER DEFAULT 0,
    created_at  TEXT DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS cache_semantic (
    id          TEXT PRIMARY KEY,
    prompt_text TEXT NOT NULL,
    embedding   BLOB NOT NULL,
    response    TEXT NOT NULL,
    model_id    TEXT NOT NULL,
    token_est   INTEGER DEFAULT 0,
    hits        INTEGER DEFAULT 0,
    similarity  REAL DEFAULT 0.0,
    created_at  TEXT DEFAULT (datetime('now'))
);
```

---

## 5. Contratos e Interfaces TypeScript (Frontend)

* **Arquivo:** [`frontend/src/types.ts`](file:///j:/Arquivos%20Osmar/Multi+/frontend/src/types.ts)

### Entidades Centrais de Mensageria e Conversas

```typescript
export interface Attachment {
  id: string
  filename: string
  mime_type: string
  file_type: 'document' | 'image'
  size_bytes: number
  thumbnail_url?: string | null
  file_url?: string
  extracted_text?: string | null
}

export interface WebSearchSource {
  title: string
  url: string
}

export interface Message {
  id: string
  role: 'user' | 'assistant' | 'system' | 'fusion_status' | 'error'
  content: string
  model_id?: string
  created_at?: string
  artifact_id?: string
  artifact_title?: string
  artifact_type?: string
  artifacts?: { id: string; type: string; title: string }[]
  provider?: string
  model_display_name?: string
  attachments?: Attachment[]
  relay_used?: boolean
  relay_model?: string | null
  web_search_used?: boolean
  web_search_query?: string
  web_search_sources?: WebSearchSource[]
  was_fallback?: boolean
}

export interface Conversation {
  id: string
  title: string
  model_id?: string
  provider_id?: string
  created_at: string
  updated_at: string
  message_count: number
  is_favorite?: boolean
  favorited_at?: string | null
  project_tag?: string | null
  project_id?: string | null
}

export interface ConversationDetail extends Conversation {
  messages: Message[]
}
```

### Provedores, Modelos e Projetos

```typescript
export interface Model {
  id: string
  display_name: string
  context_length: number
  context_source?: string
  confirmed_free?: number
  enabled?: boolean
  provider_id?: string
  supports_vision?: boolean
}

export interface Provider {
  id: string
  name: string
  base_url: string
  enabled: boolean
  is_free: boolean
  has_key?: boolean
  share_admin_key?: boolean
  models: Model[]
}

export interface Project {
  id: string
  name: string
  description?: string
  instructions?: string
  model_default?: string | null
  is_favorite?: boolean
  archived?: boolean
  retrieval_top_k?: number
  retrieval_threshold?: number
  created_at: string
  updated_at: string
  file_count?: number
  chat_count?: number
  memory_preview?: string | null
}
```

---

## 6. Recursos Avançados Integrados

1. **Smart Cache Híbrido ([`backend/cache/`](file:///j:/Arquivos%20Osmar/Multi+/backend/cache)):**
   * Verificação L1: Hash SHA-256 exato.
   * Verificação L2: Similaridade semântica de cosseno (> 0.92) via FastEmbed. Responde instantaneamente (< 20ms) e simula streaming de saída no frontend.
2. **Memória Adaptativa & Diário de Sonhos ([`backend/memory_dream.py`](file:///j:/Arquivos%20Osmar/Multi+/backend/memory_dream.py)):**
   * Extração de fatos pós-conversa em segundo plano via LLM leve.
   * Consolidação periódica em background (mescla duplicatas, resolve contradições temporais, preserva fatos fixados `is_pinned` e permite simulação dry-run com reversão em 1 clique).
3. **Projects RAG ([`backend/projects/`](file:///j:/Arquivos%20Osmar/Multi+/backend/projects)):**
   * Indexação de código e documentos em chunks com janelas de sobreposição inteligente.
   * Busca híbrida combinando densidade vetorial com recuperação léxica para termos exatos.
4. **Model Fusion ([`backend/fusion/`](file:///j:/Arquivos%20Osmar/Multi+/backend/fusion)):**
   * Dispara perguntas simultaneamente para múltiplos modelos selecionados, gerando síntese e arbitragem fundamentada.

---

## 7. Dream Memory Consolidator (Arquitetura e Fluxo de Sono)

O **Dream Memory Consolidator** é o subsistema autônomo responsável pela higiene e síntese da memória adaptativa de longo prazo:

### A. Onde Fica no Código-Fonte
* **Motor de Consolidação:** [`backend/memory_dream.py`](file:///j:/Arquivos%20Osmar/Multi+/backend/memory_dream.py) (regras de ouro, resolução temporal `{CURRENT_DATE}`, modelo Pydantic `DreamResponseSchema`, validação `verify_dream_safety`).
* **Snapshots e Banco de Dados:** [`backend/database.py`](file:///j:/Arquivos%20Osmar/Multi+/backend/database.py) (tabelas `user_memory`, `memory_snapshots`, `dream_logs`, métodos `create_memory_snapshot`, `rollback_memory_snapshot`, `update_memory_fact`).
* **Orquestração e Gatilhos:** [`backend/routers/memory.py`](file:///j:/Arquivos%20Osmar/Multi+/backend/routers/memory.py) e cron assíncrono em [`backend/main.py`](file:///j:/Arquivos%20Osmar/Multi+/backend/main.py) (`run_dream_consolidation_job`, lock `_memory_pipeline_lock`).
* **Interface Frontend:**
  * Painel principal: [`frontend/src/components/UserMemoryPanel.tsx`](file:///j:/Arquivos%20Osmar/Multi+/frontend/src/components/UserMemoryPanel.tsx) (localizado em **Configurações → Memória adaptativa**).
  * Diário de Sonhos: [`frontend/src/components/DreamJournalSection.tsx`](file:///j:/Arquivos%20Osmar/Multi+/frontend/src/components/DreamJournalSection.tsx) (timeline de ciclos, métricas de compressão, telemetria, streaming SSE de 5 passos e botão de reversão).
  * Modal Dry-Run Preview: [`frontend/src/components/DreamPreviewModal.tsx`](file:///j:/Arquivos%20Osmar/Multi+/frontend/src/components/DreamPreviewModal.tsx) (visualização prévia com abas de Fusão, Atualização, Arquivamento e Mantidos).

### B. Onde Fica na Interface Visual do App
Na tela de **Configurações → Memória adaptativa**:
1. **Diário de Sonhos:** Renderizado logo abaixo do interruptor *"Memória nas conversas (padrão: ligada)"* e acima de *"Como funciona a memória?"*.
2. **Ações:** Botões `[Simular Consolidação (Preview)]` e `[Executar Agora ⚡]`.
3. **Cards de Fatos:** Cada fato possui ícone de lápis para edição inline direta (`PUT /api/memory/facts/{id}`) e badges visuais `[PIN]`, `[Familiar]`, `[🌙 Consolidado]`, `v{version}`.
4. **Censo de Fatos:** Exibe `X ativos (+ Y no histórico)` com checkbox para incluir fatos arquivados na busca.

### C. Regras de Segurança e Garantias
1. **Zero Sobrecarga Local:** Toda a inferência pesada de LLM roda nas APIs externas gratuitas; o servidor local apenas executa transações flash SQLite (< 80ms) e FastEmbed vetorial (< 300ms).
2. **Proteção Inegociável a Fatos Fixados:** Fatos com `is_pinned = 1` nunca são arquivados ou desfixados pelo consolidador.
3. **Reversão Cirúrgica de 1 Clique:** O rollback restaura o estado anterior ao sonho sem apagar nem afetar novos fatos que o usuário tiver criado posteriormente.

