# Intelligent UI — visão e spec

**Estado:** spec para implementação futura. Não autoriza código de produto até um pedido explícito de executar um plano.

**Data:** 2026-10-08

**Produto:** Nexus Local / Multi+ (`/home/osmar/nexuslocal`). Uso familiar. Cadastro público fechado. Cada usuário usa a própria chave.

## 1. Decisão

A resposta do chat deixa de ser só markdown quando um visual ajuda. O modelo não entrega interface. Entrega dados. O frontend, já montado, escolhe o componente.

Isso não reescreve o Multi+. Não carrega um segundo app dentro de cada resposta. O modelo nunca recebe o código dos componentes. Recebe, no máximo, um catálogo curto (seção 8), e só no turno em que o visual é plausível.

A nota pede JSON com esquema fixo, atualização por SSE ou WebSocket, gráfico carregado sob demanda, imagem local ou URL confiável, e lista fechada de componentes e ações. A adaptação abaixo usa o que o Nexus já tem. Não abre canal novo e não instala o ChatKit.

| Necessidade | Pedido da nota | Decisão no Nexus |
|---|---|---|
| Tela | Não substituir o Multi+ | Frontend atual. React 18.3, Vite, Zustand. `MessageBubble.tsx` continua dono da bolha. |
| Módulo | `src/ui/DynamicRenderer` e cartões | `frontend/src/ui/`. O app mora em `frontend/`, não numa pasta `src/` na raiz. |
| Formato | JSON validado com esquema fixo | Envelope `nexus-ui/1`. Backend valida antes de gravar. Frontend valida de novo antes de pintar. |
| Progresso | SSE unidirecional ou WebSocket bidirecional | Sem SSE. O chat já é WebSocket em `backend/routers/chat.py`. Barra e clique usam esse socket. |
| Gráficos | Biblioteca sob demanda | `recharts` 3.9.2, já dependência. `ChartCard` entra por `React.lazy`. Sem import estático de `recharts` na bolha. |
| Imagens | Arquivo local ou URL confiável | Anexo servido pelo próprio app, ou host listado em `INTELLIGENT_UI_IMAGE_HOSTS`. `https` solto não passa. |
| Segurança | Lista de componentes e de ações | `DynamicRenderer` só monta os cartões desta spec. Ação fora da lista morre no backend. |
| Liga/desliga | — | `INTELLIGENT_UI_ENABLED`, padrão `false`. |

Rejeitado para a v1: Thesys, SDK do ChatKit, Apps SDK, iframe, SSE paralelo, `dangerouslySetInnerHTML`, JSX emitido pelo modelo, eval, árvore livre de layout (Box, Row, Spacer) e mandar o fonte do Multi+ no prompt.

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
- `kind`: `text`, `select` ou `number`.
- `text`: valor máximo 200 caracteres no cliente, mesmo que o modelo não declare limite.
- `number`: `min` e `max` obrigatórios, números finitos, `min` < `max`, intervalo de no máximo 1_000_000. O host corta o valor para dentro do intervalo.
- `select`: 2 a 8 opções. `value` de 1 a 64, `[a-zA-Z0-9._-]+`. `label` de 1 a 40.
- `id` de field: 1 a 32, `[a-z0-9_]+`.

Ações v1, e só estas:

1. `send_message`. `template` de 1 a 500 caracteres. Todo `{id}` do template tem de ser um field do bloco. Placeholder desconhecido descarta o bloco. No clique, o host interpola e envia pelo mesmo caminho de mensagem do composer. O texto aparece como bolha do usuário. Não há envio automático.
2. `set_model`. `field` aponta para o único `select` do bloco. Opções vindas do modelo são ignoradas. O host preenche o select com `models` do `useStore` (id visível para o usuário, valor interno `model_id`). No clique, se o id existir na lista do usuário, chama `selectModel(modelId, providerId)` em `frontend/src/store/useStore.ts`. Id inventado não muda nada e o controle mostra erro curto. Não envia mensagem.

Sem ação de apagar conversa, trocar chave, abrir URL arbitrária, rodar código ou chamar API fora do fluxo de chat já existente.

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
2. Host remoto listado em `INTELLIGENT_UI_IMAGE_HOSTS` (lista separada por vírgula, padrão vazia). O modelo não escolhe a lista.
3. `http` em IP privado (10/8, 172.16/12, 192.168/16, 127/8) ou sufixo `.local`, somente se `INTELLIGENT_UI_ALLOW_PRIVATE_HTTP=true`. Padrão `false`. Foto de ESP32 na rede de casa exige essa flag, ou um upload como anexo. Não fica aberta por padrão.

Recusar sempre: comprimento acima de 2048, userinfo (`user:pass@`), `javascript:`, `data:`, `blob:`, `file:`, e qualquer `https` cujo host não esteja na lista nem seja o host da página.

O backend tira a imagem do bloco se a URL falhar. O cartão permanece. O frontend repete a checagem antes do `<img>`, com `window.location.host` e a lista que o servidor já usa. A lista não vem do modelo.

