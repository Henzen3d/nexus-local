# Plano de Implementação — Context Window Registry
**NexusLocal** · Documento técnico de planejamento

---

## Fase 0 — Correção do Bug Imediato (Pré-requisito)

**Problema:** O schema tem `context_length INTEGER DEFAULT 8192`. Modelos já no banco com valor errado não são corrigidos pelo seed porque usamos `INSERT OR IGNORE`.

**Arquivos afetados:** `backend/database.py`

**O que fazer:**
Trocar a lógica de seed de `INSERT OR IGNORE` para um upsert que **atualiza** `context_length` se o valor atual for exatamente 8192 (o default) — preservando valores que o usuário editou manualmente via admin. A query ficaria:

```sql
INSERT INTO models (id, provider_id, name, display_name, context_length)
VALUES (?, ?, ?, ?, ?)
ON CONFLICT(id) DO UPDATE SET
  context_length = excluded.context_length
  WHERE context_length = 8192  -- só sobrescreve se ainda for o default
```

Isso resolve o banco existente na primeira inicialização após a atualização, sem apagar customizações do usuário.

---

## Fase 1 — Registry Estático (JSON curado)

**Complexidade:** Baixa
**Tempo estimado:** 1–2h
**Risco:** Sem risco
**Dependências novas:** Nenhuma

### Estrutura do arquivo

Criar `backend/data/context_registry.json` com três seções:

```json
{
  "version": "2025-06",
  "note": "Atualizar manualmente conforme documentação dos providers",
  "models": {
    "<nome-exato-do-modelo-na-api>": {
      "context_length": 131072,
      "provider": "groq",
      "source": "https://console.groq.com/docs/models",
      "verified_at": "2025-06"
    }
  }
}
```

A chave é o **nome exato como enviado na chamada de API** (ex: `"llama-3.3-70b-versatile"`, não o display name). Isso é o que já está no campo `models.name` no banco.

### Modelos a mapear no primeiro JSON

#### Groq
| Modelo (nome na API) | Context Length |
|---|---|
| `llama-3.3-70b-versatile` | 131072 |
| `llama-3.1-8b-instant` | 131072 |
| `gemma2-9b-it` | 8192 |
| `mixtral-8x7b-32768` | 32768 |

#### OpenRouter (modelos `:free`)
| Modelo (nome na API) | Context Length |
|---|---|
| `meta-llama/llama-3.3-70b-instruct:free` | 131072 |
| `qwen/qwen-2.5-72b-instruct:free` | 32768 |
| `deepseek/deepseek-r1:free` | 65536 |
| `google/gemma-3-27b-it:free` | 131072 |
| `mistralai/mistral-7b-instruct:free` | 32768 |

#### Google Gemini
| Modelo (nome na API) | Context Length |
|---|---|
| `gemini-2.0-flash` | 1048576 |
| `gemini-1.5-flash` | 1048576 |
| `gemini-2.0-flash-lite` | 1048576 |

#### Cerebras
| Modelo (nome na API) | Context Length |
|---|---|
| `llama-3.3-70b` | 131072 |
| `llama3.1-8b` | 131072 |

#### NVIDIA NIM
| Modelo (nome na API) | Context Length |
|---|---|
| `meta/llama-3.1-405b-instruct` | 131072 |
| `nv-mistralai/mistral-nemo-12b-instruct` | 128000 |
| `nvidia/llama-3.1-nemotron-70b-instruct` | 131072 |

#### SambaNova
| Modelo (nome na API) | Context Length |
|---|---|
| `Meta-Llama-3.3-70B-Instruct` | 131072 |
| `Meta-Llama-3.2-1B-Instruct` | 16384 |

#### Cloudflare Workers AI
| Modelo (nome na API) | Context Length |
|---|---|
| `@cf/deepseek-ai/deepseek-r1-distill-qwen-32b` | 131072 |
| `@cf/google/gemma-3-12b-it` | 131072 |
| `@cf/google/gemma-4-26b-it` | 131072 |
| `@cf/thudm/glm-4-32b-instruct` | 32768 |
| `@cf/qwen/qwen2.5-coder-32b-instruct` | 32768 |

