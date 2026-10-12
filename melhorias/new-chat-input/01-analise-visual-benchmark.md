# 🔍 01 - Análise Visual e Benchmark Detalhado
**Multi+ (NexusLocal) vs Claude 2026**

Este documento detalha o estudo comparativo dos prints de referência armazenados em `melhorias/new-chat-input/`, diagnosticando as deficiências de espaço, fluxo e hierarquia do Multi+ atual e contrastando com os refinamentos da interface do Claude.

---

## 🖼️ Análise Detalhada das Capturas de Tela

### 1. `tela-inicial-1.png` — O Estado Inicial (Empty State)
* **Composição Geral:**
  * O centro da tela apresenta uma saudação personalizada (*"Feliz segunda-feira, Osmar"*) com o ícone floral estilizado.
  * O campo de entrada é renderizado como um cartão amplo, centralizado, com bordas suavemente arredondadas (~16px) e fundo escuro elevado.
  * O placeholder é um convite reflexivo: *"Como posso ajudar você hoje?"*.
* **Barra de Ações Interna (Rodapé do Card):**
  * **Lado Esquerdo:**
    * Botão circular `+` (disparador de ações e conexões).
    * Pílula de seleção de modo de trabalho: `Chat` e `Cowork` (com indicador sutil do modo ativo).
  * **Lado Direito (Quando vazio):**
    * Pílula de seleção do modelo ativo: `Sonnet 5.5 Alto`.
    * Ícone de microfone (ditar pontual).
    * Ícone de linhas de áudio/onda sonora com chevron (modo de conversa contínua).

---

### 2. `tela-inicial-2.png` — Menu Suspenso de Ferramentas (`+`)
* **Comportamento ao Clicar em `+`:**
  * Abre um balão popover orientado para cima, ancorado no botão `+`.
  * **Grupo 1 (Upload e Captura):**
    * `📎 Adicionar arquivos ou fotos` com indicação de atalho à direita (`Ctrl+U`).
    * `📸 Fazer captura de tela`.
    * `📁 Adicionar ao projeto >` (com seta indicativa de submenu).
    * `🐙 Adicionar do GitHub`.
  * **Grupo 2 (Capacidades e Extensões):**
    * `🧩 Habilidades >`
    * `🔌 Conectores >`
    * `🎨 Sistema de design >`
    * `⚡ Adicionar plugins`
  * **Grupo 3 (Ferramentas Integradas / Toggles com Check):**
    * `🌐 Busca na web` (com checkmark azul/ativo à direita indicando status ligado).
    * `🧠 Memória` (com checkmark azul/ativo à direita).

---

### 3. `tela-inicial-digitacao-select-model.png` — Digitação Inicial e Balão de Modelos
* **Comportamento ao Começar a Digitar:**
  * O usuário digita *"iniciando digitação de texto"*.
  * **Instantaneamente:** os ícones de voz (`Microfone` e `Ondas de Áudio`) desaparecem da barra de ações.
  * Em seu lugar, surge o botão de envio principal: um círculo terracota/laranja com uma seta branca voltada para cima (`↑`).
* **Balão de Seleção de Modelos Aberto:**
  * O menu de modelos abre diretamente sobre a tela:
    * `Fable 5.1` (Pro ou Max) — *"Para seus desafios mais difíceis"*.
    * `Opus 5.5` (Pro) — *"Para trabalhos complexos e tarefas do dia a dia"*.
    * `Sonnet 5.5` (Marcado com `✓`) — *"Mais eficiente para tarefas mais simples"*.
    * `Haiku 5.5` — *"Mais rápido para respostas rápidas"*.
    * Divisor visual fino.
    * `Esforço` ➔ `Alto >`.
    * `Mais modelos >`.

---

