# 02 — Catálogo, payload e failover

**Multi+ / NexusLocal** · Plano, não implementação

## Onde encaixa

| Peça atual | Papel no plano |
| :--- | :--- |
| `backend/database.py` `init_db()` | `ALTER TABLE` incremental, no mesmo padrão de `supports_vision` |
| `GET /admin/models` em `backend/routers/admin.py` | O chat já consome esta lista via `api.getModels()` |
| `frontend/src/types.ts` `Model` | Ganhar os três campos novos |
| `backend/providers/base.py` `stream_chat` | Aceitar esforço opcional e traduzir |
| `backend/routers/chat.py` | Ler o campo do WebSocket |
| `backend/orchestration/resolve_request.py` | Repassar; no failover, reavaliar o modelo reserva |
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
2. Gravar `family` quando casar, `none` quando não casar.
3. Não tocar linha `admin`.
4. Rodar em cópia do banco nos testes. Nunca em `backend/nexuslocal.db` vivo durante pytest.

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

Motivos previstos: `unsupported_model`, `invalid_level`, `failover`, `fusion_excluded`.

## Tradução por provedor

Função pura, testável sem rede: `build_effort_payload(control, level, base_payload) -> payload`.

- `none` / `always_on` / nível inválido: devolve `base_payload` intocado.
- `openai_effort` e `xai_effort`: acrescenta `reasoning_effort` com o valor que a doc daquele modelo exigir (pode ser igual ao enum interno; se a doc usar outro token, a tabela de tradução vive em `families.py`, não na UI).
- `gemini_thinking`: no `GeminiProvider`, entra em `generationConfig.thinkingConfig`. Não enfiar `reasoning_effort` nesse caminho.
- `anthropic_effort`: só no cliente que já falar com a API Anthropic nativa. Se o modelo Claude do catálogo estiver atrás de OpenRouter, o controle efetivo é `openrouter_reasoning`, não `anthropic_effort`.
- `openrouter_reasoning`: objeto `reasoning` documentado pelo OpenRouter no dia da implementação. Não assumir que o destino honra.
- `CloudflareProvider`: sempre omite.

Rede de segurança, não desenho principal: se a resposta for HTTP 400 e o corpo citar o campo de esforço, **uma** retentativa sem o campo, mais evento `effort_dropped` com reason `provider_rejected`. Não fazer loop.

## Failover e Auto

1. Resolver o controle do modelo que vai atender, não do modelo que o usuário clicou se o failover já trocou.
2. Se o reserva for `none` ou `always_on`, omitir e avisar `failover`.
3. No modo Auto, o esforço é preferência do usuário. O router continua escolhendo modelo por intenção, cota e score. Depois da escolha, aplica a preferência só se aquele modelo tiver o nível. Senão omite e avisa. Não deixar o esforço mudar a escolha do modelo na v1.

## Fusion, memória, enhancer, dream

v1: essas chamadas ignoram `reasoning_effort`. Motivo: um painel Fusion pode misturar modelo com dial e modelo sem dial; um 400 num membro derruba o turno. Fica como fase posterior explícita, fora do checklist principal.

## Testes

- Arquivo novo `backend/tests/test_reasoning_effort.py`.
- Banco: `tempfile` ou `:memory:`. Proibido apontar para `backend/nexuslocal.db`.
- Casos mínimos: `none` não altera payload; nível fora da lista é omitido; failover para modelo `none` omite; source `admin` não é reescrito pelo seed.
