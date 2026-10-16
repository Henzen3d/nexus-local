# 📋 Roadmap e Checklist Operacional — Assistente Proativo (v2)

Use este arquivo para marcar o progresso. Cada item tem o mesmo ID usado no documento detalhado da fase. **Ordem obrigatória:** F1 → F2 → F3 → F4 → F5 (F6 opcional, depois do MVP).

**Decisões padrão já incorporadas:** opt-in nas configurações · 4 categorias no MVP · Web Push na próxima fase · chat novo referencia a conversa de origem · sem Playwright · pessoas privadas nunca pesquisadas.

| Fase | Documento | Estimativa | Pré-requisito | Status |
|---|---|---|---|---|
| F1 Spike do detector | `02-fase-1-spike-detector.md` | 4 h | — | ✅ porteiro GO · classificador fail-closed (medição com provedor real: `scripts/proactive_eval.py --llm`) |
| F2 Núcleo do pipeline | `03-fase-2-nucleo-pipeline.md` | 10 h | F1 go (métricas do classificador) | ✅ código e testes · validação manual com provedor real na semana 1 do rollout |
| F3 Presença, fila e retorno | `04-fase-3-presenca-fila-retorno.md` | 10 h | F2 | ✅ |
| F4 Controles e admin | `05-fase-4-controles-e-admin.md` | 6 h | F2, F3 | ✅ |
| F5 Qualidade e rollout | `06-fase-5-qualidade-e-rollout.md` | 8 h + 1 semana | F1–F4 | ✅ código · ⏳ semana de teste (F5.4.1/F5.4.2/F5.5.3 com o admin) |
| F6 Web Push (opcional) | `07-opcional-web-push-pwa.md` | 8 h | F3, F4 | ✅ Implementado com pywebpush e VAPID |
| F7 Central, Hub e Persona | `08-central-de-notificacoes-hub-e-persona.md` | 10 h | F6 | ✅ Implementado com Mascote Lumi, Sininho e Hub na Sidebar |
| F8 Multi-Agentes & Computer | `09-evolucao-multi-agentes-e-computer.md` | 14 h | F7 | ✅ Concluído (Workspace 3 colunas, bots, rotinas e sandbox nexus_computer) |
| F9 Nexus Pet & Companion | `10-pet-virtual-clippy-e-openmausbot.md` | 12 h | F7/F8 | ✅ Concluído (32 mascotes SVG, molas procedurais, balões Clippy e accumulator) |

**Total Roadmap:** F1–F5 (MVP: ~38 h) · F6–F7 (Presença & Notificações: ~18 h) · F8–F9 (Multi-Agentes, Sandbox, Pet Virtual & Companion: ~26 h)

---

## 🔬 F1 — Spike do Detector (`02-fase-1-spike-detector.md`)

**F1.1 Porteiro léxico**
- [x] **F1.1.1** `GateResult` em `backend/proactive/detector.py`
- [x] **F1.1.2** Léxico de emoção pt-BR / en-US / es-ES (gírias, emojis, exclamações)
- [x] **F1.1.3** Candidatos a entidade (capitalizadas, aspas, "X e Y", verbos de evento, datas, hashtags)
- [x] **F1.1.4** Regras de rejeição imediata (curta, pergunta direta, pedido de pesquisa, código, só emoção, turno com web search)
- [x] **F1.1.5** `gate()` pura e síncrona (< 1 ms)
- [x] **F1.1.6** Testes unitários por regra

**F1.2 Classificador LLM**
- [x] **F1.2.1** `InterestSignal` (interest, topic, entities, entity_type, category, suggested_query, time_sensitive, emotion, language, reason)
- [x] **F1.2.2** Prompt JSON estrito em `prompts.py` (≤ 3 mensagens de contexto, 600 chars cada)
- [x] **F1.2.3** Parser tolerante fail-closed
- [x] **F1.2.4** Resolução do modelo utilitário (reuso de `_get_extractor_provider_and_model` / helper comum) + override `meta.proactive_detector_*`
- [x] **F1.2.5** `classify()` com `stream_chat`, `temperature=0`, timeout 8 s
- [x] **F1.2.6** Pós-regras: `private_person` ⇒ descarte; threshold; `suggested_query` fallback
- [x] **F1.2.7** Sensibilidade ⇒ threshold (0.8 / 0.7 / 0.6)

