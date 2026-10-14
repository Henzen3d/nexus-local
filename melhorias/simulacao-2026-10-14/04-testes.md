# Testes, reprodução e regressão

## 1. Ambiente e limites

- Checkout da base `af42ceeb3c276506e819684d01487b010a545fd2`; Python 3.11 em `.venv`; Node 22.22.3; backend FastAPI real; Vite 5.4.21 instalado pelo lock; Chromium 153 distribuído por `@sparticuz/chromium` e Playwright; axe-core.
- DB da sessão: `.cache/simulacao/qa.db`, criado novo. Provas de lógica criam **outro** banco em TemporaryDirectory. Testes existentes usam `backend/tests/conftest.py`, que redireciona DB_PATH antes de importar produto.
- Provedor `tests/simulacao/fake_provider.py` é determinístico, fala SSE OpenAI-compatível e oferece qa-a/b/c/judge/slow/bad. Nunca tratá-lo como LLM, nem usar suas respostas para aprovar qualidade de RAG/Judge/visão.
- Sem credenciais comerciais, HuggingFace/Google Fonts/buscadores bloqueados. A suíte de embeddings reais ficou parcialmente sem execução útil. Sem Docker, browser físico, auditoria de todos os recursos adicionais ou teste de carga de produção.
- Dados de teste incluíram Unicode, markup hostil literal, documentos artificiais e imagens de cor sólida; nenhum dado pessoal real. Logs entregues foram sanitizados para JWTs e assinaturas de URLs. Banco, senhas, pacotes e binários de browser **não** fazem parte do PR.

## 2. O que foi executado

| Comando / grupo | Resultado | Evidência |
|---|---|---|
| Import segundo launcher (`cwd=backend`) | Falhou: pacote backend não encontrado | `boot-readme.log` |
| Import da raiz, sem JWT | Falhou com mensagem explícita de segredo ausente | `boot-no-env.log` |
| Uvicorn da raiz com JWT e DB_PATH isolados | Subiu; health respondeu; schema íntegro | `backend.log`, `schema.sql` |
| Front Vite com config só de teste | Subiu e navegação real executada | `frontend.log`, 37 PNGs |
| `npm run build` | Passou; warning de chunk 1,66 MB | `build.log` |
| `npm test` | **50 passaram** | `frontend-tests.log` |
| `npm run check:i18n:all` | Falhou: de-DE/es-419/fr-FR/ja/ko com 284 faltantes cada; es-ES com 127 | `i18n.log` |
| `.venv/bin/python -m pytest backend/tests -q` | **406 passed, 5 failed, 3 errors, 1 skipped**, 73,09 s | `pytest.log` |
| HTTP/WS: autenticação, arquivos, RAG, Fusion, shapes, concorrência | Provas positivas/negativas; diagnóstico, não suite de assert “verde” | `api-results.json`, `api-flows.log`, `api-power.log`, `final-probes.log` |
| Lógica de cache/contexto | Bugs reproduzidos em DB separado, vetores fake | `logic-results.json`, `logic.log` |
| Playwright + axe | Desktop/mobile; violações registradas por tela | `browser-*.log`, `axe-*.json`, PNG/JSON de cada etapa |
| SQLite | `integrity_check=ok` após 6 turnos concorrentes | `measurements.json`, `api-results.json` |

### Não confundir testes vermelhos com a causa de produto

- `test_single_embedding_memoization`: embedding veio `None`; download externo indisponível neste ambiente.
- `test_semantic_gate_follow_ups`: `no such table: cache_settings`.
- Três `test_smart_router` falham com `no such table: models`.
- Três erros de setup em `test_jev_fast_standalone` por fixture `db` inexistente no modo pytest coletado.
- Não foram corrigidos esses testes durante a auditoria. Uma seleção passar isolada não justificaria ocultar o resultado agregado; CI deve separar fixture/setup/integrations de regressão funcional.

