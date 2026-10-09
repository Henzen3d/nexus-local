# Gráficos — plano

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Desenhar `bar`, `line` e `compare` com Recharts, a partir de `rows` já validadas.

**Architecture:** `ChartBlock` não interpreta eixo livre. `kind` escolhe o componente Recharts. Cor vem do índice da série, não do modelo.

**Tech Stack:** `recharts` 3.9.2, já dependência. Não adicionar pacote.

**Spec:** `melhorias/intelligent-ui/00-visao-e-spec.md` seção 4.3.

## Global Constraints

- Sem cor, tooltip HTML ou formatter vindo do JSON.
- Máximo 24 rows, já garantido pelo validador. O componente recusa de novo se a lista passar, e não desenha.
- Tabela `sr-only` com os mesmos números.
- Não criar gráfico no `UsageDashboard` nem no `RankingsView`. Eles já têm os deles.
- Flag off: não montar o componente.

---

### Task 1: bar

**Files:**
- Create: `frontend/src/ui/components/ChartCard.tsx`
- Modify: `frontend/src/ui/DynamicRenderer.tsx`

**Interfaces:**
- Consumes: bloco `chart` válido
- Produces: `ChartCard({ block })`, carregado com `React.lazy`. `DynamicRenderer.tsx` não importa `recharts`. Para `kind === "bar"`, um `BarChart` com uma `Bar`.

- [ ] **Step 1: Teste.** Título "Custo por 1M tokens" aparece. A tabela acessível contém "Groq 8B" e "0.05" quando esse for o row do teste. Não exigir pixel do canvas.

- [ ] **Step 2: Implementar `bar`.** `x_key` no eixo. `series[0].key` na barra. Fill: `var(--primary)`.

- [ ] **Step 3: Commit** `feat: gráfico de barras sob demanda na bolha`

- [ ] **Step 4: Conferir o chunk.** `App.tsx` importa `AdminPanel` na linha 8, e o admin já puxa `recharts`. Rodar o build e ver se `recharts` está no chunk do chat sem um bloco de gráfico. Se estiver, trocar o import de `AdminPanel` por `React.lazy` no mesmo passo. Não adicionar outra lib.

### Task 2: line e compare

**Files:**
- Modify: `ChartCard.tsx`

**Interfaces:**
- `line`: `LineChart`, uma `Line` por série, até 3.
- `compare`: `BarChart` com uma `Bar` por série, 2 a 4.
- Paleta por índice: `--primary`, `--cyan`, `--warning`, `--success`.

- [ ] **Step 1: Teste de kind inválido no componente.** Se `kind` chegar fora da união, retornar null. O validador já barra, o componente não confia.

- [ ] **Step 2: Implementar os dois kinds. Eixo e legenda usam `series.label`, não a key crua, quando o label existe.**

- [ ] **Step 3: Commit** `feat: gráficos line e compare na bolha`

Não adicionar tipo pizza, radar, mapa ou gráfico de área nesta fase.
