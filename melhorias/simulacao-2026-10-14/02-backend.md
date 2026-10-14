# Backend — reconhecimento e auditoria técnica

## Fase 0: arquitetura real

Leitura de README, DESIGN, AGENTS, inicialização, schema, rotas e caminhos principais de chat/UI. A base não é um protótipo só com concatenação: há módulos separados de orquestração, ranking/failover, quotas, memória, projetos, busca e anexos.

| Camada | Arquivos / responsabilidades |
|---|---|
| Boot/API | `backend/main.py`: FastAPI, routers, CORS, jobs; `auth.py`: JWT; `rate_limit.py`: limite de login |
| SQLite | `database.py`: schema, seed, migrações incrementais; `evidencias/schema.sql`: schema efetivamente criado |
| Chat | `routers/chat.py`: WebSocket `/ws/chat`; `orchestration/{persist_turn,handle_attachments,build_context,resolve_request}.py` |
| Modelos | `providers/{registry,base}.py`, `ranking/`, `smart_router/`, `data/context_registry.json` |
| Fusion | `routers/fusion.py` e `fusion/orchestrator.py`: configuração global, fan-out, refinement opcional, grounding e Judge |
| Cache | `cache/manager.py`: exato + semântico; `cache_settings`; TTL, fingerprint, user scope |
| Projects | `routers/projects.py`, `projects/{chunker,indexer,embedder,vector_store,context_builder,memory_job}.py` |
| Web/vision | `web_search/{agent,providers,reader}.py`, `vision_relay/`, rotas específicas |
| Front | React/Zustand, `useChat.ts` + `ChatContext`, `ChatWindow`, `MessageInput`, `MessageBubble`, seletores, painéis, tokens CSS |

Rotas principais reais: `/api/auth/login|register`, `/api/conversations`, `/api/projects` e `/{id}/files`, `/api/admin/providers|models`, `/api/fusion/config`, `/api/attachments/upload`, `/attachments/{path}` assinado, `/api/cache/*`, `/api/web-search/*`, `/api/vision-relay/*`, `/ws/chat`, `/health`. A enumeração completa está em `evidencias/routes.txt`.

SQLite observado: tabelas de usuários/chaves/provedores/modelos; conversas/mensagens/anexos; cache exato/semântico; projects/project_files/file_chunks/chat_chunks/project_memory; configurações Fusion; ranking/quotas/usage; recursos adicionais de memória/proatividade/imagens. **81 índices**, incluindo autoíndices. WAL e foreign keys existem; `get_db()` aplica `busy_timeout=10000` (`database.py:849–852`). Outras conexões diretas aiosqlite nem sempre passam pelo helper; uniformização é oportunidade, não prova de lock ocorrido.

### Promessa versus implementação

| Recurso | Estado demonstrado |
|---|---|
| Fusion paralelo + Judge | Implementado; texto passa, falha parcial tolerada. Imagem e preservação de contexto falham |
| Cache semântico | Implementado; embeddings externos indisponíveis neste ambiente. Provas isoladas revelam scope/TTL incorretos |
| Projects/RAG | Chunking, embeddings, híbrido denso/lexical, fallback e budget existem. Re-ranking por cross-encoder não encontrado no caminho ativo; citações estruturadas de arquivos não persistidas como as de web |
| Registro de contexto | Existe, com overrides manuais e contexto por modelo; override é preservado pelo sync (`admin.py:166–170`). Poda existe, mas não fecha todos os limites |
| Busca web | Planejamento, fan-out, leitura e fontes; indisponibilidade externa exercitada, sucesso online real não validado |
| Vision Relay | Configuração, cache e troca imagem→descrição no caminho normal existem. Nenhuma transcrição visual real validada |
| Outros recursos reais | Artifacts, prompt enhancer, memória adaptativa, proatividade, ranking/auto-router, TTS e imagem — inventariados, fora do núcleo de validação end-to-end desta missão |
| Ausente/incompleto | Editar/regenerar turno; bootstrap no README; cancelamento remoto; estado degradado do embedder; citações estruturadas do RAG |
| Gancho sem caminho ativo identificado | `try_load_sqlite_vec` em `projects/vector_store.py:51–67`; a busca auditada carrega BLOBs e percorre Python. Não contabilizar isso como índice vetorial em produção |

