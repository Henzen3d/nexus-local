# 02 — Catálogo, payload e failover

**Multi+ / NexusLocal** · Plano, não implementação

## Onde encaixa

| Peça atual | Papel no plano |
| :--- | :--- |
| `backend/database.py` `init_db()` | `ALTER TABLE` incremental das 4 colunas em `models`, no mesmo padrão de `supports_vision` |
| `GET /admin/models` em `backend/routers/admin.py` | `list_all_models` inclui as 4 colunas e faz `json.loads` de `reasoning_levels` para o frontend receber array |
| `backend/models.py` `ModelUpdate` | Ganha campos opcionais de reasoning para permitir override manual |
| `PATCH /admin/models/{model_id}` em `backend/routers/admin.py` | Grava override e seta `reasoning_control_source = 'admin'` |
| `frontend/src/types.ts` `Model` | Ganhar os quatro campos novos (`reasoning_control`, `reasoning_levels`, `reasoning_default`, `reasoning_control_source`) |
| `backend/providers/base.py` `stream_chat` | `BaseProvider` e subclasses aceitam `reasoning_effort` e `reasoning_control` opcionais |
| `backend/routers/chat.py` | Ler `reasoning_effort` do payload do WebSocket e repassar a `resolve_and_stream` |
| `backend/orchestration/resolve_request.py` | Repassar; no failover ou auto, reavaliar o modelo reserva/escolhido; emitir `effort_dropped` |
| `backend/fusion/orchestrator.py` | v1 não repassa esforço |
| `backend/memory.py`, enhancer, dream | não repassam |

## Colunas novas em `models`

Somente via migração incremental. Não colocar no `CREATE TABLE` inicial de um banco já em produção sem o `ALTER`.

```sql
ALTER TABLE models ADD COLUMN reasoning_control TEXT DEFAULT 'none';
ALTER TABLE models ADD COLUMN reasoning_levels TEXT;          -- JSON array, null se none/always_on
ALTER TABLE models ADD COLUMN reasoning_default TEXT;         -- nível interno ou null
ALTER TABLE models ADD COLUMN reasoning_control_source TEXT DEFAULT 'unset';
-- unset | family | admin
```

`reasoning_control_source = admin` impede o seed de sobrescrever.

Índice: não criar no schema inicial. Se um índice for útil, criar depois do `ALTER`, como manda o `AGENTS.md`.

## Seed

Job explícito, não no meio de um request de chat:

1. Para cada modelo com `reasoning_control_source` nulo ou `unset`, aplicar `families.py`.
2. Gravar `family` quando casar, `none` quando não casar (e atualizar `reasoning_control_source = 'family'`).
3. Não tocar linha com `reasoning_control_source = 'admin'`.
4. Novos modelos inseridos por `sync_provider_models` entram com `unset` por padrão e são classificados no próximo ciclo de seed ou ao fim da sincronização.
5. Rodar em cópia do banco nos testes. Nunca em `backend/nexuslocal.db` vivo durante pytest.

## Contrato do WebSocket

Campo novo no request de mensagem, opcional:

```json
{ "reasoning_effort": "medium" }
```

Ausente = não pedir esforço (comportamento atual).

Evento novo, só quando o backend descartar o pedido:

```json
{
  "type": "effort_dropped",
  "reason": "unsupported_model",
  "model_id": "...",
  "requested": "high"
}
```

Motivos previstos: `unsupported_model`, `invalid_level`, `failover`, `fusion_excluded`, `provider_rejected`.

## Tradução por provedor

Assinatura em `BaseProvider.stream_chat`:
```python
async def stream_chat(
    self,
    model: str,
    messages: List[Dict[str, str]],
    temperature: float = 0.7,
    max_tokens: int = 4096,
    reasoning_effort: Optional[str] = None,
    reasoning_control: Optional[str] = None,
) -> AsyncIterator[str]:
```

Função pura, testável sem rede: `build_effort_payload(control, level, base_payload) -> payload`.

- `none` / `always_on` / nível inválido: devolve `base_payload` intocado.
- `openai_effort` e `xai_effort`: acrescenta `reasoning_effort` no payload raiz (`{"reasoning_effort": ...}`).
- `openrouter_reasoning`: acrescenta `{"reasoning": {"effort": ...}}` no payload raiz para OpenRouter.
- `gemini_thinking`: no `GeminiProvider`, injeta `thinkingConfig` (com `thinkingBudget` ou `thinkingLevel`) em `generationConfig` (tanto no streaming nativo quanto no cached content). Nunca manda `reasoning_effort` nesse caminho.
- `anthropic_effort`: reservado para cliente nativo Anthropic (`headers`/`body`). Se o Claude for chamado via OpenRouter, o controle ativo é `openrouter_reasoning`.
- `CloudflareProvider`: sempre omite.

### Rede de segurança (HTTP 400)
A rede de segurança vive em `stream_from_llm` (`backend/orchestration/resolve_request.py`):
Se `provider.stream_chat` levantar erro HTTP 400 cujo corpo cite termos de esforço/reasoning (`reasoning_effort`, `thinkingConfig`, `unsupported parameter`), o orquestrador:
1. Emite `effort_dropped` via WebSocket com `reason: "provider_rejected"`.
2. Executa **uma única** retentativa chamando `stream_chat` sem os parâmetros de esforço.
3. Não entra em loop e **não** deixa o erro transbordar para `check_and_deactivate_model()`, evitando que um modelo saudável seja desativado no banco por rejeição de parâmetro opcional.

## Failover e Auto

1. Resolver o controle do modelo que vai atender, não do modelo que o usuário clicou se o failover já trocou.
2. Se o reserva for `none` ou `always_on`, omitir e avisar `effort_dropped` com reason `failover`.
3. No modo Auto, o esforço é preferência do usuário. O router continua escolhendo modelo por intenção, cota e score. Depois da escolha, aplica a preferência só se aquele modelo tiver o nível. Senão omite e avisa `unsupported_model`. Não deixar o esforço mudar a escolha do modelo na v1.

## Fusion, memória, enhancer, dream

v1: essas chamadas ignoram `reasoning_effort`. Motivo: um painel Fusion pode misturar modelo com dial e modelo sem dial; um 400 num membro derruba o turno. Fica como fase posterior explícita, fora do checklist principal.

## Testes

- Arquivo novo `backend/tests/test_reasoning_effort.py`.
- Banco: `tempfile` ou `:memory:`. Proibido apontar para `backend/nexuslocal.db`.
- Casos mínimos: `none` não altera payload; nível fora da lista é omitido; failover para modelo `none` omite; source `admin` não é reescrito pelo seed.
