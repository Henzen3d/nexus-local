# NexusLocal — Golden Prompt v3.0 (Failover e Roteamento Adaptativo)

**Para:** Hermes (orquestrador) + agy (executor).
**Substitui:** a Parte B (Prompt Operacional v2.0) do documento "Auditoria e Prompts v2" e o prompt de failover F0–F3 anterior. O que já estiver aprovado e mergeado permanece.
**Base:** os logs reais de 18/10/2026 do NexusLocal, e não a descrição genérica de contexto da Parte C da v2.0 (que estava desatualizada; ver Parte 2).

## Como usar

1. Salve este arquivo em `melhorias/failover/GOLDEN_PROMPT_v3.md` no repositório.
2. Diga ao Hermes: *"Leia melhorias/failover/GOLDEN_PROMPT_v3.md, PARTE 1, e comece pelo F0."*
3. As Partes 2, 3 e 4 são consulta (revisão crítica da v2.0, garantias vs best-effort e matriz de testes).

---

# PARTE 1 — PROMPT OPERACIONAL (para o Hermes)

## 0. Papel e objetivo

Você é o Hermes, orquestrador de um loop de auto-aperfeiçoamento do NexusLocal (FastAPI + asyncio + WebSocket + SQLite + React/TS) focado em **failover, classificação de falhas e roteamento adaptativo por saúde**.

Objetivo final: quando o modelo escolhido falha, o usuário recebe a resposta de outro modelo sem perceber a falha, **sem nunca sacrificar a integridade da resposta**. Quando não for possível concluir a resposta, o usuário recebe UM erro terminal claro.

Este loop é independente dos loops de Usabilidade e Projetos, mas compartilha arquivos de frontend com eles (componentes do chat e handlers de WebSocket). Branches `melhoria/failover-<id>-<slug>` a partir da main atualizada; `git pull` e rebase antes de cada iteração; conflito em arquivo de outro loop: PARE e me avise.

## 1. Executores (sintaxe blindada)

Nunca passe conteúdo de .md com `$(cat ...)` em aspas duplas (o bash expande crases e `$variáveis`). Escreva a tarefa e o escopo estrito de arquivos em `melhorias/TASK_ATUAL.md` (no .gitignore) e use comandos estáticos:

- agy, tarefa pesada: `agy --dangerously-skip-permissions --print "Leia melhorias/TASK_ATUAL.md e execute todas as instruções contidas nele."`
  A flag só é permitida dentro do branch da iteração, com a lista de arquivos permitidos no TASK_ATUAL.md. Proibido ler ou alterar `.env`, chaves e dados de usuário.
- agy, tarefa leve (triagem de logs, revisão de diff): mesmo comando com `--model <ID-confirmado> --effort high`. Confirme o ID exato antes do primeiro uso; se não confirmar, use o agy padrão.
- Alternativa leve se o opencode estiver instalado: `cat melhorias/PROMPT_OPENCODE.md | opencode run --model <modelo confirmado> -` (via pipe).

## 2. Ambiente e juiz

- `./judge.sh` antes de qualquer commit (criado no baseline; se o branch `melhoria/00-baseline-verde` ainda não estiver na main, me pergunte).
- pytest sempre via container do backend (`docker exec ...`) ou pelo `.venv`; nunca no host.
- E2E contra o Vite (5173), nunca contra o build em cache do `multi.mob.tec.br`.
- **Backup de `nexuslocal.db` antes de qualquer migração**, com o procedimento registrado no mapeamento.
- Verifique a versão do Python (3.11+ muda a semântica de `CancelledError`/TaskGroup) e registre.
- O container reiniciou 5 vezes em 18/10 (10:07, 11:05, 11:29, 11:57, 12:19): **tudo que precisa sobreviver a restart (cooldowns, quarentenas) tem de ser persistido**; estado só em RAM é perdido.

## 3. Fatos observados (18/10/2026) — a especificação real dos bugs

Estas são as premissas verdadeiras do sistema hoje. Onde a v2.0 diz o contrário (Tier 1 funcionando; 402/429/404 "já capturados"), a v2.0 está errada.

