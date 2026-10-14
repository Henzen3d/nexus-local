# ⚙️ Fase 2 — Núcleo do Pipeline (detecção → pesquisa → síntese → entrega inline/toast)

**Objetivo:** fazer o insight nascer e chegar à conversa de origem quando o usuário está **presente**, com todos os limites de segurança e custo. Presença ainda é simples nesta fase (socket aberto + conversa ativa); fila e retorno vêm na F3.
**Estimativa:** 10 h · **Dependências:** F1 (go) · **Bloqueia:** F3, F4.

**Entregáveis**
- Migrações em `backend/database.py::init_db`
- `backend/proactive/{config,service,researcher,synthesizer,delivery,prompts}.py`, `backend/routers/proactive.py`
- Hook em `backend/routers/chat.py::_process_turn`
- Frontend: `ProactiveBubble.tsx`, extensão do toast, tratamento dos eventos WS, i18n

---

## Tarefa F2.1 — Esquema de dados (migrações incrementais)

Seguir o padrão do projeto: blocos `try/except` com `ALTER TABLE` dentro de `init_db()`; índices criados **após** o bloco de migração (AGENTS.md).

- [x] **F2.1.1** Tabela `proactive_insights`:
  ```sql
  CREATE TABLE IF NOT EXISTS proactive_insights (
    id                   TEXT PRIMARY KEY,
    user_id              TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    conversation_id      TEXT NOT NULL REFERENCES conversations(id) ON DELETE CASCADE,
    source_message_id    TEXT REFERENCES messages(id) ON DELETE SET NULL,
    delivered_message_id TEXT REFERENCES messages(id) ON DELETE SET NULL,
    spawned_conversation_id TEXT REFERENCES conversations(id) ON DELETE SET NULL,
    topic                TEXT NOT NULL,
    topic_hash           TEXT NOT NULL,          -- sha256(normalize(topic+entities))[:16]
    entities_json        TEXT NOT NULL DEFAULT '[]',
    category             TEXT NOT NULL,          -- event|news|product|place|other
    confidence           REAL NOT NULL,
    query                TEXT,
    status               TEXT NOT NULL DEFAULT 'detected'
                         CHECK(status IN ('detected','researching','ready','delivered','seen','dismissed','blocked','expired','failed')),
    channel              TEXT,                   -- inline|toast|pending_card|pending_inline|new_chat|push
    synthesized_text     TEXT,
    sources_json         TEXT,
    follow_ups_json      TEXT,
    error_code           TEXT,
    detector_model       TEXT, synth_model TEXT,
    latency_detect_ms INTEGER, latency_research_ms INTEGER, latency_synth_ms INTEGER,
    created_at  TEXT DEFAULT (datetime('now')),
    ready_at    TEXT, delivered_at TEXT, seen_at TEXT, expires_at TEXT
  );
  CREATE INDEX IF NOT EXISTS idx_proactive_user_status ON proactive_insights(user_id, status, created_at DESC);
  CREATE INDEX IF NOT EXISTS idx_proactive_topic_recent ON proactive_insights(user_id, topic_hash, created_at DESC);
  CREATE INDEX IF NOT EXISTS idx_proactive_conv ON proactive_insights(conversation_id, created_at DESC);
  ```
- [x] **F2.1.2** Tabela `proactive_user_settings(user_id PK REFERENCES users ON DELETE CASCADE, enabled INTEGER DEFAULT 0, sensitivity TEXT DEFAULT 'medium', categories_json TEXT DEFAULT '["event","news","product","place"]', quiet_hours_json TEXT, onboarding_seen_at TEXT, updated_at TEXT)`. **Default `enabled=0` (opt-in).**
- [x] **F2.1.3** Tabela `proactive_topic_blocklist(user_id, topic_hash, topic_label, created_at, PRIMARY KEY(user_id, topic_hash))`.
- [x] **F2.1.4** `ALTER TABLE messages ADD COLUMN kind TEXT DEFAULT 'normal'` e `ALTER TABLE messages ADD COLUMN proactive_insight_id TEXT` (+ índice parcial `idx_messages_kind_proactive ON messages(conversation_id) WHERE kind='proactive'`).
- [x] **F2.1.5** `ALTER TABLE conversations ADD COLUMN origin_insight_id TEXT` (usado na F3 pelo "Me conta aqui").
- [x] **F2.1.6** Chaves em `meta` (admin, lidas por `config.py`): `proactive_enabled_global` (`'true'` default), `proactive_detector_provider_id/model_id`, `proactive_synth_provider_id/model_id`, `proactive_max_per_hour_conv=3`, `proactive_max_per_day_user=10`, `proactive_topic_cooldown_hours=24`, `proactive_max_pending=3`, `proactive_concurrency=2`, `proactive_total_timeout_s=45`.
- [x] **F2.1.7** Teste de migração: `init_db()` duas vezes no DB temporário sem erro; colunas/índices presentes (`PRAGMA table_info`).