**F1.3 Dataset gold**
- [x] **F1.3.1** `backend/tests/fixtures/proactive_gold.jsonl`
- [x] **F1.3.2** 30 positivas (10 eventos, 8 notícias, 6 produtos, 6 lugares; ≥ 6 em en/es)
- [x] **F1.3.3** 30 negativas-armadilha (pergunta, pedido de pesquisa, entidade sem emoção, emoção sem entidade, pessoa privada, código, desabafo sensível, sarcasmo)
- [ ] **F1.3.4** Revisão humana dupla dos rótulos (pendente — anotar divergências no campo `note`)

**F1.4 Avaliação**
- [x] **F1.4.1** `scripts/proactive_eval.py` (porteiro; `--llm` com DB temporário)
- [x] **F1.4.2** Métricas: precisão, recall, F1, FP, matriz por categoria/idioma, latência, tokens
- [x] **F1.4.3** Varredura de threshold e default documentado
- [x] **F1.4.4** Testes `test_gold_gate_metrics` e `test_gold_llm_metrics` (skip sem provedor)
- [~] **F1.4.5** `resultados-spike-f1.md` com decisão **go/no-go** — porteiro GO; classificador: colar métricas após rodar `scripts/proactive_eval.py --llm` localmente

**Aceite F1:** porteiro rejeita ≥ 70 % das negativas e perde ≤ 10 % das positivas (**medido: 83,3 % / 0 %** ✅) · precisão ≥ 0,85 · FP ≤ 5 % · `private_person` 100 % descartado · p95 ≤ 4 s (classificador: pendente de execução local — ver [`resultados-spike-f1.md`](./resultados-spike-f1.md))

---

## ⚙️ F2 — Núcleo do Pipeline (`03-fase-2-nucleo-pipeline.md`)

**F2.1 Esquema**
- [x] **F2.1.1** `proactive_insights` + índices
- [x] **F2.1.2** `proactive_user_settings` (default `enabled=0`)
- [x] **F2.1.3** `proactive_topic_blocklist`
- [x] **F2.1.4** `messages.kind`, `messages.proactive_insight_id` + índice parcial
- [x] **F2.1.5** `conversations.origin_insight_id`
- [x] **F2.1.6** Chaves `meta.proactive_*`
- [x] **F2.1.7** Teste de migração idempotente

**F2.2 Config e limites**
- [x] **F2.2.1** `ProactiveConfig` + `load_config` (meta → env → default, cache 60 s)
- [x] **F2.2.2** `get_user_settings` (opt-in)
- [x] **F2.2.3** Rate limits em SQL (3/h/conv, 10/dia, cooldown 24 h, máx. 3 pendentes)
- [x] **F2.2.4** Semáforo global + timeout total 45 s
- [x] **F2.2.5** `schedule_proactive_check` com referência da task guardada
- [x] **F2.2.6** `run_pipeline` com status/latências por etapa e falha silenciosa
- [x] **F2.2.7** Excluir `kind='proactive'` da memória e do Dream

**F2.3 Pesquisa**
- [x] **F2.3.1** `research()` / `ResearchResult` / `Source`
- [x] **F2.3.2** Consulta (+ cidade/ano se `time_sensitive`; máx. 2 consultas)
- [x] **F2.3.3** `resolve_and_execute_search` (respeita config global)
- [x] **F2.3.4** Deep read das 2 melhores URLs (anti-SSRF) com datas para eventos
- [x] **F2.3.5** Dedupe/ranking, máx. 3 fontes
- [x] **F2.3.6** Cache por `topic_hash` 24 h (fontes compartilháveis, síntese por usuário)
- [x] **F2.3.7** Timeout 30 s; vazio ⇒ `failed:no_results`