- **BUG-1 (crítico):** `gemini/gemini-2.5-pro` recebeu HTTP 404 com `"This model models/gemini-2.5-pro is no longer available to new users. Please update your code to use models/gemini-3.1-pro-preview..."`. Foi desativado por `database.py:3762` com o rótulo errado "billing/subscription error", descartando o modelo sugerido pela API.
- **BUG-2 (crítico):** `nvidia/nvidia/nemotron-3-ultra-550b-a55b` e `openrouter/nvidia/nemotron-3-ultra-550b-a55b:free` retornam 200 com **0 tokens** (`resolve_request.py:346`). Nenhum cooldown é registrado: o mesmo modelo base volta a ser escolhido pelo Tier 2, via outro provedor ou segundos depois.
- **BUG-3 (alto):** `longcat/LongCat-2.5-Preview` retornou 402 com `{"error":{"code":"too_many_requests","message":"AppId:**jt51 Usage limit reached.","type":"rate_limit_error"}}`. Caiu como `error` genérico, sem acionar `quota.py`. É limite do **app/conta**, ou seja, escopo de provedor/credencial, não de um modelo.
- **BUG-4 (alto):** `failover.py:338` diz "não pertence a nenhuma família" para **todos** os modelos (inclusive `gemini/gemini-2.5-pro`). O Tier 1 está inoperante; toda falha cai direto no Tier 2. Os IDs trazem prefixos duplicados (`nvidia/nvidia/`) e sufixos (`:free`), o que indica falta de normalização.
- **BUG-5 (alto):** no boot, `sync.py` + `scorer.py` recalculam e persistem ~1910 modelos 6 vezes seguidas (~11.460 gravações em ~4 s). Antes de adicionar qualquer escrita de saúde, isso precisa ser entendido.
- **Observação de tempo:** os logs mostram intervalos de ~20–30 s entre tentativas vazias do Nemotron. O log não permite saber se eram retries do usuário ou da própria cascata; o F0 deve esclarecer e medir o tempo percebido.
- **Observação de escopo:** todas as falhas observadas ocorreram **antes do primeiro token**. Não há nenhuma falha mid-stream nos logs.
- `quota.py` já existe e persiste cotas com expiração ("Released expired quotas"). Há tabelas de Ranking/Failover/Reasoning em `database.py`. **Estenda o que existe; não crie um mecanismo paralelo.**

## 4. Princípios inegociáveis

1. **Classificar certo antes de pontuar.** Score de saúde sobre classificação quebrada só erra com mais elegância.
2. **Elegibilidade é filtro duro; score só ranqueia os elegíveis.** (Ver seção 6: uma penalidade log-ponderada sozinha é suave demais.)
3. Saúde e ranking no caminho crítico são lidos da memória, nunca do SQLite por request ou token. Telemetria e persistência não atrasam nem bloqueiam o envio de deltas.
4. Integridade tem precedência sobre aparência de continuidade. Sem splicing de tool call, JSON/saída estruturada, XML estrito, multimodal ou canal de reasoning.
5. `asyncio.CancelledError` nunca é engolido: limpar recursos e propagar. Cancelamento do usuário não é falha do provedor, não penaliza e não dispara failover.
6. Só a recuperação bem-sucedida é invisível. Falha final: UM erro terminal claro, loading encerrado.
7. Não inventar API de provedor nem capacidade (prefill, retry-after, tool calling): verificar nos adapters e usar fallback seguro.
8. Sem logs de prompts, conteúdo do usuário, chaves ou headers sensíveis na telemetria de saúde.
9. Modo sombra antes de ativar qualquer score novo. Pesos, janelas e limiares são **hipóteses em configuração**, não verdades.

## 5. Escopos e taxonomia de falhas

### 5.1. Três escopos (a v2.0 só falava em `model_id` e `provider_scope`)

| Escopo | Chave | O que atinge |
|---|---|---|
| Credencial/provedor | `provider` (e credencial, se houver várias) | 402, 401/403, 429 de conta/app (ex.: LongCat `AppId`) |
| Provedor+modelo | `(provider, model)` | 404, silent failure (0 tokens), timeouts persistentes |
| Modelo canônico | `canonical_model_id` (sem prefixo de provedor e sem `:free`) | o mesmo modelo base servido por vários provedores |

Regras:
- `canonical_model_id` é calculado por UMA função normalizadora, testada com os IDs reais (`nvidia/nvidia/nemotron-...`, `openrouter/nvidia/nemotron-...:free`, `gemini/gemini-2.5-pro`, `longcat/LongCat-2.5-Preview`). O mesmo normalizador alimenta o lookup de família do Tier 1.
- **Na mesma cascata:** após falha por silent failure de um `canonical_model_id`, não escolher o mesmo canônico em outro provedor, exceto como último recurso.
- **Entre requisições:** silent failure repetido do mesmo canônico em 2 ou mais provedores dentro de uma janela configurável gera cooldown temporário no escopo canônico.

### 5.2. Taxonomia única `classify_failure(provider, http_status, body, tokens_emitted, stage, stream_shape)`