## 3. Reproduzir com segurança

**Nunca usar `backend/nexuslocal.db` de produção. Não rodar os scripts de seed em servidor real.** Os scripts de exploração não são uma suite portátil com um comando: alguns dependem das etapas anteriores e do provedor sintético. `README.md` em `tests/simulacao/` descreve essa ordem e flags. O diretório `.cache/simulacao` é runtime local ignorado, não restaurado pelo PR.

Exemplo de preparação, da raiz:

```bash
python3 -m venv .venv
.venv/bin/pip install -r backend/requirements.txt playwright
npm --prefix frontend ci
mkdir -p .cache/simulacao
export DB_PATH="$PWD/.cache/simulacao/qa.db"
export JWT_SECRET="$(.venv/bin/python -c 'import secrets; print(secrets.token_urlsafe(48))')"
# Em processos próprios, não em testes contra produção:
.venv/bin/uvicorn backend.main:app --host 0.0.0.0 --port 8000
node frontend/node_modules/vite/bin/vite.js --config tests/simulacao/vite.config.mjs
```

Em estação com acesso ao CDN: `playwright install chromium` e ajustar `executable_path` dos scripts (atualmente `/tmp/chromium`, deliberadamente explícito para esta sessão). Neste sandbox a alternativa está documentada no README dos testes. Os scripts de screenshot exigem `LD_LIBRARY_PATH=/tmp/al2023/lib` para o binário mínimo.

- Primeiro: `browser_scout.py`, sem conta; `seed_qa.py`, com DB descartável inicializado; `browser_flows.py`, ainda sem provedores configurados.
- Para casos positivos: iniciar `fake_provider.py`, configurar providers/models/chaves **fictícias** da fixture (ver `configure_qa.py`) e usar `browser_daily.py`/`api_flows.py`/`api_power.py`.
- `logic_probes.py` é independente do servidor, cria e descarta seu próprio DB. Usa internals para isolar causas; os JSON são evidências de comportamento atual, não asserts de comportamento desejado.
- `browser_panels.py`, `browser_edges.py` e `final_probes.py` reutilizam sessão de teste em `.cache/simulacao/session.json`. Credencial nunca deve ser gravada na pasta de relatório. Na coleta original, uma sessão autenticada já existente foi reutilizada após o limite de logins; login UI já havia sido validado. Para repetir, obter sessão com `configure_qa.py --session`.
- Houve erros intermediários de selectors (tradução “Parar”, nome do menu lateral, idioma default), dependências do browser e limite de logins. Os scripts finais incorporam ajustes; falhas do harness estão identificadas nos logs e **não** contadas como falhas de UI. `final-probes.log` contém a falha inicial de seletor de idioma; `final-ui.log` registra execução final corrigida.

## 4. Matriz de regressão proposta

Os casos abaixo devem virar asserts com fixtures determinísticas. Valores de timeout/performance são **metas propostas**, não resultados já garantidos. Automatizar `B*` em pytest e `U*` com Playwright/axe, preservando testes de integração separados.

