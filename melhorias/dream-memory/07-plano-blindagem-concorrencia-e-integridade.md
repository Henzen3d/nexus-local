# 🛡️ Plano de Ação 1: Blindagem de Concorrência, Integridade e SQLite Resiliente

> **Foco:** Eliminação de Race Conditions, Proteção de Dados Concorrentes e Estabilidade do Banco  
> **Localização:** `melhorias/dream-memory/07-plano-blindagem-concorrencia-e-integridade.md`  
> **Status:** Pronto para Execução  
> **Dependência:** Nenhuma (Primeira fase recomendada)  

---

## 1. Visão Geral e Justificativa

Durante o ciclo de vida do NexusLocal, o processo de consolidação de memórias convive com múltiplos eventos assíncronos:
1. Mensagens sendo trocadas e gerando novos fatos em background (`extract_user_memory_background`).
2. Varreduras periódicas de ociosidade a cada 15 minutos (`run_memory_idle_extraction_job`).
3. Consolidador noturno / por atividade a cada 20 minutos (`run_dream_consolidation_job`).
4. Disparos manuais sob demanda disparados pelo usuário na UI (`dream_run_now` e `dream_preview`).

Atualmente, o lock `_memory_pipeline_lock` está confinado ao `main.py` e **não protege as rotas HTTP**. Além disso, o SQLite não possui garantia estrita de `busy_timeout` em todas as conexões abertas em `memory_dream.py`, e a suíte de testes de edge cases apresenta falhas de configuração no `pytest-asyncio`.

---

## 2. Tarefas e Subtarefas Detalhadas

### 📋 Tarefa 1: Unificação Centralizada do Lock de Concorrência da Memória
**Objetivo:** Garantir que apenas uma operação estrutural de memória (extração pesada, consolidação de fundo, preview ou disparo manual) ocorra por usuário/sistema por vez, sem condições de corrida.

* [ ] **Subtarefa 1.1: Centralizar o lock em módulo acessível sem dependência circular.**
  * Criar ou migrar o objeto de bloqueio para `backend/memory.py` ou `backend/memory_lock.py` com a definição:
    ```python
    # backend/memory_lock.py
    import asyncio
    
    # Lock global do pipeline de memória (impede colisões entre extração idle e consolidação dream)
    memory_pipeline_lock = asyncio.Lock()
    ```
  * Atualizar as importações em `backend/main.py:214` para usar o lock compartilhado.

