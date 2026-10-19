/goal Executar de ponta a ponta (sem pausas para confirmação) o loop completo de aperfeiçoamento da aba **PROJETOS** do NexusLocal (F0 a F5): paridade visual e funcional com o Projetos do Claude.ai, Barra de Capacidade de Contexto em tempo real e Montador de Contexto Único integrando Instruções, Memória e Arquivos, finalizando com todos os testes (pytest, Playwright e `./judge.sh`) 100% verdes, merge na `main`, `git push` e atualização do build de produção.

# REGRAS DE EXECUÇÃO, GIT E PRIVACIDADE
1. **Git:** Sincronize a `main` (`git checkout main && git pull`) para absorver mudanças recentes em `ProjectsPanel.tsx` e crie a branch `melhoria/projetos-claude-paridade-completa`. Faça commits atômicos ao final de cada etapa (`F0` a `F5`). Ao final, com `./judge.sh` e Playwright 100% verdes, faça merge na `main` e `git push origin main`.
2. **Subagentes (sintaxe blindada, sem `$(cat ...)` em aspas duplas):**
   - Código/Testes (`agy`): grave o plano e o escopo de arquivos em `melhorias/TASK_ATUAL.md` e rode:
     `agy --dangerously-skip-permissions --print "Leia melhorias/TASK_ATUAL.md e execute todas as instruções contidas nele."`
   - Triagem/análise rápida (`opencode`):
     `cat melhorias/PROMPT_OPENCODE.md | opencode run --model opencode/deepseek-v4.1-flash-free -`
3. **Migração Segura no SQLite:** Permitido adicionar novas colunas opcionais (`description`, `pinned`, `file_hash`, `file_size`, `token_count`, etc.) seguindo estritamente o padrão idempotente já existente no boot do `backend/database.py` (`PRAGMA table_info` / `ALTER TABLE ... ADD COLUMN` com fallback seguro e defaults compatíveis). **Proibido** apagar tabelas ou alterar/remover dados de projetos existentes.
4. **Privacidade Estrita:** Nos testes automatizados e screenshots do Playwright, crie e utilize **exclusivamente** projetos fictícios de seed (ex.: `"Projeto Robô ESP32"`). **NUNCA** abra, fotografe, altere ou exclua projetos reais existentes no banco (como `Facilita Vistorias`).

---

# ETAPA F0 — MAPEAMENTO TÉCNICO (Documentar e Seguir Imediatamente)
1. Inspecione `backend/database.py`, `backend/projects/*`, `backend/orchestration/*`, `backend/routers/*` e `frontend/src/components/ProjectsPanel.tsx`.
2. Documente em `melhorias/projetos/00-mapeamento.md`:
   - Tabelas, colunas e endpoints atuais de Projetos, Instruções, Memória e Arquivos.
   - Como o prompt das conversas de projeto é montado hoje e por que a Memória permanece vazia mesmo com conversas existentes.
   - Onde entram as novas colunas incrementais e o cálculo de tokens/hash.
3. Faça commit (`docs(projects): F0 mapeamento da arquitetura de projetos e contexto`) e avance direto para a Etapa F1.

# ETAPA F1 — SCHEMA INCREMENTAL + MONTADOR DE CONTEXTO ÚNICO (Backend)
1. **Migração idempotente (`backend/database.py`):**
   - Garanta suporte no banco para: `description` no projeto; `file_hash` (SHA-256), `file_size` (bytes) e `token_count` nos arquivos do projeto; e contagem de tokens para Instruções e Memória. Faça backfill automático de `token_count` e `file_size` para arquivos/instruções já existentes quando lidos.
