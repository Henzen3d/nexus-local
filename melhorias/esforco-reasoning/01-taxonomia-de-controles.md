# 01 — Taxonomia de controles

**Multi+ / NexusLocal** · Plano, não implementação

O app fala um enum interno. Cada provedor traduz para o campo dele. A UI nunca mostra um nível que o contrato não lista.

## Enum interno `ReasoningControl`

| Valor | Significado na UI | O que o backend faz |
| :--- | :--- | :--- |
| `none` | Oculta a linha de esforço | Não adiciona campo nenhum |
| `openai_effort` | Seletor com os níveis gravados no modelo | `reasoning_effort` no payload OpenAI-compat |
| `gemini_thinking` | Seletor | `thinkingConfig` no Gemini nativo. No caminho OpenAI-compat do mesmo modelo, só o campo que aquele endpoint documentar no dia da implementação |
| `anthropic_effort` | Seletor | Campo `effort` do Claude. Não misturar com `budget_tokens` na v1 |
| `openrouter_reasoning` | Seletor | Objeto `reasoning` do OpenRouter, e só se o modelo de destino estiver no mapa |
| `xai_effort` | Seletor | `reasoning_effort` quando o modelo Grok documentar o campo |
| `always_on` | Frase fixa, sem dial | Não manda nível. O modelo já raciocina |
| `binary_think` | Ligado / desligado | Um booleano (`think` ou equivalente). Sem escala de cinco pontos |

Valores de nível internos, do mais leve ao mais pesado:

`off`, `minimal`, `low`, `medium`, `high`, `xhigh`, `max`

Nem todo controle usa a escala inteira. A lista visível vem de `reasoning_levels` daquele modelo.

## Rótulos de UI (não são o valor da API)

| Nível interno | pt-BR | Nota |
| :--- | :--- | :--- |
| `off` | Desligado | Só se o contrato tiver "não pensar" |
| `minimal` | Mínimo | |
| `low` | Baixo | |
| `medium` | Médio | Marcar como recomendado quando for o default da família |
| `high` | Alto | |
| `xhigh` | Extra | |
| `max` | Máx | Destacar aviso de alto consumo de tokens/cota (benchmark: 5x ou mais) |

A copy de consumo fica no flyout: esforço maior aumenta latência e tokens de raciocínio. Não prometer economia em número.

## Mapa de famílias (sugestão, não verdade eterna)

Arquivo alvo: `backend/reasoning/families.py`. Match por `provider_id` + substring do `models.name`. Primeira regra que casar ganha. Se nada casar, `none`.

Confirmar cada linha na documentação do provedor **no dia da implementação**. APIs mudam. Não codificar de memória sem essa subtarefa.

| Família (nome contém) | Provedor típico | Controle sugerido | Níveis sugeridos | Default |
| :--- | :--- | :--- | :--- | :--- |
| `o1`, `o3`, `o4`, `gpt-5` com variante reasoning | openai / openrouter | `openai_effort` (OpenAI direta) ou `openrouter_reasoning` | os que a doc listar (ex: `low` `medium` `high`; OpenAI não aceita `max`); não inventar níveis | `medium` |
| `gemini-2.0-flash-thinking`, `gemini-2.5`, `gemini-3` thinking / flash-thinking | gemini | `gemini_thinking` | `off` (budget 0), `low`, `medium`, `high`; traduz para `thinkingBudget` ou `thinkingLevel` | `medium` |
| `claude` recente com effort (ex: 3.7 Sonnet) | openrouter (catálogo atual) / anthropic (futuro) | `openrouter_reasoning` (via OpenRouter) ou `anthropic_effort` (se cliente nativo Anthropic) | `low` `medium` `high` `xhigh` `max`, só os documentados pelo endpoint | `medium` |
| `grok` com reasoning | xai / openrouter | `xai_effort` ou `openrouter_reasoning` | os documentados | `medium` |
| `deepseek-r1`, `deepseek-reasoner` sem dial | deepseek / openrouter | `always_on` | vazio | — |
| `qwen` thinking sem dial (ex: Qwen3-VL-*-Thinking) | openrouter / vllm | `always_on` ou `binary_think` | vazio ou `off`/`high` conforme endpoint | — |
| Llama, Mixtral, Qwen chat sem tag thinking, Groq, Cerebras, Cloudflare | vários | `none` | vazio | — |

Heurística de nome **não dispara no request**. Ela só preenche coluna vazia no seed. Override do admin não é recalculado.

## Regra de ouro do request

```
controle resolvido == none ou always_on
  → payload idêntico ao de hoje (always_on não manda nível)

controle tem dial e o nível pedido está em reasoning_levels
  → traduzir

nível ausente, inválido ou de outro contrato
  → cair no default do modelo; se não houver default, omitir o campo
```

Nunca mandar um nível "porque a UI tinha cinco botões".