* [ ] **Subtarefa 1.2: Blindar as rotas de API manual em `backend/routers/memory.py`.**
  * Na rota `POST /dream-run-now` ([`backend/routers/memory.py:729`](file:///j:/Arquivos%20Osmar/Multi+/backend/routers/memory.py#L729)), antes de iniciar o stream SSE, checar `memory_pipeline_lock.locked()`:
    * Se já houver uma consolidação em andamento, emitir evento SSE imediato `{"step": "busy", "msg": "Uma consolidação já está em andamento. Aguarde a conclusão."}` e finalizar graciosamente.
    * No worker assíncrono, adquirir `async with memory_pipeline_lock:` durante toda a execução.
  * Na rota `POST /dream-preview` ([`backend/routers/memory.py:712`](file:///j:/Arquivos%20Osmar/Multi+/backend/routers/memory.py#L712)), também verificar o lock para evitar que a simulação leia um estado intermediário inconsistente durante um commit de consolidação real.

* [ ] **Subtarefa 1.3: Fila cooperativa para novos fatos gerados durante a consolidação.**
  * Garantir que as extrações rotineiras de chat (`extract_user_memory_background`) não fiquem travadas permanentemente se o Dream estiver rodando uma chamada longa de LLM (10-30s).
  * Adicionar timeout inteligente de aquisição com retry suave caso o lock esteja retido pelo Dream Consolidator.

---

### 📋 Tarefa 2: Resiliência do SQLite (Modo WAL e Busy Timeout Padronizado)
**Objetivo:** Eliminar de forma definitiva erros do tipo `sqlite3.OperationalError: database is locked` em sistemas operacionais Windows e ambientes com alta concorrência de I/O.

* [ ] **Subtarefa 2.1: Criar helper assíncrono padronizado para conexão ao SQLite.**
  * Em `backend/database.py`, implementar função utilitária com pragmas obrigatórios:
    ```python
    @asynccontextmanager
    async def get_resilient_db_connection():
        async with aiosqlite.connect(DB_PATH) as db:
            await db.execute("PRAGMA journal_mode = WAL;")
            await db.execute("PRAGMA busy_timeout = 10000;")  # 10 segundos de tolerância
            await db.execute("PRAGMA synchronous = NORMAL;")
            db.row_factory = aiosqlite.Row
            yield db
    ```

* [ ] **Subtarefa 2.2: Refatorar todas as conexões diretas em `backend/memory_dream.py`.**
  * Substituir todas as instâncias de `async with aiosqlite.connect(dbmod.DB_PATH) as db:` (linhas 406, 547, 624) pelo helper padronizado, assegurando que o `busy_timeout` de 10.000ms esteja ativo tanto na resolução de provedores quanto na transação relâmpago de aplicação.

* [ ] **Subtarefa 2.3: Checagem defensiva de integridade no boot do servidor.**
  * No `startup` do `backend/main.py:407`, além de `await init_db()`, executar verificação rápida `PRAGMA integrity_check(1);` para alertar nos logs caso a base SQLite tenha sido corrompida por queda abrupta anterior.

---

### 📋 Tarefa 3: Sincronização Delta de Fatos Gerados Durante o Ciclo de Sonho
**Objetivo:** Impedir perda de dados caso o usuário continue conversando com a IA durante os 15-45 segundos em que o Dream LLM está processando o lote de consolidação.

* [ ] **Subtarefa 3.1: Isolamento de escopo por snapshot ID.**
  * No início de `execute_dream_consolidation`, o snapshot registra a lista exata de `fact_ids` sob consolidação.
  * Durante a gravação em `apply_dream_operations` ([`backend/memory_dream.py:530`](file:///j:/Arquivos%20Osmar/Multi+/backend/memory_dream.py#L530)), validar estritamente que operações de `merge`, `supersede` e `archive` só afetam fatos que estavam presentes no snapshot inicial.
  * Qualquer fato inserido pelo usuário no banco enquanto a consolidação rodava (com `created_at > snapshot.created_at`) permanece intocado e ativo, sem risco de ser sobrescrito acidentalmente.

* [ ] **Subtarefa 3.2: Cláusula de proteção otimista (`WHERE status = 'active'`).**
  * Nas queries SQL de atualização de status para `merged`, `superseded` e `archived`, adicionar verificação explícita:
    ```sql
    UPDATE user_memory
    SET is_active = 0, status = 'merged', superseded_by_id = ?,
        consolidated_at = datetime('now'), updated_at = datetime('now')
    WHERE id = ? AND user_id = ? AND is_active = 1;
    ```
  * Se o fato foi editado manualmente pelo usuário ou deletado na interface durante a inferência do LLM, a operação não altera dados defasados.

---

### 📋 Tarefa 4: Correção e Expansão dos Testes Assíncronos no Pytest
**Objetivo:** Garantir 100% de passagem nos testes automatizados de regressão em `backend/tests/`.

* [ ] **Subtarefa 4.1: Corrigir fixture `temp_db` em `backend/tests/test_dream_edge_cases.py`.**
  * Atualizar o fixture para compatibilidade total com o plugin `pytest-asyncio` 1.4+:
    ```python
    import pytest_asyncio
    
    @pytest_asyncio.fixture(loop_scope="function")
    async def temp_db():
        fd, path = tempfile.mkstemp(suffix=".db")
        os.close(fd)
        original_db = dbmod.DB_PATH
        dbmod.DB_PATH = Path(path)
        await dbmod.init_db()
        try:
            yield Path(path)
        finally:
            dbmod.DB_PATH = original_db
            try:
                os.remove(path)
            except OSError:
                pass
    ```

* [ ] **Subtarefa 4.2: Adicionar arquivo `backend/pytest.ini` ou atualizar configuração raiz.**
  * Incluir:
    ```ini
    [pytest]
    asyncio_mode = auto
    asyncio_default_fixture_loop_scope = function
    ```

* [ ] **Subtarefa 4.3: Implementar teste de concorrência e tentativa simultânea.**
  * Criar teste `test_concurrent_dream_trigger_blocked` que simula duas chamadas concorrentes a `execute_dream_consolidation` e confirma que a segunda rejeita ou aguarda ordenadamente sem corromper os dados.

---

## 3. Critérios de Aceite da Fase de Blindagem
1. Execução de `$env:PYTHONPATH="."; .\.venv\Scripts\pytest backend/tests/test_dream*` passa com 100% de sucesso sem nenhum erro de setup.
2. Nenhuma exceção `sqlite3.OperationalError: database is locked` ocorre mesmo durante gravações de chat concorrentes com a consolidação.
3. Tentativa de acionar múltiplos cliques em "Consolidar Agora" na interface frontend não duplica jobs nem gera logs de erro no servidor.