## Como o sistema subiu (sem alterar produto)

1. Instalação `.venv` com **`backend/requirements.txt`** e `npm ci` no frontend. A lista Python da raiz é menor que a lista backend e omite bibliotecas diretamente importadas, por exemplo pypdf/pdfplumber/docx/Pillow/edge-tts. Não fiz instalação mínima em outra venv para determinar a primeira ausência: esse ponto é comparação estática.
2. Comando do launcher reproduzido por import em `cwd=backend`: **`ModuleNotFoundError: No module named 'backend'`**. Da raiz, sem env: **`RuntimeError: JWT_SECRET não definido...`**. Logs exatos: `boot-readme.log`, `boot-no-env.log`.
3. Correção operacional mínima, **não aplicada ao launcher**: da raiz, `DB_PATH=<db descartável> JWT_SECRET=<gerado> .venv/bin/uvicorn backend.main:app --host 0.0.0.0 --port 8000`.
4. Front com config de teste que herda a original, aceita o host do preview e faz proxy same-origin para `/api`, `/ws`, **`/attachments`**. O Vite original só encaminha `/api` e `/ws`: anexos assinados relativos no dev ficam sem proxy. Nginx de produção é outro caminho; não generalizar essa lacuna ao Docker.
5. Playwright Chromium padrão falhou ao baixar do CDN (`ECONNRESET`). Alternativa: binário `@sparticuz/chromium` via npm permitido, extração das libs auxiliares, `LD_LIBRARY_PATH=/tmp/al2023/lib`. Falhas intermediárias de harness (caminho de plugin, PWA, libnspr, seletores) foram corrigidas **só nos scripts**; não são bugs do produto.
6. DB novo, `integrity_check=ok`, sem usuários. Conta sintética criada por fixture. Provedor local sintético só após registrar falhas sem chave. Credenciais e DB ficaram fora da entrega versionável.

## B01 — Quick Start não inicializa backend como documentado

**Alto · observado + código · confiança alta.**

- **Evidência:** `start.sh:24–26` muda para backend e usa `uvicorn main:app`; `backend/main.py:10–15` importa pacote `backend`. Logs de boot acima. README também não inclui JWT/primeiro administrador; `U01`.
- **Impacto:** caminho recomendado falha em checkout limpo.
- **Reprodução:** `.venv/bin/python -c 'import main'` dentro de backend, sem PYTHONPATH adicional; depois importar da raiz sem JWT.
- **Correção:** único conjunto de dependências, `.env` validado antes de subir processos, entrada `backend.main:app` da raiz, health check antes de anunciar sucesso; bootstrap seguro documentado. Docker precisa de smoke test independente, não foi executado aqui.

## B02 — Ollama sem chave gera header HTTP inválido

**Alto · observado · confiança alta.**

- **Evidência:** `05-ollama-sem-chave-1440.png`, `browser-ollama.log`; `providers/registry.py:106–115` aceita chave vazia em Ollama; `providers/base.py:104–107` sempre cria `Authorization: Bearer {api_key}`. HTTPX falha com **`Illegal header value b'Bearer '`**.
- **Impacto:** modelo local acessível não pode responder no uso padrão sem chave; failover mascara causa como indisponibilidade.
- **Reprodução:** Ollama apontado ao servidor QA, usuário sem chave pessoal. O erro ocorre antes do request ao fake. Chave fictícia não vazia, somente na fixture, permitiu continuar.
- **Correção sugerida:** `headers={"Content-Type":"application/json"}; if self.api_key: headers["Authorization"]=f"Bearer {self.api_key}"`. Provedores que exigem segredo continuam validados no registry.

## B03 — Cache semântico ignora diferenças essenciais do contexto

**Alto · prova de módulo + rastreamento de integração · confiança alta.**

