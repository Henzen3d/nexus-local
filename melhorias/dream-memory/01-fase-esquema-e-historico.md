# 🏛️ Fase 1: Esquema de Dados, Linhagem e Snapshots

## 1. Objetivo Técnico
Evoluir a persistência do SQLite para suportar:
1. Estados granulares de memória: `active`, `merged`, `superseded`, `archived`.
2. Linhagem explícita (*lineage pointer*): campo `superseded_by_id` que aponta para o fato consolidado que substituiu este fato antigo.
3. Snapshots atômicos pré-consolidação para permitir reversão (*rollback*) em 1 clique sem perda de dados.
4. Tabela de logs de auditoria dos ciclos de sono (`dream_logs`).

---

## 2. Alterações de Esquema no SQLite

### A. Evolução da Tabela `user_memory`
Em [`backend/database.py`](file:///j:/Arquivos%20Osmar/Multi+/backend/database.py), adicionar as seguintes colunas via migração defensiva (`ALTER TABLE ADD COLUMN`):

```sql
-- Estado do ciclo de vida da memória
ALTER TABLE user_memory ADD COLUMN status TEXT DEFAULT 'active' CHECK(status IN ('active', 'merged', 'superseded', 'archived'));

-- Ponteiro para o fato que consolidou ou substituiu este fato
ALTER TABLE user_memory ADD COLUMN superseded_by_id TEXT REFERENCES user_memory(id) ON DELETE SET NULL;

-- Timestamp de quando a consolidação ocorreu
ALTER TABLE user_memory ADD COLUMN consolidated_at TEXT DEFAULT NULL;

-- Versão da memória (incrementa a cada edição/merge)
ALTER TABLE user_memory ADD COLUMN version INTEGER DEFAULT 1;

-- Índice para consultas rápidas de fatos ativos
CREATE INDEX IF NOT EXISTS idx_user_memory_status ON user_memory(user_id, status) WHERE status = 'active';
```

### B. Nova Tabela: `memory_snapshots`
Armazena cópias de segurança em JSON do estado das memórias ativas de um usuário antes de qualquer consolidação:

```sql
CREATE TABLE IF NOT EXISTS memory_snapshots (
    id             TEXT PRIMARY KEY,
    user_id        TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    trigger_type   TEXT NOT NULL,        -- 'dream_nightly' | 'dream_manual' | 'user_edit'
    facts_count    INTEGER NOT NULL,
    snapshot_json  TEXT NOT NULL,        -- dump completo dos fatos ativos em JSON
    created_at     TEXT DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_snapshots_user ON memory_snapshots(user_id, created_at DESC);
```

### C. Nova Tabela: `dream_logs`
Registra a telemetria e o histórico auditável de cada execução do Dream:

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
    duration_ms        INTEGER NOT NULL,
    status             TEXT NOT NULL,     -- 'success' | 'failed' | 'rolled_back'
    summary_notes      TEXT,              -- resumo em linguagem natural do que foi consolidado
    error_message      TEXT,
    created_at         TEXT DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_dream_logs_user ON dream_logs(user_id, created_at DESC);
```

---

## 3. Divisão de Tarefas e Subtarefas

### Tarefa 1.1: Migração Defensiva do Banco de Dados
- [ ] **1.1.1**: Adicionar checagem e execução de migração para as novas colunas de `user_memory` na inicialização em [`backend/database.py`](file:///j:/Arquivos%20Osmar/Multi+/backend/database.py).
- [ ] **1.1.2**: Criar as tabelas `memory_snapshots` e `dream_logs` no bloco `init_db()`.
- [ ] **1.1.3**: Atualizar índices para otimizar queries filtradas por `status = 'active'`.

### Tarefa 1.2: Métodos de Snapshot e Rollback no Backend
- [ ] **1.2.1**: Implementar `create_memory_snapshot(user_id: str, trigger_type: str) -> str` que serializa todos os fatos ativos em JSON e salva em `memory_snapshots`.
- [ ] **1.2.2**: Implementar `rollback_memory_snapshot(user_id: str, snapshot_id: str) -> bool`:
  * Abre transação SQLite.
  * Restaura os fatos gravados no snapshot JSON.
  * Desativa novos fatos gerados após aquele snapshot.
  * Marca o log correspondente em `dream_logs` como `rolled_back`.
- [ ] **1.2.3**: Implementar política de retenção para guardar até 7 snapshots mais recentes por usuário, descartando snapshots mais antigos automaticamente.

### Tarefa 1.3: Endpoints de API para Histórico e Restauração
- [ ] **1.3.1**: `GET /api/memory/snapshots` — lista os últimos snapshots disponíveis para o usuário.
- [ ] **1.3.2**: `POST /api/memory/snapshots/{snapshot_id}/rollback` — executa o rollback atômico.
- [ ] **1.3.3**: `GET /api/memory/dream-logs` — retorna histórico de execuções do consolidador.

---

## 4. Critérios de Aceite (Definition of Done)
* [ ] Banco de dados migra sem erros em bases existentes sem perda de nenhum fato anterior.
* [ ] Executar snapshot salva o estado íntegro dos fatos com hash e timestamp.
* [ ] Chamar rollback restaura 100% dos fatos ao estado exato do snapshot.
