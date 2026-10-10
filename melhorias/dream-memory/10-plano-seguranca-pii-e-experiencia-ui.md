# 🛡️ Plano de Ação 4: Segurança (PII/Secrets), Experiência na UI e Desambiguação Ativa

> **Foco:** Sanitização de Segredos, Visualização de Linhagem no Frontend e Desambiguação Assistida  
> **Localização:** `melhorias/dream-memory/10-plano-seguranca-pii-e-experiencia-ui.md`  
> **Status:** Pronto para Execução  
> **Dependência:** Planos 1, 2 e 3  

---

## 1. Visão Geral e Justificativa

Para que o usuário sinta que o sistema de memória do NexusLocal é não apenas mais capaz, mas também mais **seguro, transparente e controlável** do que as soluções da OpenAI ou Anthropic, duas frentes são fundamentais:
1. **Segurança e Higiene de Dados:** Desenvolvedores frequentemente colam trechos de código com tokens, chaves de API, senhas ou variáveis de ambiente no chat. Se o extrator salvar essas credenciais na memória e o consolidador fundi-las em fatos duradouros, cria-se um risco de vazamento involuntário nos prompts de conversas futuras.
2. **Transparência e Controle do Usuário:** O usuário deve ser capaz de enxergar a linhagem de qualquer fato consolidado (de onde veio, por que foi fundido, qual fato o substituiu) e ser consultado ativamente quando duas informações forem genuinamente conflitantes em vez de a IA "adivinhar" por conta própria.

---

## 2. Tarefas e Subtarefas Detalhadas

### 📋 Tarefa 1: Sanitização Automática de Dados Sensíveis (Secrets & PII Redactor)
**Objetivo:** Impedir que senhas, tokens de API ou credenciais confidenciais sejam perpetuados no banco de memória adaptativa.

* [ ] **Subtarefa 1.1: Módulo Regex de Detecção de Segredos em `backend/memory.py`.**
  * Implementar analisador de segurança com detecção para os seguintes padrões:
    * Chaves OpenAI (`sk-proj-...`, `sk-...`), Anthropic (`sk-ant-...`), Google AI (`AIza...`).
    * Tokens de acesso GitHub (`ghp_...`, `github_pat_...`), AWS Access Keys (`AKIA...`).
    * Strings de conexão com senha (ex: `postgres://user:pass@host`, `mongodb://...`).
    * Tokens JWT (`eyJh...`).
    * CPFs, senhas explicitadas (ex: `"minha senha é 123456"`).

* [ ] **Subtarefa 1.2: Política de Redação Pré-Persistência.**
  * Antes de salvar qualquer fato em `add_memory_fact` ou durante o `apply_dream_operations`:
    * Substituir o valor sensível pela máscara `[REDACTED_CREDENTIAL]`.
    * Se o fato consistir unicamente em uma credencial exposta, descartá-lo imediatamente com log de aviso: `logger.warning("[Security] Credencial detectada e descartada da memória persistente.")`.

---

### 📋 Tarefa 2: Interface Visual de Linhagem e Diff de Memórias (Frontend UX)
**Objetivo:** Permitir ao usuário explorar com facilidade o histórico e a evolução das suas memórias no painel de controle.

* [ ] **Subtarefa 2.1: Visualização de Linhagem Bidirecional no `UserMemoryPanel.tsx`.**
  * Em [`frontend/src/components/UserMemoryPanel.tsx`](file:///j:/Arquivos%20Osmar/Multi+/frontend/src/components/UserMemoryPanel.tsx), para fatos que possuem `superseded_by_id` ou foram originados de um merge (`source_dream_id IS NOT NULL`):
    * Exibir badge sutil de linhagem (ex: `✦ Consolidado`).
    * Ao clicar no badge, abrir um popover mostrando os fatos ancestrais originais que foram fundidos para dar origem àquele fato.

* [ ] **Subtarefa 2.2: Componente de Diff Visual no Preview do Diário de Sonhos.**
  * Em [`frontend/src/components/DreamJournalSection.tsx`](file:///j:/Arquivos%20Osmar/Multi+/frontend/src/components/DreamJournalSection.tsx):
    * Melhorar a exibição do relatório de simulação (`/dream-preview`), utilizando cores semânticas inspiradas em Git Diffs:
      * 🟢 Verde: Fatos novos criados por fusão.
      * 🟡 Amarelo: Fatos que substituíram informações antigas (supersede).
      * 🔴 Vermelho: Fatos arquivados (com a justificativa clara exibida).
      * ⚪ Neutro: Fatos mantidos intactos (keep).

* [ ] **Subtarefa 2.3: Filtros Avançados por Status no Painel de Memórias.**
  * Adicionar abas de navegação no topo da lista de fatos:
    * `Ativos (X)`
    * `Fixados (Y)`
    * `Consolidados / Histórico (Z)`
    * `Arquivados (W)`
  * Permitir que o usuário visualize fatos passados e, se desejar, reative um fato arquivado com um clique.

---

### 📋 Tarefa 3: Fila de Desambiguação Ativa (Perguntas Inteligentes sob Incerteza)
**Objetivo:** Quando o consolidador identificar duas informações contraditórias com nível similar de incerteza, em vez de chutar, criar uma pendência elegante para o usuário dirimir.

* [ ] **Subtarefa 3.1: Detecção de Incerteza Alta no Dream Consolidator.**
  * Se o modelo detectar duas afirmações conflitantes sem datas claras (ex: *"Usa Windows como SO principal"* vs *"Migrou para Linux como SO principal"* ambos sem timestamp conclusivo), emitir operação do tipo:
    ```json
    {
      "action": "flag_disambiguation",
      "fact_ids": ["f12", "f34"],
      "question": "Identifiquei informações conflitantes: você está utilizando Windows ou Linux atualmente?"
    }
    ```

* [ ] **Subtarefa 3.2: Card de Confirmação Rápida na Interface.**
  * Criar tabela `memory_pending_questions` no SQLite.
  * Renderizar banner discreto no topo do painel de memórias ou no chat sugerindo a escolha em 1 clique:
    * Opção A: *"Uso Windows"*
    * Opção B: *"Uso Linux"*
  * Ao clicar, o sistema aplica imediatamente o `supersede` correto com 100% de precisão e consentimento do usuário.

---

### 📋 Tarefa 4: Backup, Exportação e Importação Segura
**Objetivo:** Dar autonomia total ao usuário sobre seu cérebro digital com exportação/importação sem perda de integridade.

* [ ] **Subtarefa 4.1: Exportação Completa em JSON e Markdown.**
  * Implementar endpoint `GET /api/memory/export-bundle` que gera um arquivo `.zip` ou `.json` contendo:
    * Todos os fatos ativos e históricos com metadados (datas, confiança, fixados, linhagem).
    * Todos os snapshots salvos.
    * Relatório formatado em Markdown para leitura humana direta.

* [ ] **Subtarefa 4.2: Importação com Deduplicação Semântica.**
  * Aprimorar o endpoint existente `POST /api/memory/import` para realizar verificação prévia via FastEmbed: se um fato importado tiver similaridade $> 0.95$ com um fato ativo existente, vinculá-lo sem criar duplicatas inúteis.

---

## 3. Critérios de Aceite da Fase de Segurança e UI
1. Nenhuma chave de API ou credencial colada em conversas de teste é armazenada em texto claro no banco de dados.
2. A interface do usuário exibe com clareza o diff colorido das operações antes e depois de cada consolidação.
3. Fatos gerados por merge exibem de forma transparente seus fatos de origem ao usuário.
4. Exportação e importação de backup restauram 100% dos dados mantendo status e pinagem preservados.