- **Evidência:** `logic-results.json:cross_project_same_user` devolveu **“Projeto A: 37 dias”** para system “Projeto B: prazo 90 dias”, similarity **1.0**. `cache/manager.py:139–204`: chave semântica inclui memória/fingerprint e última mensagem, não o system; `chat.py:523–537,607–611`: fingerprint nasce da memória antes do RAG e não incorpora revisão do projeto. `use_memory=false` gera `nomem` (`build_context.py:170–173`), tornando o cenário determinístico. A prova usa o método público `get`, entrada semântica sintética e o fast path de fingerprint: não depende de similaridade de MiniLM real.
- **Impacto:** resposta errada reutilizada dentro do mesmo usuário entre projetos/documentos/anexos/contextos. **Isolamento entre usuários passou**; não foi observado vazamento cross-user.
- **Reprodução:** gravar cache semântico de A; chamar mesma pergunta/modelo/usuário/fingerprint com system B. Repetir com usuário B deve dar miss e deu.
- **Correção:** scope explícito com hash canônico de usuário, projeto, revisão documental, system/policy, perfil/memória, anexos e ferramentas/parâmetros relevantes. Excluir conteúdo dependente de tempo/web quando sem política de freshness. Similaridade somente dentro de scope idêntico; preferir bypass seguro quando houver dúvida.
- **Threshold:** padrão de cache **0,92**; não basta aumentá-lo: o bug acima dá 1,0. Teste com vetor artificial idêntico para pergunta negada comprova ausência de guardas adicionais, **não** taxa real de falso positivo. Criar corpus de negação, números, entidades e datas para calibrar precision/recall.

## B04 — TTL lexical expira cedo e entrada vencida não se renova

**Médio · observado em SQLite real isolado · confiança alta.**

- **Evidência:** `logic-results.json`: linha criada há **71 h** não é hit sob TTL **72 h**; tentativa de `set` sobre linha de 200 h mantém resposta `antiga`. `cache/manager.py:365–416,431–458,541–575`: cutoff usa `datetime.now().isoformat()` (T), SQLite grava `datetime('now')` (espaço); comparação é TEXT. Inserts detectam linha existente e retornam sem atualizar validade/resposta. Cache exato tem índice não único por hash/modelo (`database.py:86–96`).
- **Impacto:** até quase um dia de validade perdido no dia de corte; refresh não ocorre até limpeza; dois writers podem criar duplicatas.
- **Reprodução:** `logic_probes.py`, com `created_at=datetime('now','-71 hours')`; depois expirar e chamar `_set_exact` novamente.
- **Correção:** epoch UTC ou formato único, consultas com unidade temporal consistente, UNIQUE para chave completa e UPSERT atômico de resposta/versão/created_at. Janela de testes deve controlar relógio/timezone, não depender da hora real.

## B05 — RAG aparece pronto sem vetores e pode não recuperar nada

**Alto · observado no ambiente sem embedder · confiança alta sobre degradação, limitada sobre qualidade online.**

- **Evidência:** `api-results.json:rag_embeddings`: manual pronto, **62 chunks / 0 embeddings**; outros dois prontos, 1/0 cada. `indexer.py:133–153` salva blobs `None` e marca ready. `embedder.py:53–75` marca inicialização concluída mesmo ao falhar, sem retry automático posterior. `vector_store.py:138–139` sai cedo sem embedder; `context_builder.py:540–554` só usa fallback para pergunta explícita sobre arquivos ou inventário inteiro não pronto. `11-projeto-detalhe-*` exibe “Indexado”.
- **Impacto:** cliente acha que o arquivo está consultável, mas pergunta pertinente fica sem evidência; cache semântico também degrada sem indicação clara. A indisponibilidade do download foi causada pelas restrições do sandbox; a modelagem de estados/fallback é uma falha reproduzível do produto offline.
- **Medição:** arquivo = **42.689 caracteres**, 62 chunks, mais 78 caracteres em dois documentos. “Qual o código secreto de devolução?” → **0 chunks**, modo `none`, sentinel ausente. “Nos arquivos do projeto, qual é o código secreto de devolução?” → **4 de 64 chunks**, **1.372 caracteres** de corpos, sentinel **AZUL-739** presente. ~**96,8%** do texto não entrou no prompt no segundo caso, seletividade desejável para essa pergunta, **não perda indevida por si só**. O fato-alvo teve recall 0/1 no primeiro caso e 1/1 no segundo; amostra insuficiente para recall global.
- **Correção:** estado `text_ready/vector_ready/degraded/error`, health de embedder, retry/backoff/reindexação; recuperação lexical independente de embedding e da formulação explícita. Melhorar o pipeline existente, não reescrevê-lo como se não tivesse chunking: manter chunks por estrutura, enriquecer metadados/página/offset, usar índice lexical FTS5 + candidatos densos, reranking top-N, diversidade por documento e orçamento por destino.
- **Citações:** `<fonte>` já existe (`context_builder.py:373–389`), mas `chat.py:674` conta só fontes web e `MessageBubble.tsx:479–480` renderiza `web_search_sources`. Em resposta RAG da fixture, `source_count=0` mesmo com trechos. Persistir IDs de arquivo/chunk/página/revisão e validar citações; a saída do fake não mede fidelidade generativa.