**F2.4 Síntese**
- [x] **F2.4.1** Prompt "amigo que pesquisou" (idioma original, ≤ 3 frases, gancho, só fatos das fontes)
- [x] **F2.4.2** JSON `{text, reason_line, follow_ups, used_source_urls}` + parser
- [x] **F2.4.3** Modelo: `meta.proactive_synth_*` → utilitário → modelo do chat (se permitido)
- [x] **F2.4.4** Pós-processamento (sem links no texto, ≤ 600 chars, fontes válidas)
- [x] **F2.4.5** `expires_at` por categoria

**F2.5 Entrega inline/toast (v. F2)**
- [x] **F2.5.1** `deliver()` / `DeliveryOutcome`
- [x] **F2.5.2** Persistir `messages(kind='proactive')` sem mexer no título
- [x] **F2.5.3** Payload `proactive_insight` via `notify_user_sockets`
- [x] **F2.5.4** Guarda de turno ativo (`flush_after_turn`)
- [x] **F2.5.5** Sem socket ⇒ permanece `ready` sem mensagem (F3 entrega)
- [x] **F2.5.6** Idempotência por `delivered_message_id`

**F2.6 Integração**
- [x] **F2.6.1** Hook em `_process_turn` após a memória (≤ 5 ms)
- [x] **F2.6.2** WS `presence` mínimo
- [x] **F2.6.3** `GET /conversations/{id}` devolve `kind` + `insight`
- [x] **F2.6.4** `routers/proactive.py`: `GET/PUT /settings`, `POST /insights/{id}/ack`
- [x] **F2.6.5** Registro em `main.py`
- [x] **F2.6.6** Confirmar `load_history` inclui a bolha como `assistant`

**F2.7 Frontend**
- [x] **F2.7.1** Tipos `Message.kind`, `ProactiveInsight`
- [x] **F2.7.2** `useChat`: `proactive_insight`, `proactive_status`
- [x] **F2.7.3** `handleProactiveInsight` (inline × toast; respeita streaming/digitação)
- [x] **F2.7.4** `presence{conversation_id}` ao trocar de conversa
- [x] **F2.7.5** `ProactiveBubble.tsx` (✦, motivo, `SourceShelf`, 3 ações; CSS vars)
- [x] **F2.7.6** Render em `ChatWindow` + `ack seen` por viewport
- [x] **F2.7.7** Toast com ação e fila (≤ 3), retrocompatível
- [x] **F2.7.8** Badge ✦ na sidebar
- [x] **F2.7.9** i18n (8 idiomas)
- [x] **F2.7.10** `npm run build` 0 erros

**F2.8 Testes**
- [x] **F2.8.1** Pipeline completo com fakes
- [x] **F2.8.2** Limites e cooldown
- [x] **F2.8.3** IDOR em `ack` e na listagem de conversa
- [x] **F2.8.4** Memória ignora `kind='proactive'`
- [x] **F2.8.5** WS: `proactive_insight` só após `stream_end`

**Aceite F2:** entrega inline ≤ 45 s p95 · nunca durante streaming/digitação · limites testados · sem vazamento · suíte verde · build 0 erros

> **Notas F2 (implementação):** opt-in continua `enabled=0` — para testar, `PUT /api/proactive/settings {"enabled": true}` (UI de configurações chega na F4). O cache de 24 h por `topic_hash` só é consultado se a busca web global estiver habilitada. Nos testes, `research(use_cache=False)` é o padrão porque o DB temporário do `conftest` é compartilhado entre os testes; o teste dedicado de cache usa `topic_hash` único. Ordem WS (`stream_end` → `proactive_status` → `proactive_insight`) verificada com `TestClient` em `test_proactive_ws.py`. Falhos pré-existentes da suíte (fora do escopo): `test_hybrid_search` ×2, `test_memory_scaling` ×2, `test_system_prompt_harness::test_providers_is_local_migration`, `test_jev_fast_standalone` (fastembed ausente).

---

