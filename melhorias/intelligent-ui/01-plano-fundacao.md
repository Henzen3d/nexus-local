# Fundação do Intelligent UI — plano

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Validar e guardar blocos `nexus-ui/1` sem pintar nada e sem mudar o chat quando a flag está desligada.

**Architecture:** O modelo pode anexar um fence. O backend tira o fence da prosa, valida o JSON e grava o envelope numa tabela separada. O frontend recebe o envelope no `stream_end` e na releitura, valida de novo e, nesta fase, não renderiza.

**Tech Stack:** FastAPI, SQLite via aiosqlite, React 18, TypeScript. Testes de frontend: `node --experimental-strip-types --test src/lib/*.test.ts` a partir de `frontend/`. Testes de backend: pytest em `backend/tests/`.

**Spec:** `melhorias/intelligent-ui/00-visao-e-spec.md`

## Global Constraints

- `INTELLIGENT_UI_ENABLED` ausente ou diferente de `true` significa desligado.
- Envelope `{"v":1,"blocks":[]}`, fence `nexus-ui`, máximo 4 blocos, máximo 16000 caracteres de JSON.
- `messages.content` nunca guarda o JSON.
- Sem HTML, sem `dangerouslySetInnerHTML`, sem Thesys, sem segunda lib de gráfico.
- Não reescrever `MessageBubble` nesta fase. No máximo um gancho que retorna null se não houver renderer.
- Payload não vai para telemetria.
- Prosa tem de bastar sozinha. Esta fase não injeta o catálogo ainda. Injeção é tarefa da fase 2, com a flag.

---

### Task 1: Validador Python

**Files:**
- Create: `backend/ui_blocks/__init__.py`
- Create: `backend/ui_blocks/validate.py`
- Test: `backend/tests/test_ui_blocks.py`

**Interfaces:**
- Consumes: nada
- Produces: `validate_envelope(raw: str) -> dict | None`. Retorna `{"v": 1, "blocks": [...]}` só com blocos válidos, ou `None` se o envelope inteiro for inválido (`v` errado, JSON inválido, tamanho acima de 16000, `blocks` ausente). Bloco inválido some da lista. Lista vazia depois do filtro retorna `None`.

- [ ] **Step 1: Escrever o teste que falha**

```python
from ui_blocks.validate import validate_envelope

def test_rejeita_versao_errada():
    assert validate_envelope('{"v":2,"blocks":[]}') is None

def test_progress_valido():
    raw = '{"v":1,"blocks":[{"id":"seo","type":"progress","label":"Auditoria SEO","value":7,"max":10}]}'
    out = validate_envelope(raw)
    assert out["blocks"][0]["value"] == 7

def test_bloco_ruim_nao_derruba_o_bom():
    raw = '{"v":1,"blocks":[{"id":"ok","type":"progress","label":"A","value":1,"max":2},{"id":"ruim","type":"chart","kind":"pizza"}]}'
    out = validate_envelope(raw)
    assert [b["id"] for b in out["blocks"]] == ["ok"]
```

- [ ] **Step 2: Rodar e ver falhar**

Run: `cd /home/osmar/nexuslocal/backend && python -m pytest tests/test_ui_blocks.py -q`
Expected: FAIL, módulo ausente.

- [ ] **Step 3: Implementar `validate_envelope` com as regras da spec, seções 4 e 6.** Incluir progress, card, chart e controls nesta função, mesmo que a UI ainda não pinte. URL de imagem segue a seção 6: relativa do app, host da lista, ou IP privado só com flag. `https` solto não passa. Ação fora de `send_message` e `set_model` descarta o bloco.

- [ ] **Step 4: Rodar e ver passar**

Run: `cd /home/osmar/nexuslocal/backend && python -m pytest tests/test_ui_blocks.py -q`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add backend/ui_blocks backend/tests/test_ui_blocks.py
git commit -m "feat: validar envelope nexus-ui/1 sem renderizar"
```

### Task 2: Extrator do fence

**Files:**
- Create: `backend/ui_blocks/extract.py`
- Test: `backend/tests/test_ui_blocks.py`

**Interfaces:**
- Consumes: `validate_envelope`
- Produces: `extract_ui(text: str) -> tuple[str, dict | None]`. Devolve prosa sem fence e envelope validado, ou prosa original e `None`.

- [ ] **Step 1: Teste**

```python
from ui_blocks.extract import extract_ui

