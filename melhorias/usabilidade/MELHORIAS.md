# MELHORIAS.md — Backlog de Usabilidade NexusLocal

**Gerado em:** 2026-10-17  
**Fonte:** Auditoria Playwright + axe-core + Nielsen  
**Branch:** `melhoria/02-auditoria-usabilidade`

---

## Tabela de Backlog

| ID | Descrição | Severidade | Impacto (1-5) | Esforço (1-5) | Risco (1-5) | Arquivo/Linha |
|---|---|---|---|---|---|---|
| U01 | Falha silenciosa em erros HTTP 429/500 — sem mensagem de erro visível ao usuário | 🔴 Crítico | 5 | 2 | 1 | `auditoria.spec.ts:205-230` (Fluxo 6) |
| U02 | Falha silenciosa em conexão offline — sem indicador visual de status de rede | 🔴 Crítico | 4 | 2 | 1 | `auditoria.spec.ts:249` (Fluxo 7) |
| U03 | Foco de teclado não alcança o composer — após 15 Tabs para em sidebar-brand | 🟠 Alto | 4 | 3 | 2 | `auditoria.spec.ts:378` (A11Y) |
| U04 | Botão com texto não discernível (button-name, axe crítico) | 🟠 Alto | 3 | 1 | 1 | `axe-initial.json` |
| U05 | Contraste de cores abaixo do WCAG 2 AA (2 elementos) | 🟠 Alto | 3 | 2 | 1 | `axe-initial.json` |
| U06 | Label-content-name-mismatch (texto visível ≠ accessible name) | 🟠 Alto | 2 | 1 | 1 | `axe-initial.json` |
| U07 | Botão Fusion não encontrado na tela inicial — problema de discoverability | 🟡 Médio | 3 | 2 | 2 | `auditoria.spec.ts:147` (Fluxo 3) |
| U08 | WebSearchToggle não encontrado — busca web não acessível via UI | 🟡 Médio | 3 | 2 | 2 | `auditoria.spec.ts:172` (Fluxo 4) |
| U09 | 16 sobreposições de botões em layout mobile 375px | 🟡 Médio | 3 | 3 | 2 | `auditoria.spec.ts:327` (Fluxo 8) |
| U10 | Hamburger/Menu mobile não encontrado — navegação mobile comprometida | 🟡 Médio | 3 | 2 | 2 | `auditoria.spec.ts:314` (Fluxo 8) |
| U11 | Nenhum indicador de loading visível na tela inicial | 🟡 Médio | 2 | 2 | 1 | `auditoria.spec.ts:406` (Nielsen) |
| U12 | Controles avançados do Fusion ocultos corretamente — ✅ Confirmado como correto | — | — | — | — | `auditoria.spec.ts:158` |
| U13 | Seletor de provedor não exposto na tela inicial — ✅ Confirmado como correto | — | — | — | — | `auditoria.spec.ts:133` |
| U14 | Sidebar limpa com 0 itens técnicos — ✅ Confirmado como correto para nível Simples | — | — | — | — | `auditoria.spec.ts:462` |

---

## Priorização Sugerida

### P0 — Imprescindível (antes de qualquer lançamento)
1. **U01** — Feedback de erro HTTP (429/500)
2. **U02** — Indicador de offline
3. **U03** — Navegação por teclado até o composer

### P1 — Importante (melhorar UX significativamente)
4. **U04-U06** — Correções de acessibilidade (axe-core)
5. **U07-U08** — Discoverability de Fusion e WebSearch

### P2 — Desejável (melhorias incrementais)
6. **U09-U10** — Layout mobile (sobreposições e menu)
7. **U11** — Indicador de loading

---

## Observações Técnicas

- **Zero alteração em código de produto** nesta auditoria — todos os achados são observações da interface atual
- **Mocks de API** foram necessários porque o backend produz dados reais que interferem nos testes; os mocks simulam respostas neutras para isolar a avaliação da UI
- **Seletor `.composer-textarea`** é o elemento-alvo principal do composer; sua presença/ausência indica o estado de autenticação e renderização do chat
- **Provedor de TTS** (Gemini/Edge) não influencia nos testes de UI — apenas no pipeline de áudio do Web Jornal
- ** screenshots** estão em `melhorias/usabilidade/screenshots/baseline/` e são referenciais para comparação futura
