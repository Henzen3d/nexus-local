# Loop de Auto-Aperfeiçoamento — NexusLocal

> Arquivo canônico que rege o ciclo de iteração de usabilidade.
> Ramo de trabalho: `melhoria/<id>-<slug>`. Merge na main só com aprovação explícita do usuário.

---

## 1. Níveis de Interface (`ui_level`)

Armazenado em `useStore.ts` via `localStorage` (padrão: `'simples'` para novo usuário — confirmar com usuário antes de fixar).

### Simples (referência: Meta.ai / Muse.ai)
- **Input:** caixa única e limpa. Anexos e busca web visíveis.
- **Roteamento:** 100% automático (`smart_router.py` + `reasoning_effort_auto = true` por baixo dos panos).
- **Fusion:** botão único amigável `"Resposta Profunda"` (sem parâmetros expostos).
- **Escondido:** ModelSelector, ProviderSelector, RAG/Projects, UserMemoryPanel, AdminPanel, `was_fallback`, parâmetros técnicos.
- **Padrão para novo usuário:** Simples (sujeito a confirmação do usuário).

### Intermediário (referência: ChatGPT)
- Adiciona `ModelSelector` compacto (Auto / Rápido / Pensar mais), mapeado internamente para modelo e reasoning.
- `WebSearchToggle` visível.
- Projetos/RAG acessíveis pela sidebar.
- Indicador discreto de modelo ativo.
- **Ainda escondido:** provedor manual, reasoning manual, Fusion avançado, Admin.

### Avançado (referência: Claude / UI atual)
- Todos os controles expostos: modelo, provedor, reasoning manual, Fusion/Judge completo, Auto Router, Enhancer, parâmetros, `was_fallback`.
- `UserMemoryPanel`, `AdminPanel` acessíveis.

### Regras de migração
- Um único código com mapa de visibilidade `ui_level → controles` no `useStore`. Não três UIs duplicadas.
- Trocar de nível **nunca perde a conversa** (conversas persistem; só a camada de controles muda).
- Persistir primeiro em `localStorage`; tabela no SQLite só com aprovação explícita do usuário.
- Alteração de nível é instantânea, sem reload.

---

## 2. Execução Segura de Subagentes

**Regra de ouro:** NUNCA passe conteúdo de `.md` via `$(cat arquivo)` em aspas duplas (bash expande crases e `$variáveis`, corrompe o prompt).

### agy (tarefas pesadas)
```bash
agy --dangerously-skip-permissions --print "Leia o arquivo melhorias/TASK_ATUAL.md e execute todas as instruções contidas nele." --output-format json
```

### agy (tarefas leves — triagem, microcopy, resumo de diff)
```bash
agy --model deepseek/deepseek-v4-flash --effort high --dangerously-skip-permissions --print "Leia o arquivo melhorias/TASK_ATUAL.md e execute todas as instruções contidas nele." --output-format json
```
**Confirmar o ID exato do modelo antes do primeiro uso.**

### opencode (opcional, só se instalado)
```bash
cat melhorias/PROMPT_OPENCODE.md | opencode run --model opencode/deepseek-v4.1-flash-free -
```

### Proibições absolutas
- Nunca ler ou alterar `.env`, chaves de API, ou dados sensíveis do usuário.
- Nunca forçar push.
- Máximo 5 iterações por rodada; depois relatório e espera por OK.

---

## 3. Ciclo por Iteração

1. **Orquestrador escolhe** o próximo item do backlog.
2. **Mini-plano** escrito em `melhorias/TASK_ATUAL.md` (adicione ao `.gitignore`).
3. **Delegar** ao executor (agy/opencode).
4. **Rodar** `judge.sh` + Playwright dos fluxos afetados (antes/depois).
5. **Autorrevisão** do diff: regressão, escopo extra, over-engineering, segredos.
6. **Passou:** commit convencional pequeno + push do branch `melhoria/<id>-<slug>` + atualizar backlog.
7. **Falhou 2×:** reverter e marcar bloqueado.
8. **Perguntar:** "qual a melhoria de maior impacto agora?" → voltar ao passo 1.

---

## 4. Metas de Usabilidade

| Meta | Critério |
|------|----------|
| Primeira mensagem | 1 ação a partir da tela inicial (nível Simples) |
| Erros de console | Zero nos fluxos críticos |
| Estados de UI | Todo fluxo tem estados de carregando, vazio e erro, com mensagem humana + ação de recuperação |
| Acessibilidade | Zero violações críticas no axe; fluxos principais operáveis por teclado |
| Mobile | 375px sem scroll horizontal nos 3 níveis |
| Falha de API/modelo | Sempre explica o que houve e o que fazer |

---

## 5. Freios

- Merge na main só com **aprovação explícita do usuário**.
- Nunca force push.
- Proibido sem aprovação: schema do SQLite, autenticação/chaves, dependência nova (exceto Playwright), apagar dados, mudança grande de arquitetura.
- Parar de vez quando metas verdes e não houver item de impacto ≥ 3 aberto.

---

## 6. Documentos de Referência

| Arquivo | Conteúdo |
|---------|----------|
| `melhorias/usabilidade/AMBIENTE.md` | Estado do ambiente, status dos planos 01-05, comandos de teste |
| `melhorias/usabilidade/00-auditoria.md` | Achados da Fase 0 (heurísticas + acessibilidade) |
| `melhorias/usabilidade/MELHORIAS.md` | Backlog classificado (ID, descrição, severidade, impacto/esforço/risco) |
| `melhorias/usabilidade/01-niveis-de-interface.md` | Plano detalhado de implementação dos 3 níveis |
| `melhorias/TASK_ATUAL.md` | Tarefa em execução (ignorada pelo git) |
| `melhorias/PROMPT_OPENCODE.md` | Prompt para opencode (se usado) |
