# 🎯 Frente 02: Slash Commands (`/`) e Navegação Total por Teclado

## 1. Contexto e Problema Atual

Atualmente no Multi+:
* Para qualquer troca de modelo, acionamento do Fusion, limpeza de chat ou inserção de templates, o usuário precisa tirar a mão do teclado, usar o mouse e abrir modais/menus.
* Programadores e usuários avançados (público principal do Multi+) esperam agilidade estilo IDE / Raycast / Claude / Manus, onde tarefas frequentes são disparadas instantaneamente pelo teclado.

## 2. Benchmark de Mercado

* **Manus**: Placeholder explícito no input: *"Atribua uma tarefa ou digite / para mais opções"*. O `/` abre um menu contextual de ações rápidas.
* **MiniMax AI / Slack / Raycast**: Digitação de `/` filtra comandos com busca rápida e seleção por seta para cima/baixo + `Enter`.
* **Claude / ChatGPT**: Suporte a atalhos rápidos de navegação e paleta de ações.

---

## 3. Especificação da Solução para o Multi+

### A. Slash Commands Menu (`/`)
Quando o usuário digita `/` como primeiro caractere de uma linha no campo de texto:
* Abre um popover flutuante diretamente acima do input, com foco na lista de comandos.
* Se o usuário continuar digitando (ex: `/mod`), filtra em tempo real os comandos compatíveis.
* Teclas `↑` e `↓` navegam entre as opções; `Enter` ou `Tab` aplica o comando; `Escape` fecha o popover.

```
┌────────────────────────────────────────────────────────────────────────┐
│  Comandos Disponíveis:                                                 │
│  > /modelo       - Selecionar modelo ativo rapidamente                 │
│    /fusion       - Alternar Modo Fusion (orquestração multi-LLM)       │
│    /web          - Forçar pesquisa na web para esta mensagem           │
│    /melhorar     - Expandir e otimizar prompt com o Enhancer           │
│    /codigo       - Inserir template de geração e refatoração de código │
│    /resumo       - Inserir template de síntese executiva               │
│    /novo         - Limpar conversa e começar novo chat                 │
├────────────────────────────────────────────────────────────────────────┤
│  /mod                                                                  │
└────────────────────────────────────────────────────────────────────────┘
```

### B. Paleta de Comandos Global (`Ctrl+K` / `Cmd+K`)
* Atalho universal que abre um modal centralizado de busca fuzzy (estilo Spotlight/Raycast).
* Permite pesquisar em milissegundos:
  * Conversas recentes do histórico.
  * Projetos e memórias locais.
  * Artefatos salvos.
  * Troca direta de temas (Claro / Escuro / Sistema).

---

## 4. Divisão de Tarefas e Subtarefas

### Tarefa 2.1: Hook e Parser de Comandos no Input
- [ ] **2.1.1**: Criar o hook [`useSlashCommands.ts`](file:///j:/Arquivos%20Osmar/Multi+/frontend/src/hooks/useSlashCommands.ts) que monitora o valor do textarea e detecta o gatilho `/`.
- [ ] **2.1.2**: Implementar lógica de extração do termo de busca após a barra (ex: `/fus` -> query `"fus"`).
- [ ] **2.1.3**: Suporte para auto-completar com `Tab` ou `Enter` substituindo o texto pelo template ou disparando a ação direta.

### Tarefa 2.2: Componente do Popover de Slash Commands
- [ ] **2.2.1**: Criar [`SlashCommandMenu.tsx`](file:///j:/Arquivos%20Osmar/Multi+/frontend/src/components/SlashCommandMenu.tsx) posicionado acima da barra de input.
- [ ] **2.2.2**: Estilização seguindo o design system do [`DESIGN.md`](file:///j:/Arquivos%20Osmar/Multi+/DESIGN.md): fundo com leve elevação, borda sutil, cantos arredondados (`12px`) e sombra suave.
- [ ] **2.2.3**: Exibir ícone temático, nome do comando em negrito, atalho e descrição curta para cada item.

### Tarefa 2.3: Catálogo de Comandos Nativos do Multi+
- [ ] **2.3.1**: `/modelo [termo]` — exibe submenu rápido com os modelos configurados nas chaves do usuário (Groq, Gemini, DeepSeek, etc.).
- [ ] **2.3.2**: `/fusion` — ativa ou desativa o Modo Fusion instantaneamente.
- [ ] **2.3.3**: `/web` — ativa a busca na web para a pergunta atual.
- [ ] **2.3.4**: `/melhorar` ou `/enhance` — executa o otimizador de prompt no texto já digitado.
- [ ] **2.3.5**: `/limpar` ou `/novo` — chama `startNewConversation()` e limpa o campo.
- [ ] **2.3.6**: `/codigo`, `/resumo`, `/traduzir` — preenche o textarea com templates úteis de alta qualidade.

### Tarefa 2.4: Command Palette Global (`Ctrl+K`)
- [ ] **2.4.1**: Criar o componente [`CommandPaletteModal.tsx`](file:///j:/Arquivos%20Osmar/Multi+/frontend/src/components/CommandPaletteModal.tsx).
- [ ] **2.4.2**: Capturar evento de teclado global `window.addEventListener('keydown')` para `Ctrl+K` / `Cmd+K`.
- [ ] **2.4.3**: Implementar busca rápida indexada em conversas salvas no SQLite via API existente.

### Tarefa 2.5: i18n e Refinamento
- [ ] **2.5.1**: Adicionar chaves de tradução para todos os comandos em `pt-BR` e `en-US`.
- [ ] **2.5.2**: Adicionar dica sutil no placeholder do input: *"Faça uma pergunta ou digite / para comandos..."*.

---

## 5. Critérios de Aceite (Definition of Done)

* [ ] Digitar `/` no campo de prompt abre instantaneamente o popover sem atraso perceptível (< 50ms).
* [ ] Navegação por setas e seleção por `Enter` funciona de forma estável.
* [ ] `Ctrl+K` abre a paleta de comando em qualquer tela da aplicação e fecha com `Escape`.
* [ ] Não há conflito quando o usuário cola um texto que contém barras (ex: URLs ou caminhos de arquivo).
