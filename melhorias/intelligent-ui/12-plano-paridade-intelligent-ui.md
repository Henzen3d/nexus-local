# Plano 12 — Paridade com o Intelligent UI do ChatGPT

**Data:** 2026-10-14
**Estado:** em andamento. Passos 1 e 2 da seção 8 entregues em 2026-10-14 (`Origin` no WebSocket; blocos `metric`, `callout`, `follow_up`; teto 6 com subtetos; catálogo com os três tipos). Os demais passos continuam planejados; a ordem da seção 8 vale.
**Depende de:** Fases 1–7 e plano 11. A cena 2D/3D tem plano próprio (13).
**Referências:** [10-referencias-answerui-openui-openwebui.md](10-referencias-answerui-openui-openwebui.md) (tabela de paridade na seção 1; mecanismos do OpenUI na seção 3; padrões do Open WebUI na seção 4).

## 0. Regra geral: tudo aditivo ao `nexus-ui/1`

Não há `nexus-ui/2`. A spec já manda: tipo desconhecido → bloco descartado; campo desconhecido → campo ignorado. Logo um cliente antigo que receba `metric` ou `follow_up` perde só aquele bloco e segue pintando os demais. As regras de compatibilidade do OpenUI (spec §3) viram, para nós:

1. Tipo novo é adicionado à lista fechada nos **dois** validadores (`backend/ui_blocks/validate.py` e `frontend/src/lib/nexusUi.ts`) no mesmo PR, com testes espelhados.
2. Campo novo em tipo existente é sempre opcional e com padrão.
3. Nunca mudar o significado de campo existente. Se precisar, campo novo.
4. Toda tolerância nova entra na tabela da spec §4 ("auto-healing") e num teste de paridade.
5. Teto de blocos por envelope sobe de 4 para **6**, com subtetos: no máximo 1 `sandbox`, 2 `chart`, 1 `follow_up` (sempre o último) e 1 `options`. Motivo: uma resposta composta (métrica + gráfico + tabela + follow-up) não cabe em 4. O `mergeUiEnvelopes` do store e o `ui_progress` seguem o teto novo.

## 1. Entregas, em ordem

| # | Entrega | Para quê | Tamanho |
|---|---|---|---|
| 12.1 | Blocos `metric`, `callout`, `follow_up` | Resposta composta barata; três blocos pequenos, sem estado | P |
| 12.2 | Bloco `table` | Dado tabular com número alinhado e copiável; o GFM da prosa não ordena nem formata | M |
| 12.3 | Bloco `options` | Pergunta com escolhas clicáveis (ChatGPT "quick replies"; `AskUserCard` do Open WebUI) | M |
| 12.4 | Catálogo modular + regras do AnswerUI | Caber no orçamento de tokens com 10 tipos; ensinar "quando construir ferramenta" | M |
| 12.5 | Render progressivo (JSON parcial no stream) | Bloco completo aparece enquanto o modelo ainda escreve | M |
| 12.6 | Laço de correção ("Pedir correção") | Bloco descartado deixa de ser silencioso; modelo conserta em um turno | M |
| 12.7 | Estado compartilhado entre blocos | Mexer num campo recalcula métrica, fact, barra e gráfico da mesma mensagem | G |
| 12.8 | `chart` com `pie`, `unit`, rótulos de eixo e `stacked` | Cobre pedidos comuns ("distribuição", "participação") | P |
| 12.9 | Segurança do canal: `Origin` no WebSocket, `frame-ancestors` | Itens do `security.spec.ts` do AnswerUI que ainda faltam | P |
| — | Mapas com itinerário | Fora da v1 (seção 10) | — |

P = até um dia; M = dois a três dias; G = uma semana, com testes.

## 2. Blocos novos — contrato

Limites valem nos dois validadores. Texto é sempre nó de texto React (spec §7). `id` segue a regra geral.

### 2.1 `metric`

```json
{
  "id": "kpis",
  "type": "metric",
  "title": "Este mês",
  "items": [
    {"label": "Receita", "value": "R$ 48.200", "delta": "+8,1%", "trend": "up", "hint": "vs. mês anterior"},
    {"label": "Usuários ativos", "value": 1204, "trend": "flat"},
    {"label": "Churn", "value": "1,8%", "delta": "-0,3 p.p.", "trend": "down", "good": "down"}
  ]
}
```

