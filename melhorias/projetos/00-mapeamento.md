# 🗺️ Mapeamento Técnico da Arquitetura de Projetos e Contexto (F0)
**NexusLocal — Módulo de Projetos (Paridade Claude.ai)**

Data: 19 de Outubro de 2026  
Status: Etapa F0 Concluída  

---

## 1. Estado Atual: Tabelas, Colunas e Endpoints

### 1.1 Tabelas no Banco de Dados (`backend/database.py`)

1. **`projects`**:
   - `id` (TEXT PRIMARY KEY): UUID do projeto.
   - `user_id` (TEXT NOT NULL REFERENCES users(id)): Dono do workspace.
   - `name` (TEXT NOT NULL): Nome visível.
   - `description` (TEXT DEFAULT ''): Descrição cosmética (atualmente não incluída no contexto de LLM nem editável no header central).
   - `instructions` (TEXT DEFAULT ''): Prompt específico do projeto.
   - `model_default` (TEXT): Modelo selecionado como padrão.
   - `is_favorite` (INTEGER DEFAULT 0): Marcador de favorito/pin.
   - `archived` (INTEGER DEFAULT 0): Flag de arquivamento.
   - `retrieval_top_k` (INTEGER DEFAULT 6): Quantidade de chunks para RAG.
   - `retrieval_threshold` (REAL DEFAULT 0.42): Limiar de similaridade cosseno.
   - `created_at` / `updated_at` (TEXT): Timestamps ISO.

2. **`project_files`**:
   - `id` (TEXT PRIMARY KEY): ID no formato `pf_<hex>`.
   - `project_id` (TEXT NOT NULL REFERENCES projects(id) ON DELETE CASCADE).
   - `filename` (TEXT NOT NULL): Nome original do arquivo.
   - `mime_type` (TEXT): Tipo MIME detectado.
   - `raw_path` (TEXT): Caminho relativo ao armazenamento local em `backend/storage/project_files/<project_id>/`.
   - `extracted_text` (TEXT): Texto integral extraído pelo extrator (PDF, Markdown, TXT, etc.).
   - `size_bytes` (INTEGER DEFAULT 0): Tamanho do arquivo bruto em bytes.
   - `index_status` (TEXT DEFAULT 'pending'): Estado de indexação (`pending`, `indexing`, `ready`, `error`).
   - `index_error` (TEXT): Mensagem de erro caso a indexação falhe.
   - `indexed_at` (TEXT): Timestamp do fim da indexação.
   - `created_at` (TEXT): Timestamp do upload.

3. **`file_chunks`**:
   - `id` (TEXT PRIMARY KEY).
   - `project_file_id` (TEXT NOT NULL REFERENCES project_files(id) ON DELETE CASCADE).
   - `chunk_text` (TEXT NOT NULL).
   - `chunk_index` (INTEGER NOT NULL).
   - `embedding` (BLOB): Vetor serializado em float32 (384 dimensões do MiniLM).

4. **`chat_chunks`**:
   - `id` (TEXT PRIMARY KEY).
   - `chat_session_id` (TEXT NOT NULL REFERENCES conversations(id) ON DELETE CASCADE).
   - `project_id` (TEXT NOT NULL REFERENCES projects(id) ON DELETE CASCADE).
   - `chunk_text` (TEXT NOT NULL): Par `Pergunta: ... \n Resposta: ...`.
   - `role` (TEXT DEFAULT 'turn').
   - `embedding` (BLOB): Vetor serializado.
   - `created_at` (TEXT).

5. **`project_memory`**:
   - `id` (TEXT PRIMARY KEY).
   - `project_id` (TEXT NOT NULL UNIQUE REFERENCES projects(id) ON DELETE CASCADE).
   - `summary_text` (TEXT DEFAULT ''): Síntese de memória do projeto.
   - `last_synthesized_at` (TEXT): Timestamp da última síntese.
   - `source_chat_ids` (TEXT DEFAULT '[]'): Lista JSON de IDs utilizados.

### 1.2 Endpoints Atuais (`backend/routers/projects.py`)