## B06 — Judge perde instruções, memória e fontes primárias do projeto

**Alto · observado nos requests do provedor + código · confiança alta.**

- **Evidência:** `fusion/orchestrator.py:515–531` copia o histórico e **substitui** o primeiro system pelo prompt do juiz. Requests dos proposers têm `REGRA_PROJETO_QA` e `AZUL-739`; request do Judge não tem nenhum deles (`provider.jsonl`, `provider-summary.json`). O Judge recebe histórico e respostas dos participantes, não está totalmente cego, mas perde a referência primária necessária para julgar.
- **Impacto:** respostas intermediárias podem omitir ou distorcer fonte; juiz não consegue verificar e pode desobedecer instrução/estilo/restrição do projeto.
- **Reprodução:** Fusion textual em projeto com regra e fato exclusivo; inspecionar payloads dos quatro requests, sem inferir nada da resposta simulada.
- **Correção:** composição explícita `policy + judge_role + user/project_context + sources + candidates`, preservando prioridade de instruções e separação de dados não confiáveis. Reaplicar budget do modelo juiz. Compartilhar persistência/metadados pós-turno: hoje `chat.py:585–595` retorna cedo e o caminho Fusion não passa pelo indexador de sibling chats `:634`.

## B07 — Fusion multimodal quebra em todos os proposers

**Alto · observado · confiança alta.**

- **Evidência:** teste `fusion_multimodal_tres_provedores`: três status error e “Nenhum modelo retornou resposta válida.”; log **`can only concatenate list (not "str") to list`**. `orchestrator.py:391–397` soma `SELF_CRITIQUE_SUFFIX` a `content`, que com imagem é lista.
- **Impacto:** imagem em Fusion falha mesmo que todos os modelos tenham visão; não é indisponibilidade externa.
- **Reprodução:** configurar três provedores, todos com modelo vision sintético, anexar PNG válido e enviar com Fusion.
- **Correção:** normalizar content em parts e anexar a instrução como part de texto; `deepcopy` de multimodal, pois cópias rasas nas fases de refino/juiz compartilham a lista original. Tratar capability/relay separadamente por participante.

## B08 — Orçamento de contexto não garante o limite do destino

**Alto · observado + código · confiança alta.**

- **Evidência:** `logic-results.json:oversize`: 100.000 caracteres, **25.004 tokens estimados**, budget 6.144, nenhuma remoção. `handle_attachments.py:422–474` preserva sempre a última mensagem mesmo excedendo budget e admite até 120% em uma condição. `compute_safe_input_tokens(512)` retorna **1024** (`logic-results.json:tiny_context`). Poda em `chat.py:568–582` usa só modelo selecionado; Fusion envia history a outros modelos e acrescenta todas as respostas ao Judge (`orchestrator.py:391–405,496–554`). Failover normal também reutiliza history sem nova poda no destino (`resolve_request.py:118–149`).
- **Impacto:** 400/413, custo inesperado e resposta impossível; aproximação caracteres/4 subestima especialmente CJK/emoji/código, imagens são estimativas. Resumos/memórias existem, mas não substituem compactação garantida por orçamento por turno.
- **Reprodução:** enviar `測` 100 mil vezes; fake recebeu integralmente, não valida limite de modelo real. Histórico sintético de 160 mensagens, ao contrário, foi podado corretamente para últimas 16 + nova: `measurements.json`.
- **Correção:** validar bytes/tokens antes de persistir/chamar; reservar completion, system, ferramentas e imagem; orçamento por proposer/Judge e após failover. Mensagem individual impossível → erro acionável ou chunking consentido, não envio ilimitado. Compactação com resumo versionado e informação ao usuário sobre conteúdo omitido.

