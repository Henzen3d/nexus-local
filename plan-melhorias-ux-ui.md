# Plano de Execução — Melhorias UX/UI NexusLocal

## Goal
Elevar a interface do NexusLocal a um patamar "premium" (linguagem visual próxima de Claude/Notion/Linear/Raycast), sem copiar elementos protegidos, cobrindo: tokens de design, tipografia, sidebar, layout inicial dinâmico, caixa de prompt, header com CTA de apoio, e QA visual final.

**Stack assumida:** React 18 + TypeScript + Vite, estilos via CSS Modules/Tailwind + variáveis CSS (conforme DESIGN.md do projeto). Ajuste os caminhos de arquivo abaixo para os nomes reais dos seus componentes antes de rodar cada subtarefa — não tenho acesso ao repo neste chat.

---

## Fase 0 — Preparação (bloqueante, faça primeiro)

- [ ] **0.1** Criar branch `feature/ui-premium-refresh` a partir de `main` → Verify: `git status` mostra a branch ativa.
- [ ] **0.2** Localizar o arquivo central de tokens (ex: `src/styles/tokens.css` ou `tailwind.config.ts`) e o `DESIGN.md` atual → Verify: caminho confirmado e anotado no topo deste plano.
- [ ] **0.3** Tirar prints da UI atual (sidebar, tela inicial, chat ativo, header) para comparação "antes/depois" → Verify: 4 prints salvos em `/docs/ui-before/`.

---

## Fase 1 — Design Tokens (cores, espaçamento, raios, sombras)

Base para tudo que vem depois — sem isso as fases seguintes ficam inconsistentes.

- [ ] **1.1** Atualizar variáveis de cor no arquivo de tokens:
  ```css
  --bg-primary: #FCFBF8; /* ou #FBFAF7 */
  --bg-sidebar: #F7F4EE;
  --bg-card: #FFFFFF;
  --border-subtle: rgba(0,0,0,.06);
  --text-primary: #222222;
  --text-secondary: #555555;
  --text-tertiary: #777777;
  ```
  → Verify: nenhuma cor hardcoded restante nos componentes tocados nas fases seguintes (`grep -r "#F5F"` etc.).
- [ ] **1.2** Definir escala de espaçamento em múltiplos de 8 (`--space-1: 8px` até `--space-8: 64px`) e substituir paddings/margins "quebrados" (ex: `13px`, `22px`) pelos tokens mais próximos → Verify: build sem erro, visual sem elementos "espremidos".
- [ ] **1.3** Padronizar raios de borda: sidebar `16px`, cards `18px`, prompt `24px`, botões `12px` como tokens (`--radius-sidebar`, `--radius-card`, `--radius-prompt`, `--radius-button`) → Verify: inspecionar no DevTools cada componente usando o token correto.
- [ ] **1.4** Padronizar sombra única: `box-shadow: 0 6px 24px rgba(0,0,0,.06)` como `--shadow-soft`, aplicada a cards/prompt → Verify: nenhuma sombra "custom" divergente restando no CSS.

---

## Fase 2 — Tipografia

- [ ] **2.1** Trocar fonte para Inter ou Geist (import via `@fontsource` ou Google Fonts + `font-display: swap`) → Verify: `document.fonts` no console mostra a fonte carregada.
- [ ] **2.2** Aplicar pesos: títulos `600`, itens de menu `500`, texto corrido `400`; aplicar `--text-primary/secondary/tertiary` conforme hierarquia → Verify: nenhum texto usando cinza claro (`#999+`) fora do padrão definido.

---

## Fase 3 — Sidebar

- [ ] **3.1** Reduzir largura da sidebar em 20–25% (ex: de `280px` para `~220px`) → Verify: medir no DevTools.
- [ ] **3.2** Aumentar padding interno dos itens usando os tokens de espaçamento da Fase 1 → Verify: comparação visual com print "antes".
- [ ] **3.3** Corrigir alinhamento ícone+texto (usar `display:flex; align-items:center; gap: var(--space-2)`) → Verify: ícones e textos alinhados na mesma linha de base em todos os itens.
- [ ] **3.4** Reduzir peso visual das divisórias (`border-color` mais suave, ou substituir por espaçamento) entre grupos: Conversas / Favoritos / Recentes / Configurações → Verify: divisórias quase imperceptíveis, hierarquia por espaçamento.
- [ ] **3.5** Aplicar hover suave + destaque de item ativo na lista de conversas (transição 150ms) → Verify: hover/click testado manualmente em 3 itens.

---

## Fase 4 — Header Superior

- [ ] **4.1** Criar constante de configuração `SUPPORT_URL` em arquivo dedicado (ex: `src/config/support.ts`):
  ```ts
  export const SUPPORT_URL = "https://..."; // trocar depois por SUPPORT.md / Ko-fi / GitHub Sponsors
  ```
  → Verify: nenhuma URL hardcoded no componente do botão.
