# Referências: AnswerUI, OpenUI (Thesys) e Open WebUI

**Data:** 2026-10-14
**Para quê:** fechar a paridade de funcionalidades com o Intelligent UI do ChatGPT e melhorar a renderização dos cartões nativos, usando três repositórios como modelo. Este arquivo é a leitura; os planos derivados são o [11-plano-camada-visual.md](11-plano-camada-visual.md), o [12-plano-paridade-intelligent-ui.md](12-plano-paridade-intelligent-ui.md) e o [13-plano-cenas-2d-3d.md](13-plano-cenas-2d-3d.md).

Leitura feita direto do código em 2026-10-14 (clones rasos; versões: answerui `main` de 2026-10-08, openui `main` de 2026-10-14 com spec 1.0, open-webui `main`). Nada aqui depende de instalar pacote novo no Nexus.

## 0. Resumo executivo

| Repositório | O que é | Licença | O que levamos | O que fica de fora |
|---|---|---|---|---|
| [0xcro3dile/answerui](https://github.com/0xcro3dile/answerui) | Alternativa aberta ao Intelligent UI do ChatGPT. App Next.js fino em cima do OpenUI, com um componente próprio `Scene` (cenas 2D/3D em iframe) e um conjunto de regras de prompt muito bem calibradas. | MIT | Regras de prompt (`answerRules`), arquitetura de cena (runtime local, protocolo `params`/`report`, `pause/play/restart/fullscreen`, carga só perto do viewport, botão "Fix it"), segurança do iframe (guarda de navegação, CSP sem rede). | OpenUI Lang, Next.js, React 19, `@openuidev/*`. |
| [thesysdev/openui](https://github.com/thesysdev/openui) | "The Open Standard for Generative UI": linguagem compacta de streaming (OpenUI Lang), parser tolerante, estado reativo, biblioteca de componentes React com design system completo. | MIT | Ideias de contrato: render progressivo ("todo prefixo é uma página válida"), recuperação por menor unidade com erro estruturado e `hint`, estado `$var` compartilhado entre componentes, catálogo de componentes (Metric, Table, Steps, Callout, FollowUp, OptionCards), tokens de design e detalhes visuais (CardHeader, MetricIndicator, Steps, tooltip de gráfico, skeletons). | A linguagem em si, os pacotes npm, d3 nos gráficos, `Query`/`Mutation` genéricos, árvore livre de layout. |
| [open-webui/open-webui](https://github.com/open-webui/open-webui) | Chat self-hosted completo (Svelte + FastAPI). Interessa a camada de render de mensagem: artefatos HTML em iframe, code block com Executar/Pré-visualizar/Recolher, Mermaid só com fence fechado, alerts GitHub, follow-ups, elicitação (`AskUserCard`). | **Open WebUI License** (BSD-3 com cláusula de marca). **Só ideias, nenhuma linha copiada.** | Padrões de UX: flags de sandbox configuráveis, bloqueio de navegação externa no iframe, baixar artefato, render de diagrama adiado até o fence fechar, lista de follow-ups, cartão de pergunta com opções + "outro". | Código, Svelte, Pyodide, Tailwind. |

Decisão de arquitetura mantida: o Nexus continua com envelope JSON `nexus-ui/1`, lista fechada de blocos, validação dupla (Python e TS), WebSocket existente, Recharts e Vanilla CSS. O que muda é o que a lista fechada cobre, como a bolha pinta durante o stream, e a qualidade visual dos cartões. Nenhum dos três repositórios entra como dependência.

## 1. O que o ChatGPT chama de Intelligent UI

Pelo que o AnswerUI e o OpenIntelligentUI (doc 08) descrevem e pelo que o produto mostra: gráficos interativos, calculadoras reativas (divisão de conta, parcelamento) em que mexer um campo recalcula o texto da resposta, visualizadores passo a passo de algoritmos, itinerários, simulações 2D/3D (Three.js), formulários com opções, e a resposta aparecendo **enquanto** o modelo escreve. Quatro propriedades definem a experiência:

1. **Progressivo.** A interface aparece por partes durante o stream, sem salto de layout.
2. **Reativo sem o modelo.** Mexer num controle recalcula números no texto e nos cartões no cliente.
3. **Composto.** Métricas, tabela, gráfico, passos e botões de follow-up na mesma resposta.
4. **Vivo.** Cenas 2D/3D e simulações com play/pause e números que voltam para o texto.

Tabela de paridade (estado do Nexus em `main` `a0c2e74`):

| Capacidade do ChatGPT | Nexus hoje | Lacuna | Plano |
|---|---|---|---|
| Gráfico de barras/linhas/comparação | `chart` (Recharts) | Visual básico, sem formatação de número por locale, paleta fixa, sem estado vazio | 11 |
| KPI / número grande com variação | `card.facts` como chips | Sem bloco de métrica | 12 (bloco `metric`) |
| Tabela de dados | Não existe (markdown GFM na prosa) | Sem tabela nativa com alinhamento numérico | 12 (bloco `table`) |
| Passos / timeline | `progress.steps` (lista com ícones) | Visual de checklist, sem conector nem detalhe por passo | 11 (Steps) |
| Aviso / nota destacada | Não existe | — | 12 (bloco `callout`) |
| Pergunta com opções (escolha rápida) | `controls` select + botão | Sem cartões de opção clicáveis | 12 (bloco `options`) |
| Sugestões de follow-up | Não existe | — | 12 (bloco `follow_up`) |
| Calculadora reativa | `controls.computed` (1 fórmula, 1 badge) | Só um resultado; outros blocos não leem os campos | 12 (estado compartilhado) |
| Render progressivo durante o stream | Só blocos do host (`ui_progress`); blocos do modelo esperam o `stream_end` | O fence inteiro chega no fim | 12 (JSON parcial) |
| Erro do modelo vira pedido de correção | Descarte silencioso + telemetria | Usuário não sabe que um bloco caiu | 12 (laço de correção) |
| Simulação / cena 3D | `sandbox` (HTML/CSS/JS livre, módulos por esm.sh) | Sem runtime pronto, sem play/pause, sem `report()` de volta ao texto, depende de CDN | 13 |
| Mapa com itinerário | Não existe | Precisa de tiles externos | 12, seção "não agora" |

## 2. AnswerUI

### 2.1 Arquitetura

```
src/app/page.tsx          AgentInterface do @openuidev/react-ui + fetchLLM('/api/chat')
src/app/api/chat/route.ts POST → valida Host/Origin (anti DNS rebinding) → streamAnswer → NDJSON
src/server/llm.ts         OpenAI-compatible stream; TransformStream "holdUnfinishedStateLines"
src/core/prompt.ts        generateSystemPrompt({ library: spec.json, promptOptions: { bindings, examples, additionalRules } })
src/core/state-lines.ts   segura a linha "$var = ..." até o \n chegar
src/lib/library.ts        createLibrary({ ...openuiLibrary, components: [...openui, Scene] })
src/scene/Scene.tsx       componente React da cena (iframe, barra, erro, near-screen)
src/scene/document.ts     srcdoc da cena: CSP sem rede + runtime local + setup + código do modelo + start()
src/scene/protocol.ts     mensagens app↔cena, com leitura defensiva (limites de chaves e tamanho)
src/scene/runtime/*.ts    bundle IIFE local (esbuild → public/scene/runtime.js): clock, reporter, stage2d, stage3d
```

O app em si é pequeno: tudo que é linguagem, parser, estado e componentes vem do OpenUI. O valor do repositório para nós está em três lugares: as **regras de prompt**, a **cena** e os **cuidados de segurança**.

### 2.2 Regras de prompt que valem para o nosso catálogo

`src/core/prompt.ts` acrescenta `answerRules` às regras do OpenUI. Traduzidas para o vocabulário do Nexus (entram no `catalog.txt` dentro do teto de 400 tokens, ver plano 12):

- Pergunta curta ou factual: só prosa, sem cartão.
- Construir ferramenta interativa quando o usuário vai **ajustar números, comparar opções, planejar com entradas ou explorar dados**. Fora disso, prosa.
- Entradas primeiro, cada uma ligada a uma variável; todo resultado calculado a partir delas, para atualizar ao vivo.
- Valor de input de texto é texto: somar com função, não com `+`.
- Mostrar número calculado arredondado a 2 casas.
- Cena só para formas 3D, movimento e simulação; nunca para gráfico ou tabela (há componente para isso).
- Controles da cena ficam ao lado dela; os valores entram por `params` e são lidos a cada frame.
- O sandbox já dá câmera, luz, controles e loop: não criar renderer, não importar, não usar rede, timers ou DOM.
- Número que a expressão não calcula (raiz, potência, trigonometria) é calculado dentro da cena e devolvido com `report({nome: valor})`; o texto mostra `$sim.nome`.
- Criar objetos uma vez, atualizar em `onFrame`. Código < 60 linhas, sem `while`.
- A cena é a última instrução e vem com um texto que a descreve.

Essas regras são o motivo de o AnswerUI funcionar com modelos pequenos locais (Ollama). O nosso `catalog.txt` já tem o espírito ("a prosa tem de bastar sozinha"), mas não tem o gatilho positivo ("quando construir ferramenta") nem as regras de cálculo.

### 2.3 A cena: o que copiar (MIT)

`Scene` é um `sandbox` especializado. As diferenças para o nosso `SandboxCard` são todas boas ideias:

| Aspecto | AnswerUI `Scene` | Nexus `SandboxCard` hoje | Levar? |
|---|---|---|---|
| Runtime | Bundle local `public/scene/runtime.js` (three r186 + OrbitControls + CSS2DRenderer + loop) | esm.sh via importmap (rede) | Sim: runtime local servido pelo próprio app, CSP sem `connect-src` |
| Código do modelo | Só o miolo: `params`, `onFrame((t,dt)=>…)`, `report()`, `THREE`, `scene`, `camera`, `label()`, `ctx` (2D) | HTML+CSS+JS completos | Sim, como `kind: "scene"` (plano 13); `sandbox` livre continua |
| CSP | `default-src 'none'; script-src 'unsafe-inline' <runtime>; style-src 'unsafe-inline'; img-src data: blob:; base-uri 'none'` | `default-src 'none'` + esm.sh em `script-src`/`connect-src` + hosts de imagem | Sim para a cena |
| Sandbox | `sandbox="allow-scripts"` só | `allow-scripts allow-forms` | Cena sem `allow-forms` |
| Guarda de navegação | Conta `onLoad`; segundo load = "a cena tentou sair do sandbox" → erro | Não há | Sim, nos dois |
| Mensagens da cena | `readSceneMessage`: só `ready`, `report` (≤20 chaves, strings ≤200), `error` (≤500) | `__nexus_ogui_resize` e `nexus_action` | Sim: limites explícitos e tipos fechados |
| Barra | Título · Play/Pause · Restart · Fullscreen | Título · Baixar HTML | Sim (11) |
| Movimento reduzido | Começa pausada se `prefers-reduced-motion` | — | Sim |
| Carga | `IntersectionObserver` com `rootMargin: 100%`; longe do viewport desmonta (limite de contextos WebGL) | Monta sempre | Sim para cena; para `sandbox` montar ao aproximar e manter |
| Erro | `role=alert` com "Fix it" (manda ao modelo: `Fix the scene "<title>". It failed with: <msg>`) e "Restart" | — | Sim (12, laço de correção) |
| Tema | `theme {dark, text, accent}` no setup; troca de tema remonta | Tokens ao vivo por `postMessage` (melhor) | Manter o nosso |
| Clock | passo máximo 0,05 s; pausa não salta o tempo | — | Sim |
| Reporter | agrupa `report()` e envia no máximo a cada 100 ms, só se mudou | — | Sim |
| WebGL perdido | `webglcontextlost` → erro com Restart | — | Sim |

Trechos adaptados estão em [referencias-codigo/scene-protocol.ts](referencias-codigo/scene-protocol.ts), [referencias-codigo/scene-runtime-core.ts](referencias-codigo/scene-runtime-core.ts) e [referencias-codigo/scene-document.ts](referencias-codigo/scene-document.ts), com o cabeçalho de atribuição MIT.

### 2.4 Segurança do servidor

`e2e/security.spec.ts` testa três coisas que o nosso backend deve conferir no `routers/intelligent_ui.py` e no WebSocket: recusar `Host` estranho (DNS rebinding), recusar `Origin` de outro site, e `frame-ancestors 'none'` na página. O Nexus já tem auth por JWT; a checagem de `Origin` no handshake do WebSocket é barata e entra no plano 12 como item de segurança.

### 2.5 O que não levar

OpenUI Lang e os pacotes `@openuidev/*` (React 19, Next.js). O estado `$var` e as expressões são boas ideias, mas no Nexus entram como campos do JSON, não como linguagem nova.

## 3. OpenUI (Thesys)

### 3.1 O que é

Monorepo com `lang-core` (parser, prompt, runtime, sem framework), `react-lang` (renderer), `react-ui` (componentes + chat pronto), `react-headless`, `vue/svelte/angular-lang`, `langchain`, `a2ui`, CLI e docs. A peça central é a linguagem:

```
root = Card([header, chart])
header = Header("Monthly Revenue", "Last 6 months")
chart = BarChart(labels, [series])
labels = ["Jan", "Feb", "Mar", "Apr", "May", "Jun"]
series = Series("Revenue", [12000, 15000, 14000, 18000, 21000, 25000])
```

Uma instrução por linha, argumentos posicionais, referência antes da definição ("hoisting"), até 67% menos tokens que JSON (benchmarks no repositório). Spec 1.0 em `spec/{overview,language,prompt}.md` com fixtures de conformidade.

### 3.2 Ideias que entram no contrato do Nexus (sem trocar JSON por DSL)

**a) Todo prefixo é uma página válida (spec §4).** O cliente fecha strings e colchetes abertos e renderiza a cada chunk; instrução completa não muda mais; "pending não sobrescreve completed"; no fim do stream o resultado tem de ser igual ao parse do texto inteiro. No Nexus: durante o stream, procurar o fence aberto e extrair os itens **completos** de `blocks[]` com um scanner de JSON parcial (plano 12, "render progressivo"). Bloco completo pinta; bloco incompleto reserva altura. No `stream_end`, o validador normal manda; o resultado tem de ser idêntico ao de hoje.

**b) Recuperação pela menor unidade, com erro estruturado (spec §8).** "Um erro remove a menor unidade possível e o resto renderiza." Cada remoção vira um objeto `{source, code, statementId, component, path, message, hint}`, pronto para colar na conversa, e o modelo responde com um conserto de uma linha. No Nexus o validador já descarta campo → bloco → envelope; falta **devolver a lista de erros** e oferecer "Pedir correção" (plano 12).

**c) Estado reativo compartilhado (spec §2.9).** `$query` ligado a um input; qualquer componente que lê `$query` atualiza. No Nexus: campos de `controls` publicam valores por `id` dentro da mensagem; `metric.value`, `card.facts[].value`, `progress.value` e `chart.rows` podem usar expressões `={expr}` avaliadas pelo `safeMath` já existente (plano 12, "estado compartilhado"). Nada de `Query`/`Mutation`.