## B09 — JSON válido de shape inválido derruba WebSocket

**Alto · observado · confiança alta.**

- **Evidência:** `api-results.json:ws_shape_*`: `[]`, `null`, `{"message":42}` fecham conexão sem close frame. `chat.py:163–185` trata JSONDecodeError, mas executa `.get`/`.strip` sem validação de tipos fora do try que protege o turno. Stack traces no backend.
- **Impacto:** input descuidado/hostil derruba sessão; UI tenta reconectar, resposta útil não chega. Limites de mensagem/arrays também são insuficientes nesse contrato.
- **Reprodução:** autenticar e enviar cada payload por WS. Mensagem vazia normal é corretamente rejeitada, controle positivo.
- **Correção:** envelope Pydantic discriminado por `type`, campos limitados, IDs/arrays/tipos validados, erro estruturado recuperável. Max bytes no servidor/proxy. Nunca expor stack trace ao cliente.

## B10 — Turnos sem idempotência e sem identificação ponta a ponta

**Médio · observado no protocolo, hipótese quanto a duplo clique real · confiança alta no backend.**

- **Evidência:** `duplicado_sem_request_id` criou duas conversas e duas respostas para dois frames idênticos enviados antes da primeira resposta; `chat.py:183–216` processa sequencialmente, sem request_id. `useChat.ts:477–510` envia sem ID de turno. `MessageInput.tsx:197–224` tem guarda `isStreaming`; por isso **não** afirmar que todo duplo clique da UI duplica.
- **Impacto:** reenvio/reconexão, duas abas ou automação podem duplicar custo e histórico; tokens tardios não têm correlação robusta após parar/recomeçar.
- **Reprodução:** dois `ws.send` idênticos com `conversation_id=null`. Ver dois `conversation_created` no JSON de evidência.
- **Correção:** `client_request_id` único por usuário, transação atômica/unique constraint, ACK do turno, eventos contendo `turn_id`, cursor/seq para retomada; lock lógico por conversa para política explícita de concorrência.

## B11 — Ausência de cancelamento remoto

**Alto · observado · confiança alta.**

- **Evidência:** `U06`, `useChat.ts:422–451`; controller `chat.py:163–216` aguarda processamento inteiro e não possui dispatch concorrente para comando cancel. Fake completou após clique e persistiu texto integral; `measurements.json:stop_requests` identifica request completo em 16,365 s. Um request anterior foi cancelado por fechamento do browser após falha do harness: distinguir **desconexão** de **botão Parar**.
- **Impacto:** consumo desnecessário e divergência UI/SQLite; stream sem novos tokens pode manter trabalho até timeout/read timeout.
- **Reprodução:** botão de stop em qa-slow e reload após 17 s.
- **Correção:** reader WS separado de tarefa do turno, registry de tarefas por user/turn, cancelamento propagado a fan-out/client HTTP, `finally` que persiste parcial e envia terminal único. Novo turno não deve reaproveitar streams/IDs anteriores. Reconnect atual usa backoff/heartbeat e limpa busy, mas não faz replay confiável de tokens.

## B12 — Uploads validam depois de ler tudo e têm políticas divergentes

**Médio · observado + código · confiança alta; exaustão de memória é risco, não incidente medido.**

- **Evidência:** `attachments.py:68–76` e `projects.py:433–445` fazem `await file.read()` antes do limite. Limites: chat 20 MiB / projeto 25 MiB. Projeto aceitou `.exe` e PDF corrompido com 200/pending, depois error; chat recusou PDF com 400, mas aceitou arquivo de 0 bytes. `attachments/validators.py:17–55` verifica extensão e detecta MIME, sem exigir coerência entre ambos. `api-results.json:upload_*` e screenshot `18-upload-erro-390`.
- **Impacto:** pico de RAM proporcional ao upload, superfície de parser e estado enganoso; não significa que `.exe` foi executado ou disponibilizado publicamente.
- **Reprodução:** enviar corpos da fixture de zero, 26 MiB, `.exe`, PDF truncado e PNG válido aos dois endpoints.
- **Correção:** leitura em chunks com acumulador limitado; rejeitar formato/tamanho/vazio cedo; política unificada por uso; quotas por usuário e limites de descompressão/pixels/páginas, parsing isolado e cleanup de arquivos órfãos; projeto pode aceitar assíncrono, mas retornar 202 com estado e erro consultável claro.