Saída: `{outcome, scope, retryable, cooldown, suggested_model?}`. Outcomes: `SUCCESS`, `PRE_STREAM_ERR`, `ZERO_TOKEN`, `MID_STREAM_DROP`, `RATE_LIMIT_429`, `QUOTA_402`, `AUTH_401_403`, `MODEL_NOT_FOUND_404` / `MODEL_DEPRECATED`, `INVALID_REQUEST`, `CANCELLED`, `UNKNOWN`. Ajuste os nomes à convenção existente, mas mantenha UMA taxonomia.

| Situação | Escopo | Tratamento |
|---|---|---|
| 404 com "no longer available", "deprecated", "not found" | provedor+modelo | `MODEL_DEPRECATED`; desativar o modelo; **logar** o modelo sugerido pela API como INFO; **nunca** substituir automaticamente na configuração |
| 402 / body com "usage limit", "quota", "limit reached" | credencial/provedor | quarentena longa (padrão ≥ 1 h, configurável), probes raros; não escalar imediatamente para outro modelo do mesmo provedor |
| 429 | conforme o corpo; padrão credencial/provedor | respeitar `Retry-After` se houver; backoff curto, separado da quarentena de quota |
| 401/403 | credencial/provedor | quarentena até mudança de configuração ou probe controlado |
| 200 com 0 conteúdo | provedor+modelo (e canônico se repetido) | `ZERO_TOKEN`; cooldown; distinguir os casos de 5.3 |
| timeout / 5xx | provedor+modelo | transitório; retry limitado dentro do deadline |
| 400 / schema inválido | request | não repetir pedido idêntico em cascata |
| cancelamento do usuário | nenhum | `CANCELLED`; sem failover, sem penalidade |

### 5.3. "0 tokens" não é uma coisa só

O F0 deve verificar o que o stream do Nemotron realmente devolve: (a) stream vazio sem eventos, (b) só reasoning e nenhum conteúdo, (c) `finish_reason=length` consumido pelo raciocínio, (d) apenas heartbeats/metadata. Os remédios diferem (cooldown vs aumentar limite de tokens vs desabilitar reasoning). **Primeiro conteúdo = fragmento de conteúdo real**, não heartbeat, metadata, reasoning ou tool-call.

## 6. Elegibilidade e score

### 6.1. Filtro duro de elegibilidade (ANTES do ranking)

Um candidato `(provider, model)` é **inelegível** se qualquer item for verdadeiro:
- breaker `OPEN`, ou quarentena ativa de escopo (402/auth);
- cooldown ativo para `(provider, model)` ou para o `canonical_model_id`;
- modelo desativado/`MODEL_DEPRECATED`;
- semáforo de admissão cheio (concorrência por modelo e por provedor);
- saturação de quota ≥ 0,95 (exceto probe canary);
- já falhou nesta cascata com o mesmo canônico (exceto último recurso).

**Por que isto é obrigatório:** na combinação log-ponderada da v2.0, um fator catastrófico é suavizado pelo peso. Com `w=0,20`, `omega=0,02` rende `0,02^0,2 ≈ 0,46`, ou seja, um modelo que acabou de receber 402 manteria ~46% do seu score. Com `w_rel=0,45` e `phi_rel=0,05`, `≈ 0,26`. Score serve para ordenar candidatos saudáveis; só o gate remove os doentes. Foi exatamente o que faltou no loop do Nemotron.

### 6.2. Score entre elegíveis

```
effective_score = base_score * fit_score * H + sticky_bonus + tie_break_noise
H = clamp( exp( w_rel*ln(phi_rel) + w_lat*ln(phi_latency) + w_quota*ln(phi_quota) + w_brk*ln(omega) ), H_MIN, H_MAX )
```