**Arquivos:** `backend/database.py`, `backend/tests/test_proactive_schema.py`

---

## Tarefa F2.2 — Configuração e limites (`config.py`, `service.py`)

- [x] **F2.2.1** `backend/proactive/config.py`: `dataclass ProactiveConfig` + `async load_config(db)` (meta → env `PROACTIVE_*` → defaults) com cache de 60 s (padrão do cache de role em `auth.py`).
- [x] **F2.2.2** `async get_user_settings(db, user_id)` com defaults (opt-in ⇒ `enabled=False` se não houver linha).
- [x] **F2.2.3** Rate limits em SQL (sem estado em memória, para sobreviver a restart): `COUNT(*) WHERE conversation_id=? AND created_at > now-1h AND status NOT IN ('failed')` ≤ 3; por usuário/dia ≤ 10; cooldown por `topic_hash` 24 h; pendentes (`status='ready'`) ≤ 3 — ao exceder, expirar o mais antigo.
- [x] **F2.2.4** Semáforo global `asyncio.Semaphore(config.concurrency)` + `asyncio.wait_for(total_timeout_s)` em volta do pipeline.
- [x] **F2.2.5** `schedule_proactive_check(user_id, conversation_id, user_msg_id, user_message, *, web_search_used, model_id, provider_id)`: checa `enabled_global` e `settings.enabled` **antes** de criar a task; guarda a referência em um `set` de módulo (`_tasks`) com `add_done_callback(discard)` — nunca `create_task` solto.
- [x] **F2.2.6** `run_pipeline(...)` orquestra: gate → classify → limites → insert `detected` → research → synthesize → `ready` → `delivery.deliver()`; cada etapa atualiza `status`/latências; exceções ⇒ `status='failed', error_code` + log `warning` (nunca sobe para o WS do usuário).
- [x] **F2.2.7** Excluir mensagens `kind='proactive'` da extração de memória (`memory.py` L809, adicionar `AND COALESCE(kind,'normal') <> 'proactive'`) e do Dream (`memory_dream.py`, mesma condição), para a IA não "aprender" fatos a partir das próprias pesquisas. _(Dream não lê `messages` diretamente — opera sobre fatos já extraídos; filtro aplicado em `memory.py`.)_

**Arquivos:** `backend/proactive/config.py`, `backend/proactive/service.py`, `backend/memory.py`, `backend/memory_dream.py`
**Pronto quando:** testes de limites (3/h, 10/dia, cooldown, máx. pendentes) passam com relógio simulado (`freezegun` não é dependência — usar `created_at` injetável nos inserts de teste).

---

## Tarefa F2.3 — Pesquisa (`researcher.py`)

