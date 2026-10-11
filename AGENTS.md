# 🛡️ Diretrizes e Regras Operacionais para Agentes de IA (AGENTS.md)
**Multi+ / NexusLocal**

Este arquivo é a base de conhecimento de regras de comportamento e restrições operacionais para agentes de IA (Antigravity, Gemini, Claude, Hermes Agent e outros colaboradores automatizados).

---

## 🚨 1. Regras Férreas de Produção e Host (Hermes Agent)

### A. Banco de Dados ao Vivo (`nexuslocal.db`)
1. **Estado Real de Produção:** O banco ativo em produção (`nexuslocal.db`) contém dados vitais: ~1633 modelos cadastrados, logs de auditoria de uso, quotas, configurações de provedores e conversas de usuários.
2. **Integridade Obrigatória:** Antes de qualquer alteração de esquema ou deploy crítico, a integridade deve ser atestada via:
   ```sql
   PRAGMA integrity_check;
   ```
3. **ISOLAMENTO TOTAL DE TESTES:**
   * **NUNCA execute `pytest`, testes unitários ou scripts de teste contra o `nexuslocal.db` ao vivo.**
   * Todas as execuções de teste devem ocorrer obrigatoriamente em uma **cópia temporária**, banco em memória (`:memory:`) ou arquivo temporário descartável (`tempfile.mkstemp(suffix='.db')`).
   * Testes rodando no banco vivo causam corrupção de dados, locks de escrita no WAL (`aiosqlite`) e perda de histórico de usuários.

### B. Ausência de Índice GitNexus no Host
1. **Host sem GitNexus:** Este servidor/host de execução **NÃO possui** índice GitNexus e **NÃO realiza** indexação semântica de código para o Hermes Agent.
2. **Proibido nos Prompts de Deploy:** **JAMAIS** inclua instruções como "reindexar o código no GitNexus" ou "gerar embeddings do repositório" nos prompts ou scripts destinados ao Hermes Agent ou ao deploy em produção.

### C. Fluxo Padrão de Deploy no Host (Hermes)
O pipeline oficial e enxuto de deploy executado pelo Hermes Agent é composto estritamente por:
1. **Backup & Integridade:** Validar integridade e criar snapshot de backup do `nexuslocal.db`.
2. **Git Pull:** `git pull origin main`.
3. **Dependências:** Atualizar `pip` e `npm` caso haja alterações em `requirements.txt` ou `package.json`.
4. **Migração Segura:** Executar migração do banco (inclusão de novas colunas/tabelas sem perda dos 1633 modelos existentes).
5. **Compilação do Frontend:** Executar `npm run build` dentro do diretório `frontend/`.
6. **Testes do Host (se aplicável):** Somente em banco de dados isolado/cópia.
7. **Restart do Serviço:** Reiniciar o processo do backend (PM2, systemd, docker ou supervisor).
8. **Health Check:** Validar endpoint HTTP (ex: `GET /api/dashboard/auto-router/policy` ou `/health`).

---

## 🛠️ 2. Padrões de Desenvolvimento no Repositório

### A. Python / Backend
* **Ambiente Virtual:** Sempre utilizar o Python do `.venv` (`.venv/Scripts/python.exe` no Windows ou `.venv/bin/python` no Linux).
* **Migrações Incrementais:** Novas tabelas e colunas devem ser adicionadas em blocos `try/except sqlite3.OperationalError` dentro de `init_db()` em `backend/database.py`, garantindo retrocompatibilidade total com bancos existentes de produção.
* **Índices SQLite:** Nunca criar índices diretamente no `SCHEMA` de inicialização para colunas criadas incrementalmente via `ALTER TABLE`. Índices devem ser criados após o bloco de migração das colunas.

### B. Frontend
* **Vanilla CSS First:** Utilizar o sistema de design tokens (`var(--primary)`, `var(--surface-soft)`, `var(--hairline)`, `var(--ink)`) e arquivos CSS puros. Não adicionar Tailwind CSS sem solicitação explícita.
* **Radical Aesthetics:** Manter estilo glassmórfico refinado, tooltips contextuais, animações suaves e contraste impecável tanto no tema claro quanto no escuro.
* **I18n Rigoroso:** Todas as novas strings devem possuir correspondentes em `pt-BR.json`, `en-US.json` e `es-ES.json`.
* **TypeScript Estrito:** A compilação `npm run build` deve sempre passar com 0 erros de tipagem antes de qualquer commit.