**d) Ações fechadas e com contexto.** `@ToAssistant(texto, contexto)`, `@OpenUrl`, `@Set`, `@Reset`, `@Run`. O Nexus tem `send_message` e `set_model`; o `options`/`follow_up` reaproveitam `send_message`. `@OpenUrl` não entra (link já é markdown).

**e) Regras de compatibilidade de biblioteca (spec §3).** "Só acrescentar props no fim; nunca reordenar ou remover; prop nova obrigatória tem default." No JSON isso vira: tipo novo é aditivo, cliente antigo descarta tipo desconhecido (regra que já temos), campo novo é opcional. Está escrito na seção 13 da spec.

**f) Vocabulário de componentes.** O que a biblioteca `openuiLibrary` oferece e que vale ter em versão nativa pequena no Nexus: `MetricIndicator` (valor grande, valor anterior riscado, tendência ↑/↓ colorida, subtexto), `Table/Col` (coluna tipada, `number` alinha à direita), `Steps/StepsItem` (número em círculo, linha conectora, título + detalhe), `Callout(variant, title, body)`, `FollowUpBlock/FollowUpItem`, `OptionCards/OptionCard(value, title, description, icon)`, `Chips`, `CardHeader(icon, title, subtitle, actions)`, `Skeleton` por tipo (tabela, pizza). Também o formato de resposta informativa do `openuiChatLibrary`: `Card([header, intro, highlights, statsHeader, statsCards, sections, actionBtns], [sources])` com citações `[1]`.