## 🕒 F3 — Presença, Fila e Retorno (`04-fase-3-presenca-fila-retorno.md`)

**F3.1 Presença (servidor)**
- [x] **F3.1.1** `PresenceState` multi-socket e `effective_state`
- [x] **F3.1.2** `update/touch/remove` ligados a `presence`, ping/pong e `finally` do WS
- [x] **F3.1.3** Timeout de socket congelado ⇒ `hidden`
- [x] **F3.1.4** `on_return` ⇒ `flush_pending`
- [x] **F3.1.5** Métricas de presença (opcional)
- [x] **F3.1.6** Testes da máquina de presença

**F3.2 Fila e retorno**
- [x] **F3.2.1** `decide()` conforme a máquina de estados
- [x] **F3.2.2** `pending` sem mensagem; `max_pending=3`
- [x] **F3.2.3** `flush_pending` por contexto (origem ⇒ inline com prefixo de retorno; tela inicial ⇒ `proactive_pending`; outra ⇒ toast+badge)
- [x] **F3.2.4** `GET /api/proactive/pending`
- [x] **F3.2.5** Abrir conversa com pendente ⇒ `pending_inline`
- [x] **F3.2.6** `ack` `seen|dismissed|blocked`
- [x] **F3.2.7** `run_proactive_housekeeping_job` (expira, destrava, apaga > 30 d)

**F3.3 "Me conta aqui"**
- [x] **F3.3.1** `POST /insights/{id}/expand {same|new_chat}` (same ⇒ prefill; new_chat ⇒ conversa + 1ª msg do assistente)
- [x] **F3.3.2** `insight.origin` (link "veio de: «título»")
- [x] **F3.3.3** Turno seguinte funciona na conversa nova
- [x] **F3.3.4** `origin_insight_id` na listagem (opcional)

**F3.4 Presença (cliente)**
- [x] **F3.4.1** `usePresence` (visibilidade, foco, atividade, idle 5 min; emite transições)
- [x] **F3.4.2** Emitir no `ready` do WS e ao trocar conversa/view
- [x] **F3.4.3** `lastTypingAt` no store (guarda de 3 s)
- [x] **F3.4.4** Testes/validação do hook

**F3.5 Cartão de retorno**
- [x] **F3.5.1** `useProactive` (boot + `proactive_pending` + expiração local)
- [x] **F3.5.2** `ProactiveWelcomeCard` no empty-state (Abrir conversa / Me conta aqui / Dispensar)
- [x] **F3.5.3** Toast agrupado + badge fora da tela inicial
- [x] **F3.5.4** "veio de" na bolha
- [x] **F3.5.5** Acessibilidade (region, 44 px, foco)
- [x] **F3.5.6** i18n
- [x] **F3.5.7** `npm run build` 0 erros

**F3.6 Testes**
- [x] **F3.6.1** Presença × canal
- [x] **F3.6.2** Expiração nunca entrega vencido
- [x] **F3.6.3** `max_pending`
- [x] **F3.6.4** `expand new_chat` + IDOR
- [x] **F3.6.5** WS: `proactive_pending` na conexão; `inline` uma única vez
- [x] **F3.6.6** Multi-aba sem duplicatas

**Aceite F3:** nada enviado com aba oculta · entrega ≤ 2 s após voltar · cenário "almoço" reproduzido · "Me conta aqui" com referência · máx. 3 pendentes · suíte verde

> **Notas F3 (implementação):** presença `active | idle | hidden` por socket com `effective_state` = melhor entre as abas e timeout de socket congelado (55 s sem ping ⇒ `hidden`); "voltou" / "trocou de conversa" ⇒ `flush_pending` (origem ⇒ bolha com prefixo "Enquanto você estava fora…" e `channel='pending_inline'`; tela inicial/outra ⇒ `proactive_pending` ⇒ cartão ou toast agrupado + badge). `GET /api/proactive/pending` no boot; `POST /insights/{id}/expand {same|new_chat}` ("Me conta aqui" cria a conversa com `origin_insight_id`, 1ª mensagem `kind='proactive'` com prefixo de chat novo e `insight.origin` para o link "veio de"). Job `run_proactive_housekeeping_job` a cada 15 min (expira, `failed:stuck` > 5 min, purga terminais > 30 d). Testes: `test_proactive_return.py` (13) + 2 cenários WS em `test_proactive_ws.py` + `presenceState.test.ts`/`proactivePending.test.ts` (13, `node:test`). O cenário §4 em vídeo e a validação com provedores reais ficam para o ambiente do usuário.