- `GET /api/projects`: Lista projetos do usuário (`sort=updated|name|created`, `q=...`).
- `POST /api/projects`: Cria projeto com `name`, `description`, `instructions`, `model_default`.
- `GET /api/projects/{project_id}`: Detalhes do projeto, contadores e memória.
- `PATCH /api/projects/{project_id}`: Atualiza campos do projeto (nome, descrição, instruções, etc.).
- `DELETE /api/projects/{project_id}`: Exclui projeto, desanexa conversas (`project_id = NULL`) e remove arquivos físicos.
- `PATCH /api/projects/{project_id}/memory`: Atualiza manualmente o `summary_text` da memória.
- `POST /api/projects/{project_id}/memory/synthesize`: Dispara síntese forçada de memória.
- `GET /api/projects/{project_id}/files`: Lista arquivos vinculados ao projeto.
- `POST /api/projects/{project_id}/files`: Upload multipart de arquivo.
- `POST /api/projects/{project_id}/files/{file_id}/reindex`: Reindexação individual.
- `POST /api/projects/{project_id}/files/reindex-all`: Reindexação de todos os arquivos.
- `DELETE /api/projects/{project_id}/files/{file_id}`: Remoção física e lógica de arquivo.
- `GET /api/projects/{project_id}/chats`: Lista conversas associadas ao projeto.
- `POST /api/projects/{project_id}/chats`: Cria uma nova conversa vinculada ao projeto.

---

## 2. Diagnóstico: Montagem do Prompt e Causa Raiz da "Memória Vazia"

### 2.1 Como o prompt é montado atualmente
1. Em `backend/orchestration/build_context.py`:
   - Se `active_project_id` estiver presente, chama `backend.projects.context_builder.build_project_context`.
2. Em `backend/projects/context_builder.py`:
   - Orçamento rígido derivado de `safe_input_tokens` (capped em ~7000 para modelos comuns ou Groq TPM).
   - Carrega `instructions` do projeto.
   - Carrega `memory_text` de `project_memory`.
   - Monta um catálogo raso de arquivos (`_format_file_catalog`: nomes e extensões).
   - Se a query do usuário tiver palavras-chave ou vector store retornar hits, busca chunks em `file_chunks` e `chat_chunks`.
   - **Problema de Precedência e Injeção Integral:** Hoje, arquivos nunca têm seu conteúdo integral injetado (mesmo se o projeto tiver apenas 1 arquivo pequeno de 2 kB); eles sempre dependem de chunks RAG ou fallback truncado em 1200 caracteres (`FALLBACK_CHARS_PER_FILE`). Não há distinção clara entre "cabe tudo na janela do modelo -> injeta íntegra" e "excede o orçamento -> RAG com Manifesto".
   - **Falta de Cálculo Compartilhado para a UI:** O cálculo de tokens consumidos pelo projeto não possui um serviço unificado que sirva tanto à montagem do prompt quanto ao endpoint que alimentará a Barra de Capacidade no frontend.

### 2.2 Por que a Memória permanece vazia mesmo com conversas existentes
1. **Gatilho de Turnos Altos:** Em `backend/projects/memory_job.py`, `SYNTHESIS_CHUNK_THRESHOLD` está fixado em `8`. Projetos novos ou com 1 a 7 turnos nunca chegam a rodar a síntese automática.
2. **Dependência Exclusiva de `chat_chunks`:** `get_recent_chat_chunks()` lê exclusivamente da tabela `chat_chunks`. Se as conversas do projeto foram migradas de tags antigas, ou foram criadas em versões anteriores sem chunking, ou o embedding em background falhou, a tabela `chat_chunks` permanece com `0` registros. Nesses casos, `maybe_synthesize_project_memory()` retorna vazio sem olhar a tabela real `messages`.
3. **Ausência de Contexto de Instruções/Arquivos:** A função `_heuristic_summary()` apenas junta as linhas `"Pergunta: ..."` sem correlacionar com o escopo do projeto, gerando resumos pobres e muitas vezes caindo no fallback `"Ainda não há histórico suficiente para memória."`.
4. **Falta de Ação na UI:** Não havia na UI um botão claro de "Sintetizar agora" para o usuário forçar a análise do histórico existente.

---

## 3. Planejamento das Novas Colunas Incrementais e Cálculo de Tokens/Hash

### 3.1 Novas Colunas em `backend/database.py`
Seguindo o padrão idempotente com `try/except aiosqlite.OperationalError`:
1. **Tabela `projects`**:
   - `description`: Garantir coluna via `ALTER TABLE` caso o banco de produção tenha sido criado antes de sua inclusão.
2. **Tabela `project_files`**:
   - `file_hash` (TEXT): Hash SHA-256 do conteúdo binário do arquivo (para deduplicação rápida por projeto).
   - `file_size` (INTEGER): Tamanho em bytes (já existe `size_bytes`, garantir retrocompatibilidade e alias consistente).
   - `token_count` (INTEGER DEFAULT 0): Quantidade estimada de tokens do `extracted_text`.
3. **Tabela `project_memory`**:
   - `token_count` (INTEGER DEFAULT 0): Tokens da síntese de memória.
4. **Tabela `projects`**:
   - `instructions_token_count` (INTEGER DEFAULT 0) ou cálculo on-the-fly de tokens para instruções.

