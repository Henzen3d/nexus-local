# Auditoria cirúrgica do NexusLocal — segurança, bugs, otimização e melhorias

**Data:** 2026-10-13 · **Escopo:** backend (FastAPI + aiosqlite), frontend (React/TS/Vite), infraestrutura (Docker Compose, nginx, Cloudflare Tunnel) · **Base:** commit `4aa9a59` (`main`) · **Branch de trabalho:** `arena/e21b5b67-nexus-local`

> Legenda de severidade: **CRÍTICO** (acesso a dados de outros usuários / comprometimento do servidor) · **ALTO** (quebra de confidencialidade ou disponibilidade com esforço baixo) · **MÉDIO** (bug funcional, desperdício relevante ou endurecimento importante) · **BAIXO** (higiene, manutenibilidade).
>
> Cada item indica se a correção **foi aplicada** nesta branch ou se fica como **recomendação**.

---

## 1. Resumo executivo

O sistema é bem construído na maior parte: SQL 100 % parametrizado, escopo por usuário em conversas/artefatos/projetos, failover de provedores com timeout de TTFT, cache semântico isolado por usuário, iframes de artefatos sem `allow-same-origin`, uploads com whitelist e limite de tamanho. Porém, três falhas **críticas** permitiam que um usuário autenticado lesse/alterasse dados de outro (em um deploy familiar isso significa que qualquer membro da família acessaria as conversas e arquivos dos demais), e diversos pontos **altos** expunham configurações globais, a rede interna (SSRF) e a disponibilidade (sem limite de tentativas de login, histórico de chat sem poda).

| Severidade | Encontrados | Corrigidos nesta branch | Ficam como recomendação |
|---|---|---|---|
| CRÍTICO | 3 | 3 | — |
| ALTO | 9 | 6 | chaves de API em claro (§2.9), `base_url` arbitrário (§2.10), token WS na query string (§2.13); migração python-jose → PyJWT (§2.6) |
| MÉDIO | 25 | 11 | container root (§2.12), tabela §2.15, B7, tabela §4.4 |
| BAIXO | 10 | 3 | higiene de código, deprecações, scripts soltos |

**Validação:** suíte existente mantém o mesmo estado do baseline — **142 passaram**; as 9 falhas/4 erros restantes são pré-existentes (testes que criam schema parcial ou dependem de `fastembed` não instalado — ver §6); **+18 testes novos** cobrindo as correções (`backend/tests/test_security_hardening.py`) passam; smoke test ponta a ponta com `TestClient` (login, rate limit, IDOR via WebSocket, URL assinada, revogação de token) passou; `npm run build` com **0 erros de TypeScript**.

---

## 2. Falhas de segurança

### 2.1 CRÍTICO — IDOR no chat: qualquer usuário lia/escrevia em conversas alheias — **CORRIGIDO**

- **Onde:** `backend/orchestration/persist_turn.py::ensure_conversation` (quando `conversation_id` vinha no payload do WS, a conversa não era validada contra `conversations.user_id`) e `backend/routers/chat.py::_process_turn`.
- **Impacto:** com um `conversation_id` de outro usuário (UUID vazado em URL, histórico do navegador compartilhado, etc.), o atacante recebia **todo o histórico** daquela conversa injetado no prompt e ainda gravava mensagens nela.
- **Correção aplicada:** `verify_conversation_owner(db, conv_id, user_id)` + `is_valid_conversation_id` (regex UUID — o id também compõe caminhos no filesystem). `_process_turn` verifica antes de qualquer trabalho; o loop do WS devolve `{"type":"error"}` + `stream_end` sem derrubar o socket (`ConversationAccessError`). Mensagem genérica ("Conversa não encontrada.") para não confirmar a existência.

### 2.2 CRÍTICO — Sequestro de anexos: tabela `attachments` não tinha dono — **CORRIGIDO**

