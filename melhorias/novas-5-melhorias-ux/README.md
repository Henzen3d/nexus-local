# 🚀 Plano Estratégico: 5 Próximas Melhorias de UX/UI para o Multi+ (NexusLocal)

Este documento estabelece o roadmap completo de evolução da experiência do usuário (UX) e interface (UI) do **Multi+ (NexusLocal)**, derivado da análise comparativa direta com os maiores concorrentes do mercado em 2025/2026: **Claude**, **ChatGPT**, **DeepSeek**, **Xiaomi MiMo Studio**, **Manus** e **MiniMax AI**.

---

## 🎯 Visão e Posicionamento do Produto

O Multi+ é um cliente local e privado focado no público de **power users de LLMs com camadas gratuitas (free tiers)** e orquestração multi-modelo (Groq, Gemini, DeepSeek, Cerebras, OpenRouter).

A identidade do produto segue as diretrizes do [`PRODUCT.md`](file:///j:/Arquivos%20Osmar/Multi+/PRODUCT.md) e [`DESIGN.md`](file:///j:/Arquivos%20Osmar/Multi+/DESIGN.md):
* **Calmo, editorial e preciso.**
* A ferramenta deve **desaparecer na tarefa**.
* Interface de alta densidade sem poluição visual, inspirada no design limpo do Claude, Notion e Raycast.

---

## 🔍 Análise de Benchmarks (Concorrentes Mapeados)

A partir da análise dos prints e fluxos dos produtos de referência:

| Concorrente | Destaques de UX / Padrões Identificados | Aplicação no Multi+ |
| :--- | :--- | :--- |
| **Claude** (`claude.ai`) | Input box centralizado flutuante, seletor de modelo compacto embutido no rodapé do input, tags de modo (`Chat`/`Cowork`), topo limpo com botão sutil de apoio/upgrade, sidebar com atalhos fixos de topo e seção dedicada de *Fixados*. | Adotar o seletor de modelo compacto dentro do composer, sidebar com top-shelf e fixados visualmente nobres. |
| **ChatGPT** (`chatgpt.com`) | Botão *"Pensar"* (Reasoning) inline no input, chips de ação rápida logo abaixo da caixa de texto (*"Escreva ou edite"*, *"Pesquise na web"*), atalhos de voz e microfone com feedback visual imediato. | Chips de intenção rápida, botão de raciocínio direto no composer. |
| **DeepSeek** (`chat.deepseek.com`) | Pílulas ativáveis com 1 clique dentro do rodapé do composer: `[ ⚛️ Pensamento Profundo ]` e `[ 🌐 Pesquisa Inteligente ]`. Accordion de raciocínio colapsável com timer real (*"Pensou por 14 segundos ▾"*). Separação temporal limpa na barra lateral (*Hoje, Ontem, 7 dias, 30 dias*). | **Pills de modo no input**, visualização de pensamento analítico em tempo real para R1/Thinking e histórico temporal. |
| **Xiaomi MiMo Studio** (`aistudio.xiaomimimo.com`) | Cards de sugestão de tarefas em formato editorial limpo na tela inicial, pills de domínios específicos no rodapé (`Translate`, `Question Answering`, `Vision Q&A`). | Cards de ação no empty state substituindo menus profundos de texto. |
| **Manus** (`manus.im/app`) | Bento grid de intenções na tela inicial (*Compilar > Sites/apps*, *Criar > Slides/vídeos*, *Arquivo local*). Input com suporte nativo a comandos com barra (*"Atribua uma tarefa ou digite / para mais opções"*). | Bento Grid na tela inicial + Slash Commands (`/`) para programadores e power users. |
| **MiniMax AI** (`agent.minimax.io`) | Transparência em etapas de execução de agentes e orquestração multi-tarefas, fluidez com atalhos de teclado e histórico de artefatos. | Visualização das etapas do **Modo Fusion** e gerenciamento de artefatos. |

---

## 🗺️ As 5 Frentes de Melhoria

```
                               ┌────────────────────────────────────────────────────────┐
                               │       Multi+ (NexusLocal) - UX/UI Roadmap 2026         │
                               └──────────────────────────┬─────────────────────────────┘
                                                          │
          ┌───────────────────────┬───────────────────────┼───────────────────────┬───────────────────────┐
          ▼                       ▼                       ▼                       ▼                       ▼
 ┌─────────────────┐     ┌─────────────────┐     ┌─────────────────┐     ┌─────────────────┐     ┌─────────────────┐
 │   01. Composer  │     │ 02. Slash Cmds  │     │  03. Reasoning  │     │ 04. Bento Cards │     │   05. Sidebar   │
 │   Action Pills  │     │   & Shortcuts   │     │ & ThoughtStream │     │   Empty State   │     │ Pins & Timeline │
 └─────────────────┘     └─────────────────┘     └─────────────────┘     └─────────────────┘     └─────────────────┘
```

### 1. [Composer com Action Pills & Modos](file:///j:/Arquivos%20Osmar/Multi+/melhorias/novas-5-melhorias-ux/01-composer-action-pills.md)
* Unificar o rodapé da caixa de texto central com botões tipo "pílula" para acionamento rápido de **Raciocínio**, **Modo Fusion**, **Pesquisa Web** e **Melhorador de Prompt**, além de posicionar o seletor compacto de modelos dentro da caixa.

### 2. [Slash Commands (`/`) e Navegação por Teclado](file:///j:/Arquivos%20Osmar/Multi+/melhorias/novas-5-melhorias-ux/02-slash-commands-shortcuts.md)
* Permitir controle operacional imediato sem tirar a mão do teclado: digitar `/` no prompt abre popover para alternar modelos, ativar Fusion, injetar templates e executar comandos. Suporte à Paleta de Comandos global (`Ctrl+K`).

### 3. [Accordion de Raciocínio (*Thought Stream*) & Timeline do Fusion](file:///j:/Arquivos%20Osmar/Multi+/melhorias/novas-5-melhorias-ux/03-reasoning-thought-stream.md)
* Exibir os pensamentos de modelos analíticos (DeepSeek-R1, Gemini Flash Thinking) em uma gaveta colapsável e elegante com contador de tempo real (`Pensou por 8.4s ▾`). No Modo Fusion, exibir as etapas de consulta dos provedores e parecer do juiz em uma mini-timeline limpa.

### 4. [Bento Grid de Ações Rápidas no Empty State](file:///j:/Arquivos%20Osmar/Multi+/melhorias/novas-5-melhorias-ux/04-bento-starter-cards.md)
* Substituir os botões genéricos de texto no rodapé da tela inicial por cartões de intenção direta (*Comparar com Fusion*, *Codificar & Depurar*, *Analisar Documento*, *Pesquisa Factual*), que pré-carregam o prompt e reduzem o bloqueio da página em branco.

### 5. [Sidebar Modular com Fixados e Agrupamento Temporal](file:///j:/Arquivos%20Osmar/Multi+/melhorias/novas-5-melhorias-ux/05-sidebar-pins-temporal.md)
* Criar dock superior de acesso rápido (`+ Novo`, `Projetos`, `Artefatos`, `Rankings`), seção de conversas Fixadas com destaque visual e divisão cronológica do histórico (*Hoje*, *Ontem*, *7 dias*, *30 dias*).

---

## 📊 Matriz de Priorização (Impacto vs. Esforço)

| Frente de Melhoria | Impacto na UX | Esforço Técnico | Dependências Principais | Prioridade |
| :--- | :---: | :---: | :--- | :---: |
| **01. Composer Action Pills** | 🔥 **Muito Alto** | Médio | `MessageInput.tsx`, `ModelSelector.tsx`, CSS tokens | **P1 (Imediata)** |
| **03. Accordion de Raciocínio (Thought Stream)** | 🔥 **Muito Alto** | Baixo / Médio | `MessageBubble.tsx`, parsing de streaming (`<think>`) | **P2** |
| **04. Bento Cards no Empty State** | ⚡ **Alto** | Baixo | `ChatWindow.tsx`, `DESIGN.md` tokens | **P3** |
| **02. Slash Commands (`/`) & `Ctrl+K`** | ⚡ **Alto** | Médio | Hook de teclado, Popover de comandos | **P4** |
| **05. Sidebar Pins & Timeline** | ⚡ **Alto** | Médio | `Sidebar.tsx`, ordenação de conversas no store | **P5** |

---

## 📁 Estrutura desta Documentação

* [`README.md`](file:///j:/Arquivos%20Osmar/Multi+/melhorias/novas-5-melhorias-ux/README.md) - Visão geral e benchmarking (este arquivo).
* [`01-composer-action-pills.md`](file:///j:/Arquivos%20Osmar/Multi+/melhorias/novas-5-melhorias-ux/01-composer-action-pills.md) - Especificação detalhada, componentes e tarefas da melhoria 1.
* [`02-slash-commands-shortcuts.md`](file:///j:/Arquivos%20Osmar/Multi+/melhorias/novas-5-melhorias-ux/02-slash-commands-shortcuts.md) - Especificação detalhada, comandos e tarefas da melhoria 2.
* [`03-reasoning-thought-stream.md`](file:///j:/Arquivos%20Osmar/Multi+/melhorias/novas-5-melhorias-ux/03-reasoning-thought-stream.md) - Especificação detalhada, layout e tarefas da melhoria 3.
* [`04-bento-starter-cards.md`](file:///j:/Arquivos%20Osmar/Multi+/melhorias/novas-5-melhorias-ux/04-bento-starter-cards.md) - Especificação detalhada, cartões e tarefas da melhoria 4.
* [`05-sidebar-pins-temporal.md`](file:///j:/Arquivos%20Osmar/Multi+/melhorias/novas-5-melhorias-ux/05-sidebar-pins-temporal.md) - Especificação detalhada, agrupamento e tarefas da melhoria 5.
* [`ROADMAP-CHECKLIST.md`](file:///j:/Arquivos%20Osmar/Multi+/melhorias/novas-5-melhorias-ux/ROADMAP-CHECKLIST.md) - Checklist operacional consolidado de execução para marcar tarefas concluídas.