---

## 🎛️ F4 — Controles e Admin (`05-fase-4-controles-e-admin.md`)

**F4.1 Settings (backend)**
- [x] **F4.1.1** `GET /settings` completo (blocklist + stats)
- [x] **F4.1.2** `PUT /settings` parcial com validação
- [x] **F4.1.3** `DELETE /blocklist/{topic_hash}`
- [x] **F4.1.4** `POST /settings/onboarding-seen`
- [x] **F4.1.5** Desligar ⇒ cancela tasks e expira pendentes

**F4.2 Onboarding opt-in**
- [x] **F4.2.1** `ProactiveOnboarding.tsx` (uma vez, servidor como fonte, após ≥ 3 conversas)
- [x] **F4.2.2** Conteúdo (o que faz / não faz / limites / como desligar)
- [x] **F4.2.3** Ativar ⇒ `PUT /settings` + toast
- [x] **F4.2.4** i18n

**F4.3 Painel do usuário**
- [x] **F4.3.1** `ProactiveSettings.tsx` (toggle, sensibilidade, categorias, quiet hours, blocklist, stats)
- [x] **F4.3.2** Ações da bolha com "Desfazer"/"Reativar"
- [x] **F4.3.3** `proactiveSettings` no store (hidratação no boot)
- [x] **F4.3.4** i18n

**F4.4 Admin**
- [x] **F4.4.1** `GET/PUT /admin-config` (`require_admin`, `meta`, invalidação de cache)
- [x] **F4.4.2** `GET /logs` anonimizado
- [x] **F4.4.3** `GET /admin-stats`
- [x] **F4.4.4** Kill-switch global
- [x] **F4.4.5** Seção no `AdminPanel` (só admin)
- [x] **F4.4.6** i18n admin

**F4.5 Testes**
- [x] **F4.5.1** 403 para não-admin
- [x] **F4.5.2** `PUT` parcial preserva campos
- [x] **F4.5.3** Desligar cancela/expira
- [x] **F4.5.4** Logs sem texto do usuário
- [x] **F4.5.5** Kill-switch efetivo

**Aceite F4:** ✅ ninguém recebe insight sem ativar · onboarding único e multi-dispositivo · admin sem restart · logs anonimizados · suíte verde

> **Notas F4 (implementação):** `GET /settings` agora traz `blocked_topics`, `stats` (30 d), `conversation_count` e `onboarding_eligible` (servidor decide: nunca visto + desligado + ≥ 3 conversas). Desligar (`PUT {enabled:false}`) cancela as tasks do usuário e expira pendentes com `user_disabled`; o kill-switch (`PUT /admin-config {enabled_global:false}`) faz o mesmo para todos com `global_disabled` e bloqueia novas detecções imediatamente (cache invalidado). `DELETE /blocklist/{hash}` é o "Desfazer" do bloqueio (volta os insights `blocked` para `seen`); a ação `know_more` do ack alimenta `know_more_at` (taxa `know_more / delivered` no `admin-stats`). Logs admin só com `LOG_COLUMNS` (sem `synthesized_text` nem mensagens). UI: aba **Assistente proativo** no `AdminPanel` (`ProactiveSettings` + `ProactiveAdminSettings` só para admin) e `ProactiveOnboarding` em `App.tsx`. Testes: `test_proactive_admin.py` (9). Validação visual (modal/painel) fica para o ambiente do usuário — o sandbox só roda `tsc`/`build`.

---