def test_tira_fence_e_deixa_prosa():
    text = "Sete de dez já foram.\n\n```nexus-ui\n{\"v\":1,\"blocks\":[{\"id\":\"seo\",\"type\":\"progress\",\"label\":\"Auditoria SEO\",\"value\":7,\"max\":10}]}\n```"
    prose, env = extract_ui(text)
    assert "Sete de dez" in prose
    assert "nexus-ui" not in prose
    assert env["blocks"][0]["id"] == "seo"

def test_fence_aberto_nao_grava_json():
    prose, env = extract_ui("texto\n```nexus-ui\n{\"v\":1")
    assert env is None
    assert "nexus-ui" not in prose
```

Fence aberto: remover o pedaço aberto da prosa visível e não devolver envelope. O usuário não vê JSON pela metade.

- [ ] **Step 2: Rodar, ver falhar, implementar, ver passar.** Mesmo comando de pytest.

- [ ] **Step 3: Commit** `feat: extrair fence nexus-ui da prosa`

### Task 3: Tabela

**Files:**
- Modify: `backend/database.py` dentro de `init_db`, no padrão try/select já usado para colunas de `messages` (por volta da linha 733).

**Interfaces:**
- Produces: tabela `message_ui_blocks` como na spec, seção 5.

- [ ] **Step 1: Teste que abre o db de teste, chama `init_db` e faz `SELECT payload, source FROM message_ui_blocks LIMIT 1`.** Esperado antes do código: `OperationalError`.

- [ ] **Step 2: Criar a tabela se o select falhar.** `CREATE TABLE IF NOT EXISTS` da spec. Não adicionar coluna em `messages`.

- [ ] **Step 3: Commit** `feat: tabela message_ui_blocks`

### Task 4: Flag e gancho no chat, ainda sem pintar

**Files:**
- Modify: `backend/routers/chat.py`
- Modify: `backend/orchestration/persist_turn.py`
- Modify: `.env.example` com `INTELLIGENT_UI_ENABLED=false`, `INTELLIGENT_UI_IMAGE_HOSTS=` vazio e `INTELLIGENT_UI_ALLOW_PRIVATE_HTTP=false`.
- Modify: `frontend/src/types.ts`

**Interfaces:**
- Consumes: `extract_ui`
- Produces: se a flag estiver true, `stream_end.ui_blocks` carrega o envelope ou null. Se false, o campo não é enviado e o fence, se aparecer, permanece no texto como hoje (não extrair com a flag off, para não mudar comportamento).

- [ ] **Step 1: Teste da flag off.** Resposta com fence é persistida intacta. Sem linha em `message_ui_blocks`.

- [ ] **Step 2: Teste da flag on.** `content` gravado sem fence. Linha na tabela com `source='model'`. `stream_end` inclui `ui_blocks`.

- [ ] **Step 3: Implementar o mínimo.** Ler a flag uma vez por turno. Não injetar catálogo nesta task.

- [ ] **Step 4: Acrescentar o tipo em `WSMessage` e em `Message`, sem usar na bolha.**

- [ ] **Step 5: Commit** `feat: persistir ui_blocks atrás de flag desligada`

### Task 5: Validador TypeScript espelhado

**Files:**
- Create: `frontend/src/lib/nexusUi.ts`
- Create: `frontend/src/lib/nexusUi.test.ts`

**Interfaces:**
- Produces: `parseUiEnvelope(raw: unknown): UiEnvelope | null` com as mesmas rejeições do Python. Nomes de campo iguais: `v`, `blocks`, `x_key`, `submit_label`, `send_message`, `set_model`.

- [ ] **Step 1: Portar os três casos da Task 1 para o teste TS.**

- [ ] **Step 2: Rodar**

Run: `cd /home/osmar/nexuslocal/frontend && node --experimental-strip-types --test src/lib/nexusUi.test.ts`
Expected: PASS

- [ ] **Step 3: Commit** `feat: espelhar validador nexus-ui no frontend`

Não renderizar. `MessageBubble` não muda nesta fase.
