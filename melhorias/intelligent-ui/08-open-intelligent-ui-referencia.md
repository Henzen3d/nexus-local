# Open Intelligent UI (CopilotKit) — Análise Aprofundada e Modelagem para o Multi+

Documento de referência arquitetural e guia de modelagem técnica a partir do repositório [CopilotKit/OpenIntelligentUI](https://github.com/CopilotKit/OpenIntelligentUI) e do anúncio [Introducing Open Intelligent UI: the Open-Source Alternative to ChatGPT's Intelligent UI](https://www.copilotkit.ai/blog/introducing-open-intelligent-ui) (Outubro de 2026).

---

## 1. Contexto e Motivação

No início de outubro de 2026, a OpenAI lançou o **Intelligent UI** no ChatGPT: respostas que não são apenas texto ou tabelas estáticas, mas interfaces vivas geradas sob demanda (gráficos interativos, calculadoras reativas de divisão de contas, visualizadores de algoritmos passo a passo, itinerários com mapas reais e simulações 3D com Three.js).

Contudo, a solução da OpenAI é proprietária, fechada, limitada aos modelos da OpenAI e restrita ao chat do ChatGPT, sem API para produtos de terceiros.

Em resposta imediata, a CopilotKit lançou o **Open Intelligent UI**, uma alternativa open-source fundamentada em:
1. **Model & Agent Agnostic:** Funciona com qualquer agente via protocolo **AG-UI** (Agent-User Interaction Protocol 1.0) e qualquer provedor/LLM (OpenAI, Anthropic, Gemini, Groq, modelos locais).
2. **Generative UI Spectrum:** Uma taxonomia que vai desde *Controlled Generative UI* (componentes nativos estritos do design system do host) até *Open Generative UI* (código HTML/CSS/JS gerado sob demanda e executado em iframe sandbox).
3. **Harmonia com o Design System do Host:** Resolver o desafio documentado por Andrew Chen (designer da OpenAI): *"The hardest part of generative UI isn't generating the UI... it's getting it to feel like it actually belongs in the app"*.
4. **Streaming Seguro sem Layout Shift:** Ordem estrita de streaming de UI (`initialHeight` → `placeholderMessages` → `css` → `html` → `jsFunctions` → `jsExpressions`) para eliminar flashes de conteúdo sem estilo (FOUC) e saltos bruscos na rolagem da conversa.
5. **Bridge Bidirecional Host-Sandbox:** Controles e sliders reagem localmente no cliente em tempo real, enquanto ações do usuário disparam novos turnos de chat através de uma bridge validada (`postMessage`).
6. **Portabilidade Standalone:** Capacidade de baixar qualquer interface gerada como um arquivo HTML único e funcional.

---

## 2. Anatomia do Repositório CopilotKit/OpenIntelligentUI

A estrutura do projeto deles é organizada como um monorepo (pnpm + Turborepo):

```
OpenIntelligentUI/
├── apps/
│   ├── app/                 # Frontend Next.js + CopilotKit
│   │   ├── components/      # Chat, ChatHeader, API keys modal
│   │   ├── generative-ui/   # Renderizador de Sandbox, bridge de postMessage, parser de stream
│   │   └── lib/             # Hooks de streaming e gerenciamento de estado
│   ├── agent/               # Backend Python Deep Agent + FastAPI
│   │   ├── agent.py         # Orquestração do agente com LangChain Deep Agents
│   │   ├── prompts.py       # System prompt task-first e skills isoladas
│   │   └── router.py        # Visualization Router (decide entre texto, A2UI e sandbox)
│   └── mcp/                 # Servidor MCP standalone opcional
│       └── server.py        # Ferramenta assemble_document e catálogo de skills
└── packages/
    └── design-system/       # Tokens compartilhados (cores, tipografia, formulários, SVG)
```

### Principais Componentes Técnicos

1. **Visualization Router (Roteador de Visualização):**
   - Utiliza um classificador leve para definir a forma ideal da resposta antes ou durante o turno:
     - **Texto direto (Markdown):** Respostas factuais, resumos e prosa explicativa.
     - **Componente Nativo / A2UI:** Tabelas estruturadas, métricas e listas de itens com propriedades fixas.
     - **Sandbox Interativo (Open Generative UI):** Cálculos com múltiplos parâmetros, gráficos comparativos, simulações, mapas e ferramentas.

2. **Ferramenta `generateSandboxedUi`:**
   - O agente emite parâmetros em uma sequência rigorosa:
     - `initialHeight`: Altura estimada em pixels (ex: 320px). O frontend reserva o espaço antes de qualquer renderização, evitando que a tela pule enquanto o usuário lê.
     - `placeholderMessages`: Textos de carregamento progressivo (ex: *"Calculando métricas..."*, *"Preparando visualização..."*).
     - `css`: Folha de estilo isolada com injeção das variáveis de tema da aplicação.
     - `html`: Estrutura do DOM do widget.
     - `jsFunctions` e `jsExpressions`: Lógica de interação local.

3. **Isolamento de Segurança (WebSandbox):**
   - `<iframe>` com atributo `sandbox="allow-scripts allow-forms"`.
   - **Sem `allow-same-origin`:** O código gerado não tem acesso ao `localStorage`, `sessionStorage`, cookies ou tokens de autenticação do host.
   - **Lista Branca de CDNs:** Somente bibliotecas homologadas podem ser carregadas externamente (Three.js, Chart.js, D3, Leaflet, Lucide Icons).

4. **Bridge Host-Sandbox:**
   - Interações locais (como mexer em um slider de gorjeta ou rotacionar um modelo 3D) executam em JS puro no sandbox, sem fazer round-trip de rede para o servidor.
   - Botões de ação emitem um evento via `window.parent.postMessage({ type: 'copilot_action', action: 'send_message', text: '...' }, '*')`. O host escuta, valida o schema e injeta como mensagem no fluxo de chat.

---

## 3. O Que Aproveitamos e Modelamos para o Multi+ / Nexus Local

| Conceito OpenIntelligentUI | Implementação no OpenIntelligentUI | Modelagem Otimizada no Multi+ / NexusLocal |
|---|---|---|
| **Generative UI Spectrum** | Framework genérico CopilotKit (Next.js + LangChain) | **Dois Níveis:**<br>1. *Nível 1 (Controlled):* 5 cartões nativos do envelope `nexus-ui/1` (`progress`, `checklist`, `card`, `chart`, `controls`).<br>2. *Nível 2 (Interactive Tools):* Bloco `sandbox` seguro para calculadoras reativas, simulações e gráficos customizados. |
| **Theme Harmony (Andrew Chen Problem)** | `@packages/design-system` compartilhado em monorepo | **CSS Design Tokens do Nexus:** Injetar as variáveis de `frontend/src/index.css` (`--primary`, `--surface-card`, `--surface-soft`, `--hairline`, `--ink`, `--body`, dark/light theme sync) diretamente nos componentes nativos e via `<style>` bridge no iframe. |
| **Streaming Anti-Layout Shift** | Parâmetros ordenados em tool call streaming | **Pré-dimensionamento e Placeholder:** Contrato de stream do `nexus-ui` com `initial_height` e estado de skeleton antes da finalização do JSON, evitando saltos bruscos na bolha. |
| **Reatividade Local de Controles** | Sliders e formulários em JS local no sandbox | **Cálculo Reativo em Tempo Real no `ControlsCard`:** Suporte a campos de input/slider com fórmula de atualização imediata no cliente (ex: calculadora de divisão de conta ou estimativa de custo de tokens) antes do envio do clique. |
| **Host Bridge Seguro** | `postMessage` capturado por runtime Next.js | **Nexus Bridge de Ações:** O `DynamicRenderer` captura mensagens do sandbox e aciona `sendMessage` do `ChatContext` ou `selectModel` do `useStore`, aproveitando o WebSocket autenticado já existente sem abrir canais paralelos. |
| **Exportação / Portabilidade** | Botão de download standalone HTML | **1-Click Export:** Ação no canto superior do cartão/bloco para "Baixar como HTML autônomo" ou "Copiar dados", agregando valor prático para o usuário. |
| **Visualization Router** | Jev/TypeSafe API ou LLM Router dedicado | **Heurístico Refinado do Catálogo:** Expansão da lógica da Seção 8 do spec para detectar intenções de ferramentas interativas, gráficos comparativos ou fluxos passo a passo com custo zero de tokens para conversas comuns. |

---

## 4. O Que Rejeitamos Decididamente (Não Copiar)

1. **Framework Pesado e Dependências Externas Desnecessárias:**
   - O OpenIntelligentUI depende de `CopilotKit`, `LangChain Deep Agents`, `TypeSafe Jev`, Next.js e monorepo pnpm.
   - **No Multi+:** Mantemos nossa arquitetura enxuta, confiável e rápida: **FastAPI + SQLite (aiosqlite) + React 18 + Vite + Zustand + Vanilla CSS**. Sem LangChain, sem SDKs proprietários de terceiros.
2. **Dependência de Chaves de Roteamento Pagas (Jev/TypeSafe):**
   - Eles exigem `TYPESAFE_API_KEY` para o router.
   - **No Multi+:** O roteamento de catálogo roda localmente no backend Python via classificação heurística e prompt otimizado (teto de 400 tokens), com zero dependência de serviços externos adicionais.
3. **HTML Não Sanitizado na Bolha Nativa:**
   - A bolha do chat continua usando nós React puros. Nada de `dangerouslySetInnerHTML` na bolha principal.
   - Qualquer código sob demanda gerado no Nível 2 deve rodar estritamente dentro de um `<iframe>` sandboxed isolado sem acesso a credenciais.
4. **Canais Paralelos de Transporte:**
   - Não criamos SSE separado ou microserviços HTTP paralelos. Todo o transporte continua no WebSocket já existente (`backend/routers/chat.py`).

---

## 5. Como Isso se Conecta com os Nossos Planos

- **Fases 1 a 5 (`01` a `05`):** Implementam com perfeição o **Controlled Generative UI** do espectro: os blocos nativos que garantem velocidade máxima, zero risco de segurança e total aderência aos tokens visuais do Multi+.
- **Atualização do `05-plano-controles.md`:** Incorpora a reatividade local de sliders/cálculos em tempo real inspirada no *Bill Splitter* do OpenIntelligentUI.
- **Fase 7 (Futura - `09-plano-sandbox-e-exportacao.md`):** Adicionará o segundo nível do espectro (*Open Generative UI*) com sandbox isolado, pré-dimensionamento anti-FOUC, bridge de `postMessage` e download standalone de ferramentas geradas.