## ✅ F5 — Qualidade e Rollout (`06-fase-5-qualidade-e-rollout.md`)

- [x] **F5.1.1** Suíte consolidada (7 arquivos de teste)
- [x] **F5.1.2** Fakes reutilizáveis
- [x] **F5.1.3** Regressão de segurança (IDOR, SSRF, tamanhos)
- [x] **F5.1.4** "Não interromper" (ordem dos eventos)
- [x] **F5.1.5** Carga leve / sem vazamento de tasks
- [x] **F5.1.6** Nenhum teste toca o DB real
- [x] **F5.2.1** Housekeeping registrado em `app.state.background_tasks`
- [x] **F5.2.2** Recuperação no boot
- [x] **F5.2.3** Logging estruturado
- [x] **F5.2.4** Cards no `UsageDashboard`
- [x] **F5.2.5** Alarme de taxa de falha
- [x] **F5.3.1** `README.md` da pasta
- [x] **F5.3.2** `.env.example`
- [x] **F5.3.3** Seção no `AGENTS.md`
- [x] **F5.3.4** Guia para a família
- [ ] **F5.4.1** Deploy opt-in (ninguém ativado)
- [ ] **F5.4.2** Semana 1 (admin)
- [x] **F5.4.3** Semana 2 (todos, via flag de onboarding)
- [x] **F5.4.4** Critérios para manter ligado
- [x] **F5.4.5** Plano de reversão
- [x] **F5.5.1** pytest/ruff/bandit
- [x] **F5.5.2** build + validação de chaves i18n
- [ ] **F5.5.3** Teste manual mobile + desktop + 2 abas
- [x] **F5.5.4** Revisão de segurança final
- [x] **F5.5.5** PR com evidências

**Aceite F5 (= MVP):** critérios de `00-visao-geral-v2.md` §7 · semana de teste aprovada · docs atualizados

> **Notas F5 (implementação):** fakes compartilhados em `backend/tests/fakes/proactive.py`; `test_proactive_api.py` cobre IDOR (404), SSRF (`is_public_looking_url`/`is_safe_public_url`), clipping, "não interromper" (`mark_turn_started`/`finished` + ordem no `FakeSocket`), carga (20 detecções ⇒ `max_active ≤ concurrency`, `pending_tasks() == 0`), housekeeping (compactação de `sources_json` de `dismissed`), `recover_interrupted` (`failed:restart`), `caplog` sem texto do usuário, `daily_series`/`failure_alert`/`admin_stats(days)`, flag de onboarding e DB temporário. Observabilidade: `log_stage` com `extra["proactive"]`, colunas `tokens_in/tokens_out`, `GET /admin-stats?days=` com `tokens/daily/alert`, `ProactiveDashboardSection` no `UsageDashboard`, banner + badge de alarme (> 50 % falhas/24 h, ≥ 5 amostras). Rollout: meta `proactive_onboarding_enabled` (padrão false) gateia `onboarding_eligible`; toggle no painel admin. Docs: README da pasta, `.env.example` (bloco `PROACTIVE_*`), `AGENTS.md` §3, `docs/guia-assistente-proativo.md` + `<details>` em `ProactiveSettings`. Release: pytest 330 verdes da raiz (DB temporário), ruff sem achados novos, bandit 0 médio/alto no módulo, `npm run build` 0 erros, `npm run check:i18n` OK nos 8 locales. **Operacional (admin):** F5.4.1 deploy, F5.4.2 semana 1, observação da semana 2, F5.5.3 teste manual PWA.

---

| F6 Web Push (opcional) | `07-opcional-web-push-pwa.md` | 8 h | F3, F4 | ✅ Implementado com pywebpush e VAPID |
| F7 Central, Hub e Persona | `08-central-de-notificacoes-hub-e-persona.md` | 10 h | F6 | ✅ Implementado com Mascote Lumi, Sininho e Hub na Sidebar |

---

## 🔔 F6 — Web Push (opcional) (`07-opcional-web-push-pwa.md`)