### Lógica de aplicação

Em `backend/database.py`, no `init_db()`, **antes** de fazer o seed:

1. Carregar o JSON
2. Para cada modelo já no banco, verificar se o nome existe no registry
3. Se existir e o valor atual for 8192 (default), atualizar para o valor do registry
4. No seed de novos modelos, usar o valor do registry se disponível, senão 8192

### Versionamento

Adicionar um campo `"version"` no JSON e uma tabela `meta` no banco com `registry_version`. A cada init, comparar: se a versão do arquivo for mais nova que a do banco, re-aplicar o registry. Isso permite que atualizações futuras do arquivo se propaguem automaticamente.

---

## Fase 2 — Fetch Automático das APIs

**Complexidade:** Média
**Tempo estimado:** 4–6h
**Risco:** Baixo (roda em background, não bloqueia nada)
**Dependências novas:** Nenhuma (já usa `httpx`)

### Novo arquivo: `backend/providers/model_fetcher.py`

Uma classe `ModelFetcher` com um método por provider. Cada método retorna uma lista de `{"model_name": str, "context_length": int}`.

#### Groq
```
Endpoint: GET https://api.groq.com/openai/v1/models
Resposta:  { "data": [{ "id": "llama-3.3-70b-versatile", "context_window": 131072 }] }
Campo:     data[].context_window
```

#### OpenRouter
```
Endpoint: GET https://openrouter.ai/api/v1/models
Resposta:  { "data": [{ "id": "...", "context_length": 131072 }] }
Campo:     data[].context_length
Filtro:    só pegar modelos que terminam em ":free"
```

#### Google Gemini
```
Endpoint: GET https://generativelanguage.googleapis.com/v1beta/models?key={API_KEY}
Resposta:  { "models": [{ "name": "models/gemini-2.0-flash", "inputTokenLimit": 1048576 }] }
Campo:     models[].inputTokenLimit
Normalização: remover prefixo "models/" do nome
```

#### Cerebras
```
Endpoint: GET https://api.cerebras.ai/v1/models
Formato:  OpenAI-compat → data[].context_length
```

#### NVIDIA NIM
```
Sem endpoint de listagem público.
→ Usa o registry estático como fallback permanente.
```

#### SambaNova
```
Verificar na documentação (pode ter endpoint OpenAI-compat).
→ Fallback para registry estático se não disponível.
```

#### Cloudflare Workers AI
```
Endpoint: GET https://api.cloudflare.com/client/v4/accounts/{account_id}/ai/models/search
Resposta:  { "result": [{ "name": "@cf/...", "properties": [{ "property_id": "max_total_tokens", "value": "131072" }] }] }
Nota:      Requer account_id além da API key — diferença importante dos outros providers.
```

### Novo endpoint no admin router

`POST /api/admin/providers/{provider_id}/sync-models`

Comportamento:
1. Verifica se o provider tem chave configurada
2. Chama o fetcher correspondente
3. Atualiza `context_length` de todos os modelos do provider cujo valor atual é 8192 ou cujo valor mudou
4. Retorna um relatório: `{ "updated": 3, "skipped": 1, "errors": [] }`
5. **Não deleta modelos** — só atualiza contexto dos existentes (seguro)

### Job de sincronização automática

Em `backend/main.py`, no evento `startup`:

```
Para cada provider com chave configurada:
  Verificar timestamp da última sync (tabela meta: "last_sync_{provider_id}")
  Se nunca sincronizou OU se faz mais de 24h:
    Agendar fetch em background (asyncio.create_task)
    Não bloquear o startup
```

O fetch roda **em background** e silenciosamente. Se falhar, loga o erro mas não impede nada.

### Tabela nova no banco