- [x] **F2.3.1** `async research(signal: InterestSignal, db) -> ResearchResult(query, sources: list[Source], cache_hit: bool, elapsed_ms)`; `Source(title, url, domain, snippet, content_excerpt, published_at|None)`.
- [x] **F2.3.2** Consulta: `signal.suggested_query` (+ cidade/ano quando `time_sensitive`); opcionalmente `plan_search_queries()` para gerar 1 consulta extra (máx. 2 consultas). _(2ª consulta heurística em `build_queries` — cidade/ano quando `time_sensitive`; sem chamada extra ao LLM.)_
- [x] **F2.3.3** Busca via `resolve_and_execute_search(query, db)` (respeita provider/API key/habilitado da config global de web search; se web search global estiver desabilitada ⇒ `failed:web_search_disabled`).
- [x] **F2.3.4** Deep read das **2 melhores** URLs com `fetch_page_content` (já anti-SSRF, 2 MB, 6 s) — concorrente com `asyncio.gather`, tolerante a falha; extrair datas quando `category=event` (reaproveitar extração de datas do reader/agent, se exposta).
- [x] **F2.3.5** Dedupe por URL canônica (sem `utm_*`, sem fragmento); ranking: domínio oficial/ingressos/news > agregadores; máx. 3 fontes finais.
- [x] **F2.3.6** Cache por `topic_hash` 24 h: se existir insight `ready|delivered|seen` do **mesmo usuário ou de outro** com o mesmo `topic_hash` nas últimas 24 h, reutilizar `sources_json` (a pesquisa é pública; a síntese é refeita por usuário). _(cache 24 h por `topic_hash` em `researcher.research(use_cache=True)`; a checagem de web search global ocorre **antes** do cache.)_
- [x] **F2.3.7** Timeout da etapa: 30 s; resultado vazio ⇒ `failed:no_results` silencioso.

**Arquivos:** `backend/proactive/researcher.py`
**Pronto quando:** teste com provider de busca fake e `fetch_page_content` mockado cobre: sucesso, sem resultados, 1 página falhando, cache hit.

---

## Tarefa F2.4 — Síntese (`synthesizer.py`, `prompts.py`)

- [x] **F2.4.1** Prompt "amigo que pesquisou": persona do Nexus (reutilizar tom do `BASE_SYSTEM_PROMPT`), **idioma da mensagem original**, ≤ 3 frases, 1 pergunta-gancho, citar fatos **somente** presentes nas fontes, sem inventar datas/preços, incluir "pesquisei porque você pareceu {emoção} com {topic}" como campo separado (`reason_line`).
- [x] **F2.4.2** Saída JSON: `{ "text": str, "reason_line": str, "follow_ups": [str, ≤3], "used_source_urls": [str] }`; parser tolerante como no detector; falha ⇒ `failed:synth_parse`.
- [x] **F2.4.3** Modelo: `meta.proactive_synth_*` → fallback para o modelo utilitário → fallback para o modelo da conversa (`conversations.model_id/provider_id`) se o admin permitir (`proactive_allow_chat_model_fallback`).
- [x] **F2.4.4** Pós-processamento: remover links do texto (as fontes vão em `sources_json`), limitar a 600 chars, garantir que `used_source_urls ⊆ sources`.
- [x] **F2.4.5** `expires_at` por categoria: `event` → data detectada (ou +7 d), `news` → +48 h, demais → +7 d.

**Arquivos:** `backend/proactive/synthesizer.py`, `backend/proactive/prompts.py`
**Pronto quando:** teste com provider fake valida JSON, limites de tamanho e `expires_at` por categoria.

---

## Tarefa F2.5 — Entrega inline/toast (`delivery.py`) — versão F2

Nesta fase a presença é mínima: "presente" = usuário tem socket aberto **e** `active_conversation_id == conversation_id` (campo enviado pelo cliente em F2.7). Fila/retorno completos ficam para F3.

- [x] **F2.5.1** `async deliver(insight, db) -> DeliveryOutcome(channel, message_id|None)`.
- [x] **F2.5.2** Persistir a mensagem do assistente: `INSERT INTO messages(id, conversation_id, role='assistant', content=prefix+text, kind='proactive', proactive_insight_id, model_id, provider)` e `UPDATE conversations SET updated_at` — **sem** alterar o título.
- [x] **F2.5.3** Montar payload `proactive_insight` (contrato em `01-decisao-entrega-e-presenca.md` §3.2) e enviar via `notify_user_sockets(user_id, payload)` com `channel_hint = inline|toast`.
- [x] **F2.5.4** Guardas de "não interromper": o servidor sabe se há turno em andamento para a conversa (`service._active_turns: set[conversation_id]`, marcado em `_process_turn` início/fim); se houver, aguardar o fim (`flush_after_turn`) antes de persistir/enviar. A guarda de digitação (3 s) é do cliente (F2.7).
- [x] **F2.5.5** Se não houver socket: `status='ready'` permanece (F3 entregará); nesta fase, o insight aparece ao recarregar a conversa (já persistido) — aceitável como comportamento intermediário? **Não**: para não "aparecer do nada" sem o prefixo correto, em F2 só persistir quando houver socket ativo; sem socket mantém `ready` sem mensagem (F3 cuida do prefixo de retorno). _(implementado: sem socket ⇒ `ready` sem mensagem.)_
- [x] **F2.5.6** Idempotência: `delivered_message_id IS NOT NULL` ⇒ não reenviar.