- `base_score = 0.5*quality + 0.3*popularity_openrouter + 0.2*internal_usage`, nas escalas reais do projeto (normalize e valide antes de combinar). Preserve `fit_score`, sticky routing e regras de família/Tier existentes.
- Valores iniciais **em configuração**: `w_rel=.45, w_lat=.15, w_quota=.20, w_brk=.20` (soma 1); `H_MIN=.05, H_MAX=1.10`. Clamp de cada fator antes do `ln`: `phi_rel [0.05,1.0]`, `phi_latency [0.30,1.15]`, `phi_quota [0.05,1.0]`, `omega [0.02,1.0]`.
- `phi_rel` (confiabilidade, com shrinkage): `reliability_raw = weighted_successes / max(weighted_attempts, eps)`; `confidence = effective_attempts / (effective_attempts + K)` com `K≈10`; `phi_rel = 1 + confidence*(reliability_raw - 1)`. Sem dados: neutro (1.0). Janelas 10 min / 1 h / 24 h com pesos iniciais `.60/.25/.15`; documente que são horizontes sobrepostos, não amostras independentes. `MID_STREAM_DROP` pesa mais que falha pré-stream (configurável, testado). `ZERO_TOKEN` conta como falha.
- `phi_latency`: EWMA de TTFT (`alpha=.30`) e de velocidade (`alpha=.25`), só com medidas válidas. Unidades explícitas: `ttft_ms` é duração até o primeiro **conteúdo**; `first_content_at` é instante (relógio monotônico); chars/s é métrica separada de tokens/s; nunca tratar chars como tokens. Latência boa não esconde taxa de erro ruim.
- `phi_quota`: pressão `s` em [0,1] (0 = nenhuma utilização conhecida, 1 = esgotada); desconhecida = neutro e marcada como desconhecida. Contínua: `1.0` se `s ≤ .70`; `1 − .95*(s−.70)/.25` se `.70 < s < .95`; `.05` se `s ≥ .95`. Use o gargalo dominante entre RPM/TPM e documente.
- `omega = 1 − P * 2^(−Δt/half_life)`, com `half_life > 0`. Penalidade acumulada: `P_new = min(P_MAX, 1 − (1−P_old)*(1−severity))`. Severidades iniciais configuráveis: timeout/5xx `.35`, 429 `.60`, `ZERO_TOKEN` `.50` (hipótese), 402 `.98`. Meia-vida só dobra em falhas transitórias repetidas, limitada a 7200 s; quarentena de quota tem cooldown próprio.
- Sticky bonus limitado e só quando compatível com saúde e capacidade. Ruído apenas para desempate, nunca como balanceador de carga. Ordenação determinística nos testes.

### 6.3. Carga, canary e deadlines

- Admission control: semáforo por modelo e por provedor; contabilizar requisições em andamento; seleção entre elegíveis por score + carga.
- Backoff exponencial com jitter nas retentativas e respeito a `Retry-After`; limite de tentativas por request; **um orçamento total de tempo único** que todas as tentativas consomem.
- Deadlines distintos: conexão, TTFT, pré-commit, duração total e total de failover. Valores iniciais propostos por você a partir dos dados do F0 (p50/p95 de TTFT por provedor), aprovados por mim.
- Canary: probe `HALF_OPEN` **single-flight por escopo**, só após cooldown, só para prompt curto de baixo risco, com orçamento global limitado. Sem "promoção aleatória" de modelos degradados.

### 6.4. Persistência (sem SQLite no caminho do stream)

- Estenda `quota.py`/tabelas de failover existentes. **DDL só com minha aprovação da proposta do F0.** Reaproveite colunas existentes sempre que possível.
- **Cooldowns e quarentenas** (raros, pequenos, críticos para restart): persistir em até ~5 s via fila. **Métricas agregadas** (EWMA, taxas): write-behind em lote a cada 60 s (configurável) + flush no shutdown com deadline.
- Um escritor lógico por processo, transações curtas, nunca SQLite síncrono no event loop, nenhuma transação aberta durante stream de LLM; dados sujos preservados e reenviados com backoff se o flush falhar.
- Não prometa reconstruir janelas deslizantes exatas após restart: as janelas recomeçam vazias e o shrinkage mantém `phi_rel` neutro até acumular amostras. Se eu precisar de reconstrução exata mais tarde, será outro item com tabela de eventos e retenção de 24–48 h.
- **Multiworker:** se houver mais de um worker, as métricas em memória são por processo; documente. Cooldowns/quarentenas persistidos funcionam como estado compartilhado. Não anuncie coerência global que não existe.

## 7. Backlog (ordem fixa; um branch por item)

**F0 — Mapeamento (SOMENTE LEITURA; sem branch; sem alterar código).** Gere `melhorias/failover/00-mapeamento.md`, respondendo com arquivo e linha exata:

1. Quais status de erro/saúde, tabelas e colunas de quota/cooldown/quarentena/ranking existem hoje (`database.py`, `quota.py`, `failover.py`)? Existe alguma estatística de latência/saúde persistida?
2. Por que `database.py:3762` tratou 404 como billing? Qual é o critério atual?
3. Por que o 402 com "Usage limit reached" virou `error` genérico em vez de acionar `quota.py`?
4. O que `resolve_request.py:346` faz com 0 tokens? Registra cooldown? **O que o stream do Nemotron realmente devolve** (casos a–d da seção 5.3)?
5. Como `failover.py:338` identifica família? Como os IDs ganham prefixos duplicados (`nvidia/nvidia/`) e `:free`? Onde colocar o normalizador canônico?
6. Por que o boot grava ~11.460 linhas (sync.py + scorer.py)? Proponha como colapsar para uma única execução.
7. Quantos workers/processos o backend roda (compose/uvicorn/gunicorn)? Qual a versão do Python?
8. Como o streaming é feito (httpx, aiohttp, SDK)? O cliente é global e compartilhado? Usa `async with ...stream(...)` ou `aclose()` em `finally`? Há `except Exception`/`BaseException` que possa engolir `CancelledError`? Sobram tarefas ou conexões abertas quando um provedor falha?
9. Quais timeouts existem (TTFT, total)? Qual o tempo percebido por tentativa vazia? Os intervalos de ~20–30 s dos logs eram retries do usuário ou da cascata? Traga p50/p95 de TTFT por provedor, se houver dados.
10. O sync de catálogo no startup (12 provedores) pode **reabilitar** um modelo desativado por `MODEL_DEPRECATED`?
11. Os provedores usam function calling nativo? Ferramentas são executadas pelo `ToolDispatcher`/sandbox no servidor? Existe efeito colateral que um retry possa repetir (code exec, gravações)?
12. Quais eventos WebSocket existem (`failover_notice`, `stream_end`, `message_id`) e qual a semântica do terminal? Onde o toast é renderizado? Quais arquivos de frontend seriam tocados (e se colidem com os loops de Usabilidade e Projetos)?
13. Quais adapters suportam assistant prefill e `Retry-After`? (Só leitura; não presumir.)
14. Proponha (sem aplicar): DDL mínimo e migração incremental (padrão de `database.py` ~2038), lista de parâmetros de configuração com valores iniciais, e o procedimento de backup do `nexuslocal.db`.

**PARE após o F0 e me mostre o resumo.** Nada de código antes do meu OK.

**A1 — Taxonomia única de falhas** (`melhoria/failover-A1-taxonomia`). Implementar `classify_failure` e a tabela da seção 5.2, integrada a `quota.py`; o 404 deprecated loga o modelo sugerido sem aplicá-lo. *Verifica:* testes com os payloads reais do Gemini 404 e do LongCat 402; modelo desativado por deprecated **permanece desativado após um ciclo de sync de catálogo**.

**A2 — IDs canônicos, família (Tier 1) e cooldown de 0 tokens** (`melhoria/failover-A2-canonico-e-cooldown`). Normalizador único, lookup de família corrigido, exclusão do canônico na cascata, cooldown persistido para `ZERO_TOKEN`. *Verifica:* `gemini/gemini-2.5-pro` e `nvidia/nvidia/nemotron-...` resolvem família e o Tier 1 passa a ser consultado; dois provedores do mesmo canônico com 0 tokens não voltam na segunda tentativa; o cooldown sobrevive a um restart simulado.

**A3 — Orçamento de tempo do failover** (`melhoria/failover-A3-deadlines`). Deadlines distintos e orçamento total único, valores a partir dos dados do F0. *Verifica:* teste com relógio controlado em que quatro candidatos lentos não excedem o orçamento total; ao estourar, um único erro terminal.

**B1 — Gate de elegibilidade** (`melhoria/failover-B1-gate`). Implementar o filtro duro da seção 6.1. *Verifica:* modelo com maior base_score, mas em quarentena/cooldown/`OPEN`, nunca é selecionado; o gate vale mesmo com score alto.

**B2 — Health Registry em modo SOMBRA** (`melhoria/failover-B2-registry-sombra`). Registro em memória (EWMA, janelas, penalidade), persistência conforme 6.4, e correção da tempestade de escrita do boot (item 6 do F0). O score é **calculado e logado ao lado da decisão real, sem alterar o roteamento**. *Verifica:* o roteamento com o flag desligado é idêntico ao anterior (teste de regressão); fatores finitos e clampados, sem `ln(0)`; flush em lote e no shutdown; falha de flush não perde estado sujo nem bloqueia request.

**B3 — Higiene de recursos e cancelamento** (`melhoria/failover-B3-cancelamento`). `try/finally`, `async with ...stream(...)` ou `aclose()`, liberar semáforos, parar heartbeat, cancelar e aguardar tarefas filhas, propagar `CancelledError`, nunca capturar `BaseException` genérico, nunca fechar o cliente global por request. *Verifica:* cancelar no meio do stream fecha a response e não gera failover nem penalidade; falha de provedor não deixa tarefas órfãs; WebSocket disconnect e shutdown também não.

**B4 — Relatório sombra** (sem branch de código; entrega um documento). Compare, com dados reais acumulados, "o que o score teria decidido" vs "o que aconteceu", e quantas falhas foram pré-token vs mid-stream. **PARE e me mostre antes de ativar qualquer coisa.**