```sql
CREATE TABLE IF NOT EXISTS sync_log (
  id              TEXT PRIMARY KEY,
  provider_id     TEXT NOT NULL,
  synced_at       TEXT DEFAULT (datetime('now')),
  models_updated  INTEGER DEFAULT 0,
  status          TEXT DEFAULT 'ok',  -- 'ok' | 'error'
  error_msg       TEXT
);
```

Isso permite mostrar no admin "Última sync: 3h atrás — 2 modelos atualizados".

### Botão manual no Admin Panel

Em cada card de provider, um botão **↻ Sincronizar modelos** que chama o endpoint e mostra o relatório. Útil para forçar uma sync sem reiniciar o backend.

---

## Fase 3 — Híbrido Inteligente

**Complexidade:** Baixa (é composição das fases 1 e 2)
**Tempo estimado:** 2h (após as fases 1 e 2 estarem prontas)
**Risco:** Mínimo

### Lógica de prioridade (cascata)

```
Para cada modelo, o context_length final é determinado por:

1. Valor editado manualmente pelo usuário via Admin Panel
   (detectado por: existe registro em "model_overrides")
   → NUNCA sobrescrever, qualquer que seja a fonte

2. Valor do fetch automático (Fase 2)
   → Sobrescreve se não for override manual
   → É a fonte mais confiável quando disponível

3. Valor do registry estático JSON (Fase 1)
   → Usado quando o fetch não está disponível
     (sem chave, provider sem endpoint, erro de rede)

4. Default 8192
   → Último recurso, só para modelos completamente desconhecidos
```

### Nova tabela: `model_overrides`

```sql
CREATE TABLE IF NOT EXISTS model_overrides (
  model_id        TEXT PRIMARY KEY,
  context_length  INTEGER NOT NULL,
  set_at          TEXT DEFAULT (datetime('now'))
);
```

Quando o usuário edita `context_length` pelo admin, salvar também nessa tabela. O job de sync verifica essa tabela antes de atualizar e pula os modelos que estão lá.

### Indicador de fonte no Admin Panel

Cada badge de contexto mostraria de onde veio o valor:

| Cor | Fonte | Significado |
|---|---|---|
| 🔵 Azul | Fetch automático | Valor direto da API do provider, mais confiável |
| 🟡 Amarelo | Registry estático | Valor curado manualmente no JSON |
| 🟣 Roxo | Override do usuário | Editado manualmente no admin, nunca sobrescrito |
| 🔴 Vermelho | Default 8192 | Modelo desconhecido, requer atenção |

### Lógica de startup completa (Fase 3)

```
init_db()
  → Aplicar schema
  → Seed de providers/modelos com INSERT OR IGNORE
  → Aplicar registry estático nos modelos ainda em 8192   [Fase 1]
  → Para cada provider com chave configurada:
      → Se fetcher disponível para esse provider:
          → asyncio.create_task(fetch_and_update(provider_id))  [Fase 2]
      → Senão: manter valor do registry
```

---

## Resumo Executivo

| | Fase 0 | Fase 1 | Fase 2 | Fase 3 |
|---|---|---|---|---|
| **O que resolve** | Bug imediato | Todos os modelos conhecidos | Sync automática | Combinação inteligente |
| **Arquivos novos** | 0 | 1 (JSON) | 2 (fetcher + sync_log) | 1 (tabela overrides) |
| **Arquivos modificados** | 1 | 1 | 3 | 2 |
| **Tempo estimado** | 30min | 1–2h | 4–6h | 2h |
| **Dependências novas** | Nenhuma | Nenhuma | Nenhuma | Nenhuma |
| **Risco** | Zero | Zero | Baixo | Baixo |

**Sequência recomendada:** 0 → 1 → 2 → 3

Cada fase é independente e já entrega valor por si. A Fase 3 é basicamente unir o que as fases 1 e 2 construíram com uma camada de prioridade, então o trabalho pesado já está feito antes dela.