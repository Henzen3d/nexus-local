# 🏛️ Fase 1: Esquema de Dados, Linhagem e Snapshots

## 1. Objetivo Técnico
Evoluir a persistência do SQLite para suportar:
1. **Estados granulares com retrocompatibilidade:** Adicionar `status` (`active`, `merged`, `superseded`, `archived`) mantendo sincronização estrita com a coluna existente `is_active` (`INTEGER 0/1`) para não quebrar as mais de 20 queries existentes no backend.
2. **Linhagem bidirecional e rastreabilidade:**
   * Campo `superseded_by_id` que aponta para o fato consolidado resultante.
   * Campo `source_dream_id` vinculando novos fatos ao log do ciclo de consolidação correspondente (essencial para rollbacks cirúrgicos).
3. **Snapshots atômicos pré-consolidação:** Serialização protegida com checksum SHA-256 e suporte a compressão para permitir reversão (*rollback*) em 1 clique sem perda de dados legítimos inseridos após o ciclo.
4. **Tabela de auditoria expandida (`dream_logs`):** Com suporte a estados de ciclo de vida (`running`, `success`, `failed`, `rolled_back`, `aborted_safety`).

---

## 2. Alterações de Esquema no SQLite

### A. Evolução da Tabela `user_memory`
Em [`backend/database.py`](file:///j:/Arquivos%20Osmar/Multi+/backend/database.py), adicionar as colunas via migração defensiva com retrocompatibilidade garantida:

```sql
-- 1. Estado detalhado do ciclo de vida da memória
ALTER TABLE user_memory ADD COLUMN status TEXT DEFAULT 'active' CHECK(status IN ('active', 'merged', 'superseded', 'archived'));

-- 2. Ponteiro para o fato que consolidou ou substituiu este fato
ALTER TABLE user_memory ADD COLUMN superseded_by_id TEXT REFERENCES user_memory(id) ON DELETE SET NULL;

-- 3. Identificador do sonho que gerou este fato consolidado (facilita rollback seguro)
ALTER TABLE user_memory ADD COLUMN source_dream_id TEXT REFERENCES dream_logs(id) ON DELETE SET NULL;

-- 4. Timestamp de consolidação
ALTER TABLE user_memory ADD COLUMN consolidated_at TEXT DEFAULT NULL;

-- 5. Versão da memória (incrementa a cada edição inline ou merge)
ALTER TABLE user_memory ADD COLUMN version INTEGER DEFAULT 1;

-- 6. Índices compostos de alta performance
CREATE INDEX IF NOT EXISTS idx_user_memory_status ON user_memory(user_id, status) WHERE status = 'active';
CREATE INDEX IF NOT EXISTS idx_user_memory_lineage ON user_memory(superseded_by_id) WHERE superseded_by_id IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_user_memory_dream_source ON user_memory(source_dream_id) WHERE source_dream_id IS NOT NULL;
```

#### 🛡️ Regra de Coexistência `status` ↔ `is_active`:
Para evitar quebra em rotinas existentes (ex: `get_relevant_memory`, `build_memory_block` e filtros `WHERE is_active = 1`):
* Na migração inicial: atualizar linhas antigas com:
  `UPDATE user_memory SET status = CASE WHEN is_active = 1 THEN 'active' ELSE 'archived' END WHERE status IS NULL OR status = 'active';`
* Em todas as operações de escrita (`add_memory_fact`, consolidador, exclusão e rollback):
  * Se `status == 'active'` ➔ sempre setar `is_active = 1`.
  * Se `status IN ('merged', 'superseded', 'archived')` ➔ sempre setar `is_active = 0`.

---

### B. Nova Tabela: `memory_snapshots`
Armazena cópias de segurança em JSON do estado das memórias ativas antes de qualquer consolidação:

```sql
CREATE TABLE IF NOT EXISTS memory_snapshots (
    id             TEXT PRIMARY KEY,
    user_id        TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    trigger_type   TEXT NOT NULL,        -- 'dream_nightly' | 'dream_manual' | 'pre_edit'
    facts_count    INTEGER NOT NULL,
    snapshot_json  TEXT NOT NULL,        -- dump completo dos fatos ativos em JSON
    snapshot_hash  TEXT NOT NULL,        -- SHA-256 do payload JSON para conferência de integridade
    is_compressed  INTEGER DEFAULT 0,    -- 1 se o payload estiver compactado (gzip)
    created_at     TEXT DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_snapshots_user ON memory_snapshots(user_id, created_at DESC);
```

---

### C. Nova Tabela: `dream_logs`
Registra telemetria, status de execução e histórico auditável de cada consolidação:

```sql
CREATE TABLE IF NOT EXISTS dream_logs (
    id                 TEXT PRIMARY KEY,
    user_id            TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    snapshot_id        TEXT REFERENCES memory_snapshots(id) ON DELETE SET NULL,
    provider_id        TEXT NOT NULL,
    model_id           TEXT NOT NULL,
    facts_before       INTEGER NOT NULL,
    facts_after        INTEGER NOT NULL,
    facts_merged       INTEGER NOT NULL,
    facts_superseded   INTEGER NOT NULL,
    facts_created      INTEGER NOT NULL,
    facts_total_active INTEGER NOT NULL,  -- censo total de fatos ativos após término
    duration_ms        INTEGER NOT NULL,
    status             TEXT NOT NULL,     -- 'running' | 'success' | 'failed' | 'rolled_back' | 'aborted_safety'
    summary_notes      TEXT,              -- resumo legível do que foi consolidado
    error_message      TEXT,
    interrupted_fixed  INTEGER DEFAULT 0, -- 1 se o processo foi recuperado após interrupção abrupta do servidor
    created_at         TEXT DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_dream_logs_user ON dream_logs(user_id, created_at DESC);
```

---

## 3. Divisão de Tarefas e Subtarefas

### Tarefa 1.1: Migração Defensiva e Camada de Acesso a Dados
- [ ] **1.1.1**: Adicionar checagem incremental e execução de migração para as novas colunas de `user_memory` na inicialização em [`backend/database.py`](file:///j:/Arquivos%20Osmar/Multi+/backend/database.py).
- [ ] **1.1.2**: Implementar sincronizador defensivo: garantir que `is_active` reflita fielmente `status == 'active'` em todas as atualizações.
- [ ] **1.1.3**: Criar as tabelas `memory_snapshots` e `dream_logs` no bloco `init_db()`.
- [ ] **1.1.4**: Configurar `PRAGMA foreign_keys = ON;` no ciclo de conexão ou aplicar integridade referencial programática caso o SQLite rode em modo permissivo.

### Tarefa 1.2: Métodos de Snapshot, Rollback Cirúrgico e Purge de Privacidade
- [ ] **1.2.1**: Implementar `create_memory_snapshot(user_id: str, trigger_type: str) -> tuple[str, str]`:
  * Serializa os fatos ativos com `id`, `category`, `fact`, `fact_key`, `confidence`, `is_pinned`, `version`, `created_at`.
  * Suporta `trigger_type`: `'dream_nightly'`, `'dream_manual'`, `'pre_edit'` e `'pre_import'` (protege importações externas de JSON).
  * Calcula checksum SHA-256 e grava em `memory_snapshots`.
- [ ] **1.2.2**: Implementar `rollback_memory_snapshot(user_id: str, snapshot_id: str) -> bool`:
  * **Regra de Rollback Único & Validação de Expiração:** Só permite reverter o sonho mais recente e cujo snapshot ainda conste na base (`can_rollback == True`).
  * Abre transação flash (`BEGIN IMMEDIATE`).
  * Valida o hash SHA-256 do snapshot antes de qualquer mutação.
  * Reativa os fatos originais com `status = 'active'`, `is_active = 1` e limpa `superseded_by_id`.
  * Desativa apenas os fatos derivados criados por este ciclo (`WHERE source_dream_id = :dream_log_id`).
  * **Preservação de Dados Novos:** NÃO toca em fatos inseridos pelo usuário ou extraídos em conversas após o snapshot que tenham `source_dream_id IS NULL`.
  * Atualiza o log em `dream_logs` para `status = 'rolled_back'`.
  * Recalcula embeddings, resumos rolling e fingerprint de cache semântico.
- [ ] **1.2.3**: Implementar política de retenção automática: manter os 7 snapshots mais recentes por usuário, expurgando os anteriores.
- [ ] **1.2.4**: Atualizar `clear_all_memory(user_id: str)` para conformidade com privacidade (LGPD/Direito ao Esquecimento):
  * Remove todos os fatos (`user_memory` ativos e arquivados).
  * Remove todos os `memory_snapshots` vinculados ao usuário.
  * Remove resumos rolling em `user_memory_summaries`.
  * Marca registros em `dream_logs` como `purged_by_user`.

### Tarefa 1.3: Endpoints de API para Memória, Histórico e Rollback
- [ ] **1.3.1**: `GET /api/memory/snapshots` — lista os snapshots disponíveis com timestamps, trigger_type e hashes.
- [ ] **1.3.2**: `POST /api/memory/snapshots/{snapshot_id}/rollback` — executa o rollback atômico e cirúrgico.
- [ ] **1.3.3**: `GET /api/memory/dream-logs` — lista histórico das últimas execuções, enriquecendo cada item com a flag computada:
  `can_rollback = (log.id == latest_log_id) AND (log.snapshot_id IS NOT NULL) AND (snapshot_exists_in_db)`
- [ ] **1.3.4**: `PUT /api/memory/facts/{fact_id}` — endpoint de edição inline direta de fato:
  * Valida posse do fato pelo usuário logado.
  * Atualiza texto e/ou categoria, incrementa `version`, atualiza `updated_at`.
  * Recalcula embedding com FastEmbed e invalida o `memory_fingerprint`.
- [ ] **1.3.5**: Atualizar endpoint `POST /api/memory/import` para acionar `create_memory_snapshot(user_id, 'pre_import')` antes de mesclar novos fatos externos.

---

## 4. Critérios de Aceite (Definition of Done)
* [ ] Migração do banco não quebra nenhuma query preexistente que filtre por `is_active = 1`.
* [ ] Executar snapshot salva o estado íntegro dos fatos com hash SHA-256 verificado.
* [ ] Rollback restaura com exatidão os fatos consolidados sem apagar novos fatos criados manualmente pelo usuário no intervalo.
* [ ] Apenas o sonho mais recente e com snapshot íntegro existente pode sofrer reversão direta (`can_rollback == True`).
* [ ] A importação de memória gera snapshot prévio permitindo reversão em caso de inconsistência externa.
* [ ] O comando "Esquecer Tudo" elimina completamente snapshots e referências históricas do usuário.