### 3.3 Detalhes visuais que vamos reproduzir em CSS puro

De `packages/react-ui/src/components/*` (SCSS com tokens `--openui-*`):

- **Card:** `display:flex; flex-direction:column; gap: space-xl; border: 1px solid transparent` nas variantes `card`/`clear`; `sunk` com `background: sunk; border-color: border-default; shadow-m; radius-3xl`. Ou seja: cartão plano, sem sombra forte, raio generoso.
- **CardHeader:** linha de cima com ícone (1em) + título (`heading/small`) à esquerda e ações à direita; subtítulo embaixo em `text-neutral-secondary`; `overflow-wrap: break-word`.
- **MetricIndicator:** `number/heavy` para o valor, `previous-value` riscado em `text-neutral-secondary`, tendência `+12%` em `text-success-primary` ou `-3%` em `text-danger-primary`, subtexto `body/small`; linha com `flex-wrap` e `align-items: flex-end`.
- **Steps:** círculo 24 px com `background: elevated; border: 1px solid border-default; color: secondary; label/small`; linha de 1 px `background: sunk` que some no último item; conteúdo com `title/default` + `body/default`, `margin-bottom: space-l`.
- **Tooltip de gráfico:** `min-width 128px; max-width 240px; padding xs; radius-l; border 1px border-default; background: foreground; shadow-s; label/extra-small`; indicador de série como ponto 10×10 ou barra de 4 px com a cor da série.
- **Legenda:** `flex; wrap; gap m; justify center; padding-top m`; itens com quadradinho 10×10 e `label/extra-small`.
- **Skeleton:** `@keyframes pulse` opacidade 0,3 → 0,85 em 1,2 s; barras com `radius-s`; esqueleto específico de tabela (grid de células com larguras pseudo-aleatórias) e de pizza (anel).
- **Gráficos:** estado vazio explícito ("No data available") antes de qualquer hook; `MIN_TICK_SPACING = 40` px por tick no eixo Y (`max(2, floor(height / 40))`); domínio Y sempre ancorado em zero (`[min(0, dataMin), max(0, dataMax)]`, com soma por sinal em pilhas); paleta como **rampa** e `getDistributedColors(ramp, n)` que pega cores a partir do meio da rampa para fora (1 série = cor do meio; 2 séries = vizinhas; n séries = distribuídas); animação desligada por padrão e respeitando `prefers-reduced-motion` (`useEffectiveAnimation`); rótulos do eixo X quebrados em até 2 linhas ou rotacionados por medição.

