# 📋 Checklist Operacional de Execução: 5 Frentes de Melhoria UX/UI

Use este arquivo para marcar o progresso conforme cada tarefa for sendo implementada no código.

---

## 📌 Frente 01: Composer com Action Pills & Modos
*Arquivo de especificação detalhada:* [`01-composer-action-pills.md`](file:///j:/Arquivos%20Osmar/Multi+/melhorias/novas-5-melhorias-ux/01-composer-action-pills.md)

- [ ] **1.1.1**: Criar componente `ComposerPill.tsx` com estados inativo/ativo/disabled.
- [ ] **1.1.2**: Implementar micro-animações de hover e transição de estado ativo (150ms).
- [ ] **1.1.3**: Suporte a atalhos de teclado para alternar pills (`Alt+F`, `Alt+W`).
- [ ] **1.2.1**: Reorganizar layout de rodapé em `MessageInput.tsx` (`.input-actions-left` e `.input-actions-right`).
- [ ] **1.2.2**: Adicionar Pill do Modo Fusion no composer conectada ao `useStore`.
- [ ] **1.2.3**: Adicionar Pill de Raciocínio (DeepThink/Thinking) com alternância rápida de modelo.
- [ ] **1.2.4**: Atualizar botão de Pesquisa Web para formato de Pill com indicador de estado.
- [ ] **1.2.5**: Integrar Pill do Prompt Enhancer com loader animado durante requisição.
- [ ] **1.3.1**: Adaptar `ModelSelector.tsx` para versão compacta embutida no canto direito do input.
- [ ] **1.3.2**: Exibir badges de provedor e latência no dropdown do modelo.
- [ ] **1.4.1**: Ajustar responsividade mobile (< 640px) com BottomSheet para overflow de pills.
- [ ] **1.4.2**: Garantir área de toque mínima de 44x44px em botões mobile.
- [ ] **1.5.1**: Definir variáveis semânticas CSS em `index.css` para as pills.
- [ ] **1.5.2**: Validar contraste WCAG AA e navegação acessível por teclado.

---

## 📌 Frente 02: Slash Commands (`/`) e Navegação Total por Teclado
*Arquivo de especificação detalhada:* [`02-slash-commands-shortcuts.md`](file:///j:/Arquivos%20Osmar/Multi+/melhorias/novas-5-melhorias-ux/02-slash-commands-shortcuts.md)

- [ ] **2.1.1**: Criar hook `useSlashCommands.ts` para capturar gatilho `/` no início do input.
- [ ] **2.1.2**: Implementar parser de filtragem de comandos em tempo real.
- [ ] **2.1.3**: Suporte para auto-completar com `Tab` e `Enter`.
- [ ] **2.2.1**: Criar componente `SlashCommandMenu.tsx` ancorado sobre a caixa de texto.
- [ ] **2.2.2**: Aplicar estilização editorial do design system (`border-radius: 12px`, sombras suaves).
- [ ] **2.2.3**: Exibir ícones, nomes e atalhos na lista de comandos.
- [ ] **2.3.1**: Mapear comando `/modelo [nome]` para seleção instantânea.
- [ ] **2.3.2**: Mapear comando `/fusion` para alternar orquestração multi-LLM.
- [ ] **2.3.3**: Mapear comando `/web` para forçar busca na internet.
- [ ] **2.3.4**: Mapear comando `/melhorar` para acionar o Prompt Enhancer.
- [ ] **2.3.5**: Mapear comando `/novo` para limpar e iniciar novo chat.
- [ ] **2.3.6**: Mapear comandos de template (`/codigo`, `/resumo`, `/traduzir`).
- [ ] **2.4.1**: Criar componente `CommandPaletteModal.tsx` para atalho `Ctrl+K`.
- [ ] **2.4.2**: Registrar listener global para `Ctrl+K` e `Cmd+K`.
- [ ] **2.4.3**: Busca fuzzy rápida indexando conversas, projetos e ações do sistema.
- [ ] **2.5.1**: Cadastrar textos de comando no i18n (`pt-BR` e `en-US`).
- [ ] **2.5.2**: Adicionar dica de `/` no placeholder do input.

---

## 📌 Frente 03: Accordion de Raciocínio (Thought Stream) & Timeline Fusion
*Arquivo de especificação detalhada:* [`03-reasoning-thought-stream.md`](file:///j:/Arquivos%20Osmar/Multi+/melhorias/novas-5-melhorias-ux/03-reasoning-thought-stream.md)

- [ ] **3.1.1**: Criar utilitário `thoughtParser.ts` para separar tags `<think>` do texto final.
- [ ] **3.1.2**: Gerenciar streaming com tag `<think>` aberta sem quebra de renderização.
- [ ] **3.1.3**: Suporte ao campo nativo `reasoning_content` da API do DeepSeek/OpenRouter.
- [ ] **3.2.1**: Criar componente `ThoughtAccordion.tsx`.
- [ ] **3.2.2**: Implementar cronômetro em tempo real de inferência analítica (*Pensando... (3.4s)* ➔ *Pensou por 8.2s ▾*).
- [ ] **3.2.3**: Implementar auto-recolhimento suave ao iniciar a chegada da resposta final.
- [ ] **3.2.4**: Adicionar botão de cópia isolada para o processo de pensamento.
- [ ] **3.3.1**: Redesenhar `FusionStatusCard.tsx` com layout de timeline minimalista.
- [ ] **3.3.2**: Exibir indicadores de latência e progresso por provedor participante.
- [ ] **3.3.3**: Permitir colapsar e expandir os rascunhos individuais de cada IA.
- [ ] **3.4.1**: Definir estilos e contrastes discretos em `index.css`.
- [ ] **3.4.2**: Aplicar tipografia mono suave/itálica com alta legibilidade.

---

## 📌 Frente 04: Bento Starter Cards no Empty State
*Arquivo de especificação detalhada:* [`04-bento-starter-cards.md`](file:///j:/Arquivos%20Osmar/Multi+/melhorias/novas-5-melhorias-ux/04-bento-starter-cards.md)

- [ ] **4.1.1**: Criar componente `BentoStarterGrid.tsx` com layout 2x2 responsivo.
- [ ] **4.1.2**: Criar componente `BentoCard.tsx` com hover elegante e badges temáticos.
- [ ] **4.1.3**: Aplicar transição de fade-in escalonada na renderização inicial da tela vazia.
- [ ] **4.2.1**: Integrar card *Modo Fusion Multi-LLM* com ativação automática e prompt pronto.
- [ ] **4.2.2**: Integrar card *Código & Alta Performance* pré-selecionando modelo ultra-rápido.
- [ ] **4.2.3**: Integrar card *Análise de Documentos* disparando abertura de arquivo local.
- [ ] **4.2.4**: Integrar card *Pesquisa Atualizada na Web* ativando busca na internet.
- [ ] **4.3.1**: Configurar transição de saída dos cards sem pulos bruscos ao enviar primeira mensagem.
- [ ] **4.3.2**: Garantir centralização vertical perfeita no empty state conforme `melhorias-UX-UI.md`.
- [ ] **4.4.1**: Conectar ordenação de cards ao perfil e histórico de uso do usuário.

---

## 📌 Frente 05: Sidebar Modular com Fixados e Agrupamento Temporal
*Arquivo de especificação detalhada:* [`05-sidebar-pins-temporal.md`](file:///j:/Arquivos%20Osmar/Multi+/melhorias/novas-5-melhorias-ux/05-sidebar-pins-temporal.md)

- [ ] **5.1.1**: Adicionar botão destacado `+ Nova Conversa` no topo da sidebar.
- [ ] **5.1.2**: Implementar Quick Shelf para *Projetos*, *Artefatos* e *Rankings*.
- [ ] **5.2.1**: Criar seção visual nobre dedicada para conversas `Fixadas`.
- [ ] **5.2.2**: Adicionar botão de pino/estrela no hover de cada conversa para fixar em 1 clique.
- [ ] **5.2.3**: Permitir colapsar o grupo de fixados quando houver muitos itens.
- [ ] **5.3.1**: Implementar agrupamento cronológico automático (*Hoje*, *Ontem*, *7 dias*, *30 dias*).
- [ ] **5.3.2**: Estilizar cabeçalhos de data discretos com estilo editorial.
- [ ] **5.4.1**: Adicionar barra de busca rápida no topo da lista com filtro em tempo real.
- [ ] **5.4.2**: Realçar texto pesquisado nos títulos filtrados.
- [ ] **5.5.1**: Revisar padding e respiros verticais em múltiplos de 8px na sidebar.
- [ ] **5.5.2**: Homogeneizar estados de hover e item selecionado.