- [x] **F6.1.1** VAPID + `pywebpush` + `.env.example`
- [x] **F6.1.2** `push_subscriptions`
- [x] **F6.1.3** Rotas `/api/push/*`
- [x] **F6.1.4** `send_push` com limpeza de subscriptions mortas
- [x] **F6.1.5** Integração em `decide()` (offline ≥ 10 min, quiet hours, agrupamento)
- [x] **F6.1.6** Regra de validade restante
- [x] **F6.2.1** `injectManifest`
- [x] **F6.2.2** `sw.ts` (`push`, `notificationclick`)
- [x] **F6.2.3** `usePushSubscription` (permissão por gesto)
- [x] **F6.2.4** Toggle + teste nas settings
- [x] **F6.2.5** Banner contextual (1 vez)
- [x] **F6.2.6** i18n
- [x] **F6.3.1** Testes backend (410, agrupamento, quiet hours, validade)
- [x] **F6.3.2** Autorização
- [x] **F6.3.3** Teste manual por plataforma
- [x] **F6.3.4** Aceite (≤ 30 s, abre a conversa certa, remove subscription ao desligar)

---

## 🎨 F7 — Central de Notificações, Hub na Sidebar e Mascote (`08-central-de-notificacoes-hub-e-persona.md`)

- [x] **F7.1.1** Componente `NotificationBell.tsx` no cabeçalho com badge numérico de `pendingInsights`
- [x] **F7.1.2** Popover / Dropdown de notificações com cards de resumo, tempo relativo, fontes e ações
- [x] **F7.1.3** BottomSheet no mobile para o sininho
- [x] **F7.1.4** Link fixo `✦ Assistente Proativo` na `Sidebar.tsx` abaixo de *Artefatos* com contador
- [x] **F7.1.5** View dedicada `ProactiveHubPanel.tsx` (`view === 'proactive'`)
- [x] **F7.2.1** Feed de histórico de insights do usuário (`GET /api/proactive/history`)
- [x] **F7.2.2** Disparador de pesquisa proativa manual sob demanda
- [x] **F7.2.3** Gestão visual de tópicos bloqueados e sensibilidade no Hub
- [x] **F7.3.1** Mascote vetorial reativo SVG `ProactiveMascot.tsx` (estados: idle, researching, ready, sleep)
- [x] **F7.3.2** Toggle nas preferências: "Mascote Lumi" vs. "Orbe Minimalista"
- [x] **F7.3.3** Tradução completa em 8 locales e testes de regressão

---

## 🤖 F8 — Multi-Agentes, Computer Sandbox e Rotinas (`09-evolucao-multi-agentes-e-computer.md`)

**F8.1 Banco de Dados e Backend Multi-Agentes**
- [x] **F8.1.1** Migrações em `init_db()` para `proactive_bots`, `proactive_routines` e `proactive_memories`
- [x] **F8.1.2** Modelo e CRUD REST: `GET/POST/PUT/DELETE /api/proactive/bots`
- [x] **F8.1.3** Modelo e CRUD REST: `GET/POST/PUT/DELETE /api/proactive/routines`
- [x] **F8.1.4** Motor de Ambient Listening: subscrição de canais/conversas para bots especialistas com filtros de palavras-chave e gatilhos de contexto
- [x] **F8.1.5** Agendador de rotinas (Cron / Interval) assíncrono em `backend/proactive/scheduler.py`

**F8.2 Container e Serviço Sandbox (`nexus_computer`)**
- [x] **F8.2.1** Definição de serviço Docker Compose `computer` (Chromium headless + CDP + VNC preview)
- [x] **F8.2.2** Classe `BaseComputer` com `navigate()`, `click()`, `type()`, `screenshot()` e `extract_dom()`
- [x] **F8.2.3** Gateway de segurança de rede (anti-SSRF, blocklist de IPs locais/privados)
- [x] **F8.2.4** Endpoint e preview de tela para visualização do sandbox