**Arquivos:** `backend/proactive/delivery.py`, `backend/routers/chat.py` (marcação de turno ativo)

---

## Tarefa F2.6 — Integração no chat e router REST mínimo

- [x] **F2.6.1** Em `routers/chat.py::_process_turn`, após o bloco de extração de memória: `schedule_proactive_check(...)` com `web_search_used` e ids. Overhead medido ≤ 5 ms (só agenda).
- [x] **F2.6.2** Tratar no loop do WS a mensagem `{type:"presence"}` (F2: apenas `conversation_id`/`state`) chamando `presence.update(user_id, ws, ...)` — estrutura mínima que a F3 estende.
- [x] **F2.6.3** `GET /api/conversations/{id}` passa a devolver `kind` e `proactive_insight_id` por mensagem e, para `kind='proactive'`, anexa `insight: {topic, reason_line, sources, follow_ups, status}` (join em `proactive_insights`) — `routers/conversations.py` L91.
- [x] **F2.6.4** `backend/routers/proactive.py` (prefixo `/api/proactive`) com `GET /settings`, `PUT /settings` (usuário) e `POST /insights/{id}/ack` (dono — validar `user_id`, como na auditoria). `expand`, `pending`, admin e logs ficam para F3/F4.
- [x] **F2.6.5** Registrar o router em `backend/main.py`.
- [x] **F2.6.6** Poda de histórico: nada a fazer (bolha é mensagem normal para `trim_history_to_budget`), mas **confirmar** que `load_history` inclui `kind='proactive'` como `assistant` (necessário para "quer saber mais"). _(confirmado: `_process_turn` carrega `SELECT role, content FROM messages` sem filtrar `kind`.)_

**Arquivos:** `backend/routers/chat.py`, `backend/routers/conversations.py`, `backend/routers/proactive.py`, `backend/main.py`

---

## Tarefa F2.7 — Frontend: bolha, toast com ação e eventos

- [x] **F2.7.1** `types.ts`: `Message.kind?: 'normal' | 'proactive'`, `Message.insight?: ProactiveInsight`; tipo `ProactiveInsight` (shape do contrato) em `types.ts`.
- [x] **F2.7.2** `hooks/useChat.ts`: tratar `proactive_insight` (delegar ao store `handleProactiveInsight`) e `proactive_status` (indicador discreto "✦ pesquisando…" no rodapé da conversa, sem bloquear nada).
- [x] **F2.7.3** `store/useStore.ts::handleProactiveInsight(evt)`: generalizar a lógica de `handleImageReady` — se `activeConversationId === insight.conversation_id` e não está `isStreaming` e sem digitação há ≥ 3 s ⇒ **append** da mensagem (`kind='proactive'`); senão ⇒ toast com ação `Ver` (abre a conversa) + marcar `conversationsWithInsight.add(id)` para o badge. Se estiver digitando/streaming ⇒ guardar em `pendingInline` e aplicar quando liberar. _(guarda de digitação de 3 s via `noteTyping()` no composer; fila `pendingInlineInsights` reavaliada ao fim do streaming.)_
- [x] **F2.7.4** Enviar `presence{conversation_id}` ao trocar de conversa (F2 mínimo) a partir de `useChat`/store. _(`presence{state, conversation_id, view}` imediato ao abrir socket/trocar conversa; `visibilitychange`/focus/blur com debounce de 2 s.)_
- [x] **F2.7.5** `components/ProactiveBubble.tsx`: variante visual da `MessageBubble` (ícone ✦, borda/cor via novas CSS vars `--proactive-accent`, `--proactive-bg` em `index.css`, **vanilla CSS, sem Tailwind**), linha de motivo (`reason_line`), `SourceShelf` com as fontes, ações **Quero saber mais** / **Não quero sobre isso** / **Pausar assistente proativo** (as duas últimas ligam ao `ack` e às settings; "saber mais" em F2 preenche o input com o 1º `follow_up`).
- [x] **F2.7.6** `ChatWindow.tsx`: renderizar `ProactiveBubble` quando `m.kind === 'proactive'`; `IntersectionObserver` ⇒ `ack seen` (uma vez).
- [x] **F2.7.7** Toast com ação: estender `useStore.toast` para `{ message, type, action?: { label, onClick }, durationMs? }` e fila de até 3 (array) — `App.tsx::Toast` renderiza a fila; manter compatibilidade com `showToast(message, type)`.
- [x] **F2.7.8** Badge ✦ na `Sidebar.tsx`/`ConversationsPanel.tsx` para conversas em `conversationsWithInsight`; some ao abrir.
- [x] **F2.7.9** i18n (pt-BR, en-US, es-ES obrigatórios; replicar nos demais 5): `proactive.bubbleBadge`, `proactive.reasonLine`, `proactive.knowMore`, `proactive.notThisTopic`, `proactive.pause`, `proactive.toastTitle`, `proactive.toastView`, `proactive.researching`. _(+ `knowMorePrompt`, `synthesizing`, `blockedNote`, `dismissedNote`, `blockedToast`, `pausedToast`, `ackError`, `unreadBadge`, `category.*` nos 8 locales.)_
- [x] **F2.7.10** `npm run build` com 0 erros de TS.