O plano 11 traduz isso para `frontend/src/index.css` com os tokens do Multi+ (`--primary`, `--surface-card`, `--surface-soft`, `--hairline`, `--ink`, `--body`, `--success`, `--warning`, `--error`), sem cor nova.

### 3.4 O que não levar

A linguagem, o parser, `Query`/`Mutation`, d3, a árvore livre (`Stack` com direção e `wrap`), Tabs/Accordion/Modal como blocos de modelo (layout livre foi rejeitado na v1 e continua fora), `EditableTable`, `Carousel`, telemetria em nuvem.

## 4. Open WebUI

### 4.1 Licença

Open WebUI License: BSD-3 mais a cláusula 4, que proíbe alterar ou remover a marca "Open WebUI" acima de 50 usuários. **Nenhum trecho de código deste repositório pode ser copiado para o Nexus.** O que segue são observações de comportamento, lidas no código para entender o padrão, e reimplementadas do zero.

### 4.2 Padrões observados que valem para o Nexus

- **Artefatos em iframe** (`Artifacts.svelte`): `srcdoc` com CSP injetada pela configuração do servidor; flags do `sandbox` configuráveis pelo usuário (`allow-scripts`, `allow-forms`, `allow-downloads`, `allow-same-origin` desligado por padrão); clique em `<a>` dentro do iframe é interceptado e navegação externa é bloqueada com log; botões Tela cheia e Baixar `.html`. Para o Nexus: a guarda de navegação (como no AnswerUI) e o Tela cheia entram no `SandboxCard`; as flags continuam fixas (`allow-scripts allow-forms`), por decisão da spec §7.
- **Code block** (`CodeBlock.svelte`): barra com nome da linguagem, Recolher/Expandir, Copiar, Executar (Pyodide, só Python) e Pré-visualizar (só `html`/`svg`, abre no painel de artefato). Mermaid e Vega só renderizam quando o fence já fechou (`token.raw` termina com ```` ``` ````), evitando redesenhar diagrama a cada token. Para o Nexus: o mesmo princípio de "não pintar bloco com fence aberto" já está na spec; vale copiar o critério para o render progressivo (um bloco só pinta quando o objeto JSON dele fechou).
- **Alerts GitHub** (`> [!NOTE]`, `[!TIP]`, `[!WARNING]`…) no markdown (`AlertRenderer`): o mesmo papel do `callout` do OpenUI, sem precisar de bloco. Para o Nexus: o bloco `callout` cobre o caso estruturado; suportar `[!NOTE]` na prosa é melhoria do `MessageBubble`, fora desta pasta.
- **Follow-ups** (`FollowUps.svelte`): lista vertical de botões de texto, separados por `<hr>` fino, `aria-label="Follow up: …"`, clique envia a pergunta. Simples e eficaz; é o modelo do bloco `follow_up`.
- **Elicitação** (`AskUserCard.svelte`): uma ou mais perguntas, cada uma com `header`, `question`, `options[{label, description}]`, `allow_other` (campo de texto livre), navegação entre perguntas, botão Enviar só quando todas respondidas, cancelamento por timeout. É o modelo do bloco `options`, reduzido a uma pergunta por bloco.
- **Citações** (`Citations.svelte`, `citation-extension.ts`): `[1]` inline vira chip clicável com favicon; modal com a fonte. O Nexus já tem cartões de fonte da busca web (`sourceCards`); não duplicar.
- **Esqueleto de mensagem** (`Skeleton.svelte`): barras de largura variada durante a espera; mesmo princípio do skeleton por tipo do OpenUI.

### 4.3 O que não levar

Svelte, Tailwind, Pyodide, execução de código no host, painel de artefatos (o Nexus já tem o seu), `allow-same-origin` como opção.

## 5. Síntese: o que muda no Nexus

1. **Camada visual** (plano 11): um `UiCard` compartilhado (cabeçalho com ícone, título, subtítulo e ações; corpo; rodapé), CSS em classes no `index.css` em vez de estilo inline repetido, `Steps` com conector, métrica grande, tooltip e legenda de gráfico padronizados, formatação de número por locale, estado vazio, movimento reduzido, barra do sandbox com Reiniciar/Tela cheia, guarda de navegação, carga ao aproximar do viewport. **Primeira fatia implementada junto com este documento** (ver plano 11, seção "Entregue").
2. **Paridade de funcionalidades** (plano 12): blocos `metric`, `table`, `callout`, `options`, `follow_up`; estado compartilhado entre blocos; render progressivo; laço de correção; regras de prompt do AnswerUI no catálogo; checagem de `Origin` no WebSocket.
3. **Cenas 2D/3D** (plano 13): `sandbox` com `kind: "scene"`, runtime local empacotado pelo Vite, protocolo `params`/`report`, barra de controle, limites de código, regras de prompt específicas.

Tudo aditivo ao `nexus-ui/1`: cliente antigo descarta tipo desconhecido e ignora campo desconhecido, como a spec já manda.

## 6. Atribuições

- AnswerUI © 0xcro3dile, MIT. Trechos adaptados em `referencias-codigo/scene-*.ts` carregam o aviso.
- OpenUI © Thesys, MIT. Nenhum arquivo copiado; padrões de CSS reescritos com os tokens do Multi+.
- Open WebUI © Open WebUI Inc., Open WebUI License. Nenhum arquivo nem trecho copiado.
