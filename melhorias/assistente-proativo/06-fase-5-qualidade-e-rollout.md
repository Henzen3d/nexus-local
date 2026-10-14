# ✅ Fase 5 — Qualidade, Observabilidade e Rollout com a Família

**Objetivo:** fechar o MVP com segurança: suíte completa, housekeeping, métricas, documentação e uma semana de teste real com ajustes de threshold.
**Estimativa:** 8 h (+ 1 semana de observação) · **Dependências:** F1–F4.

---

## Tarefa F5.1 — Suíte automatizada consolidada

- [ ] **F5.1.1** Revisar cobertura dos testes criados em F1–F4 e completar: `test_proactive_detector.py`, `test_proactive_schema.py`, `test_proactive_pipeline.py`, `test_proactive_delivery.py`, `test_proactive_presence.py`, `test_proactive_api.py` (REST + autorização), `test_proactive_ws.py` (integração com `TestClient`).
- [ ] **F5.1.2** Fakes reutilizáveis em `backend/tests/fakes/proactive.py`: `FakeProvider` (respostas JSON programáveis para detector/síntese), `FakeSearch` (resultados fixos), `FakeReader`, `FakeSocket` (captura `send_json`).
- [ ] **F5.1.3** Testes de regressão de segurança no padrão da auditoria: IDOR em `ack/expand/pending` (usuário B nunca vê insight de A), `expand new_chat` só na conversa do dono, SSRF (fontes com IP privado nunca lidas — `is_safe_public_url`), tamanho máximo do texto sintetizado.
- [ ] **F5.1.4** Teste de "não interromper": insight pronto durante turno ativo é entregue **após** `stream_end` (ordem dos eventos no socket fake).
- [ ] **F5.1.5** Teste de carga leve: 20 detecções simultâneas ⇒ no máximo `concurrency` pipelines ativos; nenhum vazamento de task (`_tasks` vazio ao final).
- [ ] **F5.1.6** Garantir que **nenhum** teste toca `backend/nexuslocal.db` (conftest) e que a suíte roda da raiz: `.venv/bin/python -m pytest backend/tests -q`.

---

## Tarefa F5.2 — Housekeeping, resiliência e observabilidade

- [ ] **F5.2.1** `run_proactive_housekeeping_job()` registrado em `main.py::startup` com referência em `app.state.background_tasks` (padrão da auditoria): expira vencidos, destrava `researching` > 5 min, apaga terminais > 30 dias, compacta `sources_json` de insights `dismissed` (só URLs).
- [ ] **F5.2.2** Recuperação no boot (padrão `recover_interrupted_dreams`): insights `detected|researching` de antes do restart ⇒ `failed:restart`.
- [ ] **F5.2.3** Logging estruturado por etapa com `request_id` do insight (`logger.info(..., extra={"insight_id", "stage", "latency_ms"})`), nível `warning` em falhas, nunca o texto do usuário.
- [ ] **F5.2.4** Cards no `UsageDashboard` (admin): insights/dia por status, taxa "saber mais", taxa "bloqueado", p95 das latências, custo estimado em tokens (entrada/saída do detector + síntese via `task_benchmark_manager`).
- [ ] **F5.2.5** Alarme simples: se `failed / detected > 50 %` nas últimas 24 h, badge de alerta na aba admin (sem e-mail/push).

**Arquivos:** `backend/main.py`, `backend/proactive/service.py`, `backend/routers/proactive.py`, `frontend/src/components/UsageDashboard.tsx`

---

## Tarefa F5.3 — Documentação e operação

- [ ] **F5.3.1** `melhorias/assistente-proativo/README.md`: índice dos documentos v2 + estado de cada fase.
- [ ] **F5.3.2** `.env.example`: `PROACTIVE_ENABLED_GLOBAL`, `PROACTIVE_MAX_PER_HOUR_CONV`, `PROACTIVE_MAX_PER_DAY_USER`, `PROACTIVE_TOPIC_COOLDOWN_HOURS`, `PROACTIVE_MAX_PENDING`, `PROACTIVE_CONCURRENCY`, `PROACTIVE_TOTAL_TIMEOUT_S` (todos opcionais; `meta` tem precedência).
- [ ] **F5.3.3** Seção no `AGENTS.md`: regras do módulo (nunca pesquisar `private_person`; mensagens `kind='proactive'` fora da memória/Dream; limites; onde ficam os prompts).
- [ ] **F5.3.4** Guia rápido para a família (1 página, pt-BR, dentro do onboarding/ajuda): o que é, como ligar/desligar, como bloquear um assunto.

---

## Tarefa F5.4 — Rollout gradual

- [ ] **F5.4.1** Deploy com `enabled_global=true` mas **nenhum usuário ativado** (opt-in). Rebuild: `docker compose build backend frontend && docker compose up -d`; migrações rodam no boot.
- [ ] **F5.4.2** Semana 1 — só o admin ativa; validar latências reais com os provedores gratuitos do deploy, ajustar `sensitivity` default se necessário; conferir custo/TPM no dashboard.
- [ ] **F5.4.3** Semana 2 — liberar o onboarding para todos (flag `proactive_onboarding_enabled` em `meta`), coletar feedback informal: "pareceu spam?", "fez sentido?", "pesquisou algo que não devia?".
- [ ] **F5.4.4** Critérios para manter ligado: 0 relatos de pesquisa sobre pessoa privada; ≤ 1 relato de spam; ≥ 1 "saber mais" por usuário ativo/semana; `failed` < 20 %.
- [ ] **F5.4.5** Plano de reversão: kill-switch global (sem deploy); rollback de código não exige migração reversa (colunas novas são ignoradas pela versão anterior).

---

## Tarefa F5.5 — Checklist de release

- [ ] **F5.5.1** `pytest` verde da raiz com DB temporário; `ruff check` sem erros novos; `bandit` sem achados altos.
- [ ] **F5.5.2** `npm run build` com 0 erros de TypeScript; i18n validada (script que compara chaves entre `pt-BR.json` e os outros 7 arquivos).
- [ ] **F5.5.3** Teste manual do cenário "saiu para almoçar" em celular (PWA instalado) e desktop, com duas abas abertas.
- [ ] **F5.5.4** Revisão de segurança final: todas as rotas novas com `get_current_user`/`require_admin`; queries com `user_id`; nenhum log com texto do usuário.
- [ ] **F5.5.5** PR com descrição, prints/vídeo do fluxo e link para os documentos desta pasta.

---

## Critérios de aceite da fase (= aceite do MVP)
- [ ] Todos os critérios de `00-visao-geral-v2.md` §7 atendidos e evidenciados no PR.
- [ ] Semana de teste concluída com os critérios de F5.4.4.
- [ ] Documentação e `.env.example` atualizados; `README.md` da pasta com o estado final das fases.