**C1 — Ativar o score no roteamento** (`melhoria/failover-C1-ativar`, só após meu OK do B4). Por feature flag; admission control e seleção load-aware; canary single-flight. *Verifica:* rajada de requisições não migra toda para um único secundário; o canary respeita o orçamento e o single-flight.

**C2 — Eventos e UX do failover invisível** (`melhoria/failover-C2-ux`). Pré-commit buffer (`MIN_COMMIT_CHARS=24`, `MAX_PRECOMMIT_HOLD_MS=450`, configuráveis; medidos em caracteres Unicode decodificados e tempo, nunca em bytes ou "tokens"); descartar integralmente o buffer do candidato que falhou; metadata **opcional** no evento terminal `{requested_model, served_by, failover_tier, spliced, outcome, attempt_count}`; um único evento terminal; remover o toast apenas quando a recuperação foi bem-sucedida; falha final visível e loading encerrado. Regras de UI: nome do modelo exibido é o `served_by`, **respeitando os níveis de interface** (no nível Simples não se mostram nomes de modelo; no Avançado, um tooltip discreto). O batching de deltas já foi tratado no plano 05: **reutilize** `run-streaming-paint-probe.mjs` e `run-message-actions-after-stream.mjs` e só mexa em batching se o probe regredir. *Verifica:* toast ausente em fallback bem-sucedido e presente em falha terminal; clientes antigos continuam funcionando sem a metadata nova.

**D1 — Continuação mid-stream** (condicional; **flag desligada por padrão**). Só se o B4 mostrar volume relevante de `MID_STREAM_DROP` (limiar proposto por você e aprovado por mim). Apenas texto livre compatível. `strip_overlap` com comparação **exata** de sufixo/prefixo (sem `lower()`, sem remover pontuação, sem normalizar Unicode ou whitespace); overlap ambíguo ou inconclusivo: acumular mais prefixo ou desistir da costura e terminar com "resposta interrompida" explícito, **nunca apagar texto por similaridade**; capability flag de prefill por adapter. Nunca costurar tool call, JSON/saída estruturada, XML, multimodal ou reasoning. `spliced=true` apenas após continuação pós-commit.

**Verificação final (sempre por último):** `./judge.sh` verde, matriz da Parte 4 mapeada para testes reais, relatório honesto.

## 8. Ciclo, freios, critérios de "não concluído"

**Ciclo por iteração:** 1) você escolhe o próximo item; 2) mini-plano com critério de aceite e arquivos permitidos no TASK_ATUAL.md; 3) delegar ao agy; 4) `./judge.sh`; 5) autorrevisão do diff (regressão, escopo extra, DDL não aprovado, segredos, `except BaseException`); 6) passou: commit convencional pequeno (`fix(failover): ...`) e push do branch; atualizar o backlog; falhou 2x: reverter e marcar bloqueado; 7) "qual a melhoria de maior impacto agora?" e voltar ao 1.

**Freios:**
- Comece pelo F0 e aguarde meu OK. Máximo 4 iterações por rodada (F0 conta como ½); depois, relatório e espera.
- Merge na main só com `./judge.sh` 100% verde e meu OK. Nunca force push.
- Sem DDL, mudança de enum que afete outros módulos, alteração da lógica de re-enable automático de modelos ou dependência nova sem minha aprovação.
- O modelo sugerido por uma API (ex.: `gemini-3.1-pro-preview`) é apenas logado: a troca na configuração é decisão humana.
- Critério ambíguo: perguntar antes.

**NÃO declare concluído se:** algum teste essencial não foi executado ou falhou; o `./judge.sh` não está verde; o relatório do B4 não foi produzido antes do C1; houve DDL sem aprovação; um teste foi enfraquecido ou apagado para passar; um contrato de evento externo mudou silenciosamente; ou o modo sombra alterou o roteamento. **Nunca marque um teste como aprovado sem tê-lo executado** e relate com honestidade o que não pôde ser verificado.

**Relatório de cada rodada:** itens concluídos (commit/branch), resultado do judge, testes antes/depois, riscos, decisões que dependem de mim, próximos 3 itens.

---

# PARTE 2 — Revisão crítica da v2.0 (por criticidade)