- [ ] **4.2** Substituir botão "Plano Gratuito" por `❤️ Apoiar o NexusLocal`, estilo discreto (outline/ghost), abrindo `SUPPORT_URL` em nova aba → Verify: clique abre a URL correta em `_blank`.
- [ ] **4.3** Ajustar estilo do botão para ficar visualmente equivalente a um CTA "elegante, não-propaganda" (padding, radius `--radius-button`, sem cor saturada demais) → Verify: comparação lado a lado com referência.

---

## Fase 5 — Layout Inicial (empty state) + Caixa de Prompt Dinâmica

Esta é a mudança de maior risco técnico — trata-se de estado de UI (centralizado vs. rodapé), não só CSS.

- [ ] **5.1** Identificar o componente de tela de nova conversa e o estado que controla "conversa vazia vs. conversa com mensagens" (ex: `messages.length === 0`) → Verify: estado localizado e logado no console.
- [ ] **5.2** Implementar layout condicional:
  - Se `messages.length === 0`: renderizar `Logo → Mensagem de boas-vindas → Prompt` centralizados verticalmente (flex column, `justify-content: center`, `height: 100%`).
  - Se houver mensagens: prompt fixo no rodapé (comportamento atual padrão de chat).
  → Verify: abrir nova conversa mostra layout centralizado; enviar 1ª mensagem faz o prompt "migrar" para o rodapé sem salto visual brusco.
- [ ] **5.3** Adicionar transição suave (200ms) na migração do prompt do centro para o rodapé (não precisa ser física complexa — fade/slide já resolve) → Verify: testar manualmente enviando a 1ª mensagem.
- [ ] **5.4** Redesenhar a caixa de prompt: mais larga, mais alta, mais padding interno, `--radius-prompt: 24px`, sombra `--shadow-soft` → Verify: comparação visual "antes/depois".

---

## Fase 6 — Ícones e Botões (Design System)

- [ ] **6.1** Auditar ícones usados no projeto e migrar tudo para uma única lib (Lucide ou Heroicons), mesmo `size` e `stroke-width` em todo o app → Verify: `grep` por imports de ícones de libs diferentes retorna vazio.
- [ ] **6.2** Criar/consolidar componente `<Button>` único com variantes (primary/secondary/ghost) compartilhando radius, padding, altura, peso de fonte e hover → Verify: todos os botões do app usam o componente (nenhum botão "solto" com estilo inline divergente).

---

## Fase 7 — Micro-animações

- [ ] **7.1** Aplicar transições padronizadas: hover `150ms`, fade `200ms`, slide `200ms` via token CSS (`--transition-fast`, `--transition-base`) nos componentes já tocados (sidebar, botões, prompt) → Verify: nenhuma animação abrupta perceptível ao navegar.

---

## Fase 8 — Responsividade

- [ ] **8.1** Testar colapso da sidebar em viewport mobile (< 768px) → Verify: sidebar colapsa/expande corretamente sem quebrar layout.
- [ ] **8.2** Verificar que o prompt permanece centralizado (empty state) e com espaçamento preservado em telas pequenas → Verify: testar em DevTools mobile emulation (iPhone SE e um Android médio).

---

## Fase 9 — Revisão Geral (QA visual) — sempre por último

- [ ] **9.1** Percorrer toda a interface procurando: desalinhamentos, paddings/radius/sombras fora do Design System, textos apagados, contraste insuficiente → Verify: checklist item a item comparado aos tokens da Fase 1.
- [ ] **9.2** Rodar teste de contraste (ex: DevTools Lighthouse ou axe) nos textos principais → Verify: contraste AA mínimo atingido nos textos `--text-primary/secondary`.
- [ ] **9.3** Comparar prints "antes" (Fase 0.3) vs. "depois" lado a lado → Verify: aprovação visual própria antes de abrir PR.
- [ ] **9.4** Abrir PR da branch `feature/ui-premium-refresh` com prints antes/depois na descrição → Verify: PR criado e revisável.

---

## Done When
- [ ] Sidebar 20–25% mais estreita, com hierarquia clara entre seções.
- [ ] Paleta neutra/quente aplicada (fundo, sidebar, cards, bordas, hover) via tokens.
- [ ] Tipografia legível (Inter/Geist, pesos corretos, sem cinza apagado).
- [ ] Tela inicial com layout centralizado (logo → mensagem → prompt) que migra para rodapé após a 1ª mensagem.
- [ ] Botão "❤️ Apoiar o NexusLocal" funcional, usando `SUPPORT_URL` configurável.
- [ ] Espaçamentos, raios, sombras e ícones consistentes em todo o app.
- [ ] QA visual final sem inconsistências identificadas.

## Notes
- A Fase 5 (empty state dinâmico) é a de maior risco/esforço técnico real — as demais são majoritariamente CSS/tokens. Priorize-a com folga de tempo.
- Se o NexusLocal usa Tailwind, os tokens da Fase 1 podem virar `theme.extend` no `tailwind.config.ts` em vez de CSS vars puras — adapte a sintaxe, a lista de decisões (cores/espaçamento/radius/sombra) continua a mesma.
- Recomendo versionar o `SUPPORT_URL` junto com o restante da config de ambiente, já pensando na troca futura para Ko-fi/GitHub Sponsors sem tocar em componente.