- **Onde:** `backend/attachments/storage.py::move_attachments_to_conversation` aceitava qualquer `att_*` enviado pelo cliente e o vinculava à mensagem do chamador.
- **Impacto:** um usuário podia "adotar" o anexo de outro (bastava o id), recebendo o `extracted_text` do PDF/DOCX e a imagem no próprio contexto de chat.
- **Correção aplicada:**
  - Migração incremental em `backend/database.py::init_db` (padrão try/except do projeto): `ALTER TABLE attachments ADD COLUMN user_id TEXT` + *backfill* via `messages → conversations.user_id` + índice parcial `idx_attachments_user_unsent`.
  - `routers/attachments.py::upload_attachment` e `image_gen/worker.py` gravam `user_id`.
  - `move_attachments_to_conversation(..., user_id=)` só move anexos **sem `message_id`** e **do próprio usuário** (linhas legadas sem dono continuam aceitas, e passam a ter dono via `COALESCE`); ids fora do padrão `att_…` são ignorados; `conversation_id` precisa ser UUID.

### 2.3 CRÍTICO — Uploads servidos publicamente e cacheados como `public` — **CORRIGIDO**

- **Onde:** `backend/main.py` (`StaticFiles` em `/attachments`) + `frontend/nginx.conf` (`expires 1h; add_header Cache-Control "public"`).
- **Impacto:** qualquer pessoa com a URL (previsível: `/attachments/<conversation_uuid>/<att_id>_<nome>`) baixava o arquivo sem autenticação; o Cloudflare ainda podia **cachear e servir** para terceiros.
- **Correção aplicada:** URLs assinadas (HMAC-SHA256 com expiração, `backend/attachments/signing.py`) geradas em todos os 4 pontos que montam `file_url`/`thumbnail_url` (upload, biblioteca, conversas, worker de imagem). Nova rota `GET /attachments/{rel_path}` (`routers/attachments.py::files_router`) valida assinatura e expiração, garante que o caminho resolvido fica dentro de `STORAGE_DIR`, responde `Cache-Control: private`, `X-Content-Type-Options: nosniff` e só exibe *inline* MIME seguros. O mount estático foi removido; o nginx deixou de forçar `public`. O frontend já consumia as URLs vindas da API, então não houve mudança de contrato.
  - Segredo: `ATTACHMENTS_SIGNING_SECRET` (opcional; se vazio deriva do `JWT_SECRET`). TTL: `ATTACHMENTS_URL_TTL_SECONDS` (padrão 7 dias).

### 2.4 ALTO — Configurações globais editáveis por qualquer usuário — **CORRIGIDO**

- **Onde:** `routers/enhancer.py` / `vision_relay.py` / `web_search.py` `POST /config`; `routers/memory.py` `PUT /extractor-config` e `PUT /dream-config`; `routers/cache_admin.py` `GET /entries/{tipo}` (listava os prompts de **todos** os usuários).
- **Correção aplicada:** `Depends(require_admin)` em todos (os módulos `fusion`/`image_gen` já faziam isso). No frontend, a seção "modelo do extrator" em `UserMemoryPanel.tsx` agora só aparece para admin (antes, um usuário comum veria o botão e receberia 403).

### 2.5 ALTO — Login sem limite de tentativas e com enumeração de usuários — **CORRIGIDO**

- **Onde:** `routers/auth.py::login`. Público via Cloudflare Tunnel, sem rate limit; para usuário inexistente respondia **sem rodar o bcrypt** (tempo de resposta denunciava quais logins existem).
- **Correção aplicada:** `backend/rate_limit.py` (janela deslizante em memória, sem dependências): 10 tentativas/IP/15 min e 5/usuário/15 min → `429` + `Retry-After`; sucesso zera o contador do usuário. Hash *dummy* verificado quando o usuário não existe (tempo constante). `Field` com limites de tamanho no schema. IP real via `CF-Connecting-IP`/`X-Forwarded-For`. Frontend: nova string i18n `auth.tooManyAttempts` (8 idiomas) exibida no 429.