## B13 — JWT do WebSocket aparece integralmente nos logs

**Alto · observado · confiança alta.**

- **Evidência:** `useChat.ts:15` inclui token na query; `chat.py:112` lê query token; access log do uvicorn registrou URI completa. `backend.log` entregue contém **`token=[REDACTED]`**, substituído após captura. Nenhum token válido foi incluído deliberadamente no relatório.
- **Impacto:** leitores de logs/APM/proxy obtêm credencial de sessão reutilizável por até sete dias (`auth.py:33`). Exploração por terceiros não foi realizada.
- **Reprodução:** conectar pelo navegador e inspecionar access log local. Não copiar o token para tickets.
- **Correção:** ticket WS curto, de uso único, obtido por canal autenticado; alternativamente autenticação no primeiro frame antes de qualquer dado. Redação obrigatória de query e secrets em todos os logs, não apenas logger próprio. CORS não protege WebSocket sozinho; validar Origin no handshake de browser como defesa adicional, sem substituir autenticação.

## B14 — Segredos em texto puro e política de memória por destino incompleta

**Médio (at-rest) / alto (política de privacidade) · código · confiança alta na implementação, impacto externo não testado.**

- **Evidência:** `database.py:25,53–58`: `providers.api_key`/`user_api_keys.api_key` são TEXT, lidas diretamente por `providers/registry.py:71–116`. `build_context.py:214–218` decide sanitização por ID do modelo selecionado, antes do fan-out/failover. IDs customizados locais também não são reconhecidos como locais por essa lista fixa.
- **Impacto:** cópia do DB/backups expõe chaves; política preparada para modelo local pode seguir a participante remoto no Fusion. Memória é explicitamente enviada como contexto permitido, contrariando promessa absoluta de `U07`. **Não foi comprovado envio de dado sensível real.**
- **Reprodução:** inspecionar schema/registry e construir plano com seleção local + proposer remoto; testar payloads em fixture sem dados pessoais antes de liberar.
- **Correção:** criptografia envelope com chave fora do DB/backups, permissões mínimas e máscaras em UI/logs; política de minimização por cada destino efetivo, usando capability `is_local` validada, e revisão dos summaries incluídos. Em self-hosted pessoal pode haver outra aceitação de risco, a ser decidida.

## B15 — Configuração Fusion com mesmo provedor retorna 500 e grava parcialmente

**Médio · observado · confiança alta.**

- **Evidência:** `api-results.json:fusion_config` = 500; log `UNIQUE constraint failed: fusion_models.provider_id`. `database.py:154–160` impõe unique(provider_id); Pydantic aceita lista sem essa restrição. `routers/fusion.py:103–140` commit da configuração do juiz acontece **antes** da transação dos modelos.
- **Impacto:** configuração fica parcialmente atualizada; usuário não sabe restrição, nem recebe 422 útil. Três provedores distintos funcionaram.
- **Reprodução:** POST `/api/fusion/config` com três modelos Ollama; ler configuração depois. Não remover constraint sem decidir se a restrição é requisito de diversidade.
- **Correção:** validar regra declarada e referências modelo/provedor, transação única; erro 422 nomeando conflito; se múltiplos por provedor forem desejados, UNIQUE(provider_id,model_id) com migração segura.

## B16 — Escala e observabilidade: trabalho linear e correlação incompleta

**Médio · código + medições limitadas · confiança alta no desenho, média no impacto de escala.**

