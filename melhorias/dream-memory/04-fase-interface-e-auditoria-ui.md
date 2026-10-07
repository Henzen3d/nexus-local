# 🖥️ Fase 4: Interface de Usuário, Edição Inline e Auditoria

## 1. Objetivo Técnico
Aprimorar o componente [`UserMemoryPanel.tsx`](file:///j:/Arquivos%20Osmar/Multi+/frontend/src/components/UserMemoryPanel.tsx) para transformar a memória em uma experiência transparente, auditável e sob total controle do usuário:
1. **Edição Inline Direta:** Permitir que o usuário clique e edite o texto ou categoria de qualquer fato da memória em tempo real.
2. **Histórico de Linhagem (Supersede View):** Aba ou filtro para ver fatos que foram substituídos/fundidos por consolidações anteriores, com link para o fato sucessor.
3. **Log de Sonhos (Dream Journal):** Linha do tempo visual mostrando quando o Dream rodou, quantos fatos foram fundidos/otimizados e notas do resumo.
4. **Botão de Rollback em 1 Clique:** Capacidade de reverter o último ciclo de consolidação com confirmação segura.

---

## 2. Especificação dos Novos Componentes de UI

### A. Edição Inline de Fatos (Inline Edit)
Na lista de memórias:
* Ícone de lápis (`Pencil`) em cada card de fato.
* Ao clicar, o texto vira um input com botões de Salvar (`Save`) e Cancelar (`X`).
* Salvar chama `PUT /api/memory/facts/{fact_id}` atualizando o fato, versionando e invalidando o fingerprint de cache.

### B. Painel "Diário de Sonhos" (Dream Journal)
Aba secundária no `UserMemoryPanel`:

```
┌────────────────────────────────────────────────────────────────────────┐
│  🌙 Diário de Sonhos (Consolidação Noturna)     [Executar Agora ⚡]    │
├────────────────────────────────────────────────────────────────────────┤
│  ● Hoje às 03:32 (Ollama · Qwen 2.5 7B)                     [Reverter] │
│    - 14 fatos analisados ➔ 8 fatos consolidados (-42% de ruído)        │
│    - 4 fatos fundidos em stack técnica                                 │
│    - 2 datas relativas convertidas em absolutas                        │
│    - Nota: "Consolidou tecnologias frontend e atualizou residência."   │
├────────────────────────────────────────────────────────────────────────┤
│  ● 05/10 às 03:30 (Groq · Llama 3.3 70B)                    [Reverter] │
│    - 22 fatos analisados ➔ 15 fatos consolidados                       │
└────────────────────────────────────────────────────────────────────────┘
```

### C. Filtro de Linhagem de Memória
* Filtro de status: `[ Ativas (default) ] | [ Substituídas / Merged ] | [ Todas ]`.
* Fatos com status `superseded` exibem um badge discreto:
  `↳ Substituído por: "Stack frontend: React e Tailwind"` com link direto.

---

## 3. Divisão de Tarefas e Subtarefas

### Tarefa 4.1: Edição Inline de Fatos no Frontend
- [ ] **4.1.1**: Adicionar estado de edição por ID (`editingFactId`, `editText`, `editCategory`) no [`UserMemoryPanel.tsx`](file:///j:/Arquivos%20Osmar/Multi+/frontend/src/components/UserMemoryPanel.tsx).
- [ ] **4.1.2**: Implementar `api.updateMemoryFact(id, { fact, category })` no cliente API.
- [ ] **4.1.3**: Endpoint correspondente no backend `PUT /api/memory/facts/{fact_id}` em [`backend/routers/memory.py`](file:///j:/Arquivos%20Osmar/Multi+/backend/routers/memory.py).

### Tarefa 4.2: Seção de Logs e Auditoria do Dream
- [ ] **4.2.1**: Criar componente `DreamJournalCard.tsx` exibindo data, provedor/modelo, taxa de compressão e notas.
- [ ] **4.2.2**: Adicionar botão *"Executar Consolidação Agora"* com spinner e feedback de conclusão.
- [ ] **4.2.3**: Adicionar botão de *"Reverter este Sonho"* disparando modal de confirmação.

### Tarefa 4.3: Visualização de Fatos Substituídos e Linhagem
- [ ] **4.3.1**: Adicionar toggle de exibição de fatos arquivados/superseded.
- [ ] **4.3.2**: Exibir tag com data de desativação e o motivo da consolidação.

### Tarefa 4.4: Internacionalização e Tokens
- [ ] **4.4.1**: Adicionar textos nos arquivos de tradução (`pt-BR.json` e `en-US.json`).
- [ ] **4.4.2**: Aplicar tokens de design editorial do [`DESIGN.md`](file:///j:/Arquivos%20Osmar/Multi+/DESIGN.md).

---

## 4. Critérios de Aceite (Definition of Done)
* [ ] O usuário consegue editar diretamente qualquer fato em menos de 2 cliques.
* [ ] A lista de sonhos exibe o histórico real retornado da tabela `dream_logs`.
* [ ] Clicar em "Reverter" desfaz a consolidação e atualiza a lista de fatos imediatamente na tela.