### 2.6 ALTO — Token JWT válido por 7 dias sem revalidação — **CORRIGIDO**

- **Onde:** `backend/auth.py::get_current_user` confiava no `role` embutido no token e nunca consultava o banco.
- **Impacto:** usuário excluído ou rebaixado continuava operando (inclusive como admin) por até 7 dias.
- **Correção aplicada:** `_current_role()` revalida existência/role no banco com cache de 60 s; `invalidate_user_state_cache()` é chamado em `DELETE /admin/users/{id}` (efeito imediato). WebSocket passou a usar `resolve_token_user()` (mesma validação). Alerta em log se `JWT_SECRET` tiver < 32 caracteres. `verify_password` não propaga mais exceção de hash corrompido (evitava 500).
- **Recomendação pendente:** migrar `python-jose==3.3.0` (CVE-2024-33663/33664) para `PyJWT`, reduzir expiração para 24 h com *refresh*, e usar `iat`/`token_version` por usuário para revogar tudo na troca de senha.

### 2.7 ALTO — SSRF no Deep Reader da busca web — **CORRIGIDO**

- **Onde:** `backend/web_search/reader.py::fetch_page_content` — `verify=False`, `follow_redirects=True`, nenhum filtro de destino; o domínio lido vem do prompt do usuário (`agent.py::extract_domains_and_urls`).
- **Impacto:** `leia http://nexus_backend:8000/health` ou um DNS apontando para `127.0.0.1`/`172.x` devolvia o conteúdo de serviços internos (backend, Portainer na porta 8000 do host, metadata endpoints) dentro da resposta do modelo.
- **Correção aplicada:** `is_safe_public_url()` resolve o host e bloqueia loopback, privados, link-local, multicast, reservados, IPv6 mapeado, `localhost`/`.local`/`.internal`; apenas `http(s)`; redirects seguidos **manualmente** (máx. 4) revalidando cada salto; corpo limitado a 2 MB e a `Content-Type` textual. `WEB_SEARCH_ALLOW_PRIVATE_HTTP=true` desliga o bloqueio se algum dia for intencional.
- **Observação:** `verify=False` foi mantido (sites com TLS quebrado são comuns no scraping), mas vale considerar `verify=True` com fallback explícito.

### 2.8 ALTO — Histórico de chat sem poda (disponibilidade + custo) — **CORRIGIDO** (ver §4.1)

### 2.9 ALTO — Chaves de API em texto puro no SQLite — **RECOMENDAÇÃO**

`user_api_keys.api_key` e `providers.api_key` ficam em claro em `backend/nexuslocal.db`, arquivo *bind-mounted* no host. Recomendo cifrar com Fernet (`cryptography` já é dependência transitiva) usando chave em `API_KEYS_ENCRYPTION_KEY`, com migração *lazy* (decifrar; se falhar, tratar como texto puro e recifrar). Enquanto isso, garanta `chmod 600` no `.db` e nos `-wal`/`-shm`, e backups cifrados.

### 2.10 ALTO — `base_url` arbitrário por provedor — **RECOMENDAÇÃO**

`PATCH /api/admin/providers/{id}` aceita qualquer `base_url` (admin-only, mas combinado com um token admin vazado vira SSRF autenticado com a chave do usuário). Validar esquema `https`, host não privado (reutilizar `is_safe_public_url`) e, idealmente, uma *allowlist* por provedor.

### 2.11 MÉDIO — Cabeçalhos de segurança e proxy — **CORRIGIDO**