No `<img>`: `referrerPolicy="no-referrer"`, `loading="lazy"`, `alt` do contrato, largura máxima da bolha. Falha de carga: sumir a imagem, ficar o cartão.

## 6.1 Transporte

A nota oferece SSE para fluxo unidirecional e WebSocket para interação de ida e volta. O Nexus já tem WebSocket de chat. Segundo canal (SSE) duplicaria autenticação e reconexão, e o clique do controle precisa voltar pelo mesmo lugar que a mensagem.

Por isso:

- progresso do host: evento `ui_progress` no socket atual;
- bloco do modelo: campo `ui_blocks` em `stream_end`;
- clique: `sendMessage` do chat, já autenticado.

Sem endpoint SSE novo.

## 7. Segurança e acessibilidade

- Pintar texto com nó de texto React. Nunca `dangerouslySetInnerHTML` nestes componentes.
- Não executar string do modelo.
- Clique em controle é gesto do usuário. Nada dispara no `stream_end`.
- Ação autorizada é nome fechado, conferido no backend (`validate_envelope`), não no clique solto do browser. v1 só tem `send_message` e `set_model`.
- `send_message` entra no WebSocket de chat já autenticado. Não há endpoint novo que execute string.
- `set_model` só aceita id que o servidor já listou para aquele usuário. Não é comando de shell.
- Script, arquivo do disco e controle de outro serviço não são ação de widget. Se um dia existirem, o backend autoriza o nome da ação. O modelo não manda o comando.
- Payload de bloco não sai para telemetria de terceiro. Uso familiar.
- Alvos de toque do controle: mínimo 44×44 px, como em `PRODUCT.md`.
- `prefers-reduced-motion`: barra sem animação de loop. Transição de step é corte seco.
- Contraste dos tokens já usados no chat. Sem cor nova.
- Barra de progresso: `role="progressbar"`, `aria-valuenow`, `aria-valuemin`, `aria-valuemax`, `aria-label` = `label`. Step list: `role="list"`.
- Gráfico: a prosa e, se couber, uma tabela simples `sr-only` com os mesmos `rows`. Quem não vê o desenho lê o número.

## 8. Catálogo no prompt

Texto fixo, arquivo futuro `backend/ui_blocks/catalog.txt`. Injeção só quando a flag está ligada e o turno passa no heurístico. Teto: 400 tokens estimados por `len(texto) / 4`. Se passar, não injetar e seguir sem visual.

Heurístico, case insensitive, na última mensagem do usuário. Ligar o catálogo se qualquer item bater:

- regex: `gráfico|grafico|compar|versus|\bvs\b|etapa|progresso|escolh|selecion|cartão|cartao|imagem|foto|indicador|barra`
- ou três ou mais números e uma destas palavras: `custo`, `tempo`, `modelo`, `%`

Turno que não bater: sem catálogo, sem cobrança de token extra, sem widget de modelo. Bloco de host (Fusion, busca, upload) não depende deste heurístico.

Texto do catálogo, copiar literal na implementação. O bloco usa quatro crases para o fence interno não fechar o externo.

~~~~
Se um visual ajudar, anexe um único fence no final, depois da prosa. A prosa tem de bastar sozinha.

```nexus-ui
{"v":1,"blocks":[]}
```

Máximo 4 blocos. Tipos: progress, card, chart, controls.
progress: label, value, max, steps com state pending|active|done|error.
card: title, body, image com url e alt, facts com label e value.
chart: kind bar|line|compare, x_key, series, rows numéricas. Sem cor.
controls: fields text|select|number e uma action.
action send_message usa template com {id_do_campo}.
action set_model usa field do select. Não invente id de modelo.
Não escreva HTML, JavaScript nem CSS. URL de imagem só se for arquivo do app ou host da lista confiável. Sem visual, sem fence.
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
| Flag | `.env.example` | `INTELLIGENT_UI_ENABLED=false`. Ausente significa falso. |

Módulo novo, separado do resto da UI. O esboço da nota era `src/ui/`. No repo o caminho real é `frontend/src/ui/`. Nomes dos cartões seguem a nota. `ControlsCard` não estava no esboço de quatro pastas; entra porque a nota também pede botões e formulários.

```
frontend/src/ui/DynamicRenderer.tsx
frontend/src/ui/components/ProgressCard.tsx
frontend/src/ui/components/ChecklistCard.tsx
frontend/src/ui/components/ImageCard.tsx
frontend/src/ui/components/ChartCard.tsx
frontend/src/ui/components/ControlsCard.tsx
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

## 10. Fora de escopo

- Implementar agora. Esta pasta é plano.
- Substituir `ArtifactPanel` ou aceitar HTML/JSX na bolha.
- Instalar ChatKit, Thesys ou desenhar árvore livre de widgets.
- Abrir SSE ao lado do WebSocket.
- Aceitar qualquer URL `https` como imagem.
- Mais de 4 blocos, dashboard, mapa, vídeo, áudio player, upload novo (anexo já existe).
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
| 5 | 05-plano-controles | send_message e set_model, só no clique. |
| 6 | 06-criterios-aceite | Lista do que impede ligar a flag no servidor da família. |

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