- `title`: opcional, 1–80.
- `items`: 1 a 4. `label` 1–40; `value` número ou texto de 1–24; `unit` opcional 1–8 (vai depois do número, só quando `value` é número); `delta` opcional 1–12; `trend` opcional `up|down|flat`; `good` opcional `up|down` (qual direção é boa; padrão `up`) — define a cor do delta (`--success` quando `trend === good`, `--error` quando o oposto, `--muted` em `flat`); `hint` opcional 1–40.
- `value` numérico é formatado por locale (`formatNumber`). Texto vai como está.
- Render: grade `auto-fit` de 140 px, cada item como o `MetricIndicator` do OpenUI (valor 20 px, delta ao lado em 12 px com seta `↑ ↓ →`, label em cima, hint embaixo). Altura reservada: 84 + 70 por linha de itens.
- Com 12.7: `value` aceita expressão `"={valor} * 1.2"` (seção 7).

### 2.2 `callout`

```json
{"id": "aviso", "type": "callout", "kind": "warning", "title": "Atenção", "body": "A taxa Selic usada é a de outubro de 2026."}
```

- `kind`: `info|success|warning|danger`; ausente → `info`. `title` opcional 1–60. `body` 1–400.
- Render: faixa com borda esquerda de 3 px na cor do tipo (`--primary`, `--success`, `--warning`, `--error`), ícone lucide (`Info`, `CircleCheck`, `TriangleAlert`, `OctagonAlert`), `role="note"` (`danger` usa `role="alert"` só se vier do host). Altura reservada: 56 + 20 por 80 caracteres de `body`.
- Não substitui `> [!NOTE]` na prosa; isso é melhoria do markdown, fora desta pasta.

### 2.3 `follow_up`

```json
{"id": "proximos", "type": "follow_up", "items": ["Comparar com 2025", "Mostrar por região", "Exportar como tabela"]}
```

- `items`: 1 a 4 textos de 3–80 caracteres. Só um `follow_up` por envelope e sempre o último bloco (validador reordena se vier antes; descarta o segundo).
- Render: lista vertical de botões de texto separados por linha fina (padrão do Open WebUI), `aria-label="Sugestão: …"`. Clique = `sendMessage(texto)` (ação `send_message` implícita; sem template). Depois de clicar, o item escolhido fica marcado e os outros continuam clicáveis; nova mensagem do usuário não apaga a lista (fica no histórico como estava).
- Prosa: o catálogo diz que as sugestões **não** repetem o que o texto já respondeu.

### 2.4 `table`

```json
{
  "id": "custos",
  "type": "table",
  "title": "Custo por 1M tokens",
  "columns": [
    {"key": "modelo", "label": "Modelo"},
    {"key": "entrada", "label": "Entrada (US$)", "kind": "number"},
    {"key": "saida", "label": "Saída (US$)", "kind": "number"}
  ],
  "rows": [
    {"modelo": "GPT-4o mini", "entrada": 0.15, "saida": 0.6},
    {"modelo": "Gemini Flash", "entrada": 0.1, "saida": 0.4}
  ],
  "sort": {"key": "saida", "dir": "asc"}
}
```

- `columns`: 2 a 8; `key` `[a-z0-9_]{1,32}` único; `label` 1–40; `kind` opcional `text|number|date` (padrão `text`); `unit` opcional 1–8 para `number`.
- `rows`: 1 a 50 objetos. Célula `number` precisa ser número (texto → `type_mismatch` na célula, mostrada como "—"); `text` até 120 caracteres; `date` ISO `YYYY-MM-DD` (formatada por locale).
- `sort` opcional; o usuário pode reordenar clicando no cabeçalho (estado local, não volta ao modelo).
- Render: `<table>` real (não grid de divs), cabeçalho fixo no scroll horizontal do cartão, número alinhado à direita com `tabular-nums` e `formatNumber`, zebra suave (`--surface-soft`), mais de 10 linhas colapsa com "Mostrar todas (n)". Ação "Copiar dados" reaproveita `chartToCsv` (generalizar para `tableToCsv`). Altura reservada: 56 + 36 × min(linhas, 11).
- Tamanho do fence: tabela de 8 × 50 com textos longos pode passar dos 16 000; o catálogo pede até 20 linhas e o validador corta em 50.