| ID | Camada | Fixture / ação | Asserts mínimos desejados |
|---|---|---|---|
| R01 — B01/U01 | Smoke instalação | Container/venv limpos, DB novo, sem JWT/conta | Mensagem de configuração útil; bootstrap idempotente sem senha padrão; comando documentado sobe API+UI; primeiro usuário não precisa editar SQLite |
| R02 — B02 | Provider HTTP | Fake OpenAI e Ollama com chave vazia | Sem Authorization vazio; streaming normal; provedores obrigatórios recusam falta de chave antes da rede |
| R03 — B03 | Cache scope | Mesmo texto, usuário/modelo; alternar projeto/system/revisão/anexo/voz/web | Miss em toda mudança relevante; hit só em scope igual; usuário B nunca recebe A; follow-up não usa cache semântico |
| R04 — B03 | Semântica real, opt-in CI | MiniLM versionado, pares negados/números/data/entidades | Taxa de falso positivo abaixo da meta acordada; relatório precision/recall por idioma; nunca passar com embeddings fake |
| R05 — B04 | SQLite/relógio congelado | UTC, virada do dia, -71/-72/-73 h, refresh de expirado | TTL exato na fronteira; resposta/timestamp renovados; uma linha sob duas inserções simultâneas |
| R06 — B05 | Indexação degradada | Embedder ausente, depois disponível | `text_ready/degraded`, nunca vector_ready com todos blobs nulos; fallback recupera fato sem palavra “arquivos”; retry preenche vetores |
| R07 — B05 | RAG corpus | 3+ docs, fatos início/meio/fim, formatos/md/pdf, documento revisionado | Recall@k definido; não usar documento excluído; budget respeitado; resposta rastreável até chunk/página/revisão |
| R08 — B06 | Fusion payload capture | Projeto/memória/system com canários; 3 respostas | Judge recebe policy/contexto/fontes necessários; não apenas opinião de proposers; pós-turno indexa e persiste modelo efetivo |
| R09 — B07 | Fusion multimodal | `content` string e lista com PNG/texto; relay capability distinta | Nenhum TypeError; cópia sem mutação; instrução extra em part de texto; relay por participante quando necessário |
| R10 — B08 | Budget property-based | Contextos 512/8k/32k, CJK/emoji/código/imagem, system gigante, failover menor | Nenhuma chamada viola janela após reserva de output; última mensagem impossível dá erro antes do provider; clamp não produz orçamento maior que contexto |
| R11 — B09 | WS fuzz contrato | null/lista/número/json inválido/arrays enormes/campos extras | Erro estruturado e conexão utilizável; ping seguinte responde; sem stack trace exposto; tamanho máximo rejeitado cedo |
| R12 — B10 | Idempotência/race | 2 frames mesmo ID; 2 abas mesma conversa; reconexão/retry | Uma geração por ID; nenhum turno mistura tokens; política de concorrência explícita; IDs de usuário/conversa autorizados |
| R13 — B11/U06 | Cancelamento | Fake lento bloqueia em wait; parar/fechar socket/timeout | Cancel chega ao provider em <1 s como meta inicial; fan-out inteiro encerrado; parcial persistido; reload não ressuscita final; um único terminal |
| R14 — B12 | Upload streaming | 0 bytes, limite−1/+1, MIME conflitante, PDF truncado, zip bomb sintética limitada, pixels extremos | 4xx/202 coerentes; leitura interrompida no teto; parser isolado; nenhum arquivo órfão; quotas por usuário |
| R15 — B13 | Segurança de sessão/logs | Capturar access/proxy/app logs e URL; ticket usado duas vezes/expirado | JWT e API key nunca aparecem; ticket não se reutiliza; Origin inválido recusado; owner check antes de emitir dados |
| R16 — B14/U07 | Privacidade por destino | Seleção local e proposer remoto; perfil/sumário com canário secreto | Conteúdo local-only ausente em cada payload remoto, inclusive retries/relay/Judge; texto de onboarding fiel |
| R17 — B15 | Transação Fusion | Modelo/provedor inválido, mesmo provedor, falha de INSERT forçada | 422 amigável ou suporte explícito; nenhuma alteração parcial; leitura concorrente vê config consistente |
| R18 — B16 | Carga SQLite | 6/20/100 turnos + upload/listagem; 1k/10k/100k candidatos | integrity ok, zero perda/duplicação; medir p50/p95 TTFT/RAG/locks; EXPLAIN registrado; budgets de p95 aprovados antes de gate |
| R19 — B16 | Recovery jobs | Matar processo durante indexação e reiniciar | Pending retomado; sem status indexing eterno; tarefas rastreadas/canceladas; nenhum job usa DB de produção nos testes |
| R20 — B17 | Segurança RAG | Documento com `</fonte>`, prompt injection, citações inventadas | Sem mudança de política/ferramenta não autorizada; citações inexistentes rejeitadas; execução com modelos reais separada de parser unitário |
| R21 — U02 | Erros/i18n | Simular 401/429/timeout/contexto/rede/offline | Mensagem localizada sem chave crua; CTA apropriado; reenvio só explícito; rascunho preservado se não houve ACK |
| R22 — U03/U04 | Acessibilidade | 1440/390, claro/escuro, keyboard Tab/Escape | Axe sem falhas inventariadas; sidebar oculta não focável; labels; trap/restore; contraste medido e targets ≥44 px |
| R23 — U05 | Histórico | Termo só no corpo; editar/regenerar variantes | Busca encontra snippet; identidade/autoria/ordem preservadas; exclusão de variantes não apaga conversa indevidamente |
| R24 — U08 | Estados finitos | Busca vazia/falha/sucesso; Fusion parcial/juiz concluído | Nenhum “consolidando” após terminal; fonte vazia não vira sucesso factual; modelo efetivo exibido |
| R25 — U09 | Visual/performance | Fonts bloqueadas, first load cold, idioma longo, zoom 200% | Layout sem overflow, fallback legível; snapshot revisado; orçamento de JS inicial e LCP definido/medido em rede móvel real |
| R26 — segurança positiva | Autorização | Outro usuário, bearer revogado, ID malformado, URL anexo expirada/traversal | Nenhum acesso cruzado; 401/403/404 consistente; conteúdo não executa script; anexos só via assinatura válida |

