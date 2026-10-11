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
| `backend/database.py` | migração incremental das tabelas abaixo, no estilo `try/except sqlite3.OperationalError` de `supports_vision`. Índice só depois do `ALTER`/`CREATE` da migração, nunca no `SCHEMA` inicial para coluna nova |
| `backend/providers/base.py` | `CloudflareProvider.run_image(...)` |
| `backend/main.py` | include do router; start/stop do worker no lifespan |
| `backend/routers/chat.py` | registrar o socket aberto por `user_id`; no turno, chamar o classificador |
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
   - criar `message_id` do assistente já com texto curto ("Gerando imagem…") e `image_gen_tasks` em `pending`
   - emitir no socket atual `{"type":"image_pending","task_id","msg_id","conv_id","prompt"}`
   - se o pedido foi slash puro, encerrar o turno aqui
   - senão, acrescentar ao system prompt desta chamada apenas: "O usuário pediu uma imagem raster. Não escreva SVG, não escreva código de imagem, não descreva tags. Uma imagem será anexada em separado."
2. No fim do turno, `detect_and_save_artifacts` recebe a flag e descarta detecção `svg`.

O hint não entra no system prompt permanente. Só naquela chamada. Não muda o prefixo cacheado das outras conversas além do necessário desta requisição. Aceitável: é o mesmo tipo de injeção que web search já faz por turno.

## Worker

Sobe no lifespan de `backend/main.py`. Para no shutdown.

Loop:

1. `recover`: tasks em `generating` com `started_at` mais velho que 3 minutos voltam para `pending`. Cobre kill do processo.
2. Claim atômico de uma `pending`:

```sql
UPDATE image_gen_tasks
   SET status = 'generating', started_at = datetime('now')
 WHERE id = (
   SELECT id FROM image_gen_tasks
    WHERE status = 'pending'
    ORDER BY created_at
    LIMIT 1
 )
 AND status = 'pending';
```

SQLite serializa o write. Uma instância do backend. Não precisa de Redis.

3. Contar tasks `ready` do `user_id` desde 00:00 UTC. Se `>= daily_cap_per_user`, falhar com mensagem de teto, sem chamar a API.
4. Token e account id do `user_id`. Sem par → fail claro. Não usar `CLOUDFLARE_ACCOUNT_ID` do ambiente nem token de outro usuário. `run_image` recebe o account id desse usuário; `_run_url` hoje lê o `base_url` compartilhado, então a chamada de imagem monta a URL com o account id do usuário, não com o do seed.
5. `run_image`. Timeout 60s. 429 → `RateLimitError` já existe; marcar failed com "cota Cloudflare cheia, tenta depois do reset 00:00 UTC". Não fazer retry em loop.
6. Bytes JPEG → `save_file()` em `backend/attachments/storage.py` (`save_file(file_content, filename, attachment_id, is_image=True)`). Inserir linha em `attachments` com `message_id` do placeholder.
7. Status `ready`. Avisar sockets.

Falha: status `failed`, `error_message` curta, mesmo evento WS com `status: "failed"`. O placeholder troca o spinner pelo erro. Sem stack trace para o usuário.

Paralelismo: 1. Não subir para 4 porque a doc do Hermes usa 4. Aqui a cota é compartilhada pelo account id da Cloudflare daquele usuário.

## Entrega no socket que já existe

`chat.py` guarda `dict[user_id, set[WebSocket]]` enquanto a conexão vive. Tira no `finally`.

Evento, mesmo estilo do `artifact` que o frontend já entende:

```json
{
  "type": "image_ready",
  "task_id": "...",
  "msg_id": "...",
  "conv_id": "...",
  "status": "ready",
  "attachment_id": "...",
  "url": "/api/attachments/..."
}
```

`status: "failed"` no mesmo tipo, com `error`.

Se não houver socket, não é erro. A mensagem e o attachment já foram gravados. `GET` da conversa tem que devolver o attachment como qualquer imagem enviada pelo usuário hoje. Reusar a rota de attachment existente. Não inventar `/attachments/{filename}` solto.

## `run_image`

Não passar pelo `stream_chat`.

```python
async def run_image(self, model: str, prompt: str, steps: int = 4) -> bytes:
    # POST self._run_url(model)
    # body: {"prompt": prompt[:2048], "steps": min(steps, 8)}
    # header Authorization: Bearer {self.api_key}
    # timeout 60s
    # extrair base64 do envelope confirmado no spike
    # devolver bytes JPEG
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
