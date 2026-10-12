# ➕ 03 - Menu Integrado de Ações (Botão `+`)
**Multi+ (NexusLocal) — Unificação Ergonômica de Ferramentas Existentes**

Este documento detalha o design, arquitetura de componentes e regras de interação para o **Botão `+`** e seu respectivo menu flutuante.

> [!IMPORTANT]
> **Princípio de Escopo Estrito (NexusLocal):** Conforme definido nas diretrizes de produto, o menu `+` **não inclui funcionalidades fictícias** (como "Sistema de Design" ou "Captura de tela"). Ele unifica exclusivamente **capacidades reais já existentes no sistema**: **Anexos**, **Melhoria de Prompt**, **Busca na Web** e o **Modo Fusion** (com toggle switch idêntico ao benchmark de conectores do Claude em `trogle-conectores.jpg`).

---

## 🧭 O Desafio da Fragmentação Atual

No Multi+ atual, os controles de contexto e ferramentas estão espalhados:
* `AttachmentButton` (ícone de clipe solto no composer).
* `Enhancer` (botão de varinha/sparkles solto no composer).
* `WebSearchToggle` (ícone de globo solto no composer).
* `Fusion` (botão de DNA isolado no header superior da janela, separado do fluxo de mensagem).

Essa fragmentação obriga o usuário a olhar para o topo da janela para ativar o Fusion e para o rodapé para anexar ou ligar a busca web.

---

## 🎯 A Solução: O Ponto Focal `+`

Inspirado no padrão do Claude (`tela-inicial-2.png`, `Melhorias-de-design-do-chat-Claude-...png` e `trogle-conectores.jpg`), todas as ferramentas reais do Multi+ convergem para o menu flutuante aberto pelo botão `+`:

```
┌─────────────────────────────────────────────────────────────────┐
│ [ Balão Popover do Botão '+' ]                                  │
├─────────────────────────────────────────────────────────────────┤
│  📎  Adicionar arquivos ou fotos                                │
├─────────────────────────────────────────────────────────────────┤
│  ✨  Melhorar prompt atual                                      │
│  🌐  Busca na web                                         [ ✓ ] │
│  🧬  Modo Fusion (Multi-IAs)                 [ Toggle: ON/OFF ] │
└─────────────────────────────────────────────────────────────────┘
             ▲
          [ (+) ]  Escreva uma mensagem...
```

---

## 📋 Especificação dos Controles Integrados

### 1. Adicionar Arquivos ou Fotos
* **Ícone:** `Paperclip` (16px).
* **Ação:** Aciona o `input type="file"` nativo encapsulado em `AttachmentButton`.
* **Sem atalhos conflitantes:** Removido atalho `Ctrl+U` (que em navegadores abre "Exibir código-fonte"). O acionamento é feito pelo clique ou drag-and-drop no composer.
* **Formatos suportados:** Imagens, documentos e arquivos aceitos pela API de upload existente.

### 2. Melhoria de Prompt (`Enhancer`)
* **Ícone:** `Sparkles` (16px).
* **Ação:** Dispara `api.enhancePrompt(text)`.
* **Comportamento de Estado:**
  * Se o campo contiver texto: executa a melhoria, exibe loader no ícone e substitui o texto com animação `enhance-flash`.
  * Se o campo estiver vazio ou enhancer desligado nas configurações do sistema: item fica visualmente desabilitado com tooltip informativo (`t('chat.enhanceDisabledEmpty')`).

### 3. Busca na Web (`Web Search`)
* **Ícone:** `Globe` (16px).
* **Comportamento:** Item de alternância (Toggle) controlando a store `webSearchActive`.
* **Feedback Visual:**
  * **No botão `+` externo:** Nenhum ponto ou badge luminoso adicional é exibido (mantendo o botão 100% limpo conforme preferência do usuário).
  * **Dentro do menu:** Exibe um checkmark nítido `✓` ou highlight ativo à direita do item indicando que a busca na web está ativada.

### 4. Modo Fusion (com Toggle Switch estilo `trogle-conectores.jpg`)
* **Ícone:** `Dna` (16px).
* **Referência Visual:** Adota exatamente o componente de toggle switch azul/colorido documentado em `melhorias/new-chat-input/trogle-conectores.jpg`.
* **Estrutura do Item:**
  * **Esquerda:** Ícone de DNA + Rótulo *"Modo Fusion"* + Subtítulo sutil *"Combina respostas de múltiplos modelos"*.
  * **Direita:** Toggle switch deslizante (track arredondado com thumb branco).
* **Integração de Estado:** Conectado diretamente a `fusionMode` e `setFusionMode` da store global.
* **Efeito no Header:** Permite remover o botão isolado de Fusion do cabeçalho superior (`ChatWindow.tsx`), despoluindo totalmente a barra de título do chat.

---

## 🎨 Especificação Visual do Balão Flutuante (Desktop)

* **Posicionamento:** Ancorado acima do botão `+` (`bottom: calc(100% + 8px)`, `left: 0`).
* **Largura:** `260px` fixa.
* **Superfície Glassmórfica:**
  * Fundo: `var(--surface-dark-elevated)` no dark mode / `var(--surface-card)` no light mode.
  * Borda: `1px solid var(--popover-border, rgba(255, 255, 255, 0.08))`.
  * Raio: `14px` (`var(--radius-lg)`).
  * Sombra: `var(--popover-shadow, 0 12px 36px rgba(0, 0, 0, 0.45))`.
* **Itens (`.plus-menu-item`):**
  * Altura de linha: `36px` a `40px`.
  * Padding: `8px 12px`.
  * Hover: `var(--btn-icon-hover)`.
  * Tipografia: `13.5px`, peso 450, cor `var(--ink)`.
* **Navegação por Teclado e Acessibilidade:**
  * `aria-haspopup="true"`, `aria-expanded={menuOpen}`.
  * Pressionar `Escape` fecha o menu e devolve o foco para o botão `+` ou textarea.
  * Fechamento automático ao clicar fora (`mousedown` handler).

---

## 📱 Comportamento em Telas Móveis (< 768px)

* No mobile, o clique em `+` abre o **`BottomSheet`** já padronizado no projeto.
* Todos os itens mantêm altura mínima de toque de **`48px`** (`touch-target`).
* O toggle de Fusion e a opção de busca web oferecem ergonomia perfeita para toque com uma mão.