### 3.2 Novo Módulo `backend/projects/context_assembler.py`
- Serviço unificado que calcula:
  1. `tokens_instructions`: Tokens das instruções do projeto.
  2. `tokens_memory`: Tokens da memória atual.
  3. `tokens_files`: Soma dos tokens de todos os arquivos prontos do projeto.
  4. `total_project_tokens = tokens_instructions + tokens_memory + tokens_files`.
  5. `capacity_limit`: Orçamento de referência (padrão 128.000 tokens ou configurável por modelo).
  6. `usage_percent = min(100.0, (total_project_tokens / capacity_limit) * 100)`.
  7. `mode`: `"full"` (se couber tudo confortavelmente) ou `"rag"` (se exceder a janela de injeção direta).
- Ordem estrita de montagem no prompt:
  1. **Instruções do Projeto**
  2. **Memória do Projeto**
  3. **Manifesto Completo dos Arquivos** (índice compacto: nome, tamanho, tokens)
  4. **Conteúdo dos Arquivos** (integral no modo `"full"`, ou chunks mais relevantes com `[Fonte: nome_arquivo]` no modo `"rag"`).

---

## 4. Roteiro de Execução das Etapas

- **F1 (Backend):** Concluído. Migração idempotente no schema, criação do `context_assembler.py`, novo endpoint `/api/projects/{id}/capacity`, integração do assembler em `build_context.py`, deduplicação SHA-256 e síntese consciente de memória. Testes unitários com 16/16 aprovados em `backend/tests/test_projects_assembler.py`.
- **F2 (Frontend):** Concluído. Deduplicação por SHA-256 no upload com mensagem amigável, barra de capacidade de contexto com tooltip breakdown e alerta de RAG, grid de contexto em 2 colunas com badges de extensão e busca instantânea.
- **F3 (Frontend):** Concluído. Card lateral unificado Claude.ai com 3 seções contínuas (`1. Instruções` -> `2. Memória` -> `3. Contexto`), prévia de instruções, modal de memória com botão "Sintetizar agora" e badge de privacidade "Apenas você".
- **F4 (Frontend):** Concluído. Header central Claude.ai com breadcrumb `Projetos / Nome`, edição rápida de descrição in-place, lista de conversas recentes em linha única compacta (`claude-chat-single-row`), e composer completo com suporte a áudio/microfone.
- **F5 (Validação & Deploy):** Concluído. Testes Playwright E2E em `melhorias/projetos/projetos.spec.ts` executados com 100% de sucesso em Desktop e Mobile (4/4 testes aprovados). 8 screenshots oficiais salvas em `melhorias/projetos/screenshots/`.

---

## 5. Relatório de Execução e Evidências Visuais (F5)

Todos os testes de ciclo completo foram executados e validados contra a aplicação ativa:

1. **Lista de Projetos (`01-projetos-lista.png`):**
   - Renderização limpa dos cards de projetos com título, descrição, estatísticas e botão "Novo projeto".
2. **Detalhe do Projeto e Header Claude.ai (`02-projeto-detalhe-header.png`):**
   - Breadcrumb no topo (`Projetos / Projeto Robô ESP32`), título com tipografia clássica, descrição editável in-place e composer central com seletor de modelos e botão de voz.
3. **Prévia de Instruções (`03-instrucoes-preview.png`):**
   - Seção 1 do card lateral unificado exibindo prévia de instruções e atalho direto para edição.
4. **Grid de Contexto em 2 Colunas (`04-contexto-grid-2colunas.png`):**
   - Seção 3 exibindo arquivos adicionados em grid responsivo de 2 colunas com badges coloridas por tipo (`MD`, `PDF`), tamanho formatado (`2,8 kB`, `15,4 kB`) e busca em tempo real com ícone `🔍`.
5. **Barra de Capacidade em Tempo Real (`05-barra-capacidade.png`):**
   - Indicador visual do uso do contexto (`1% da capacidade do projeto utilizada`) com tooltip de detalhamento (tokens de instruções, memória e arquivos).
6. **Modal de Memória e Síntese Instantânea (`06-modal-memoria-sintese.png`):**
   - Modal com badge "Apenas você", botão "Sintetizar agora", notificação toast de sucesso e editor de fatos consolidados.
7. **Isolamento Estrito entre Projetos (`07-isolamento-projeto-b.png`):**
   - Projeto B totalmente desacoplado: 0% de uso de capacidade, zero arquivos do Projeto A, memórias e instruções estritamente isoladas.
8. **Responsividade Mobile (`08-responsivo-mobile.png`):**
   - Validação da interface em viewport estreito (375x667 e iPhone 12) sem overflow horizontal, mantendo navegabilidade impecável.