- `frontend/nginx-security-headers.conf` (novo, incluído em todos os blocos com `add_header`, pois no nginx `add_header` em `location` descarta os herdados): `X-Content-Type-Options`, `X-Frame-Options`, `Content-Security-Policy: frame-ancestors 'self'`, `Referrer-Policy`, `Permissions-Policy`; `server_tokens off`. **Sem CSP completa de propósito:** os artefatos rodam em iframes `srcdoc`, que herdam a CSP do pai — `script-src 'self'` quebraria os CDNs (React/Tailwind) usados pelo `ArtifactPanel`.
- Bundles `/assets/*` (hash no nome) agora com `immutable, max-age=1y` (antes `no-cache` em tudo → recarregava ~1,5 MB a cada visita).
- `backend/Dockerfile`: `--forwarded-allow-ips=*`. Sem isso o uvicorn **ignorava** `X-Forwarded-*` do nginx (confia só em 127.0.0.1) e `request.client.host`/`url.scheme` ficavam errados. Seguro porque a porta 8000 não é publicada no host.
- **Recomendação:** HSTS pelo painel do Cloudflare (não pelo nginx, para não afetar acesso LAN http).

### 2.12 MÉDIO — Container do backend roda como root — **RECOMENDAÇÃO (não aplicado de propósito)**

Trocar para `USER app` quebraria o deploy atual: `./backend/nexuslocal.db` e `./backend/storage` são *bind mounts* criados pelo container root, logo pertencem a root no host. Roteiro seguro: (1) `adduser --uid 1000 app` no Dockerfile + `USER app`; (2) no host, `chown -R 1000:1000 backend/nexuslocal.db* backend/storage`; (3) trocar `fastembed_cache:/root/.cache/fastembed` por `/home/app/.cache/fastembed`; (4) `cap_drop: [ALL]` e `read_only: true` com `tmpfs: /tmp` no compose.

### 2.13 ALTO — Token WS via query string — **RECOMENDAÇÃO**

`/ws/chat?token=…` deixa o JWT em logs do nginx/Cloudflare. Alternativa sem quebrar clientes: emitir um *ticket* de uso único (`POST /api/auth/ws-ticket`, 30 s de validade) e passá-lo na query; ou autenticar na primeira mensagem do socket.

### 2.14 MÉDIO — Token no `localStorage` + sem tratamento de 401 — **PARCIALMENTE CORRIGIDO**

- `frontend/src/api/client.ts`: `fetchJSON` lança `ApiError(status, detail)` e, em 401 de rota autenticada, dispara `nexuslocal:unauthorized`; `App.tsx` ouve o evento e faz `logout()` (antes, com o token expirado, a UI ficava "quebrada" silenciosamente com erros `HTTP 401` no console). O `message` continua `HTTP <status>` para não quebrar quem compara a string.
- **Recomendação:** cookie `HttpOnly; Secure; SameSite=Strict` para o JWT (exige ajuste do WS e CSRF token nas mutações) — mitiga roubo de token por XSS.

### 2.15 Outros pontos de segurança (MÉDIO/BAIXO) — **RECOMENDAÇÕES**

| Onde | Problema | Sugestão |
|---|---|---|
| `routers/projects.py::upload_project_file` (~L424) | lê 25 MB em RAM, sem whitelist de extensão, confia no MIME do cliente; nginx 25m → 413 em HTML | reutilizar `attachments/validators.py`, ler em *chunks* com limite, `error_page 413` JSON no nginx |
| `routers/attachments.py::upload_attachment` | lê o arquivo inteiro antes de checar tamanho | `await file.read(MAX+1)` em *stream* |
| `backend/main.py` CORS | `allow_methods/allow_headers="*"` com `allow_credentials=True` | listar métodos e headers usados |
| `database.py::init_db` (~L934) | promove automaticamente o usuário mais antigo a admin se não houver admin | exigir `ADMIN_USERNAME` explícito ou comando CLI |
| `routers/artifacts.py::create_artifact` (L151) | aceita `id`/`msg_id` do cliente sem checar dono da mensagem | gerar `id` no servidor; validar `msg_id` ∈ conversas do usuário |
| `routers/chat.py` (~L540) | `max_tokens`/`reasoning_effort` do cliente sem limites | `clamp(1, 32000)` e enum |
| `routers/tts.py` | texto sem limite de tamanho (custo/abuso) | `max_length=5000` |
| `memory.py:1579` | `hashlib.sha1` dispara alerta de scanner | `hashlib.sha1(..., usedforsecurity=False)` ou blake2b |
| `backend/reset_admin_pwd.py`, `frontend/_patch_*.cjs` | scripts operacionais soltos no repositório | mover para `scripts/` ou remover |

