# 02 — Arquitetura de backend

Espelha o Vision Relay e o turno de chat que já existem. Não introduz Redis, fila externa nem segundo WebSocket.

## Módulos novos

```
backend/image_gen/
  intent.py          # função pura. raster | vector | none
  config.py          # lê image_gen_config
  queue.py           # insert, claim, complete, fail, recover
  worker.py          # loop no lifespan
  cloudflare_image.py  # só o POST de imagem; reusa CloudflareProvider._run_url
backend/routers/image_gen.py   # GET/POST config, GET task (admin e o próprio usuário)
```

Toques em código existente, e só estes:

| Arquivo | Mudança |
|---|---|
| `backend/database.py` | migração incremental em `init_db()`: `image_models`, `image_gen_config`, `image_gen_tasks` e `ALTER TABLE user_api_keys ADD COLUMN account_id TEXT;` (no estilo `try/except sqlite3.OperationalError` de `supports_vision`). Índices só depois do `ALTER`/`CREATE` da migração |
| `backend/providers/base.py` | `CloudflareProvider.run_image(model, prompt, steps, account_id=...)` tratando Content-Type binário (`image/*`) e JSON |
| `backend/main.py` | include do router `image_gen`; start/stop do worker e do `asyncio.Event` no lifespan |
| `backend/routers/chat.py` | registrar sockets por `user_id`; classificar intent antes do stream; checagem precoce de teto diário; em `/imagem` puro emitir `stream_end` (destrava composer do frontend); disparar `task_notify_event.set()` |
| `backend/orchestration/persist_turn.py` | se o turno tem job de imagem, não persistir artefato `svg` |
| `backend/orchestration/resolve_request.py` | injetar o hint anti-SVG só quando `image_intent` e o chat model ainda for chamado |

Não mexer em `models`, `fusion_models`, ranking, nem no seed dos 1633 modelos.

## Tabelas

`image_models` é o "outro lugar". Não aparece no seletor de chat.

```sql
CREATE TABLE IF NOT EXISTS image_models (
    id            TEXT PRIMARY KEY,          -- ex.: cloudflare/flux-1-schnell
    provider_id   TEXT NOT NULL,             -- cloudflare
    name          TEXT NOT NULL,             -- @cf/black-forest-labs/flux-1-schnell
    display_name  TEXT NOT NULL,
    notes         TEXT,                      -- custo em neurons, em texto, para a UI
    enabled       INTEGER DEFAULT 1
);

CREATE TABLE IF NOT EXISTS image_gen_config (
    id                  INTEGER PRIMARY KEY DEFAULT 1,
    enabled             INTEGER DEFAULT 0,   -- nasce desligado
    auto_detect         INTEGER DEFAULT 1,
    provider_id         TEXT,                -- cloudflare
    model_id            TEXT,                -- id em image_models
    steps               INTEGER DEFAULT 4,   -- teto 8 no schnell
    width               INTEGER DEFAULT 1024,
    height              INTEGER DEFAULT 1024,
    daily_cap_per_user  INTEGER DEFAULT 20
);

CREATE TABLE IF NOT EXISTS image_gen_tasks (
    id               TEXT PRIMARY KEY,
    conversation_id  TEXT NOT NULL,
    user_id          TEXT NOT NULL,
    message_id       TEXT NOT NULL,          -- placeholder já visível no chat
    prompt           TEXT NOT NULL,
    status           TEXT NOT NULL,          -- pending | generating | ready | failed
    model_id         TEXT,
    error_message    TEXT,
    created_at       TEXT DEFAULT (datetime('now')),
    started_at       TEXT,
    completed_at     TEXT
);

-- Coluna nova na tabela existente de chaves (para Account ID da Cloudflare):
-- Executado em try/except sqlite3.OperationalError:
ALTER TABLE user_api_keys ADD COLUMN account_id TEXT;
```

Índices, depois da migração:

```sql
CREATE INDEX IF NOT EXISTS idx_image_tasks_status ON image_gen_tasks(status, created_at);
CREATE INDEX IF NOT EXISTS idx_image_tasks_user_day ON image_gen_tasks(user_id, created_at);
```

Seed de um modelo só, no mesmo bloco da migração:

- id `cloudflare/flux-1-schnell`
- name `@cf/black-forest-labs/flux-1-schnell`
- display `FLUX.1 Schnell (Cloudflare, cota diária grátis)`