### 2.5 `options`

```json
{
  "id": "destino",
  "type": "options",
  "question": "Qual estilo de viagem combina mais com você?",
  "mode": "single",
  "options": [
    {"value": "praia", "label": "Praia e descanso", "description": "Litoral, pouca agenda"},
    {"value": "trilha", "label": "Natureza e trilhas"},
    {"value": "cidade", "label": "Cidade e cultura"}
  ],
  "allow_other": true,
  "action": {"name": "send_message", "template": "Prefiro: {choice}"}
}
```

- `question` 1–160. `mode` `single` (padrão) ou `multiple`. `options` 2 a 6; `value` como `SELECT_VALUE_REGEX`; `label` 1–60; `description` opcional 1–100. `allow_other` opcional (campo de texto de até 200, como `text` de `controls`).
- `action`: só `send_message` com `template` contendo `{choice}` (em `multiple`, `{choice}` vira a lista separada por vírgula; `{other}` opcional). Sem `template` → bloco descartado (mesma regra de `controls`).
- Render: cartões de opção (padrão `OptionCards` do OpenUI) em grade `auto-fit` 160 px, `role="radiogroup"`/`group` com `aria-checked`; em `single`, um clique envia na hora (é gesto do usuário: spec §7 permite); em `multiple` e com "outro", botão "Enviar". Depois de enviar, o bloco trava e mostra "Respondido: …". Durante o stream (12.5) fica desabilitado.
- É o substituto natural de `controls` com um só `select`; o catálogo diz quando usar cada um.

### 2.6 Extensões de `chart` (12.8)

- `kind: "pie"`: `series` com exatamente 1 item; `rows` 2 a 8; render em rosca (`PieChart` + `Pie innerRadius 55%`), cores por `distributeColors` numa rampa `color-mix` do `--primary`, legenda sempre, percentual no tooltip; tabela sr-only igual.
- `unit` (1–8), `x_label` e `y_label` (1–40) opcionais: aparecem no tooltip/eixos e na tabela sr-only.
- `stacked: true` só em `compare`: barras empilhadas, domínio pela soma por sinal (`yDomainThroughZero(rows, keys, true)`).
- Tolerância: `pie` com mais de 8 linhas → agrupa o resto em "Outros"; `pie` com 2+ séries → usa a primeira.

## 3. Catálogo modular (12.4)

**Passo 3 implementado (2026-10-14):** `catalog.txt` é a base e
`catalog_modules/*.txt` contém os oito contratos atuais. `catalog.py` compõe
apenas os módulos selecionados, com teto de 450 tokens estimados (`len/4`,
mesmo critério anterior), inclusive para a pior combinação de três módulos.
Prioridade estável: chart → metric → progress → controls → callout → card →
sandbox. Duas vagas de conteúdo + uma reservada a follow_up (três no total).
O gatilho numérico anterior mantém chart como fallback; falsos positivos por
radical continuam excluídos. Flag desligada e modo voz não carregam catálogo.
`modules_offered` e `modules_produced` contam turnos por módulo (produzido =
tipo sobrevivente à validação, mesmo sem oferta); `block_types` segue contando
blocos. O log inclui `modules=` sem texto do usuário. Tipos futuros `table`,
`options`, `scene`, `pie` e funções de cálculo futuras não são anunciados.
A proposta abaixo descreve também a expansão futura, não contratos presentes.


Hoje `catalog.txt` tem ~277 tokens e teto de 400. Com dez tipos e as regras de cálculo ele passaria de 600. Em vez de subir o teto para todo turno, o catálogo vira **base + módulos**:

- **Base** (sempre que o heurístico liga; ≈ 170 tokens): o parágrafo "se um visual ajudar…", o exemplo mínimo de fence, o teto de blocos, as regras gerais (nome do fence, sem HTML na bolha, prosa completa) e a lista dos tipos **em uma linha** (`progress, card, chart, metric, table, callout, options, follow_up, controls, sandbox`).
- **Módulos** (uma a três linhas cada; ≈ 40–90 tokens): a definição detalhada de cada tipo, com o próprio gatilho no `should_offer.py`:

| Módulo | Gatilho (além do heurístico geral) |
|---|---|
| `chart` | `gráfico|grafico|compar|versus|vs|evolu|tendên|distribui|participa` |
| `table` | `tabela|planilha|lista de|ranking|top \d` ou 3+ números e 2+ entidades |
| `metric` | `indicador|kpi|métrica|resumo|total|taxa|%` |
| `progress` | `etapa|progresso|checklist|passo a passo|roteiro` |
| `controls` + `options` | `calcul|simul|estim|parcel|divid|escolh|selecion|prefer|qual (dos|das)` |
| `callout` | `atenção|cuidado|importante|aviso|risco` |
| `follow_up` | sempre que qualquer outro módulo entra (é barato) |
| `card` | `imagem|foto|cartão|cartao|produto|ficha` |
| `sandbox`/`scene` | `simul|anima|3d|visualiz(e|ar) o algoritmo|interativ` (plano 13) |

- Teto por turno: 450 tokens (base + até três módulos; o quarto módulo não entra, por ordem de prioridade do gatilho). Teste `test_catalogo_cabe_no_teto` passa a conferir base + a pior combinação de três módulos.
- Regras traduzidas do `answerRules` do AnswerUI (doc 10 §2.2) entram na base ou no módulo de `controls`:
  - "Pergunta curta ou factual: só prosa."
  - "Construa ferramenta quando o usuário for ajustar números, comparar opções, planejar com entradas ou explorar dados."
  - "Em `controls`, defina os campos primeiro e calcule todo resultado a partir deles (`computed`), para atualizar ao vivo. Arredonde com `round(x, 2)`." (depende de 12.7 para `round`)
  - "Sugestões de `follow_up` não repetem o que a prosa já respondeu."
  - "`options` para uma escolha; `controls` para vários valores."
- Telemetria ganha `modules=` na linha de log e um contador por módulo oferecido/produzido, para calibrar os gatilhos.

## 4. Render progressivo (12.5)

Hoje o fence só vira bloco no `stream_end` (o backend extrai e valida; durante o stream a bolha esconde o fence parcial com `stripUiFences`). O ChatGPT mostra o visual se formando. O princípio do OpenUI (spec §4): **todo prefixo é uma página válida** e, no fim, o resultado é igual ao parse do texto inteiro.

Desenho (só frontend; o transporte não muda):

1. `frontend/src/lib/nexusUiStream.ts`: `scanPartialEnvelope(text) → { blocks: unknown[], pendingType: string | null, closed: boolean }`. Procura o último fence `nexus-ui` aberto no início de linha; dentro dele, percorre o JSON com um autômato simples (profundidade de `{}`/`[]`, estado "dentro de string", escape) e devolve cada item **completo** de `blocks[]` como texto JSON parseado individualmente. O item em andamento devolve só o `"type"` se ele já chegou (regex no prefixo), para o esqueleto ter a altura certa. Sem heurística de fechar colchetes: bloco incompleto não pinta (regra "Fence sem fechar: não pintar JSON parcial" continua valendo para o bloco; o que muda é a granularidade).
2. Cada bloco completo passa por `parseUiEnvelope({v:1, blocks:[bloco]})` — "menor unidade que falha cai". Resultado vai para `streamingUiBlocks` do store (hoje só recebe `ui_progress` do host) com `source: 'model'`, respeitando o teto de 6 e os subtetos, e usando `mergeUiEnvelopes`.
3. `DynamicRenderer` recebe `streaming: boolean`. Durante o stream: `controls`, `options`, `follow_up` e `sandbox` pintam **desabilitados** (OpenUI: "interactive features wait"); `sandbox` nem monta o iframe, mostra o placeholder. O bloco pendente vira um esqueleto com `reservedHeight` pelo `pendingType`.
4. No `stream_end`, o envelope do servidor substitui `streamingUiBlocks` (fonte da verdade; já é assim). Teste de propriedade: para todo prefixo de um fence válido, `scanPartialEnvelope(prefixo).blocks` é prefixo (em ordem e conteúdo) de `validate_envelope(fence completo)`. Fixtures em `frontend/src/lib/__fixtures__/stream/*.txt` com cortes em pontos difíceis (dentro de string com `}`; depois da vírgula; no meio de `\"`).
5. Catálogo: "escreva um bloco por linha dentro de `blocks`" (melhora a granularidade; não é exigido pelo scanner).
6. Zero CLS: o esqueleto do pendente aparece assim que `"type"` chega; o bloco completo troca o esqueleto pelo cartão da mesma altura.