---

## 3. Bugs

| # | Severidade | Onde | Bug | Status |
|---|---|---|---|---|
| B1 | MÉDIO | `routers/memory.py` (~L588–613) | `re.` usado sem `import re` → `NameError` engolido por `except Exception` → **o merge de perfil nunca rodava** | **Corrigido** (`import re`) |
| B2 | MÉDIO | `routers/memory.py::_error_sse` | montava JSON por f-string (aspas na mensagem quebravam o evento SSE) | **Corrigido** (`json.dumps`) |
| B3 | MÉDIO | `routers/web_search.py::WebSearchConfigUpdate` | Pydantic v2: `Optional[int]` **sem default é obrigatório**; o painel precisava mandar todos os campos e `null` sobrescrevia valores | **Corrigido** (`= None`, limites em `max_results`/`injection_template`) |
| B4 | MÉDIO | `backend/Dockerfile` | `--proxy-headers` sem `--forwarded-allow-ips` → IP/esquema do cliente ignorados | **Corrigido** |
| B5 | MÉDIO | `backend/tests/` | sem `conftest.py`: `pytest` criava/escrevia `backend/nexuslocal.db` **real** (viola AGENTS.md) | **Corrigido** (`conftest.py` + `DB_PATH` por env em `database.py`) |
| B6 | MÉDIO | `tests/test_image_gen.py` | assert de URL fixa de anexo | **Atualizado** para validar assinatura |
| B7 | MÉDIO | `database.py::check_and_deactivate_model` (~L3049) | erro vindo da chave **pessoal** de um usuário desativa o modelo **globalmente** para todos | Recomendação: contar por `(model_id, user_id)` e exigir N erros em janela |
| B8 | MÉDIO | `orchestration/resolve_request.py` TTFT timeout | gerador do provedor ficava aberto até o GC | **Corrigido** (`aclose()` explícito) |
| B9 | MÉDIO | `main.py::startup` | `asyncio.create_task` sem guardar referência (jobs de fundo podem ser coletados pelo GC — comportamento documentado do asyncio) | **Corrigido** (`app.state.background_tasks`) |
| B10 | BAIXO | `providers/base.py` Gemini nativo | chave de API na **query string** (`?key=`) → aparece em logs/URLs de erro | **Corrigido** (`x-goog-api-key`) |
| B11 | BAIXO | `routers/admin.py` | `except Exception → 500 str(e)` engole `HTTPException` (403/404 viram 500) em 5 handlers; import duplicado de `ModelFetcher` | Import duplicado removido; recomendação: `except HTTPException: raise` |
| B12 | BAIXO | `main.py` | `@app.on_event` (deprecado → `lifespan`), `datetime.utcnow()` (deprecado) | Recomendação |
| B13 | BAIXO | `routers/chat.py` | `search_failed` atribuído e nunca usado; `resolve_and_execute_search` importado sem uso; `except: pass` amplos | Recomendação (ruff aponta 105 imports não usados e 18 `raise ... from` faltando no projeto) |
| B14 | BAIXO | `backend/data/test_scorer.py` | script solto que quebra a coleta do pytest quando rodado de `backend/` | Recomendação: renomear/mover |

---

## 4. Otimização e desempenho

### 4.1 Poda do histórico (ALTO) — **CORRIGIDO**

