# Intelligent UI — visão e spec

**Estado:** implementado (Fases 1–7) e auditado em 2026-10-14. Esta spec continua sendo o contrato de referência; os desvios encontrados no código e as pendências estão anotados em cada plano e em `06-criterios-aceite.md` e resumidos no `README.md` da pasta.

**Data:** 2026-10-08

**Produto:** Nexus Local / Multi+ (`/home/osmar/nexuslocal`). Uso familiar. Cadastro público fechado. Cada usuário usa a própria chave.

## 1. Decisão

A resposta do chat deixa de ser só markdown quando um visual ajuda. O sistema implementa o **Generative UI Spectrum** (conceito formalizado em outubro de 2026 pelo [CopilotKit Open Intelligent UI](https://github.com/CopilotKit/OpenIntelligentUI) como resposta aberta ao Intelligent UI do ChatGPT):
- **Nível 1 — Controlled Generative UI (Fases 1 a 6):** O modelo não entrega interface livre nem código cru; entrega dados estruturados em JSON validado (`nexus-ui/1`). O frontend do Multi+, já carregado, escolhe o componente nativo correspondente. Zero risco de segurança e 100% de aderência visual ao design system.
- **Nível 2 — Open Generative UI & Sandboxed Tools (Fase 7):** Para tarefas dinâmicas que excedem os componentes nativos (calculadoras reativas de divisão/parcelamento, simulações, algoritmos passo a passo, gráficos 3D/Canvas), o sistema oferece um container isolado em `iframe` com sandbox estrito, injeção dos design tokens do Multi+ (`var(--primary)`, `var(--surface-card)`, etc.) e bridge validada de `postMessage`.

Isso não reescreve o Multi+. Não carrega um segundo app pesado dentro de cada resposta. O modelo nunca recebe o código dos componentes. Recebe, no máximo, um catálogo curto (seção 8), e só no turno em que o visual é plausível.

A nota e os aprendizados do OpenIntelligentUI pedem JSON com esquema fixo, atualização por WebSocket, gráfico sob demanda, imagens seguras, prevenção de layout shifts durante o streaming, e lista fechada de componentes e ações. A adaptação abaixo usa o que o Nexus já tem. Não abre canal novo e não instala SDKs pesados de terceiros.

| Necessidade | Pedido da nota / Referência OpenIntelligentUI | Decisão no Nexus |
|---|---|---|
| Tela | Não substituir o Multi+ | Frontend atual. React 18.3, Vite, Zustand, Vanilla CSS. `MessageBubble.tsx` continua dono da bolha. |
| Módulo | `src/ui/DynamicRenderer` e cartões | `frontend/src/ui/`. O app mora em `frontend/`, não numa pasta `src/` na raiz. |
| Formato | JSON validado com esquema fixo | Envelope `nexus-ui/1`. Backend valida antes de gravar. Frontend valida de novo antes de pintar. |
| Progresso e Ações | SSE unidirecional ou WebSocket bidirecional | Sem SSE. O chat já é WebSocket em `backend/routers/chat.py`. Barra, cálculo reativo e cliques usam esse socket. |
| Gráficos | Biblioteca sob demanda | `recharts` ^2.15.0, já dependência. `ChartCard` entra por `React.lazy`. Sem import estático de `recharts` na bolha. |
| Imagens | Arquivo local ou URL confiável | Anexo servido pelo próprio app, ou host listado em `INTELLIGENT_UI_IMAGE_HOSTS`. `https` solto não passa. |
| Harmonia Visual | Resolver o dilema do Andrew Chen ("parecer que pertence ao app") | Design tokens de `frontend/src/index.css` (`--primary`, `--surface-card`, `--hairline`, `--ink`, dark/light theme) compartilhados com os cartões nativos e injetados via bridge no sandbox. |
| Anti-Layout Shift | Ordem estrita de streaming do OpenIntelligentUI | `initial_height` e mensagens de placeholder progressivo para reservar espaço vertical antes da pintura. |
| Segurança | Lista de componentes e de ações | `DynamicRenderer` só monta os cartões desta spec. Ação fora da lista morre no backend. Sandbox sem `allow-same-origin`. |
| Liga/desliga | — | `INTELLIGENT_UI_ENABLED`, padrão `false`. |

Rejeitado para a v1: Thesys, SDK do ChatKit, LangChain pesado, SSE paralelo, `dangerouslySetInnerHTML` na bolha principal, JSX emitido pelo modelo, eval, árvore livre de layout (Box, Row, Spacer) e mandar o fonte do Multi+ no prompt.


## 2. O que já existe e não deve ser duplicado

Hoje a bolha é markdown (`react-markdown` + `remark-gfm` em `MessageBubble.tsx`). Artefato HTML, SVG, markdown, code e jsx abre no painel lateral (`ArtifactPanel.tsx`, evento WS `artifact`). Fusion tem `FusionStatusCard.tsx` e eventos `fusion_*`. Ferramenta tem `ToolCard.tsx`. Indicador de pensamento tem `AIStatusIndicator`.

Intelligent UI não substitui nenhum desses. Artefato continua no painel. Fusion continua no cartão de Fusion até o plano 02, e mesmo lá o cartão antigo não é apagado no primeiro passo: o bloco `progress` do host é um caminho novo, ao lado.

`messages.content` é `TEXT NOT NULL` (`backend/database.py`, tabela `messages`). Cache, TTS e extração de memória leem esse texto. Por isso o JSON visual não pode morar dentro de `content`.

## 3. Duas origens

**Host (confiável).** O servidor emite o bloco. Exemplos: etapa do Fusion, busca web, upload. O modelo não participa. Evento WS `ui_progress`.

**Modelo (não confiável).** O modelo anexa um fence no fim da prosa. O backend extrai, valida, descarta o que falhar e grava só o que passou. Texto do modelo é conteúdo, nunca marcação.

Os dois usam o mesmo tipo `UiBlock`. A origem fica gravada (`source`: `host` ou `model`) e não vai para o prompt de volta.

## 4. Contrato `nexus-ui/1`

Fence, sozinho no fim da resposta, depois da prosa:

````
```nexus-ui
{"v":1,"blocks":[]}
```
````

Envelope:

```json
{
  "v": 1,
  "blocks": []
}
```

Limites do envelope, iguais no backend e no frontend:

- `v` só pode ser `1`. Outro valor: envelope inteiro descartado.
- `blocks` é lista. Máximo 4 itens. Lista vazia: descartar o envelope, manter a prosa.
- JSON do fence: no máximo 16000 caracteres.
- `id` de cada bloco: 1 a 32 caracteres, `[a-z0-9_-]+`, único na mensagem.
- Campo desconhecido: ignorar o campo, não o bloco. Tipo desconhecido: descartar o bloco.
- Bloco inválido: descartar o bloco. Os válidos permanecem.
- Fence sem fechar no `stream_end`: descartar o fence, não pintar JSON parcial.
- Mais de um fence: usar só o último. Os anteriores saem da prosa e não viram bloco.

**Tolerâncias do validador** (iguais em `backend/ui_blocks/validate.py` e `frontend/src/lib/nexusUi.ts`; os testes `test_ui_blocks.py` e `nexusUi.test.ts` cobrem a paridade):

| Situação | Tratamento | Motivo |
|---|---|---|
| `v` ausente | assume 1 | modelo pequeno esquece o campo |
| `v` presente e ≠ 1 (inclusive `null`) | envelope inteiro descartado | outro contrato |
| Bloco solto sem envelope, ou `blocks` como objeto | embrulha em `{"v":1,"blocks":[…]}` | idem |
| `type` ausente | inferido pelos campos (`steps`/`value+max` → progress, `kind+series` → chart, `fields` → controls, `html` → sandbox, `facts`/`body`/`title` → card) | idem |
| `id` ausente, inválido ou repetido | gerado (`tipo_n`) | id é só âncora de render |
| `label`/`title` ausente | texto padrão | não vale perder o bloco por isso |
| `chart.kind` ausente | `bar` | padrão razoável |
| `chart.kind` fora de `bar`/`line`/`compare` | **bloco descartado** | não existe gráfico "parecido"; a prosa segue |
| `controls.action` ausente ou `name` fora de `send_message`/`set_model` | **bloco descartado** | nunca inventar um envio |
| `send_message` sem `template` | **bloco descartado** | idem |
| `controls.fields` com mais de 4 | corta nos 4 primeiros; placeholder que aponta para campo cortado invalida o bloco | teto da spec (4.4) |
| `sandbox.html` > 12000, `css` > 4000, `js` > 8000 | html estoura → bloco fora; css/js estouram → campo fora | caber nos 16000 do fence com folga |
| `sandbox.initial_height` string numérica/decimal | arredonda; fora de 120–800 → 300 | tolerância de tipo |

A prosa tem de fazer sentido sem os blocos. Bloco é complemento. Se o dado importante só existir no JSON, o turno falhou o critério de aceite, mesmo com o widget bonito.

### 4.1 `progress`

```json
{
  "id": "seo",
  "type": "progress",
  "label": "Auditoria SEO",
  "value": 7,
  "max": 10,
  "steps": [
    {"id": "titulos", "label": "Títulos", "state": "done"},
    {"id": "links", "label": "Links", "state": "active"}
  ]
}
```

- `label`: 1 a 80 caracteres.
- `value` e `max` vêm juntos ou não vêm. `max` entre 1 e 1000. `value` entre 0 e `max`.
- `steps`: 0 a 12. `state` só `pending`, `active`, `done`, `error`. No máximo um `active`.
- Tem de haver `value`+`max` ou pelo menos um step. Os dois juntos são válidos.
- `id` do step: mesma regra do `id` do bloco.

Exemplo de produto: "Auditoria SEO — 7 de 10 verificações concluídas".

### 4.2 `card`

```json
{
  "id": "esp32",
  "type": "card",
  "title": "ESP32-S3",
  "body": "MCU com Wi-Fi e Bluetooth.",
  "image": {"url": "/attachments/esp32.jpg", "alt": "Placa ESP32 sobre a mesa"},
  "facts": [{"label": "Flash", "value": "8 MB"}]
}
```

- `title`: 1 a 80 caracteres.
- `body`: opcional, até 400 caracteres.
- `facts`: 0 a 6. `label` e `value` de 1 a 40 caracteres.
- `image` opcional. Se vier, `url` e `alt` são obrigatórios. `alt` de 1 a 120 caracteres.
- URL de imagem, regras da seção 6. URL recusada: o cartão permanece, sem a foto.

Exemplo de produto: foto do componente ao lado da explicação. A explicação continua na prosa.

### 4.3 `chart`

```json
{
  "id": "custos",
  "type": "chart",
  "title": "Custo por 1M tokens",
  "kind": "bar",
  "x_key": "modelo",
  "series": [{"key": "usd", "label": "USD"}],
  "rows": [
    {"modelo": "Groq 8B", "usd": 0.05},
    {"modelo": "Gemini Flash", "usd": 0.1}
  ]
}
```

- `kind`: `bar`, `line` ou `compare`.
- `bar`: exatamente 1 série. `line`: 1 a 3. `compare`: 2 a 4. `compare` é barra agrupada, não um tipo novo de eixo.
- `rows`: 1 a 24. Cada row é objeto. `x_key` existe em todas e o valor é string de 1 a 40 caracteres.
- Cada `series.key` existe em todas as rows e o valor é número finito. Sem string numérica. Sem `NaN`.
- O modelo não escolhe cor, eixo extra, tooltip HTML nem biblioteca.
- Cores saem da paleta fixa do host, por índice da série: `--primary`, `--cyan`, `--warning`, `--success`. Fundo do cartão: `--surface-card`. Texto: `--ink` e `--body`. Borda: `--hairline`. Definidas em `frontend/src/index.css`.

Exemplo de produto: comparar custo, tempo ou desempenho de modelos. O modelo manda os números. O Recharts desenha.

### 4.4 `controls`

```json
{
  "id": "tarefa",
  "type": "controls",
  "title": "Executar tarefa",
  "submit_label": "Executar",
  "fields": [
    {
      "id": "agente",
      "kind": "select",
      "label": "Agente",
      "options": [
        {"value": "seo", "label": "Auditoria SEO"},
        {"value": "custo", "label": "Comparar custos"}
      ]
    },
    {"id": "nota", "kind": "text", "label": "Nota"}
  ],
  "action": {
    "name": "send_message",
    "template": "Execute o agente {agente}. Nota: {nota}"
  }
}
```

- Um bloco, uma ação.
- `submit_label`: 1 a 32 caracteres.
- `fields`: 1 a 4.
- `kind`: `text`, `select`, `number` ou `range` (slider).
- `text`: valor máximo 200 caracteres no cliente, mesmo que o modelo não declare limite.
- `number` e `range`: `min` e `max` obrigatórios, números finitos, `min` < `max`, intervalo de no máximo 1_000_000. `step` opcional (padrão 1). O host corta o valor para dentro do intervalo.
- `select`: 2 a 8 opções. `value` de 1 a 64, `[a-zA-Z0-9._-]+`. `label` de 1 a 40.
- `id` de field: 1 a 32, `[a-z0-9_]+`.
- **Reatividade local (cálculo em tempo real):** Opcional `computed`: `{"template": "Total por pessoa: R$ {resultado}", "formula": "({total} * (1 + {gorjeta}/100)) / {pessoas}"}`. Avaliado estritamente no cliente com parser aritmético seguro (sem `eval`). Os inputs e sliders atualizam o display na hora, sem round-trip de rede para o servidor (inspirado na calculadora e divisor de contas do OpenIntelligentUI).

Ações v1, e só estas:

1. `send_message`. `template` de 1 a 500 caracteres. Todo `{id}` do template tem de ser um field do bloco. Placeholder desconhecido descarta o bloco. No clique, o host interpola e envia pelo mesmo caminho de mensagem do composer. O texto aparece como bolha do usuário. Não há envio automático.
2. `set_model`. `field` aponta para o único `select` do bloco. Opções vindas do modelo são ignoradas. O host preenche o select com `models` do `useStore` (id visível para o usuário, valor interno `model_id`). No clique, se o id existir na lista do usuário, chama `selectModel(modelId, providerId)` em `frontend/src/store/useStore.ts`. Id inventado não muda nada e o controle mostra erro curto. Não envia mensagem.

Sem ação de apagar conversa, trocar chave, abrir URL arbitrária, rodar código arbitrário no host ou chamar API fora do fluxo de chat já existente.

### 4.5 `sandbox` (Extensão Nível 2 / Fase 7 — Open Generative UI)

Para ferramentas dinâmicas sob demanda (calculadoras complexas, simulações interativas, Three.js, visualizadores de algoritmos):

```json
{
  "id": "simulador",
  "type": "sandbox",
  "title": "Simulador de Alocação de Tokens",
  "initial_height": 340,
  "html": "<div id='app'>...</div>",
  "css": "#app { display: flex; flex-direction: column; }",
  "js": "function update() { ... }",
  "standalone_download": true
}
```

- **Pré-dimensionamento Anti-Layout Shift:** `initial_height` (120 a 800 px) reserva imediatamente o espaço vertical na bolha, impedindo saltos visuais durante o streaming.
- **Isolamento de Segurança:** Renderizado em `<iframe sandbox="allow-scripts allow-forms">`. Sem `allow-same-origin` (zero acesso a cookies, `localStorage` ou tokens do Multi+).
- **Injeção de Design Tokens (Theme Bridge):** O host injeta automaticamente um bloco `<style>` com as variáveis CSS de `frontend/src/index.css` (`--primary`, `--surface-card`, `--ink`, `--body`, etc.) e a classe de tema `.dark` / `.light` correspondente.
- **Host Bridge Seguro via `postMessage`:** Comunicação bidirecional estrita: o sandbox só pode disparar `{ type: 'nexus_action', action: 'send_message', text: '...' }` para o host. O host valida a mensagem antes de encaminhar ao chat.
- **1-Click Export Standalone:** Quando `standalone_download` for true, o cartão exibe botão para baixar o código como arquivo HTML autônomo funcional com as dependências embutidas.

## 5. Persistência e stream

Tabela nova, criada no `init_db` de `backend/database.py` no mesmo estilo das migrações incrementais (try/select, senão create):

```sql
CREATE TABLE IF NOT EXISTS message_ui_blocks (
    message_id TEXT PRIMARY KEY REFERENCES messages(id) ON DELETE CASCADE,
    payload    TEXT NOT NULL,
    source     TEXT NOT NULL CHECK(source IN ('host', 'model')),
    created_at TEXT DEFAULT (datetime('now'))
);
```

`payload` é o envelope já validado, `{"v":1,"blocks":[...]}`. Não é o fence cru.

`messages.content` guarda a prosa com o fence removido. Se a remoção falhar, grava a prosa e não grava bloco. Nunca grava o JSON dentro de `content`.

Eventos, acrescentados em `WSMessage` (`frontend/src/types.ts`):

- `stream_end` ganha `ui_blocks?: UiEnvelope | null`.
- `ui_progress`: `{ type: 'ui_progress'; block: ProgressBlock }`. Só o servidor emite. Substitui o bloco de mesmo `id` na mensagem em stream. Não vem do modelo no meio dos tokens.

Ao recarregar a conversa, a API de mensagens devolve `ui_blocks` junto da mensagem. O frontend valida de novo. Payload inválido no banco: mostrar só a prosa.

Histórico reenviado ao modelo: só `content`. Sem payload visual. Sem frase do tipo "a resposta anterior tinha um gráfico".

Cache exato (`backend/cache/manager.py`) hasheia `messages`. Como `content` não inclui o JSON, um hit de cache devolve a prosa. O bloco visual não entra no cache na v1. Hit de cache não reconstitui widget. Isso é aceitável: o cache devolve texto, como hoje.

TTS lê `content`. Não lê label de botão. Por isso a prosa tem de carregar a informação.

## 6. Imagem

O browser busca a imagem. O backend não faz proxy na v1. Proxy de URL inventada pelo modelo viraria SSRF.

Fonte confiável, só estas:

1. Arquivo local do app: URL relativa que começa com `/`, ou URL absoluta cujo host é o host da página. Anexos já servidos pelo Nexus entram aqui (`file_url` / `thumbnail_url` do próprio backend).
2. Host remoto listado em `image_hosts` da configuração efetiva (painel admin ou, enquanto ninguém salvou lá, `INTELLIGENT_UI_IMAGE_HOSTS`; lista separada por vírgula, padrão vazia). O modelo não escolhe a lista.
3. `http` em IP privado (10/8, 172.16/12, 192.168/16, 127/8) ou sufixo `.local`, somente se `allow_private_http` estiver ligado (painel ou `INTELLIGENT_UI_ALLOW_PRIVATE_HTTP=true`). Padrão `false`. Foto de ESP32 na rede de casa exige essa flag, ou um upload como anexo. Não fica aberta por padrão.

Recusar sempre: comprimento acima de 2048, userinfo (`user:pass@`), `javascript:`, `data:`, `blob:`, `file:`, e qualquer `https` cujo host não esteja na lista nem seja o host da página.

O backend tira a imagem do bloco se a URL falhar. O cartão permanece. O frontend repete a checagem antes do `<img>`, com `window.location.host` e a lista que o servidor já usa (ela chega por `GET /api/intelligent-ui/config`, carregada no boot e guardada no store). A lista não vem do modelo.

No `<img>`: `referrerPolicy="no-referrer"`, `loading="lazy"`, `alt` do contrato, largura máxima da bolha. Falha de carga: sumir a imagem, ficar o cartão.

## 6.1 Transporte

A nota oferece SSE para fluxo unidirecional e WebSocket para interação de ida e volta. O Nexus já tem WebSocket de chat. Segundo canal (SSE) duplicaria autenticação e reconexão, e o clique do controle precisa voltar pelo mesmo lugar que a mensagem.

Por isso:

- progresso do host: evento `ui_progress` no socket atual;
- bloco do modelo: campo `ui_blocks` em `stream_end`;
- clique: `sendMessage` do chat, já autenticado.

Sem endpoint SSE novo.

## 7. Segurança, acessibilidade e prevenção de layout shift

- Pintar texto com nó de texto React. Nunca `dangerouslySetInnerHTML` na bolha principal.
- Não executar string do modelo no DOM do host.
- **Isolamento de Sandbox (Nível 2 / Fase 7):** Qualquer código dinâmico gerado pelo modelo roda exclusivamente em `<iframe sandbox="allow-scripts allow-forms">`. Sem `allow-same-origin` (zero acesso ao storage ou tokens do host). Sem `allow-top-navigation`.
- **Prevenção de Layout Shift (Zero CLS):** O container do bloco reserva o espaço vertical usando `initial_height` antes de iniciar a pintura do componente, eliminando saltos bruscos na conversa durante a leitura do usuário (regra de ouro do OpenIntelligentUI).
- **Theme Bridge (Design Tokens):** Os blocos nativos usam diretamente os tokens de `frontend/src/index.css`. O container sandbox recebe injeção automática de `<style>` com `--primary`, `--surface-card`, `--ink`, etc., garantindo que ferramentas sob demanda tenham a mesma aparência nativa do Multi+ (resolvendo o problema de harmonia do design system).
- Clique em controle é gesto do usuário. Nada dispara no `stream_end`.
- Ação autorizada é nome fechado, conferido no backend (`validate_envelope`), não no clique solto do browser. v1 tem `send_message` e `set_model`.
- `send_message` entra no WebSocket de chat já autenticado. Não há endpoint novo que execute string.
- `set_model` só aceita id que o servidor já listou para aquele usuário. Não é comando de shell.
- Script, arquivo do disco e controle de outro serviço não são ação de widget. Se um dia existirem, o backend autoriza o nome da ação. O modelo não manda o comando.
- Payload de bloco não sai para telemetria de terceiro. Uso familiar.
- Alvos de toque do controle: mínimo 44×44 px, como em `PRODUCT.md`.
- `prefers-reduced-motion`: barra sem animação de loop. Transição de step é corte seco.
- Contraste dos tokens já usados no chat. Sem cor nova.
- Barra de progresso: `role="progressbar"`, `aria-valuenow`, `aria-valuemin`, `aria-valuemax`, `aria-label` = `label`. Step list: `role="list"`.
- Gráfico: a prosa e, se couber, uma tabela simples `sr-only` com os mesmos `rows`. Quem não vê o desenho lê o número.

## 8. Catálogo no prompt e Visualization Router

Texto fixo, arquivo futuro `backend/ui_blocks/catalog.txt`. Injeção só quando a flag está ligada e o turno passa no classificador/heurístico de visualização. Teto: 400 tokens estimados por `len(texto) / 4`. Se passar, não injetar e seguir sem visual.

**Princípios do Visualization Router (inspirados no OpenIntelligentUI):**
1. *Fato direto / prosa explicativa:* Resposta em Markdown puro sem envelope (sem poluição visual).
2. *Métricas, processos e comparações pontuais:* Catálogo nativo Nível 1 (`progress`, `card`, `chart`).
3. *Cálculos com variáveis, simulações e ferramentas ativas:* `controls` reativo ou `sandbox` isolado.

Heurístico, case insensitive, na última mensagem do usuário. Ligar o catálogo se qualquer item bater:

- regex: `gráfico|grafico|compar|versus|\bvs\b|etapa|progresso|escolh|selecion|cartão|cartao|imagem|foto|indicador|barra|calcul|simul`
- ou três ou mais números e uma destas palavras: `custo`, `tempo`, `modelo`, `%`, `taxa`, `valor`

Turno que não bater: sem catálogo, sem cobrança de token extra, sem widget de modelo. Bloco de host (Fusion, busca, upload) não depende deste heurístico.

Texto do catálogo, copiar literal na implementação. O bloco usa quatro crases para o fence interno não fechar o externo.

~~~~
Se um visual ajudar, anexe um único fence no final, depois da prosa. A prosa tem de bastar sozinha.

```nexus-ui
{"v":1,"blocks":[]}
```

Máximo 4 blocos. Tipos: progress, card, chart, controls, sandbox.
progress: label, value, max, steps com state pending|active|done|error.
card: title, body, image com url e alt, facts com label e value.
chart: kind bar|line|compare, x_key, series, rows numéricas. Sem cor.
controls: fields text|select|number|range, computed opcional e uma action.
action send_message usa template com {id_do_campo}.
action set_model usa field do select. Não invente id de modelo.
sandbox: title, initial_height, html, css, js, standalone_download (para simulações/calculadoras dinâmicas isoladas).
Não escreva HTML na bolha principal. URL de imagem só se for arquivo do app ou host da lista confiável. Sem visual, sem fence.
~~~~

O fence de exemplo dentro do catálogo é texto de instrução, não um bloco a renderizar. O extrator só olha a resposta do assistente, não o system prompt.

## 9. Onde encaixa

Não criar um app paralelo.

| Peça | Arquivo atual | Mudança futura |
|---|---|---|
| Bolha | `frontend/src/components/MessageBubble.tsx` | Depois do markdown, `<DynamicRenderer />`. Não mover o markdown para dentro do cartão. |
| Tipos | `frontend/src/types.ts` | `UiEnvelope` e campos novos de WS e `Message`. |
| Estado | `frontend/src/store/useStore.ts` | `finalizeStream` recebe `ui_blocks`. `ui_progress` atualiza a mensagem em stream. `selectModel` já existe e é a única via de `set_model`. |
| Chat WS | `backend/routers/chat.py` | Extrair fence antes de persistir. |
| Persistência | `backend/orchestration/persist_turn.py` | Gravar prosa limpa. Insert do payload na tabela nova. |
| Schema | `backend/database.py` | `CREATE TABLE message_ui_blocks` dentro de `init_db`. |
| Flag | `.env.example` + `backend/ui_blocks/config.py` | `INTELLIGENT_UI_ENABLED=false` é só o valor inicial. Ausente significa falso. A tabela singleton `intelligent_ui_config` (salva por `POST /api/intelligent-ui/config`, admin, em Configurações → Ferramentas → Interface Inteligente) manda sobre o `.env` assim que existe uma linha; vale no turno seguinte, sem restart. Com a flag desligada o turno é idêntico ao de antes do recurso: sem catálogo no prompt, sem extração do fence (o texto fica intacto, fence vira bloco de código), sem linha em `message_ui_blocks`, sem `ui_blocks` no `stream_end`, e o `DynamicRenderer` devolve `null` mesmo que exista payload antigo. Em modo voz o catálogo nunca entra. |
| Config | `backend/routers/intelligent_ui.py`, `frontend/src/components/IntelligentUiSettings.tsx`, `frontend/src/ui/hooks/useIntelligentUi.ts` | `GET` para qualquer usuário autenticado (o frontend precisa da flag e dos hosts), `POST` só admin. O frontend não reparseia o markdown: o envelope vem sempre do servidor. |

Módulo novo, separado do resto da UI. O esboço da nota era `src/ui/`. No repo o caminho real é `frontend/src/ui/`. Nomes dos cartões seguem a nota. `ControlsCard` entra com formulários e calculadoras reativas. `SandboxCard` para ferramentas dinâmicas da Fase 7.

```
frontend/src/ui/DynamicRenderer.tsx
frontend/src/ui/components/ProgressCard.tsx
frontend/src/ui/components/ChecklistCard.tsx
frontend/src/ui/components/ImageCard.tsx
frontend/src/ui/components/ChartCard.tsx
frontend/src/ui/components/ControlsCard.tsx
frontend/src/ui/components/SandboxCard.tsx
frontend/src/ui/themeBridge.ts
frontend/src/lib/nexusUi.ts
frontend/src/lib/nexusUi.test.ts
backend/ui_blocks/validate.py
backend/ui_blocks/extract.py
backend/ui_blocks/catalog.txt
backend/tests/test_ui_blocks.py
```

`DynamicRenderer` recebe o envelope, chama `parseUiEnvelope`, olha o `type` e monta um cartão. Tipo sem cartão: null, prosa intacta. Cada cartão é `React.lazy`. Import estático de `recharts` em `DynamicRenderer.tsx` ou em `MessageBubble.tsx` é erro de implementação.

Um bloco `progress` com `value` e `max` monta `ProgressCard`. Com `steps`, monta `ChecklistCard`. Com os dois, monta os dois. Continua um bloco só no teto de 4.

`ChartCard` é o único arquivo que importa `recharts`. `App.tsx` importa `AdminPanel` de forma estática (linha 8), e `UsageDashboard.tsx` / `RankingsView.tsx` já importam `recharts`. Enquanto essa cadeia for estática, a lib pode continuar no chunk principal. O plano 04 inclui deixar o admin atrás de `React.lazy` se um build mostrar `recharts` no chunk do chat. Sem segunda biblioteca de gráfico.

ChatKit não entra nesse módulo. Ver [07-chatkit-referencia.md](07-chatkit-referencia.md).
Open Intelligent UI detalhado em [08-open-intelligent-ui-referencia.md](08-open-intelligent-ui-referencia.md).

## 10. Fora de escopo

- ~~Implementar agora. Esta pasta é plano.~~ *(Superado: implementado em 2026-10.)*
- Substituir `ArtifactPanel` ou aceitar HTML/JSX desprotegido na bolha principal.
- Instalar SDKs pesados de terceiros ou desenhar árvore livre de widgets no host.
- Abrir SSE ao lado do WebSocket.
- Aceitar qualquer URL `https` como imagem.
- Mais de 4 blocos, dashboard, vídeo, áudio player, upload novo (anexo já existe).
- Proxy de imagem.
- Widget no cache semântico ou exato.
- Ação de widget que rode script, leia arquivo arbitrário ou controle outro serviço.
- Ligar a flag em produção antes do plano 06 da fase correspondente.
- Mudar voz, ranking, Fusion, memória ou cadastro.

## 11. Fases

| Fase | Plano | Entrega testável |
|---|---|---|
| 1 | 01-plano-fundacao | Flag off. Parser e validador cobertos por teste. Tabela criada. Bolha ainda não pinta. |
| 2 | 02-plano-indicadores | Barra e steps na bolha, com flag on em dev. |
| 3 | 03-plano-cartoes-imagens | Cartão com e sem foto. URL ruim não quebra a bolha. |
| 4 | 04-plano-graficos | bar, line, compare com dados do contrato. |
| 5 | 05-plano-controles | Formulários e calculadoras reativas com send_message e set_model, só no clique. |
| 6 | 06-criterios-aceite | Lista do que impede ligar a flag no servidor da família. |
| 7 | 09-plano-sandbox-e-exportacao | Micro-ferramentas sob demanda em sandbox isolado, theme bridge e exportação 1-click HTML. |

Cada fase deixa o chat atual intacto com a flag desligada.

## 12. Riscos

| Risco | Corte |
|---|---|
| Modelo inventa JSON quebrado | Descartar bloco ou envelope. Prosa permanece. |
| Modelo esconde o fato só no gráfico | Critério de aceite: prosa completa. Catálogo diz isso. |
| Clique dispara ação que o usuário não pediu | Sem auto-submit. Ações fora da lista morrem no validador. |
| URL de imagem rastreia ou aponta para esquema perigoso | Seção 6. Sem proxy. `https` fora da lista não pinta. |
| Segundo canal SSE | Recusado. Mesmo WebSocket do chat. |
| Copiar o ChatKit inteiro | Referência só. Sem SDK. Sem árvore livre de nós. |
| Prompt inchado em todo turno | Heurístico. Sem match, sem catálogo. |
| Flag ligada cedo demais | Padrão falso. `.env.example` documenta falso. |