Custo: o scanner roda a cada token em texto que já chegou ao fence (só o sufixo após a abertura), O(n) por chamada; com `useDeferredValue` já usado na bolha, não pesa.

## 5. Laço de correção (12.6)

Hoje um bloco inválido some e só a telemetria sabe. O OpenUI devolve um objeto de erro pronto para colar na conversa; o AnswerUI tem o botão "Fix it" na cena.

1. **Validador devolve erros.** `validate_envelope` passa a retornar também `errors: list[UiError]` com `code` (`unknown_type`, `missing_required`, `type_mismatch`, `limit_exceeded`, `invalid_action`, `invalid_expression`, `unsafe_url`, `duplicate_id`, `invalid_json`, `fence_unclosed`, `rejected_envelope`), `block_id` (ou índice), `path` (`rows[2].v`), `message` curto e `hint` (assinatura do tipo: `chart: title, kind bar|line|compare|pie, x_key, series[{key,label}], rows[]`). O TS espelha a lista de códigos; teste de paridade confere que o mesmo fence gera os mesmos códigos nos dois lados.
2. **Transporte.** `stream_end` ganha `ui_errors` (até 4 itens, `message` ≤ 160) e `ui_dropped` (inteiro). Persistir só a contagem e os códigos na telemetria (`telemetry.py`), não o payload.
3. **Bolha.** Com a flag ligada, abaixo dos blocos: "1 visual não pôde ser exibido · **Pedir correção**" (texto discreto, `--muted`, botão com 44 px de alvo). O clique manda, pelo mesmo `sendMessage`, uma mensagem do usuário visível: `Corrija o visual "vendas" da resposta anterior: rows[2].v deveria ser número (recebi "12k"). Responda com a prosa curta e o fence nexus-ui corrigido.` Nada automático: é gesto do usuário (spec §7). Uma única solicitação por mensagem (o botão some depois).
4. **Sandbox e cena.** Erro de runtime do iframe (bootstrap captura `error`/`unhandledrejection` e manda `{type: '__nexus_ogui_error', message}` ≤ 500) mostra o mesmo botão: `Corrija a ferramenta "<title>": falhou com: <mensagem>`.
5. **Medição.** `correction_offered`, `correction_requested`, `correction_valid` (fence da resposta seguinte válido). Se `correction_valid / requested` ficar abaixo de 50% com um modelo, o painel admin mostra a taxa e o catálogo desse modelo é revisto.

## 6. Segurança do canal (12.9)

Do `e2e/security.spec.ts` do AnswerUI:

- [x] `websocket_chat` confere o cabeçalho `Origin` (`backend/ws_origin.py`): aceita se `host[:porta]` do `Origin` é o mesmo do `Host` da requisição ou se o `Origin` está em `ALLOWED_ORIGINS` (a mesma lista do CORS; vazio = padrões de dev `localhost:5173`/`127.0.0.1:5173`). Sem `Origin` passa (cliente que não é navegador); `Origin: null` não. Caso contrário `ws.close(code=4003)` antes do `accept` (HTTP 403). Teste em `tests/test_ws_origin.py`.
- [x] Clickjacking: o `index.html` é servido pelo nginx, que já manda `Content-Security-Policy: frame-ancestors 'self'` e `X-Frame-Options: SAMEORIGIN` (`frontend/nginx-security-headers.conf`). Fica em `'self'`, não `'none'`: os iframes `srcdoc` dos artefatos e do sandbox herdam a CSP do documento pai, e `'none'` os bloquearia. Nada a fazer no backend.
- [x] `POST /api/intelligent-ui/config` só aceita corpo JSON (modelo Pydantic) e o JWT vai por cabeçalho `Authorization`, não por cookie: formulário cross-site não consegue nem autenticar nem passar no parser. Sem mudança.