- **Antes:** `handle_attachments.py::load_history` enviava **todas** as mensagens da conversa a cada turno; só o contexto de projetos tinha orçamento (`compute_safe_input_tokens`). Conversas longas estouravam o `context_length` (HTTP 400/413, principalmente Groq com TPM ~8k) e o custo/latência cresciam linearmente.
- **Agora:** `trim_history_to_budget()` + `resolve_input_budget()` (mesmo módulo), aplicados em `chat.py` logo antes de prefixar o `system`. Orçamento = `compute_safe_input_tokens(context_length, known_tpm, provider)` com teto `HISTORY_INPUT_TOKEN_CAP` (padrão 32 000; Groq continua limitado a 7 500 pela regra existente) **menos** os tokens do system prompt (memória + projeto). Remove sempre as mensagens mais antigas; **nunca** descarta a última mensagem do usuário; não deixa o histórico começar com uma resposta órfã do assistente (Anthropic/Gemini rejeitam). Imagens inline contam como custo fixo (~1 000 tokens) em vez de `len(base64)/4`, que podaria a conversa inteira. Falha na poda nunca bloqueia o turno (fallback: envia completo).
- **Melhoria futura:** resumo rolante das mensagens podadas (1 chamada barata a cada N turnos) para preservar fatos antigos.

### 4.2 Pool HTTP compartilhado (MÉDIO) — **CORRIGIDO**

`providers/base.py` criava um `httpx.AsyncClient` novo em cada chamada (7 pontos): handshake TCP+TLS a cada turno (~100–300 ms + CPU). Agora `get_http_client()` mantém um cliente por event loop (`max_connections=64`, keep-alive 60 s), fechado no `shutdown`. `_pooled_client()` preserva a forma `async with … as client:` dos trechos existentes.

### 4.3 Cache de assets estáticos (MÉDIO) — **CORRIGIDO** (ver §2.11)

### 4.4 Recomendações restantes

| Onde | Problema | Sugestão |
|---|---|---|
| `database.py::get_db` / `cache/manager.py::_db` | nova conexão SQLite (e thread do aiosqlite) por request, `PRAGMA` ×3 + `commit` a cada abertura | pool pequeno (`asyncio.Queue` com 4–8 conexões) ou pelo menos remover o `commit()` após PRAGMAs; `PRAGMA journal_mode=WAL` uma vez no boot |
| `routers/conversations.py::list_conversations` | `COUNT(m.id)` via `LEFT JOIN` + `GROUP BY` em toda listagem; `LIKE` sem escape de `%`/`_`; `page`/`limit` sem limites | subquery correlacionada ou coluna `message_count` mantida por trigger; `escape_like()`; `limit ≤ 200` |
| `auth.py::_current_role` | 1 query por request (cache 60 s mitiga) | OK para o porte atual; medir antes de otimizar |
| `frontend` bundle | `index-*.js` com 1,5 MB (408 kB gzip) | `React.lazy` para `AdminPanel`, `ProjectsPanel`, `UserMemoryPanel`; `manualChunks` para `react-markdown`/`highlight.js` |
| `memory.py` / `memory_dream.py` | jobs periódicos abrem conexão por iteração | reutilizar conexão por ciclo |
| `providers/base.py` | `content.replace("'", '"')` como heurística de JSON; corpo bruto do provedor exibido ao usuário | `json.loads` tolerante + mensagem sanitizada |

---

## 5. Melhorias gerais e manutenibilidade

- **Dependências** (`backend/requirements.txt`): `loguru`, `numpy`, `lxml` são importados diretamente mas só vinham como dependências transitivas → agora pinados. `pytest`/`pytest-asyncio` continuam em runtime (recomendo `requirements-dev.txt`). `requirements.txt` da raiz está divergente do `backend/` — manter um só. `bcrypt==4.0.1` é um pin antigo imposto pelo `passlib` 1.7.4 (sem manutenção): considere trocar `passlib` por `bcrypt` direto.
- **Variáveis novas** documentadas em `.env.example`: `ATTACHMENTS_SIGNING_SECRET`, `ATTACHMENTS_URL_TTL_SECONDS`, `HISTORY_INPUT_TOKEN_CAP`, `DB_PATH`, além de `WEB_SEARCH_ALLOW_PRIVATE_HTTP`.
- **i18n:** adicionada `auth.tooManyAttempts` em pt-BR, en-US, es-ES, es-419, de-DE, fr-FR, ja, ko.
- **Higiene (ruff/bandit):** 105 imports não usados, 18 `B904`, imports duplicados de `datetime` dentro de funções em `database.py` (L2115/2391/2747). Os 2 avisos `B608` (SQL por f-string) foram verificados: as colunas vêm de *allowlists* internas e os valores vão por parâmetros — **seguros**.
- **Observabilidade:** o `RequestContext` ganhou `history_trimmed` (memo) — vale expor nas métricas de fase junto com `llm_ttfb`.