Config nasce `enabled = 0`. Ligar é ato do admin, depois da chave existir. Igual ao espírito do Vision Relay, que também é opt-in de configuração.

Schnell na doc consultada não publica `width`/`height` no input, só `prompt` e `steps`. Guardar width/height na config, mas **não enviar** até a chamada de spike provar que a API aceita. Se ignorar, a imagem sai no default do modelo (o exemplo oficial não fixa tamanho). Não inventar parâmetro.

## Classificador

`classify_image_intent(text) -> "raster" | "vector" | "none"`.

Pura, sem LLM, sem rede. Teste unitário com a tabela de frases do `00`. Ordem:

1. Se bater na lista negativa (svg, vetor, diagrama, fluxograma, mermaid, gráfico, ícone, html, código) → `vector`. A lista negativa ganha do verbo "desenhe".
2. Se começar com `/imagem`, `/img` ou `/image` → `raster`. O resto da linha é o prompt. Esse caso não chama o modelo de chat.
3. Se casar verbo de criação + substantivo de imagem → `raster`. O prompt enviado à Cloudflare é a frase do usuário, cortada em 2048 caracteres. Não pedir a um LLM para reescrever o prompt na fase 1.
4. Senão → `none`.

## Turno de chat

Dentro de `_process_turn`, depois de autenticar e antes do stream:

1. Se `image_gen_config.enabled` e intent `raster`:
   - Checagem precoce de teto diário: `SELECT COUNT(*) FROM image_gen_tasks WHERE user_id = :u AND status != 'failed' AND created_at >= date('now', 'start of day')`. Se `>= daily_cap_per_user`, emitir erro imediato no WebSocket ("Limite diário atingido") e abortar a geração de imagem sem poluir o histórico com placeholders.
   - Criar `message_id` do assistente no banco já com texto curto inicial ("Gerando imagem…") e inserir linha em `image_gen_tasks` com `status = 'pending'`.
   - Despertar o worker imediatamente via `task_notify_event.set()` (zero latência de espera por polling).
   - Emitir no socket atual `{"type":"image_pending","task_id","msg_id","conv_id","prompt"}`.
   - **Se o pedido foi slash puro (`/imagem ...`):**
     - Despachar evento `stream_end` (com `finish_reason: "image_pending"` e `message_id`) no WebSocket para destrancar imediatamente o composer no frontend (`isStreaming = false`).
     - Encerrar o turno aqui, sem chamar nenhum modelo de chat LLM.
   - **Senão (pedido misto com texto):**
     - Acrescentar ao system prompt desta chamada apenas: *"O usuário pediu uma imagem raster. Não escreva SVG, não escreva código de imagem, não descreva tags. Uma imagem será anexada em separado."*
     - O turno de texto prossegue via streaming normal.
2. No fim do turno, `detect_and_save_artifacts` recebe a flag e descarta detecção `svg`.

O hint não entra no system prompt permanente. Só naquela chamada. Não muda o prefixo cacheado das outras conversas além do necessário desta requisição.

## Worker

Sobe no lifespan de `backend/main.py` gerenciado por task assíncrona. Para no shutdown.

Estrutura do loop (reativo via `asyncio.Event` + timeout para heartbeat de recuperação):

```python
task_notify_event = asyncio.Event()

async def image_worker_loop():
    while not shutdown_event.is_set():
        try:
            # Espera evento de nova task; timeout de 60s atua como heartbeat de recovery
            await asyncio.wait_for(task_notify_event.wait(), timeout=60.0)
        except asyncio.TimeoutError:
            pass
        task_notify_event.clear()

        # 1. Recover: tasks em 'generating' com started_at > 3 min voltam para 'pending'
        await queue.recover_stale_tasks(timeout_seconds=180)

        # 2. Processa tasks pending da fila uma a uma
        while (task := await queue.claim_next_task()):
            await process_image_task(task)
```