2. **Montador de Contexto do Projeto (`backend/projects/context_assembler.py` ou módulo central equivalente):**
   - Crie uma única função/serviço que alimente **tanto** o cálculo da Barra de Capacidade na UI **quanto** a injeção real no prompt enviado ao LLM em conversas do projeto.
   - **Ordem de Precedência Estrita no Prompt:** `1. Instruções do Projeto` > `2. Memória do Projeto` > `3. Contexto de Arquivos`.
   - **Manifesto de Arquivos Sempre Presente:** Sempre injete no contexto do projeto um índice compacto com todos os arquivos do projeto (nome, extensão, tamanho), permitindo que o modelo responda perguntas globais sobre o acervo mesmo em modo RAG.
   - **Modo Integral vs. Modo Recuperação (RAG):**
     - Defina o Orçamento de Contexto do Projeto (ex.: capacidade base de referência de 128k tokens ou ajustada à janela do modelo selecionado; no modo Auto, use uma capacidade padrão clara documentada na API).
     - Se `tokens(Instruções + Memória + Todos os Arquivos)` couber dentro do limite de injeção direta sem comprometer a janela da conversa, injete o conteúdo integral dos arquivos.
     - Se exceder, ative automaticamente o **Modo Recuperação (RAG)** usando o embedder local (`paraphrase-multilingual-MiniLM-L12-v2`), enriquecendo a query de busca com o título/descrição do projeto e instruindo o modelo a citar a fonte (`[Fonte: nome_arquivo]`).
   - **Isolamento Absoluto:** Garanta em todas as queries SQL e vetoriais que nenhum arquivo, instrução ou memória vaze para outro `project_id` ou para conversas fora de projeto.
3. **Validação:** Crie testes unitários em `pytest` provando a precedência, o cálculo de capacidade, o fallback para RAG+Manifesto e o isolamento entre projetos. Rode `./judge.sh` e faça commit (`feat(projects): F1 montador de contexto unico, capacidade e isolamento`).

# ETAPA F2 — DEDUPLICAÇÃO DE ARQUIVOS, BARRA DE CAPACIDADE E GRID DE CONTEXTO
1. **Upload com Deduplicação por Hash (`SHA-256`) e Metadados:**
   - No upload de arquivo do projeto, calcule o `SHA-256`, `file_size` e `token_count`. Se já existir arquivo com o mesmo `file_hash` (ou mesmo nome e conteúdo) naquele `project_id`, impeça a duplicação e retorne aviso amigável para a UI.
2. **Seção "Contexto" no Painel Direito (`ProjectsPanel.tsx`):**
   - Renomeie a seção `"Arquivos"` para **`"Contexto"`**, com botão de busca (`🔍` para filtrar arquivos por nome em tempo real) e botão `+` (adicionar arquivo).
   - **Barra de Capacidade de Contexto:** renderize logo abaixo do título `"Contexto"` uma barra de progresso horizontal fina + texto `"N% da capacidade do projeto utilizada"` + ícone `ⓘ` com tooltip explicando o uso de Instruções, Memória e Arquivos (e indicando quando o modo RAG entra em ação). Mude o estilo visual em `>=70%` (alerta âmbar) e `100%` (modo recuperação ativo).
   - **Grid de Arquivos em 2 Colunas (estilo Claude.ai):** substitua a lista vertical antiga por cartões em grade de 2 colunas. Cada card deve mostrar: nome do arquivo no topo, tamanho formatado logo abaixo (`2,8 kB`, `1,2 MB`), badge emoldurado com a extensão na parte inferior esquerda (`MD`, `PDF`, `DOCX`, `TXT`), status visual se estiver indexando/erro e botão `×` para remover com confirmação.
3. **Validação:** Rode testes unitários/frontend + `./judge.sh` e faça commit (`feat(projects): F2 dedupe por hash, barra de capacidade e grid de contexto`).

# ETAPA F3 — CARD DIREITO UNIFICADO, INSTRUÇÕES COM PRÉVIA E MEMÓRIA VIVA
1. **Unificar Coluna Direita em um Único Container:**
   - Agrupe as 3 seções da coluna direita dentro de um único card contínuo dividido por linhas sutis (`var(--hairline)`), na ordem exata de cima para baixo: **`1. Instruções` -> `2. Memória` -> `3. Contexto`**.
2. **Seção 1 — Instruções:**
   - Título `"Instruções"` com botão de ícone de lápis à direita (abrir edição).
   - Quando houver instruções salvas, exiba prévia truncada (2 a 3 linhas) direto no card; quando vazio, exiba placeholder convidativo clicável. Ao salvar, recalcule imediatamente a Barra de Capacidade.