---

## 6. Testes

- Rodar sempre da raiz do repositório (o pacote é `backend.*`):
  ```bash
  cd /caminho/nexus-local && .venv/bin/python -m pytest backend/tests -q
  ```
  O novo `backend/tests/conftest.py` aponta `DB_PATH` para um diretório temporário e define `JWT_SECRET` — **o banco real nunca é tocado**.
- Resultado nesta branch: **142 passaram**, 9 falhas e 4 erros **pré-existentes** (idênticos ao baseline: 124 ✓ / 9 ✗ / 4 erros antes das mudanças): `test_hybrid_search`/`test_memory_scaling` criam um schema parcial sem `user_memory`; `test_jev_fast_standalone` exige `fastembed` instalado; `test_smart_router` passa isolado (poluição de ordem entre testes). Recomendo migrá-los para usar `init_db()` no DB temporário do conftest.
- Novos: `backend/tests/test_security_hardening.py` (18 casos: assinatura/expiração/traversal de anexos, rota pública, rate limit, poda de histórico, estimativa multimodal, anti-SSRF, dono de conversa, anti-sequestro de anexo).

---

## 7. Pontos positivos (vale manter)

- Escopo por `user_id` em conversas, artefatos, projetos, cache semântico e `get_provider` (chaves estritamente por usuário).
- Nenhuma concatenação de valores em SQL; `basename` + whitelist + limite em uploads; `api_key` mascarada nas respostas; registro público fechado; mensagem de login uniforme.
- Cascata de failover com timeout de TTFT, *coalescing* de tokens e orçamento de contexto para RAG de projetos e trechos de documentos (`select_document_excerpt`).
- Frontend: `react-markdown` sem `rehype-raw`, highlighter escapando HTML, iframes `sandbox="allow-scripts"` sem `allow-same-origin`, `sw.js` sem cache, `ui_blocks/validate.py` já tinha guarda de IP privado (reutilizada como referência).
- Infra: backend não publicado no host, `init: true`, `env_file` em vez de `environment` interpolado (comentário no compose explica o porquê).

---

## 8. Como implantar esta branch

1. **Variáveis (opcional):** adicione ao `.env` `ATTACHMENTS_SIGNING_SECRET=<32+ chars>` (se omitido, deriva do `JWT_SECRET`). Confira que `JWT_SECRET` tem ≥ 32 caracteres.
2. **Rebuild dos dois serviços** (o nginx ganhou um snippet novo e o backend uma flag de CMD):
   ```bash
   docker compose build backend frontend && docker compose up -d
   ```
3. A migração `attachments.user_id` roda sozinha no boot (`init_db`) e faz o *backfill*. Nenhuma ação manual.
4. Efeitos visíveis: links de anexos passam a ter `?exp=&sig=` (links antigos copiados deixam de funcionar — a UI gera novos); após 5 senhas erradas o login bloqueia por 15 min; usuários comuns não veem mais a seção "modelo do extrator"; conversas muito longas passam a enviar só as mensagens mais recentes que cabem no modelo (log `Histórico podado…` informa quantas).
5. Ordem sugerida para o que ficou como recomendação: (a) cifrar chaves de API; (b) PyJWT + expiração menor; (c) validar `base_url`; (d) container não-root (roteiro em §2.12); (e) `conftest`-izar os testes antigos; (f) pool de conexões SQLite; (g) code-splitting do bundle.
