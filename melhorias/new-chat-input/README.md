# 💬 Redesign do Chat Input & Seletor Unificado — Multi+ (NexusLocal)
**Benchmark Visual: Claude 2026 (Sonnet 5.5 / Fable 5.1 / Opus 5.5)**

Este documento e os planos nesta pasta detalham a especificação completa, arquitetura de componentes, refinamento de espaçamentos e checklist de execução para alinhar o **Chat Input** do Multi+ aos padrões de excelência e ergonomia do Claude (referências registradas em `melhorias/new-chat-input/`).

---

## 🎯 Objetivos Centrais da Modernização

1. **Eficiência Vertical no Chat Ativo (Linha Única):**
   - No estado vazio (tela inicial), o input preserva formato de cartão convidativo e acolhedor com múltiplas linhas de boas-vindas.
   - Após o primeiro envio (conversa ativa), o input contrai dinamicamente para uma **barra compacta de linha única (~44px de altura)**, liberando área útil vital para leitura de mensagens.

2. **Migração da Seleção de Modelo para o Rodapé (Footer Disclaimer):**
   - O pill de seleção do modelo (`Sonnet 5.5`, `Nexus 3.5`, `🎯 Auto`) desce para a mesma linha do aviso de responsabilidade da IA (*"O NexusLocal é uma IA e pode cometer erros..."*), alinhado à direita.
   - Isso desocupa o interior do campo de digitação, eliminando congestionamento horizontal.

3. **Ações Dinâmicas Contextuais (Voz ➔ Enter - Opção A):**
   - Quando o campo de texto está vazio: exibe ícones de voz (`Microfone` e `Conversar / Loop de Áudio`).
   - Ao iniciar a digitação de texto (ou inserir anexos): os ícones de voz transitam suavemente para o botão de envio `↵ Enter` (Opção A — glifo de retorno clássico), mantendo os controles de voz disponíveis enquanto a escuta estiver ativa.

4. **Hub de Ferramentas Reais no Botão `+`:**
   - Unificação exclusiva das funcionalidades reais existentes no NexusLocal:
     - `📎 Adicionar arquivos ou fotos` (upload nativo de arquivos).
     - `✨ Melhoria de prompt` (`api.enhancePrompt`).
     - `🌐 Busca na web` (toggle com checkmark `✓` interno no menu, sem pontos ou badges externos poluindo o botão).
     - `🧬 Modo Fusion` (com toggle switch idêntico ao benchmark de conectores do Claude em `trogle-conectores.jpg`).
   - Limpeza total do composer e do cabeçalho superior (o botão isolado de Fusion no header é removido).

5. **Balão Unificado de Modelos & Provedores (com Toggle de Auto-Roteamento):**
   - Eliminação do `ProviderSelector` solto no topo do header da janela.
   - Consolidação no balão/popover aberto pelo botão de modelo no rodapé:
     - **Topo do Balão:** Switch/Toggle de ativação do **Auto-Roteamento Inteligente (Smart Router)**, com restauração segura da seleção manual anterior ao desligar.
     - **Sub-header de Filtro:** Abas horizontais deslizantes de Provedores (`Todos`, `OpenRouter`, `Anthropic`, `OpenAI`, `Groq`, etc.), funcionando estritamente como filtro de navegação sem alterar a seleção ativa prematuramente.
     - **Corpo:** Lista de modelos reais do catálogo com destaque ao ativo, score NexusLocal, contexto e status de cotas.

---

## 📸 Referências Visuais Analisadas (Screenshots Claude)

| Arquivo de Imagem | Contexto Capturado | Elementos-Chave Notados |
| :--- | :--- | :--- |
| `tela-inicial-1.png` | Tela inicial vazia (Empty State) | Card amplo, `+` à esquerda, pílulas de modo, `Sonnet 5.5` + Microfone + Onda de voz à direita. |
| `tela-inicial-2.png` | Menu aberto pelo botão `+` na inicial | Flyout suspenso com Anexar arquivos, Captura, Habilidades, Busca na web (check) e Memória. |
| `tela-inicial-digitacao-select-model.png` | Digitação ativa na tela inicial | Ícones de voz saem e dão lugar ao botão circular de envio `↑`. Popover de modelos aberto. |
| `Melhorias-de-design-do-chat-Claude-...png` | Conversa ativa com input vazio | **Barra de 1 linha só**, botão `+`, placeholder *"Escreva uma mensagem..."*, ícones de voz à direita, **modelo no rodapé**. |
| `digitacao-input-enter.png` | Conversa ativa com digitação em andamento | **Barra de 1 linha só**, ícones de voz somem e aparece o botão `↵ Enter`, modelo no rodapé com disclaimer. |
| `selecao-modelos.png` | Balão de modelos aberto a partir do rodapé | Popover ancorado no botão do rodapé com modelo atual `✓`, controle de Esforço e submenu Mais modelos. |
| `selecao-esforco.jpg` | Submenu de esforço de raciocínio | Flyout lateral com Baixo, Médio (Recomendado), Alto, Extra, Máx e explicação de consumo. |
| `selecao-modelos-open.jpg` | Submenu *"Mais modelos >"* | Flyout lateral com versões legadas e variantes dos modelos. |

---

## 🗂️ Índice de Documentação e Planos

1. [01-analise-visual-benchmark.md](file:///j:/Arquivos%20Osmar/Multi+/melhorias/new-chat-input/01-analise-visual-benchmark.md) — Decomposição aprofundada dos prints, anatomia comparativa dos estados e diagnóstico dos problemas de espaçamento do NexusLocal atual.
2. [02-arquitetura-input-single-line.md](file:///j:/Arquivos%20Osmar/Multi+/melhorias/new-chat-input/02-arquitetura-input-single-line.md) — Especificação técnica do input em linha única, auto-expansão, transição dinâmica Voice ➔ Enter e migração para o rodapé.
3. [03-menu-integrado-acoes.md](file:///j:/Arquivos%20Osmar/Multi+/melhorias/new-chat-input/03-menu-integrado-acoes.md) — Design e engenharia do menu flutuante `+` (Anexos, Melhoria de Prompt, Busca Web, atalhos de teclado e acessibilidade).
4. [04-popover-modelos-e-provedores.md](file:///j:/Arquivos%20Osmar/Multi+/melhorias/new-chat-input/04-popover-modelos-e-provedores.md) — Novo balão unificado de modelos e provedores, toggle de Auto-Roteamento, tabs de navegação de provedores e lista de modelos reais.
5. [05-especificacao-css-design-tokens.md](file:///j:/Arquivos%20Osmar/Multi+/melhorias/new-chat-input/05-especificacao-css-design-tokens.md) — Tabela de design tokens, medidas pixel-perfect, regras de Dark/Light mode e micro-animações CSS.
6. [06-roadmap-subtarefas-execucao.md](file:///j:/Arquivos%20Osmar/Multi+/melhorias/new-chat-input/06-roadmap-subtarefas-execucao.md) — Roadmap de execução dividido em 6 fases granulares com critérios de aceitação e rollback seguro.

---

> [!IMPORTANT]
> **Status Operacional:** Esta pasta contém planos e especificações técnicas completas para aprovação do usuário. **Nenhuma alteração em código foi realizada neste momento.**