## 5. CI e execução sugeridos

1. **PR obrigatório, offline:** lint/typecheck/build, unit tests com DB por teste, contratos WS, cache com relógio fixo, provider fake, Playwright/axe dos quatro fluxos. Segredos aleatórios efêmeros e teardown obrigatório.
2. **Integração separada:** MiniLM real com cache de artefato versionado/checksum; teste nunca baixa modelo implicitamente durante unit test. Opt-in explícito para APIs externas, custos máximos e prompts sem dados pessoais.
3. **Noturno:** corpus RAG, matriz de permutações do Judge, load/restart/cancel; medir p95 e custo, não “parece rápido”.
4. **Antes de release:** iOS/Android reais, teclado virtual, VoiceOver/NVDA, conexão lenta/perdida/reconectada, instalação Docker nova e upgrade de cópia do SQLite de versão anterior.
5. **Saúde dos testes:** impedir fixtures ausentes, módulos importando DB antes de monkeypatch, sleeps frágeis e tolerância silenciosa de erro. Substituir sleeps do harness exploratório por waits de estado/evento na suíte final.

## 6. Índice de evidências

- PNGs `01–03`: iniciante sem configuração; `04–08`: modelo/local/chat/troca/busca.
- `09–14`: home/projetos/detalhe/chat/menu/biblioteca nos dois viewports, com JSON de DOM e axe.
- `15–18`: envio mobile, anexos, PDF corrompido; `19–22`: streaming, stop, reload e tentativa offline.
- `23–25`: Fusion em andamento/concluído e tema escuro. Captura “loading” é instantânea; não constitui medição de duração de animação.
- `api-results.json`: eventos completos/timings, inclusive erros, não apenas resumo positivo.
- `logic-results.json`: scope/TTL/refresh/contexto gigante/microcontexto, com vetores artificiais declarados.
- `provider.jsonl`: payloads do fake com dados exclusivamente sintéticos; `provider-summary.json` e `measurements.json`: sentinels, cancelamento e volume de histórico.
- `schema.sql`, `routes.txt`, `source-excerpts.txt`, logs: evidência estática/runtime da base auditada.

Screenshots não foram produzidos para cada frame de testes via API (malformed JSON, 26 MiB, concorrência etc.). A tabela distingue explicitamente cobertura visual, protocolo e código; nenhuma etapa sem screenshot foi apresentada como visualmente validada.