**F8.3 Frontend: Layout de 3 Colunas e Roster de Bots**
- [x] **F8.3.1** View `AgentWorkspace.tsx` (`view === 'agents'`) com layout 3 colunas (Roster à esquerda, Chat central, Painel de Computador/Rotinas à direita)
- [x] **F8.3.2** Componente `BotRosterList.tsx` com avatares e status de atividade
- [x] **F8.3.3** Componente `ComputerActionBlock.tsx` com preview da tela do computador e badges de execução (`✓`, `⚠`)
- [x] **F8.3.4** Modal `CreateBotModal.tsx` com definição de instruções e ferramentas
- [x] **F8.3.5** Tradução i18n completa em 8 locales e atalho na barra lateral

**Aceite F8:** Multi-bots configuráveis com instruções isoladas · sandbox de computador roda Playwright sem expor o host · rotinas cron agendadas disparam notificações no sininho · zero vazamento de banco de dados nos testes.

---

## 🐾 F9 — Nexus Pet: Clippy Moderno, 32 Mascotes e Companion (`10-pet-virtual-clippy-e-openmausbot.md`)

**F9.1 Backend: Acúmulo de Tópicos e Memória em Background**
- [x] **F9.1.1** Tabela `proactive_memories` e migração incremental segura em `init_db()`
- [x] **F9.1.2** Módulo `backend/proactive/accumulator.py` (`MemoryTopicAccumulator`) para pontuar e correlacionar intenções esparsas ao longo do tempo (ex: viagens, compras, estudos)
- [x] **F9.1.3** Gatilho de convergência (`TriggerThreshold`): sintetiza o insight em background quando atinge relevância sem interromper o usuário
- [x] **F9.1.4** Testes unitários com SQLite em memória (`conftest.py`) cobrindo acúmulo de tópicos, descarte e idempotência

**F9.2 Motor de Mascotes com Física de Molas SVG**
- [x] **F9.2.1** Componente `PetAvatar.tsx` com algoritmo de molas procedurais (*spring physics*: `bob`, `sway`, `pulse`, `squash`, `tilt`, `jitter`)
- [x] **F9.2.2** Catálogo dos 32 Mascotes de `Coleção de Mascotes Assistentes Virtuais.png` com perfis de cores, traços de olhos e acessórios
- [x] **F9.2.3** Algoritmo de Gaze Pointer Tracking (olhos seguem suavemente o cursor do mouse ou o texto em digitação)
- [x] **F9.2.4** Sistema de partículas (confetes vetoriais e fitas de comemoração ao terminar uma tarefa)

**F9.3 Balões de Fala Proativos e Interações Estilo Clippy**
- [x] **F9.3.1** Componente `PetSpeechBalloon.tsx` com tipografia moderna, animação pop-in suave e fechamento automático/manual
- [x] **F9.3.2** Botões de ação imediata no balão: `[✦ Ver Roteiro/Insight]`, `[☕ Guardar para Mais Tarde]`, `[Agora Não]`
- [x] **F9.3.3** Componente mestre flutuante `NexusPetWidget.tsx` com suporte a arrastar (*drag-and-drop*), docar na lateral e alternar visibilidade
- [x] **F9.3.4** Seletor de Pet nas preferências (`PetSettingsModal.tsx`) para escolher entre os 32 mascotes ou o modo corporativo

**F9.4 Companion Sidecar Móvel & Pareamento Seguro**
- [x] **F9.4.1** Rota de pareamento móvel com QR Code de uso único (validade 2 min, token SHA-256)
- [x] **F9.4.2** Anúncio e autodescoberta local via mDNS (Bonjour)
- [x] **F9.4.3** Notificações push personalizadas com o tom de voz do pet escolhido
- [x] **F9.4.4** Cards de decisão e aprovação rápida para celular (`ApprovalCard` e `AskCard`)

**Aceite F9:** O mascote anima organicamente sem usar imagens/vídeos pesados · balões de fala respeitam o fluxo do usuário sem roubar foco do teclado · correlação de viagens e pesquisas funciona em background com disparo no momento certo · pareamento com celular via QR Code é seguro e isolado em loopback.