### 4. `Melhorias-de-design-do-chat-Claude-...png` — Conversa Ativa: O Salto para Linha Única
* **Transformação Estrutural Chave:**
  * Esta é a mudança mais significativa observada pelo usuário:
  * **No chat ativo, o input deixa de ser um card de duas linhas (textarea + barra de ferramentas) e se torna uma barra horizontal contínua de linha única (~44px de altura).**
  * **Lado Esquerdo:** Botão `+` perfeitamente alinhado verticalmente.
  * **Centro:** Campo de texto com placeholder *"Escreva uma mensagem..."*.
  * **Lado Direito:** Ícones de voz (`Microfone` e `Ondas de Áudio`).
* **Rodapé (Footer Bar):**
  * O campo de texto agora não possui mais a seleção de modelo dentro de si!
  * **Abaixo do input**, em uma linha de apoio com espaçamento respirável:
    * **À esquerda:** Mensagem de responsabilidade da IA (*"Claude é uma IA e pode cometer erros. Por favor, verifique as fontes citadas."*).
    * **À direita (na mesma linha do texto de aviso):** O pill do modelo selecionado: `Sonnet 5.5 Alto`.

---

### 5. `digitacao-input-enter.png` — Conversa Ativa com Digitação
* **Dinâmica de Envio em Linha Única:**
  * O usuário começa a digitar no campo: *"ao começar a digitar sai os ícones de ditar e de conversar e muda para "Enter""*.
  * Os ícones de voz somem imediatamente.
  * Surge o botão de ação rápida: o símbolo clássico de retorno/envio **`↵` (Enter)** em um botão sutil com contorno ou fundo discreto.
  * O pill `Sonnet 5.5 Alto` permanece estável no rodapé inferior, sem interferir nem tremer a altura do campo de digitação.

---

### 6. `selecao-modelos.png`, `selecao-modelos-open.jpg` e `trogle-conectores.jpg` — Balão Ancorado e Toggles
* **Ancoragem Ergonômica:**
  * Ao clicar no pill de modelo posicionado no rodapé (`[ 🎯 Auto ]` ou `[ Modelo Ativo ▾ ]`), o balão de seleção abre verticalmente para cima, ancorado no rodapé direito.
* **Toggles Deslizantes (Benchmark `trogle-conectores.jpg`):**
  * A referência `trogle-conectores.jpg` demonstra como o Claude implementa toggles elegantes para ferramentas ativas (ex: Gmail, Google Calendar com switch azul deslizante).
  * No Multi+, essa exata mecânica é aplicada para o **Modo Fusion** no menu `+` e para o **Toggle de Roteamento Inteligente (Smart Router)** no topo do balão de modelos.
* **Escopo Estrito do Multi+:**
  * Recursos ausentes no catálogo e contratos atuais (como "Esforço de raciocínio", "Captura de tela" ou "Sistema de design") ficam expressamente fora do escopo. O Multi+ adota estritamente os campos reais de seu catálogo de modelos (`display_name`, `provider_name`, `nexuslocal_score`, `quota_status`, `context_length`).

---

## ⚖️ Comparativo Visual: Multi+ Hoje vs. Nova Arquitetura Proposta

### Cenário 1: Conversa Ativa (Durante o Chat)

#### ❌ Como o Multi+ (NexusLocal) está Hoje:
```
┌────────────────────────────────────────────────────────────────────────┐
│ [Header] [Menu] [ProviderSelector: Todos ▼] [Fusion] [Projeto]         │  <-- Header poluído
├────────────────────────────────────────────────────────────────────────┤
│                                                                        │
│  [Mensagens da conversa ocupam a tela]                                 │
│                                                                        │
├────────────────────────────────────────────────────────────────────────┤
│ ┌─ [input-card] (Altura excessiva: ~90px fixos) ─────────────────────┐ │  <-- Ocupa muito espaço
│ │ [Textarea: "Escreva uma mensagem..."]                              │ │
│ │                                                                    │ │
│ │ [Mic] [Ondas] [Clip] [Sparkles] [Globo]    [ModelSelector ▼] [ ↑ ] │ │  <-- 7 controles amontoados
│ └────────────────────────────────────────────────────────────────────┘ │
│         NexusLocal pode cometer erros. Verifique informações...        │  <-- Aviso isolado
└────────────────────────────────────────────────────────────────────────┘
```

