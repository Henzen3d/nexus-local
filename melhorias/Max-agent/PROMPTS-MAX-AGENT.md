# 🚀 Roteiro de Tarefas Estratégicas para o Max Agent (Arena)
**NexusLocal / Multi+**  
*Data: Outubro de 2026*  
*Modelo Alvo: Max (Agent Mode — Frontier Router nível Claude Fable 5.1 / Opus)*

Este documento reúne **5 missões de alto impacto técnico e estratégico** especialmente desenhadas para aproveitar a capacidade analítica e de codificação avançada do modelo **Max** no Arena. Cada missão inclui o contexto, os ganhos para o projeto e o **prompt completo pronto para copiar e colar**.

---

## 📌 Sumário das Missões

1. [Missão 1: Implementação Real do Assistente Proativo (Fase 1 — Motor Assíncrono)](#missão-1-implementação-real-do-assistente-proativo-fase-1--motor-assíncrono)
2. [Missão 2: Criptografia Transparente de Chaves de API em Repouso (Fernet)](#missão-2-criptografia-transparente-de-chaves-de-api-em-repouso-fernet)
3. [Missão 3: Code-Splitting do Frontend e Otimização Extrema de Bundle (Vite + React.lazy)](#missão-3-code-splitting-do-frontend-e-otimização-extrema-de-bundle-vite--reactlazy)
4. [Missão 4: Pool Assíncrono de Conexões SQLite e Eliminação de Locks Concorrentes](#missão-4-pool-assíncrono-de-conexões-sqlite-e-eliminação-de-locks-concorrentes)
5. [Missão 5: Modernização da Autenticação (Migração para PyJWT e Refresh Tokens)](#missão-5-modernização-da-autenticação-migração-para-pyjwt-e-refresh-tokens)

---

## Missão 1: Implementação Real do Assistente Proativo (Fase 1 — Motor Assíncrono)

* **Categoria:** Inovação de Produto / Inteligência Agêntica
* **Por que o Max é ideal:** O Max já conhece a arquitetura e os planos em `melhorias/assistente-proativo/`. Ele tem raciocínio suficiente para implementar um pipeline assíncrono em background sem interferir na latência do streaming do chat principal.
* **Ganhos:** Transforma o NexusLocal de um chat passivo comum em um assistente pioneiro que pesquisa eventos, dados e novidades em segundo plano com base no entusiasmo genuíno do usuário.

### 📋 Prompt para copiar e colar no Arena:
```text
Agora que você tem o contexto completo da arquitetura e dos planos do assistente proativo em melhorias/assistente-proativo/, vamos implementar o código da FASE 1 do Assistente Proativo no backend do NexusLocal:

1. Crie o pacote backend/proactive/ com os seguintes módulos:
   - detector.py: Analisador leve e não-bloqueante que avalia a mensagem do usuário via prompt enxuto e rápido para extrair entidades e grau de entusiasmo/interesse genuíno (sem comprometer o streaming do chat principal).
   - deduplication.py: Gerenciador de cache com TTL de 24h (SQLite/memória) para evitar disparar pesquisas redundantes sobre os mesmos temas já pesquisados recentemente.
   - worker.py: Tarefa assíncrona desacoplada (asyncio background task) que executa a pesquisa web segura reutilizando o módulo web_search/reader existente.
2. Integre o gatilho em backend/routers/chat.py logo após a persistência do turno do usuário, disparado em background via app.state.background_tasks com tratamento defensivo (try/except seguro, sem risco de afetar a resposta do chat se falhar).
3. Adicione testes unitários em backend/tests/test_proactive.py utilizando o conftest.py existente (banco temporário isolado, sem tocar no nexuslocal.db).
4. Garanta retrocompatibilidade total com a main atual e siga rigorosamente as diretrizes do AGENTS.md.

Ao concluir, valide a execução dos testes com pytest e envie a PR para a main.
```

---

## Missão 2: Criptografia Transparente de Chaves de API em Repouso (Fernet)

* **Categoria:** Segurança em Nível Corporativo
* **Por que o Max é ideal:** Modelos comuns costumam corromper dados existentes ao mexer com criptografia. O Max é capaz de arquitetar uma *lazy migration* (migração sob demanda): ao carregar uma chave legada em texto puro, ele a lê perfeitamente e a recifra de forma transparente, sem quebrar o banco vivo de produção.
* **Ganhos:** Atende à recomendação §2.9 da auditoria (`docs/auditoria-sistema.md`). Se o arquivo `nexuslocal.db` for vazado ou o host for violado, nenhuma chave de API pessoal ou de provedores (Groq, OpenRouter, Google, etc.) é exposta.

### 📋 Prompt para copiar e colar no Arena:
```text
Implemente a recomendação §2.9 da auditoria de segurança (docs/auditoria-sistema.md): Criptografia em repouso das chaves de API no SQLite com migração transparente (lazy migration).

Requisitos:
1. Crie backend/security/crypto.py utilizando Fernet (biblioteca cryptography já instalada). A chave de encriptação deve ser lida de API_KEYS_ENCRYPTION_KEY no .env, com fallback seguro derivado do JWT_SECRET via PBKDF2/SHA-256 (garantindo que o sistema funcione mesmo sem a variável extra).
2. Forneça funções encrypt_api_key(raw_key: str) -> str e decrypt_api_key(stored_value: str) -> str.
3. Compatibilidade retroativa obrigatória: se decrypt_api_key receber uma chave antiga gravada em texto puro, deve retornar a chave normalmente sem lançar exceção.
4. Aplique a criptografia de forma transparente onde as chaves são gravadas e lidas:
   - backend/providers/model_fetcher.py
   - backend/routers/admin.py
   - backend/auth.py (ou locais onde user_api_keys e providers.api_key são manipulados).
5. Adicione testes unitários abrangentes em backend/tests/test_crypto.py cobrindo: encriptação, decriptação, e leitura transparente de chaves legadas em texto puro (utilizando o banco temporário do conftest.py).
6. Documente a variável opcional API_KEYS_ENCRYPTION_KEY no .env.example.

Valide com pytest e envie a PR para a main.
```

---

## Missão 3: Code-Splitting do Frontend e Otimização Extrema de Bundle (Vite + React.lazy)

* **Categoria:** Desempenho do Frontend e Experiência Mobile (PWA)
* **Por que o Max é ideal:** O bundle principal de produção do Vite está gerando um único arquivo `dist/assets/index-*.js` com **1,506 MB**, gerando avisos de bundle size e lentidão em redes móveis. O Max consegue reestruturar o `App.tsx` com `React.lazy` + `Suspense` e afinar o `rollupOptions` sem quebrar o roteamento ou os estilos glassmórficos.
* **Ganhos:** Reduz o carregamento inicial de ~1.5 MB para menos de **200 kB**. Os painéis como Administração, Projetos, Artefatos e Memória passam a ser baixados apenas quando o usuário clica neles.

### 📋 Prompt para copiar e colar no Arena:
```text
Otimize o empacotamento do frontend Vite/React (atualmente gerando um bundle monolítico index-*.js de 1,5 MB) aplicando Code-Splitting inteligente e divisão em chunks:

1. Em frontend/src/App.tsx, substitua os imports estáticos diretos dos painéis pesados por carregamento sob demanda com React.lazy() e <Suspense fallback={<LoadingFallback />}>:
   - AdminPanel
   - ProjectsPanel
   - LibraryPanel
   - ArtifactsPanel
   - UserMemoryPanel
2. Em frontend/vite.config.ts, configure build.rollupOptions.output.manualChunks para segregar bibliotecas de terceiros que raramente mudam em chunks estáveis de longa duração (ex: vendor-react, vendor-icons com lucide-react, vendor-markdown com react-markdown/highlight.js).
3. Garanta que nenhum arquivo individual exceda o limite de 500 kB do Vite e que os assets, webmanifest e o service worker (sw.js) continuem íntegros.
4. Execute `npm run build` e garanta 0 erros de tipagem TypeScript e 0 warnings de chunk size.

Ao terminar, abra o PR trazendo na descrição o comparativo de tamanho dos chunks antes e depois.
```

---

## Missão 4: Pool Assíncrono de Conexões SQLite e Eliminação de Locks Concorrentes

* **Categoria:** Estabilidade de Infraestrutura e Escalabilidade
* **Por que o Max é ideal:** Atualmente, a função `get_db()` em `backend/database.py` abre uma nova conexão do `aiosqlite` do zero em cada requisição HTTP, executando 3 comandos `PRAGMA` repetidos e um `commit()`. Isso cria threads extras no Python e pode causar contenção de escrita no modo WAL.
* **Ganhos:** Atende à recomendação §4.4 da auditoria. Reduz o tempo de resposta das APIs em 20–50ms sob carga, estabiliza o consumo de memória do container Docker e evita travamentos acidentais por *database is locked*.

### 📋 Prompt para copiar e colar no Arena:
```text
Implemente a recomendação §4.4 da auditoria de sistema (docs/auditoria-sistema.md): Criação de um pool assíncrono leve de conexões SQLite reutilizáveis em backend/database.py.

Contexto e Diretrizes:
1. Atualmente, cada chamada a get_db() conecta ao arquivo, roda PRAGMA journal_mode=WAL, PRAGMA foreign_keys=ON, PRAGMA busy_timeout=5000 e um commit(), gerando sobrecarga de threads aiosqlite por request.
2. Crie um gerenciador de pool assíncrono (ex: usando asyncio.Queue com limite de 4 a 8 conexões no modo leitura/escrita) ou um connection manager que mantenha conexões abertas prontas para uso.
3. Garanta que os PRAGMAs de journal_mode e busy_timeout sejam configurados apenas uma vez na inicialização ou reciclagem da conexão.
4. Mantenha compatibilidade total com a interface `async with get_db() as db:` ou `db = await get_db(); try: ... finally: await db.close()` usada por todo o backend.
5. Adicione um teste de concorrência em backend/tests/test_db_pool.py validando múltiplas leituras e escritas simultâneas sem deadlocks nem vazamento de conexões (usando o conftest.py temporário).
6. Respeite as regras do AGENTS.md (nunca tocar no nexuslocal.db real nos testes).

Valide a suíte com pytest e envie a PR para a main.
```

---

## Missão 5: Modernização da Autenticação (Migração para PyJWT e Refresh Tokens)

* **Categoria:** Segurança Avançada e Conformidade de Dependências
* **Por que o Max é ideal:** O pacote `python-jose==3.3.0` atualmente utilizado no backend está obsoleto, sem manutenção e com CVEs documentadas (CVE-2024-33663 / CVE-2024-33664). Migrar para a biblioteca mantida `PyJWT` e estruturar um ciclo com Refresh Token exige consistência no backend e no frontend (`client.ts`).
* **Ganhos:** Atende à recomendação §2.6 da auditoria. Elimina alertas de segurança em scanners de vulnerabilidade (Trivy/Snyk/Dependabot) e adiciona renovação de sessão segura e transparente.

### 📋 Prompt para copiar e colar no Arena:
```text
Implemente a modernização da camada de autenticação conforme recomendado em docs/auditoria-sistema.md (§2.6): Migração de python-jose para PyJWT oficial e renovação segura de sessão.

Objetivos:
1. Em backend/requirements.txt, remova python-jose e adicione pyjwt[crypto]>=2.9.0.
2. Atualize backend/auth.py para utilizar jwt do PyJWT:
   - Mantenha a mesma assinatura das funções create_access_token, decode_token, resolve_token_user.
   - Trate exceções nativas (jwt.PyJWTError, jwt.ExpiredSignatureError, jwt.InvalidTokenError).
   - Reduza a expiração do Access Token de 7 dias para 24 horas e implemente a geração de um Refresh Token seguro (7 dias).
3. Adicione o endpoint POST /api/auth/refresh em backend/routers/auth.py para emissão de novo Access Token a partir do Refresh Token válido.
4. No frontend (frontend/src/api/client.ts), capture respostas 401 para tentar renovar o token automaticamente uma vez via /api/auth/refresh antes de deslogar o usuário.
5. Atualize os testes em backend/tests/ cobrindo emissão, validação, expiração e renovação com PyJWT (usando o banco temporário do conftest.py).
6. Valide a compilação do frontend com `npm run build` e o backend com `pytest`.

Abra a PR na main com a descrição técnica da migração.
```

---

## 🎯 Ordem de Execução Sugerida

Recomenda-se enviar uma missão por vez para o Max no Arena, na seguinte sequência de prioridade:

| Ordem | Missão | Foco Principal | Benefício Imediato |
| :---: | :--- | :--- | :--- |
| **1º** | **Missão 1** (Assistente Proativo Fase 1) | Inovação | Entrega o motor inteligente que já foi planejado |
| **2º** | **Missão 2** (Criptografia de Chaves Fernet) | Segurança | Blinda as chaves de API salvas no SQLite |
| **3º** | **Missão 3** (Code-Splitting no Frontend) | Desempenho | Carregamento ultrarrápido em celulares e conexões 4G/5G |
| **4º** | **Missão 4** (Pool SQLite Concorrente) | Estabilidade | Zero locks de banco com múltiplos usuários conectados |
| **5º** | **Missão 5** (Migração PyJWT + Refresh) | Modernização | Fim das CVEs antigas e tokens com renovação segura |
