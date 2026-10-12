# 🧠 Especificação Técnica: Sequência de Pensamento e Ações Inline (Grok-Style)
**NexusLocal / Multi+**

---

## 🎯 1. Diagnóstico do Problema Atual de UX

1. **Modal / Toast Intrusivo de Pesquisa Web:**
   - Atualmente, quando o modelo decide fazer pesquisa web (`search_start`), o frontend emite um toast/notificação (`s.showToast(i18n.t('chat.searchingWeb'))`).
   - **Impacto:** O usuário sente que isso parece um erro ou uma interrupção inesperada do fluxo, quebrando a imersão da conversa.
2. **Fragmentação de Processos Assíncronos:**
   - O `ThinkingBlock` apenas exibe o conteúdo de `<think>...</think>` isoladamente.
   - A pesquisa web só exibe suas fontes no final (`WebSearchSources`) de maneira desconectada.
   - Navegações de páginas, múltiplas queries de busca e ações de ferramentas ficam invisíveis durante a execução.
3. **Falta de Feedback Temporal:**
   - Não há indicador de tempo decorrido em tempo real (`Trabalhando para 14s...`) nem de tempo total final consolidado (`Trabalhou por 1m 13s`).

---

## 📸 2. Análise Visual da Referência (Grok 4.7)

Com base nos registros em `melhorias/sequencia-pensamento/`:

### Fase 1: Em Execução (Streaming Ativo)
- O assistente não exibe modais nem toasts.
- Diretamente na bolha da resposta, uma árvore/linha do tempo vertical com micro-ícones é renderizada em tempo real:
  - 🌐 `Navegado fixblu.com.br`
  - 🔍 `Executou 2 pesquisas`
    - Sub-itens indentados com as queries exatas executadas (ex: `site:fixblu.com.br (...)`).
  - 🌐 `Accessing the Fix Serviços blog`
  - 🌐 `Navegado fixblu.com.br/blog/`
  - ▽ `Executou 1 ação do navegador`
- No rodapé da lista, um indicador dinâmico com ícone pulsante:
  - ⚡ `Trabalhando para {X}s` (contador de segundos rodando ao vivo).

### Fase 2: Concluído (Resposta Entregue)
- Toda a árvore se recolhe automaticamente em uma barra discreta e minimalista:
  - Exemplo: `Trabalhou por 1m 13s` (ou `Pensou e pesquisou por 14s`) acompanhado de um chevron `v`.
- Ao clicar na barra, o usuário pode expandir a qualquer momento para auditar todos os passos, queries, URLs e o texto de raciocínio.
- A resposta final em Markdown começa logo abaixo, sem ruído visual.

---

## 🏗️ 3. Arquitetura e Contratos de Dados Propostos

### A. Tipos no Frontend (`frontend/src/types.ts`)
```typescript
export type ProcessStepType = 'think' | 'search' | 'navigate' | 'tool' | 'browser'

export interface ProcessStep {
  id: string
  type: ProcessStepType
  title: string
  detail?: string
  subSteps?: string[]
  status: 'running' | 'completed' | 'failed'
  durationMs?: number
}

export interface ThoughtProcess {
  steps: ProcessStep[]
  thinkingContent?: string
  totalDurationMs?: number
  isWorking: boolean
}
```

### B. Eventos SSE / WebSocket no Backend (`backend/routers/chat.py`)
- Em vez de apenas `search_start` genérico:
  - `process_step_start`: `{ id, type: 'search', title: 'Executando pesquisa web', detail: query }`
  - `process_step_update`: `{ id, subSteps: [query1, query2] }`
  - `process_step_end`: `{ id, status: 'completed' }`
- Manter retrocompatibilidade total com clientes antigos.

### C. Ajuste no Hook (`frontend/src/hooks/useChat.ts`)
- **Remover** o `s.showToast(i18n.t('chat.searchingWeb'))` no evento `search_start`.
- Alimentar o estado da mensagem atual com o `ProcessStep` correspondente.

### D. Componente Visual (`ExecutionSequence.tsx` / `ThinkingBlock.tsx`)
- Estilo alinhado aos design tokens do NexusLocal:
  - `var(--surface-soft)`, `var(--hairline)`, `var(--ink)`, `var(--muted)`, `var(--primary)`.
  - Tipografia: `var(--font-thinking, 13px)` e pesos sutis.
  - Animação suave para novos passos surgindo (fade-in + slide down de 2px).
  - Timer suave atualizando a cada 1 segundo enquanto `isWorking === true`.