- **Evidência:** `cache/manager.py:481–510` busca todos os candidatos do scope e percorre embeddings em Python; `vector_store.py:151–191` faz o mesmo por projeto. Isso não é ANN apesar de comentário de vetorização. `admin.py:385–402` e `projects.py:179–190` têm subconsultas correlacionadas; não são necessariamente N+1 round-trips, mas merecem EXPLAIN/medição. Histórico é carregado antes da poda. `logging_config.py:49–52` formatador não inclui campos de `extra` como turn_id; existe `phase_latencies` no caminho normal (`chat.py:675`), ponto positivo. Jobs de indexação usam `create_task` sem fila durável (`indexer.py:205–209`). Bundle frontend: `U09`.
- **Impacto:** custo cresce com documentos/cache/histórico; reinício pode perder job pendente; investigação entre WS→provider→DB difícil. **Seis conexões não geraram lock**, não inferir falha de produção sem load test.
- **Reprodução:** ler consultas e planos; `api-results.json:concorrencia_*` e `measurements.json` fornecem baseline pequeno.
- **Correção:** métricas de candidatos/chunks/tokens descartados/TTFT/persistência, logs JSON com redaction e request/turn id; FTS e índice vetorial quando cardinalidade justificar; pré-agregações e LIMITs; fila rastreável com recovery. Fazer benchmark 1k/10k/100k antes de trocar SQLite. Uniformizar pragmas/transações curtas, não simplesmente aumentar timeout.

## B17 — Delimitadores de RAG não são fronteira de segurança

**Médio · risco estático / hipótese de sucesso contra LLM · confiança alta no caminho, indeterminada na exploração.**

- **Evidência:** `build_context.py:121–125` escapa origem mas insere conteúdo bruto entre `<fonte>`; documento pode conter `</fonte>` e instruções adversariais. `context_builder.py:373–388` já orienta não executar comandos das fontes, defesa positiva, porém textual.
- **Impacto:** possível confusão de instruções, citações falsas e evasão das regras; não houve modelo real nem execução de comandos nesse teste. Não rotular como RCE comprovado.
- **Reprodução:** unidade pode demonstrar fechamento da tag por conteúdo; sucesso de prompt injection exige benchmark adversarial com modelo real e segredos fictícios.
- **Correção:** representação estruturada/escape/IDs controlados, instruções de prioridade separadas dos dados, citações verificadas após geração, ferramentas com autorização independente do texto e mínimo acesso; suíte adversarial e canários, sem prometer blindagem só por XML.

## Fusion: tolerância, viés e custo — sem extrapolar os testes

- **Falha parcial:** a fixture de 401 de um proposer ainda produziu resposta do Judge. Há `try/except` por proposer e timeout 90 s; fan-out usa gather. Falha ao criar o Judge ocorre antes do fan-out, e erro/timeout de Judge não entrega automaticamente as respostas boas como resposta final (`orchestrator.py:326–334,570–580`).
- **Latência:** limites locais = refino 45 s, proposers 90 s, detecção de claims 30 s, buscas paralelas 20 s, Judge 180 s (`orchestrator.py:18–22`). Caminho que usa todas as fases tem envelope nominal ~365 s, fora overhead/configuração, não um SLA medido. Aguarda todos os proposers antes de julgar. Sugerir deadline global, quorum e fallback visível, respeitando decisão de produto.
- **Custo:** configuração de três modelos normalmente faz 3 gerações + Judge; pode somar refino, detecção de claims e até 3 buscas. Não há ganho de qualidade medido para justificar sempre esse custo.
- **Viés:** ordem fixa vem de `ORDER BY position`; respostas completas sem equalização são concatenadas em `:496–500`; prompt prioriza autoconfiança declarada e consenso (`:76–84`). Risco de posição, verbosidade e confiança mal calibrada é **hipótese**, não resultado experimental. Avaliar permutações, contrabalanceamento, discordâncias e factualidade cega antes de escolher randomização permanente.
- **Retries/rate limits:** caminho normal tem três tentativas de failover, considera `Retry-After` e token bucket (`resolve_request.py:31,349–355`); não declarar que não há tratamento de 429. Não há garantia uniforme de backoff/deadline entre normal/Fusion e jobs. Pool compartilhado HTTP existe; read timeout não equivale a duração total de turno.

## Controles positivos de segurança

Auth requerida no WS/API, revalidação de usuário, checks de dono, hash bcrypt, parâmetros SQL, URLs de anexos assinadas/traversal guard, ReactMarkdown sem execução do `<script>` da fixture, CORS restrito por padrão e `/register` fechado. `idor_project` retornou 403 e CORS hostil 400. Isso não é pentest completo: não foram feitos scanning de dependências, ataque distribuído, stress de disco/RAM, análise de implantação pública ou avaliação de todos os endpoints administrativos.