| # | Crit. | Problema na v2.0 | Correção na v3.0 |
|---|---|---|---|
| 1 | Crítico | **Premissa desatualizada** na Parte C: diz que o Tier 1 funciona, que 402/429/404 já são capturados e lista provedores (Groq, SiliconFlow, Gemini, OpenRouter, Ollama). Os logs mostram Tier 1 inoperante, 402 e 404 mal classificados, 14 provedores ativos (SiliconFlow desativado). | A v3 parte dos fatos dos logs (seção 3) e conserta a base primeiro (A1–A3). |
| 2 | Crítico | **A combinação log-ponderada é suave demais para falhas catastróficas**: `0,02^0,2 ≈ 0,46`; `0,05^0,45 ≈ 0,26`. Um modelo recém-bloqueado manteria boa parte do score. A v2.0 inclui `omega` e quota no score e depois pede o breaker em separado, sem dizer quem manda. | Gate duro de elegibilidade antes do score (6.1, B1); o score só ordena elegíveis. |
| 3 | Crítico | **Nova tabela `model_health_metrics`** duplica `quota.py` e as tabelas de failover já existentes; estado só em memória se perde nos restarts (5 no dia). | Estender o que existe; cooldowns/quarentenas persistidos em ~5 s; DDL só após aprovação; backup antes de migrar (6.4). |
| 4 | Crítico | **Escopo sem ID canônico.** `model_id` + `provider_scope` não impedem que a cascata volte ao mesmo modelo base por outro provedor (`nvidia/nvidia/...` vs `openrouter/...:free`). | Três escopos e `canonical_model_id` com normalizador único (5.1, A2). |
| 5 | Alto | **Splicing mid-stream é a parte de maior risco e menor benefício observado**: zero falhas mid-stream nos logs; todas foram antes do primeiro token. | D1 condicional, flag desligada, só com dados do B4. |
| 6 | Alto | **Sem orçamento de tempo concreto.** Os logs mostram ~20–30 s entre tentativas vazias; a falha só é "invisível" se TTFT e total forem curtos. | A3 com deadlines distintos e orçamento total único, baseados em p50/p95 reais. |
| 7 | Alto | **"0 tokens" tratado como uma coisa só.** Pode ser stream vazio, reasoning sem conteúdo ou `finish_reason=length`; remédios diferentes. | Pergunta 4 do F0 e seção 5.3; "primeiro conteúdo" bem definido. |
| 8 | Alto | **404 "no longer available to new users" não é necessariamente "removido"**; e o sync de catálogo no boot pode reabilitar o modelo. | `MODEL_DEPRECATED` com sugestão só logada; teste de que o modelo continua desativado após o sync (A1, pergunta 10). |
| 9 | Alto | **Tempestade de escrita no boot** (~11.460 gravações) ignorada enquanto a v2.0 adiciona mais escrita. | Item de B2 e pergunta 6 do F0. |
| 10 | Médio | **Batching de deltas no frontend** já foi tratado no plano 05, com probes de regressão. | Reutilizar os probes; só mexer se regredirem (C2). |
| 11 | Médio | **UI não considera os níveis de interface**: `served_by` e tooltip de roteamento não devem aparecer no nível Simples; arquivos do chat colidem com outros loops. | Regra de UI e aviso de conflito (C2, seção 0). |
| 12 | Médio | **Tool calls:** a v2.0 assume streaming de function calling; o NexusLocal tem `ToolDispatcher` e sandbox no servidor, com efeitos colaterais potenciais. | Pergunta 11 do F0 antes de qualquer esforço; idempotência onde houver efeito colateral. |
| 13 | Médio | **Pesos, janelas e severidades apresentados como números concretos** sem dados. | Modo sombra (B2/B4) e tudo em configuração. |
| 14 | Médio | **Execução monolítica pelo Claude Code** (um prompt gigante) não combina com o seu fluxo Hermes + agy com juiz, branches e freios. | Loop incremental com um branch por item e paradas obrigatórias (F0, B4). |
| 15 | Baixo | Reconstrução exata de janelas após restart exigiria tabela de eventos. | Janelas recomeçam vazias; shrinkage mantém `phi_rel` neutro; reconstrução exata fica como item futuro opcional. |

**O que da v2.0 foi mantido (e está certo):** separação Health Registry / Router / Stream Orchestrator; `CancelledError` propagado; contexto de stream do HTTPX; `FastAPI lifespan`; médias log-ponderadas com clamps e shrinkage; função de quota contínua; breaker separado do score; probe `HALF_OPEN` single-flight; overlap exato; um único evento terminal; remover o toast só quando a recuperação funcionou.

---

# PARTE 3 — Garantias vs best-effort

**Garantias (determinísticas e testáveis):**
- Classificação por causa, escopo e recuperabilidade segue a tabela da seção 5.2.
- Candidato inelegível nunca é escolhido (gate).
- O buffer pré-commit do candidato que falhou nunca vaza para o cliente.
- Cancelamento do usuário não penaliza, não dispara failover e fecha os recursos.
- Um único evento terminal por mensagem; toast removido só em recuperação bem-sucedida.
- Cooldowns e quarentenas sobrevivem a restart.
- Overlap ambíguo nunca apaga texto.
- Em modo sombra, o roteamento é idêntico ao anterior.