Processamento de cada task (`process_image_task`):
1. **Validação de chaves:** Buscar `api_key` e `account_id` em `user_api_keys` para o `user_id`. Se faltar token ou account_id → marcar `status = 'failed'` com erro amigável "Falta a chave ou Account ID da Cloudflare na sua conta", atualizar mensagem e notificar socket.
2. **Revalidação de teto:** Contar tasks com `status != 'failed'` criadas desde `00:00 UTC`. Se exceder o teto diário → marcar `failed` com mensagem de cota.
3. **Execução:** Chamar `CloudflareProvider.run_image(model, prompt, steps, account_id=account_id)` com timeout de 60s. Em caso de 429 (`RateLimitError`) → marcar `failed` com mensagem "Cota diária da Cloudflare atingida".
4. **Armazenamento:**
   - Salvar os bytes JPEG diretamente no diretório da conversa (`storage/attachments/{conversation_id}/{filename}`) via `save_file(..., conversation_id=conv_id, is_image=True)`.
   - Inserir linha na tabela `attachments` vinculada ao `message_id` do placeholder.
   - **Limpeza do placeholder:** Executar `UPDATE messages SET content = '' WHERE id = :message_id` (remove o texto provisório "Gerando imagem…" para que não persista após o reload da tela).
   - Atualizar a task: `status = 'ready'`, `completed_at = datetime('now')`.
5. **Tratamento de falha:** Se ocorrer erro, `UPDATE image_gen_tasks SET status = 'failed', error_message = :err`, e `UPDATE messages SET content = :err_display WHERE id = :message_id`.
6. **Notificação WebSocket:** Broadcast seguro para os sockets abertos do usuário (ver abaixo).

Paralelismo: 1 (evita saturar a cota da conta familiar e locks desnecessários).

## Entrega no socket que já existe

`chat.py` mantém um registro `dict[user_id, set[WebSocket]]`. Cada WebSocket é adicionado na conexão e descartado no `finally`.

Broadcast defensivo contra sockets fechados ou desconexões súbitas:
```python
async def notify_user_sockets(user_id: str, message: dict):
    sockets = list(user_sockets.get(user_id, set()))
    for ws in sockets:
        try:
            await ws.send_json(message)
        except Exception:
            user_sockets.get(user_id, set()).discard(ws)
```

Evento emitido:
```json
{
  "type": "image_ready",
  "task_id": "...",
  "msg_id": "...",
  "conv_id": "...",
  "status": "ready",
  "attachment_id": "...",
  "url": "/attachments/conv_id/filename.jpg"
}
```

> **Atenção à rota:** A URL do arquivo estático é `/attachments/{storage_path}`, e **NÃO** `/api/attachments/...` (que contém apenas endpoints de upload e exclusão). O frontend e o backend (`conversations.py`) servem anexos montados em `/attachments`.

Se não houver socket conectado no momento em que a imagem fica pronta, a entrega não falha: o anexo e a mensagem já estão gravados no SQLite. O próximo `GET /api/conversations/{id}` trará a mensagem com seu `attachments: [...]` normalmente.

## `run_image`

Não passa pelo `stream_chat`. Executa no `CloudflareProvider`:

```python
async def run_image(self, model: str, prompt: str, steps: int = 4, account_id: str | None = None) -> bytes:
    # URL: https://api.cloudflare.com/client/v4/accounts/{account_id}/ai/run/{model}
    # Headers: Authorization: Bearer {self.api_key}, Content-Type: application/json
    # Body: {"prompt": prompt[:2048], "steps": min(steps, 8)}
    # Resposta:
    #   - Se Content-Type contém 'image/' ou 'octet-stream': return resp.content
    #   - Se Content-Type for 'application/json': extrair base64 de resp.json()['result']['image']
    #   - Se status de erro HTTP: extrair mensagem amigável e levantar ProviderAPIError / RateLimitError
```

O parser do envelope fica isolado e testado com um fixture JSON gravado no spike. Sem o fixture, o teste não inventa o formato.

## Erros que a UI precisa distinguir

| Caso | Mensagem |
|---|---|
| Config desligada | não dispara; chat segue normal |
| Sem token do usuário | "Falta a chave Cloudflare na sua conta." |
| 429 / neurons | "Cota diária da Cloudflare acabou. Reseta 00:00 UTC." |
| Teto local 20 | "Limite de 20 imagens hoje." |
| Prompt vazio depois do slash | erro imediato, sem task |
| Timeout / 5xx | "A Cloudflare não devolveu a imagem." |

## Segurança

- Task só é lida pelo `user_id` dono. Admin vê a config, não a fila dos outros, na fase 1.
- Prompt vai para a Cloudflare. Avisar na UI de config, uma linha: a imagem é gerada na conta Cloudflare do usuário, não no servidor.
- Não logar o base64. Logar `task_id`, status, latency, provider error code.
- Testes só em banco temporário. `AGENTS.md` proíbe pytest no `nexuslocal.db` vivo.