## 7. Estado compartilhado entre blocos (12.7)

O que torna a calculadora do ChatGPT "viva": mexer no campo recalcula tudo. O OpenUI faz isso com `$var` e expressões; aqui entra como **expressão em campo de valor**, avaliada pelo `safeMath` já existente, com escopo de **uma mensagem**.

### 7.1 Contrato

- Toda `controls.fields[].id` publica o valor atual no estado da mensagem sob o nome `id` (se dois blocos `controls` repetem o id, o validador rejeita o segundo bloco — `duplicate_id`).
- Campos que aceitam expressão: `metric.items[].value`, `card.facts[].value`, `progress.value`, `callout.body` (só interpolação `{expr}`), `chart.rows[][série]`, `table.rows[][coluna number]`, `controls.computed[].formula` (já existe, vira lista).
- Sintaxe: string que começa com `=`: `"={valor} * (1 + {taxa} / 100)"`. Dentro, a gramática do `safeMath` estendida: `+ - * / ( )`, números, `{id}`, e funções `round(x, casas)`, `abs`, `min`, `max`, `floor`, `ceil`, `sqrt`, `pow(x, y)`. Sem `^` (o AnswerUI também evita; modelos erram a precedência). Teto de 160 caracteres e 40 tokens por expressão; `{id}` tem de existir em um `controls` do mesmo envelope, senão `invalid_expression` e o campo vira `"—"`.
- `controls.computed` vira lista: `[{"id": "parcela", "template": "Parcela: R$ {resultado}", "formula": "..."}]`; o `id` de um `computed` também publica no estado (encadeamento), sem ciclo (validador ordena topologicamente; ciclo → `invalid_expression`).
- Formatação: resultado numérico passa por `formatNumber` com 2 casas; `unit` do item vai depois.

### 7.2 Implementação

- `frontend/src/ui/lib/safeMath.ts`: funções, `round` com casas, `pow`, `sqrt`; `evaluateExpression(expr, vars)` e `isExpression(value)`; testes.
- `backend/ui_blocks/expr.py`: mesmo tokenizador e as mesmas regras **só para validar** (sintaxe, ids conhecidos, tamanho); não avalia. Teste de paridade com uma tabela de expressões válidas/inválidas compartilhada em `backend/tests/fixtures/expressions.json` e lida pelos dois lados.
- `frontend/src/ui/state/messageUiState.ts`: `createMessageUiStore(messageId)` (um `Map` por mensagem dentro do Zustand existente, não um store novo) com `publish(id, value)` e `useUiValue(id)`. `ControlsCard` publica no `onChange`; os consumidores (`MetricCard`, `ImageCard`, `ProgressCard`, `ChartCard`, `TableCard`) usam `useResolvedValue(raw)` que devolve o literal quando não é expressão.
- `ChartCard` com linhas reativas recalcula `rows` memoizado; animação de atualização desligada (`isAnimationActive={false}` quando o valor vem de expressão) para não "dançar" a cada tecla.
- Persistência: o estado dos campos **não** é gravado (igual hoje: recarregar volta ao `default`). O OpenUI grava `formState` no `context` da mensagem; fica como item futuro se a família sentir falta.
- Prosa reativa (números do texto que mudam ao mexer no campo) **não entra**: texto do modelo é conteúdo, não marcação (spec §3). O lugar do número vivo é o `metric` ou o `computed`.

## 8. Ordem de implementação e testes