3. **Seção 2 — Memória (Síntese Real e Gerenciamento):**
   - Header com `"Memória"`, badge `"🔒 Apenas você"` e botão/link **`"Ver memória"`**.
   - **Pipeline de Síntese Consciente do Projeto:** corrija/implemente a síntese assíncrona de memória do projeto para que leia as conversas do projeto levando em conta as `Instruções` e os nomes dos `Arquivos` (evitando repetir instruções e extraindo fatos, decisões e contexto útil).
   - **Botão `"Sintetizar agora"` (Backfill) + Edição:** no modal/drawer `"Ver memória"`, permita visualizar o texto da memória, editar manualmente, limpar ou clicar em **`"Sintetizar agora"`** para gerar imediatamente a memória a partir das conversas já existentes no projeto (resolvendo o estado `"Nenhuma memória sintetizada ainda"` em projetos que já possuem conversas).
4. **Validação:** Crie testes em `pytest` para o endpoint de síntese/edição de memória do projeto, rode `./judge.sh` e faça commit (`feat(projects): F3 card direito unificado, previa de instrucoes e sintese de memoria`).

# ETAPA F4 — CABEÇALHO CLAUDE.AI, DESCRIÇÃO, "RECENTES" COMPACTO E COMPOSER
1. **Cabeçalho Central do Projeto:**
   - Adicione no topo o breadcrumb clicável: `Projetos / <Nome do Projeto>`.
   - Abaixo do título principal, adicione a **Descrição do Projeto** editável (clique ou lápis para editar, salvando no banco).
   - À direita do título, mantenha os botões de Fixar (pin/estrela) e menu `⋮` (editar nome/descrição, excluir projeto).
2. **Composer do Projeto:**
   - Garanta que o composer dentro da tela do projeto exiba o botão `+` (gaveta de ações), seletores respeitando o `ui_level` (`simple | intermediate | advanced`) e restaure os botões de entrada de voz / áudio ao lado do botão de enviar.
3. **Lista `"Recentes"` em Linha Única:**
   - Adicione o rótulo **`"Recentes"`** acima da lista de conversas do projeto.
   - Renderize cada conversa em **uma única linha**: título à esquerda e data curta/relativa alinhada à direita (`Hoje`, `Ontem`, `26 de set.`), eliminando a segunda linha `"Última mensagem..."`.
4. **Validação:** Rode `./judge.sh` e faça commit (`feat(projects): F4 header com breadcrumb e descricao, lista recentes compacta e voz no composer`).

# ETAPA F5 — TESTE E2E DE CICLO DE VIDA COMPLETO (PLAYWRIGHT) + DEPLOY LOCAL
1. Crie `melhorias/projetos/projetos.spec.ts` no Playwright (rodando contra `http://localhost:5173` com projeto fictício criado no teste e interceptação/mock determinístico) verificando todo o ciclo integrado:
   - Criar Projeto A (`"Robô e Gravações Teste"`) com título e descrição.
   - Adicionar Instruções e verificar que a prévia aparece no topo do card direito e a Barra de Capacidade sobe.
   - Fazer upload de 2 arquivos `.md` fictícios, verificar renderização em grid de 2 colunas com tamanho (`kB`) e badge `MD`, e testar que o reenvio do mesmo arquivo é bloqueado por hash duplicado.
   - Enviar uma pergunta na conversa do projeto e comprovar (no payload enviado ou no mock de resposta) que **Instruções + Manifesto/Conteúdo dos Arquivos** foram injetados no prompt.
   - Acionar/verificar a Memória do Projeto (`"Ver memória"` / síntese) e confirmar que uma nova conversa no Projeto A recebe `Instruções + Memória + Contexto`.
   - Criar Projeto B vazio e comprovar **isolamento total** (zero vazamento de instruções, memória ou arquivos do Projeto A).
   - Validar layout responsivo (`1280x800` e `375x667` sem overflow horizontal) e zero erros de console.
2. Capture screenshots do projeto fictício em `melhorias/projetos/screenshots/` e atualize `melhorias/projetos/00-mapeamento.md` com o relatório final de entrega.
3. Rode `./judge.sh` + `npx playwright test` até que **100% dos testes passem**.
4. Faça commit, merge da branch `melhoria/projetos-claude-paridade-completa` na `main`, execute `git push origin main` e reconstrua/atualize o container/dist de produção do frontend para que as melhorias fiquem imediatamente ativas no servidor.