#### ✅ Como ficará com o Novo Design Inspirado no Claude:
```
┌────────────────────────────────────────────────────────────────────────┐
│ [Header] [Menu] [Projeto: Meu App]               [Fusion] [Usuário]   │  <-- Header limpo (sem ProviderSelector)
├────────────────────────────────────────────────────────────────────────┤
│                                                                        │
│  [Mensagens da conversa com +25% de visibilidade vertical]            │
│                                                                        │
├────────────────────────────────────────────────────────────────────────┤
│ ┌─ [input-card-compact] (Altura esguia: ~44px linha única) ──────────┐ │  <-- Compacto e elegante!
│ │  (+)  Escreva uma mensagem...                       (Mic) (Ondas)  │ │  (Vazio)
│ │  (+)  iniciando digitação de texto...                     [  ↵  ]  │ │  (Digitando)
│ └────────────────────────────────────────────────────────────────────┘ │
│                                                                        │
│   NexusLocal é uma IA e pode cometer erros.        [ 🎯 Sonnet 5.5 ▾ ] │  <-- Modelo na linha do aviso!
└────────────────────────────────────────────────────────────────────────┘
```

---

## 🩺 Diagnóstico Crítico dos Espaçamentos no Multi+ Atual

1. **Desperdício de Espaço Vertical no Chat Ativo:**
   * O Multi+ usa o mesmo layout de `.input-card` na tela inicial e no meio da conversa.
   * O card atual possui um bloco de digitação em cima (`padding: 12px 16px 8px`) e uma barra de ações inteira embaixo (`padding: 2px 8px 8px`), somando mais de **86px a 110px** de altura mínima antes de qualquer quebra de linha.
   * Em telas de notebook (13" a 15") ou janelas divididas, esse bloco rouba leitura preciosa da resposta da IA.

2. **Poluição Horizontal na Barra de Ferramentas:**
   * Atualmente, o rodapé interno do input espreme lado a lado:
     `Mic` (28px) + `AudioLines` (28px) + `AttachmentButton` (28px) + `Enhancer` (28px) + `WebSearchToggle` (28px) = **140px só de ferramentas à esquerda**.
     À direita: `ModelSelector` (~160px a 240px) + `SendButton` (28px) = **200px**.
   * Em telas médias, os botões quase se encostam no centro, gerando claustrofobia visual.

3. **Duplicação Cognitiva de Provedores vs. Modelos:**
   * Hoje o usuário escolhe o provedor no topo esquerdo da página (`chat-header-left`), e depois escolhe o modelo no canto inferior direito do chat (`input-actions-right`).
   * Essa separação espacial obriga os olhos do usuário a varrerem a tela de uma ponta à outra (diagonal de 1000px) para fazer uma configuração simples.
   * Ao unir a seleção de Provedores e o Auto-Roteamento dentro do mesmo balão de modelos, a ergonomia mental se torna 10x mais fluida.

---

## 💡 Princípios Orientadores do Redesign

* **Princípio 1 — Respiração e Foco:** No chat em andamento, o input deve ser discreto como uma caneta pousada na mesa — presente, porém invisível até o momento do uso.
* **Princípio 2 — Uma Ação Visível de Cada Vez:** Ícones de voz e botão de envio têm propósitos mutuamente exclusivos no momento da digitação. Não há motivo para ambos ocuparem a tela simultaneamente.
* **Princípio 3 — Rodapé Integrado:** A linha inferior deixa de ser um "aviso legal abandonado" e ganha função utilitária nobre ao ancorar o seletor de IA.
* **Princípio 4 — Balão Rico e Modular:** O popover de modelo é o cockpit do usuário para definir quem responde (Auto ou Manual), de qual provedor e com qual esforço.