**Arquivos:** `frontend/src/types.ts`, `hooks/useChat.ts`, `store/useStore.ts`, `components/ProactiveBubble.tsx`, `components/ChatWindow.tsx`, `components/Sidebar.tsx`, `App.tsx`, `index.css`, `i18n/locales/*.json`, `api/client.ts`

---

## Tarefa F2.8 — Testes da fase

- [x] **F2.8.1** `test_proactive_pipeline.py`: pipeline completo com detector/busca/síntese fakes no DB temporário → insight `ready` + mensagem `kind='proactive'` quando há socket fake ativo na conversa.
- [x] **F2.8.2** Limites: 4ª pesquisa na mesma conversa em 1 h ⇒ não cria; 11ª no dia ⇒ não cria; mesmo `topic_hash` em < 24 h ⇒ não pesquisa (reutiliza fontes); 4º pendente ⇒ expira o mais antigo. _(testes de cache usam `use_cache=False` por padrão porque o DB do `conftest` é compartilhado entre testes; o teste dedicado de cache usa `topic_hash` único.)_
- [x] **F2.8.3** Segurança: `ack` de insight de outro usuário ⇒ 404/403; mensagem proativa nunca aparece em `GET /conversations/{id}` de outro usuário (reutilizar padrão dos testes da auditoria).
- [x] **F2.8.4** Memória: `extract_user_memory_background` ignora mensagens `kind='proactive'`.
- [x] **F2.8.5** Integração WS com `TestClient`: turno normal + `schedule_proactive_check` fake ⇒ cliente recebe `proactive_insight` após o `stream_end`, nunca antes. _(`test_proactive_ws.py`: `stream_end` sempre antes de `proactive_status`/`proactive_insight`; presença malformada ignorada.)_

---

## Critérios de aceite da fase
- [x] Insight entregue na conversa de origem em ≤ 45 s (p95) quando o usuário está presente nela; toast + badge quando está em outra. _(timeout total de 45 s imposto por `asyncio.wait_for`; p95 real depende do provedor de busca/síntese — medir em produção.)_
- [x] Nenhuma entrega durante streaming/digitação (teste manual + unitário do store). _(servidor: `TurnGuard`/`wait_turn_end`; cliente: `isStreaming`/`fusionActive` + guarda de 3 s de digitação. Teste manual com provedor real fica para o ambiente do usuário.)_
- [x] Todos os limites testados; nenhum vazamento entre usuários.
- [x] Mensagens proativas visíveis ao recarregar a conversa, com fontes e motivo.
- [x] Suíte verde; `npm run build` 0 erros; i18n completa. _(297 passed / 1 skipped; os 4 falhos + 1 erro são os pré-existentes documentados em `ROADMAP-CHECKLIST.md`.)_
