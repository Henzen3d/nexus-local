# 🖥️ Fase 4: Interface de Usuário, Edição Inline, Diário de Sonhos e Auditoria

## 1. Objetivo Técnico
Aprimorar o componente [`UserMemoryPanel.tsx`](file:///j:/Arquivos%20Osmar/Multi+/frontend/src/components/UserMemoryPanel.tsx) para transformar a memória em uma experiência transparente, auditável e sob total controle do usuário:
1. **Edição Inline Direta:** Permitir que o usuário clique e edite o texto ou categoria de qualquer fato da memória em tempo real com auto-invalidação de cache.
2. **Modo Simulação (*Dry-Run Diff Preview*):** Visualizar antecipadamente quais fatos seriam fundidos, substituídos ou arquivados antes de efetivar o sonho.
3. **Diário de Sonhos com Streaming de Progresso:** Linha do tempo visual com telemetria detalhada e barra de progresso em tempo real para disparos manuais.
4. **Reversão Segura em 1 Clique (Regra do Último Sonho):** Botão de rollback restrito ao ciclo mais recente, com confirmação contextual e bloqueio contra reversões em cascata incoerentes.
5. **Banner Discreto Pós-Sonho:** Notificação sutil ao reabrir o app após uma consolidação noturna automática.

---

## 2. Especificação dos Novos Componentes de UI

### A. Edição Inline de Fatos (Inline Edit)
Na lista de memórias:
* Ícone de lápis (`Pencil`) em cada card de fato.
* Ao clicar, o texto converte-se em textarea ajustável com seletor de categoria e botões `Salvar` e `Cancelar`.
* Salvar chama `PUT /api/memory/facts/{fact_id}`, incrementando `version` e recalculando embedding FastEmbed e fingerprint.
* Exibição de badge visual discreto `[📌 Fixado]` e `[Familiar]` (para fatos com chaves `family.*`).

---

### B. Painel "Diário de Sonhos" (Dream Journal)
Aba dedicada no `UserMemoryPanel`:

```
┌────────────────────────────────────────────────────────────────────────┐
│  🌙 Diário de Sonhos (Consolidação Inteligente)                        │
│  [ Simular Consolidação (Preview) ]     [ Executar Agora ⚡ ]          │
├────────────────────────────────────────────────────────────────────────┤
│  ● Hoje às 03:32 (Ollama · Qwen 2.5 7B)                     [Reverter] │
│    - 14 fatos analisados ➔ 8 fatos consolidados (-42% de ruído)        │
│    - 4 fatos fundidos em stack técnica                                 │
│    - 2 datas relativas convertidas em absolutas                        │
│    - 0 fatos fixados alterados                                         │
│    - Resumo: "Consolidou tecnologias frontend e atualizou residência." │
├────────────────────────────────────────────────────────────────────────┤
│  ● 05/10 às 03:30 (Groq · Llama 3.3 70B)           [Reversão Bloqueada]│
│    - 22 fatos analisados ➔ 15 fatos consolidados                       │
│    - [Tooltip: Apenas o ciclo mais recente pode ser revertido]         │
└────────────────────────────────────────────────────────────────────────┘
```

#### 🛡️ Regra de Negócio para Reversão (Rollback):
* Apenas o **último registro ativo** que tenha `can_rollback === true` retornado pela API pode ser revertido diretamente.
* Se o snapshot já foi expurgado pela retenção circular de 7 dias, o botão vira uma tag neutra *"Snapshot Expirado"* com tooltip explicativo.
* A reversão abre modal de confirmação com a lista exata dos fatos que serão restaurados.

---

### C. Modal de Simulação (Dry-Run Diff Preview)
Ao clicar em *"Simular Consolidação"*:
* Dispara `POST /api/memory/dream-preview`.
* Exibe modal com abas de categorização das operações propostas:
  * 🟢 **Novos Fatos Fundidos (Merge):** Mostra fatos A + B e o fato resultante formulado.
  * 🟡 **Atualizados (Supersede):** Mostra o fato antigo e o novo substituto.
  * 🔴 **Arquivados (Archive):** Exibe o motivo fundamentado pelo LLM.
  * ⚪ **Mantidos (Keep):** Lista de fatos inalterados.
* Botão de ação: `[Confirmar e Aplicar Agora]` (comuta a simulação para execução atômica real).

---

### D. Streaming de Progresso em Tempo Real (Disparo Manual)
Ao clicar em *"Executar Agora"*:
* Card de progresso dinâmico com indicador por etapas:
  * `[✓]` 1. Snapshot atômico de segurança criado (Hash: 4f8a...)
  * `[✓]` 2. Modelo conectado: Ollama (Qwen 2.5 7B, num_ctx: 8192)
  * `[⟳]` 3. Analisando contradições e unificando referências temporais...
  * `[ ]` 4. Aplicando transação flash (<80ms) e gerando vetores FastEmbed...
  * `[ ]` 5. Recalculando resumos rolling e atualizando cache semântico...

---

### E. Banner de Notificação Pós-Sonho
Exibido no topo do app no primeiro carregamento do dia seguinte após execução com sucesso:
`🌙 Memória consolidada com sucesso às 03:32: 14 ➔ 8 fatos otimizados (-42% de ruído). [Ver Diário] [Desfazer]`

---

### F. Contadores Transparentes e Busca Filtrada
No topo da listagem de fatos em `UserMemoryPanel.tsx`:
* **Censo de Fatos:** Exibe com precisão **"24 fatos ativos"** e, se houver histórico, um chip discreto **"(+ 18 consolidados no histórico)"**.
* **Busca Inteligente:** O campo de busca pesquisa apenas fatos ativos por padrão. Uma checkbox discreta `[ ] Incluir histórico consolidado` expande a pesquisa para fatos com status `merged`/`superseded`/`archived`.

---

## 3. Divisão de Tarefas e Subtarefas

### Tarefa 4.1: Edição Inline de Fatos no Frontend
- [x] **4.1.1**: Adicionar estado de edição por ID (`editingFactId`, `editText`, `editCategory`) no [`UserMemoryPanel.tsx`](file:///j:/Arquivos%20Osmar/Multi+/frontend/src/components/UserMemoryPanel.tsx).
- [x] **4.1.2**: Implementar `api.updateMemoryFact(id, { fact, category })` no cliente API [`frontend/src/api/client.ts`](file:///j:/Arquivos%20Osmar/Multi+/frontend/src/api/client.ts).
- [x] **4.1.3**: Suporte visual para badges de fatos fixados (`Pin`) e familiares (`family.*`).
- [x] **4.1.4**: Recarregamento atômico de estados: após salvar edição ou executar rollback, disparar recarregamento simultâneo via `Promise.all([api.getUserMemory(), api.getMemoryStats(), api.getMemorySummaries()])` para evitar renderizações intermediárias descompassadas.

### Tarefa 4.2: Seção de Logs e Diário do Dream
- [x] **4.2.1**: Criar componente `DreamJournalCard.tsx` exibindo data, provedor/modelo, taxa de compressão e notas analíticas.
- [x] **4.2.2**: Adicionar botão *"Executar Agora"* com consumo do stream SSE para feedback em tempo real das 5 etapas.
- [x] **4.2.3**: Implementar botão de rollback respeitando a flag `can_rollback` da API. Se `can_rollback === false`, renderizar estado desabilitado com tooltip informativo.

### Tarefa 4.3: Modal de Simulação (Dry-Run Preview)
- [x] **4.3.1**: Implementar `DreamPreviewModal.tsx` com visualização de diff lado a lado (antes vs depois).
- [x] **4.3.2**: Integração do botão *"Confirmar e Aplicar"* para efetivar a proposta simulada.

### Tarefa 4.4: Internacionalização e Tokens de Design
- [x] **4.4.1**: Adicionar chaves de tradução em `pt-BR.json` e `en-US.json` para todas as ações (`merge`, `supersede`, `archive`, `keep`, `preview`, `rollback`, `expiredSnapshot`).
- [x] **4.4.2**: Alinhar tipografia editorial e espaçamentos aos tokens do [`DESIGN.md`](file:///j:/Arquivos%20Osmar/Multi+/DESIGN.md).

---

## 4. Critérios de Aceite (Definition of Done)
* [x] O usuário consegue editar diretamente qualquer fato da lista em menos de 2 cliques.
* [x] O botão "Reverter" só fica ativo se `can_rollback === true` para o último ciclo; exibe estado expirado se o snapshot tiver sido purgado.
* [x] A listagem exibe claramente a quantidade de fatos ativos separados dos consolidados/arquivados.
* [x] A simulação (Dry-run) permite ao usuário revisar 100% das alterações antes de aplicá-las ao banco.
* [x] O disparo manual fornece feedback visual dinâmico em tempo real sem travar a interface.