| Passo | Entrega | Testes obrigatórios | Situação |
|---|---|---|---|
| 1 | 12.9 (Origin, headers) | `test_ws_origin.py`; header no `index.html` | **Entregue** (2026-10-14): `backend/ws_origin.py`, checagem em `websocket_chat`, CORS e WS com a mesma lista; `test_ws_origin.py` (7 testes). Headers de clickjacking já existiam no nginx (`frame-ancestors 'self'`, `X-Frame-Options: SAMEORIGIN`) — mantidos em `'self'` porque os iframes `srcdoc` herdam a CSP do pai. O `POST /config` só aceita corpo JSON (Pydantic) e JWT por cabeçalho: sem CSRF por formulário. |
| 2 | 12.1 `metric`, `callout`, `follow_up` + teto 6 | paridade Python/TS por tipo; `mergeUiEnvelopes` com teto 6; render SSR dos três cartões | **Entregue** (2026-10-14): validadores espelhados (`validate.py` / `nexusUi.ts`) com `MAX_BLOCKS = 6` e `MAX_BLOCKS_PER_TYPE`; `MetricCard`, `CalloutCard`, `FollowUpCard`; `DynamicRenderer` com alturas reservadas; 9 chaves i18n ×8; catálogo com os três tipos (≈ 389 tokens, ainda sob o teto de 400); testes em `test_ui_blocks.py` (+5) e `nexusUi.test.ts` (+5). |
| 3 | 12.4 catálogo modular | teto por combinação; gatilhos com casos positivos e negativos (falsos positivos do `should_offer` de hoje continuam cobertos) | Próximo: o catálogo está a 11 tokens do teto; `table`/`options`/`pie` não cabem sem os módulos. |
| 4 | 12.6 laço de correção | códigos de erro iguais nos dois lados; `stream_end.ui_errors`; botão só com flag ligada; um pedido por mensagem | Planejado |
| 5 | 12.2 `table`, 12.8 `pie`/`unit`/`stacked` | validação de célula; CSV; `pie` com "Outros" | Planejado |
| 6 | 12.5 render progressivo | propriedade "prefixo ⊆ final"; fixtures de corte; bloco interativo desabilitado no stream | Planejado (`referencias-codigo/partial-json.ts` pronto) |
| 7 | 12.3 `options` | um clique envia só em `single`; trava após envio; `{choice}` em `multiple` | Planejado |
| 8 | 12.7 estado compartilhado | expressões (paridade), ciclo, ids desconhecidos, recalculo de `metric`/`chart` | Planejado |

Cada passo é um PR com a flag desligada por padrão; o `06-criterios-aceite.md` ganha uma seção por passo.

## 9. Riscos

| Risco | Corte |
|---|---|
| Catálogo maior piora modelos pequenos | Módulos por gatilho; medir `produced/offered` por módulo; desligar módulo com taxa baixa |
| Render progressivo pinta bloco que o servidor depois rejeita | O servidor manda; no `stream_end` o envelope final substitui; telemetria `stream_block_reverted` para medir divergência (meta: < 2%) |
| Expressão vira vetor de abuso | Sem `eval`, gramática fechada, tetos de tamanho, só `{id}` de `controls` do mesmo envelope |
| `options` dispara envio sem o usuário querer | Só em `single` o clique envia, e o cartão diz "toque para enviar"; `multiple`/`other` têm botão |
| Laço de correção em loop | Um pedido por mensagem; sem envio automático |
| Teto de 6 blocos incha o fence | Subtetos; 16 000 caracteres continuam valendo; `table` limitada a 50 linhas |

## 10. Fora da v1 (e por quê)

- **Mapas com itinerário.** Precisa de tiles externos (OSM/Mapbox) ou de um proxy: rede nova, privacidade da família, CSP do sandbox aberta para um host de tiles. Caminho possível depois: imagem estática de um host em `INTELLIGENT_UI_IMAGE_HOSTS` dentro de um `card`, ou Leaflet servido localmente com tiles em cache, como ferramenta explícita do admin.
- **Prosa reativa** (número do texto que muda com o campo): texto é conteúdo, não marcação.
- **`Query`/`Mutation` genéricos do OpenUI** (widget chamando ferramenta do servidor): ação de widget continua lista fechada (`send_message`, `set_model`). Uma terceira ação nasce no backend, nunca no prompt.
- **Edição incremental de UI** (patch por nome como no OpenUI §2.6): um envelope por mensagem (spec §5). Mudança pede nova resposta.
- **Árvore livre de layout** (Stack/Tabs/Accordion): rejeitada na v1 e continua fora; o `DynamicRenderer` empilha blocos.