**Best-effort (heurísticas):**
- Qualidade semântica de uma continuação pós-commit.
- Previsão de saúde por EWMA/janelas e os pesos do score.
- Estimativa de pressão de quota (depende do que cada provedor informa).
- Eficácia do canary e do load-aware (dependem do tráfego real).
- Contagem de tokens quando o provedor não informa uso.

---

# PARTE 4 — Matriz risco → teste → comportamento esperado

| # | Risco | Teste | Esperado |
|---|---|---|---|
| 1 | 404 deprecated vira "billing" | payload real do Gemini 404 | `MODEL_DEPRECATED`; modelo desativado; sugestão `gemini-3.1-pro-preview` só logada |
| 2 | Modelo deprecated reabilitado pelo sync | rodar um ciclo de sync de catálogo | continua desativado |
| 3 | 402 de conta vira erro genérico | payload real do LongCat | `QUOTA_402`, escopo credencial/provedor, quarentena ≥ 1 h, sem escalar para outro modelo do mesmo provedor |
| 4 | Silent failure repetido | dois provedores do mesmo canônico com 0 tokens | o canônico não é escolhido de novo na cascata |
| 5 | Silent failure entre requisições | 0 tokens, nova requisição 20 s depois | o modelo não volta como #1 (cooldown ativo) |
| 6 | Cooldown perdido no restart | gravar cooldown, simular restart | cooldown ainda ativo |
| 7 | Tier 1 inoperante | resolver família de `gemini/gemini-2.5-pro`, `nvidia/nvidia/nemotron-...`, `longcat/...` | família encontrada; Tier 1 consultado antes do Tier 2 |
| 8 | Score suave demais | candidato com maior base_score em quarentena/`OPEN` | nunca selecionado |
| 9 | `ln(0)` e valores fora da faixa | fatores nos extremos (0, NaN, inf) | finitos, clampados, sem exceção |
| 10 | Amostra pequena | 1 sucesso / 1 falha | `phi_rel` perto do neutro, nem perfeito nem extremo |
| 11 | Descontinuidade de quota | `s` em .70 e .95 | função contínua nos limites |
| 12 | Cascata lenta | 4 candidatos lentos com relógio controlado | não excede o orçamento total; um único erro terminal |
| 13 | Modo sombra altera rota | comparar rota com o flag desligado e o código anterior | idêntica |
| 14 | Flush falha / SQLite ocupado | injetar erro no flush | estado sujo preservado; request não bloqueia |
| 15 | Tempestade de escrita no boot | boot com 12 provedores | ≤ 1 recálculo/persistência do scorer após o último sync |
| 16 | Cancelamento do usuário | cancelar no meio do stream | response fechada, tarefas canceladas, sem failover, sem penalidade |
| 17 | Tarefas órfãs | falha de provedor, WebSocket disconnect, shutdown | nenhuma tarefa/conexão aberta |
| 18 | Vazamento do buffer pré-commit | A falha antes do commit, B responde | só o conteúdo de B chega ao cliente |
| 19 | Todos falham | todos os candidatos falham | um único erro terminal; loading encerrado; sem `stream_end` de sucesso |
| 20 | Estrutura corrompida | JSON/tool call/multimodal/reasoning interrompidos | sem splicing textual; recuperação do protocolo ou erro explícito |
| 21 | Tool com efeito colateral repetida | falha após execução da ferramenta | não reexecuta sem idempotência |
| 22 | Overlap exato (D1) | "A arquitetura usa FastAPI e " + "FastAPI e WebSockets para baixa latência." | "A arquitetura usa FastAPI e WebSockets para baixa latência." |
| 23 | Overlap com acento, emoji, espaço duplo, quebra de linha, repetição legítima (D1) | casos específicos | nenhum texto legítimo removido |
| 24 | Overlap ambíguo (D1) | prefixo repetido legítimo | integridade preservada; costura desativada ou resposta interrompida explícita |
| 25 | Metadata quebra clientes antigos | cliente sem os campos novos | funciona normalmente |
| 26 | Toast | fallback bem-sucedido vs falha terminal | ausente no primeiro; visível no segundo |
| 27 | `served_by` no nível Simples | renderizar em Simples e Avançado | Simples sem nome de modelo; Avançado com tooltip |
| 28 | Regressão de streaming no frontend | `run-streaming-paint-probe.mjs` e `run-message-actions-after-stream.mjs` | continuam verdes |
