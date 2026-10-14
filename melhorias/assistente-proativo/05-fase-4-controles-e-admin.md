# 🎛️ Fase 4 — Controles do Usuário, Onboarding (opt-in) e Painel Admin

**Objetivo:** dar ao usuário controle total e transparente (ligar/desligar, sensibilidade, categorias, tópicos bloqueados) e ao admin as alavancas globais (kill-switch, modelos, caps, logs anonimizados). **Padrão: desligado até o usuário ativar.**
**Estimativa:** 6 h · **Dependências:** F2 (settings REST), F3 (ack/blocklist) · **Bloqueia:** F5.

**Entregáveis**
- `frontend/src/components/ProactiveSettings.tsx`, `ProactiveOnboarding.tsx`
- Bloco "Assistente Proativo" no `AdminPanel.tsx` (`require_admin` no backend)
- `GET/PUT /api/proactive/admin-config`, `GET /api/proactive/logs`, `DELETE /api/proactive/blocklist/{topic_hash}`

---

## Tarefa F4.1 — Settings do usuário (backend)

- [x] **F4.1.1** `GET /api/proactive/settings` devolve `{enabled, sensitivity, categories, quiet_hours, onboarding_seen_at, blocked_topics: [{topic_hash, topic_label, created_at}], stats: {insights_30d, know_more_30d}}`.
- [x] **F4.1.2** `PUT /api/proactive/settings` com Pydantic **com defaults `None`** (lição da auditoria: `Optional` sem default é obrigatório no v2) e validação: `sensitivity ∈ {low, medium, high}`, `categories ⊆ {event, news, product, place}`, `quiet_hours` `{start:"22:00", end:"08:00"}` ou `null`.
- [x] **F4.1.3** `DELETE /api/proactive/blocklist/{topic_hash}` (desbloquear tópico).
- [x] **F4.1.4** `POST /api/proactive/settings/onboarding-seen` (marca `onboarding_seen_at`, sem alterar `enabled`).
- [x] **F4.1.5** Desligar (`enabled=false`) ⇒ cancelar tasks em andamento do usuário (`service.cancel_user(user_id)`), expirar pendentes (`status='expired', error_code='user_disabled'`), manter histórico já entregue.

**Arquivos:** `backend/routers/proactive.py`, `backend/proactive/service.py`

---

## Tarefa F4.2 — Onboarding opt-in (frontend)

- [x] **F4.2.1** `components/ProactiveOnboarding.tsx` no padrão de `MemoryOnboarding.tsx` (modal acessível, `role="dialog"`), exibido **uma vez** quando `onboarding_seen_at` é nulo **e** o usuário já tem ≥ 3 conversas (não assustar no primeiro login). Fonte da verdade no servidor (não só `localStorage`), para funcionar em vários dispositivos.
- [x] **F4.2.2** Conteúdo: o que é ("quando você parecer animado com um show, notícia, lançamento ou lugar, eu pesquiso e te conto"), o que **não** faz (não pesquisa pessoas da sua vida, não compartilha nada com outros usuários, só fontes públicas), limites (poucas vezes por dia), e como desligar. CTA primário **Ativar**, secundário **Agora não**.
- [x] **F4.2.3** Ao ativar: `PUT /settings {enabled:true}` + toast "Assistente proativo ativado — ajuste em Configurações".
- [x] **F4.2.4** i18n: `proactive.onboardingTitle`, `proactive.onboardingBody`, `proactive.onboardingNot1..3`, `proactive.onboardingEnable`, `proactive.onboardingLater`, `proactive.enabledToast`.

**Arquivos:** `frontend/src/components/ProactiveOnboarding.tsx`, `App.tsx` (montagem), `i18n/locales/*.json`

---

## Tarefa F4.3 — Painel de configurações do usuário (frontend)

- [x] **F4.3.1** `components/ProactiveSettings.tsx` acessível pelo mesmo lugar das preferências pessoais (onde fica `UserMemoryPanel`): toggle principal; sensibilidade (baixa/média/alta com explicação "quantas vezes eu puxo assunto"); categorias (4 chips); horário silencioso (preparado para F6; em F4 só influencia o toast? **Não** — fica desabilitado com nota "usado por notificações nativas"); lista de tópicos bloqueados com "desbloquear"; mini-estatística (insights nos últimos 30 dias, quantas vezes você pediu "saber mais").
- [x] **F4.3.2** Ligações da bolha: **Não quero sobre isso** ⇒ `ack blocked` + toast com "Desfazer" (chama `DELETE /blocklist/{hash}`); **Pausar assistente proativo** ⇒ `PUT /settings {enabled:false}` + toast com "Reativar".
- [x] **F4.3.3** Estado no `useStore` (`proactiveSettings`) hidratado no boot junto com `hydrateProfileFromServer`.
- [x] **F4.3.4** i18n: `proactive.settingsTitle`, `proactive.settingsDesc`, `proactive.enabled`, `proactive.sensitivity{Low,Medium,High}`, `proactive.categories.{event,news,product,place}`, `proactive.quietHours`, `proactive.blockedTopics`, `proactive.unblock`, `proactive.stats`, `proactive.undo`, `proactive.reactivate`.

**Arquivos:** `frontend/src/components/ProactiveSettings.tsx`, `components/ProactiveBubble.tsx`, `store/useStore.ts`, `api/client.ts`, `i18n/locales/*.json`

---

## Tarefa F4.4 — Admin: configuração global, kill-switch e logs

- [x] **F4.4.1** `GET/PUT /api/proactive/admin-config` (`Depends(require_admin)`): `enabled_global`, `detector_provider_id/model_id`, `synth_provider_id/model_id`, `allow_chat_model_fallback`, `max_per_hour_conv`, `max_per_day_user`, `topic_cooldown_hours`, `max_pending`, `concurrency`, `total_timeout_s`, `expiry_news_hours`, `expiry_default_days`. Persistir em `meta` (padrão `_get_meta`/`_set_meta`); invalidar cache do `config.py`.
- [x] **F4.4.2** `GET /api/proactive/logs?limit=50&status=` (`require_admin`): linhas **anonimizadas** — `created_at, username (ou id), category, topic (apenas rótulo curto), confidence, status, channel, latências, detector_model, synth_model, error_code`. **Nunca** o texto da mensagem do usuário nem `synthesized_text`.
- [x] **F4.4.3** `GET /api/proactive/admin-stats`: contadores por status nas últimas 24 h/7 d, taxa `know_more / delivered`, taxa `blocked / delivered`, p95 das latências — base para o `UsageDashboard`.
- [x] **F4.4.4** Kill-switch: `enabled_global=false` ⇒ `schedule_proactive_check` retorna antes de tudo; tasks em andamento são canceladas; pendentes expiram com `error_code='global_disabled'`.
- [x] **F4.4.5** `AdminPanel.tsx`: nova aba/seção "Assistente Proativo" (ao lado de Enhancer/Vision Relay/Web Search): seletores de provider/modelo reutilizando o padrão de `EnhancerSettings.tsx`, campos numéricos com limites, kill-switch com confirmação, tabela de logs e cards de stats. Visível **só** para admin (`useStore.user.role`), como o gating feito na auditoria para o extrator.
- [x] **F4.4.6** i18n admin: `proactive.admin.*` (título, campos, ajuda, confirmação do kill-switch, colunas da tabela).

**Arquivos:** `backend/routers/proactive.py`, `backend/proactive/config.py`, `frontend/src/components/AdminPanel.tsx`, `components/ProactiveAdminSettings.tsx` (novo), `api/client.ts`, `i18n/locales/*.json`

---

## Tarefa F4.5 — Testes da fase

- [x] **F4.5.1** Autorização: `admin-config`/`logs`/`admin-stats` ⇒ 403 para usuário comum; `settings` só afeta o próprio usuário.
- [x] **F4.5.2** `PUT /settings` parcial (só `sensitivity`) não zera os outros campos.
- [x] **F4.5.3** Desligar cancela pipeline em andamento (task fake) e expira pendentes.
- [x] **F4.5.4** Logs não contêm texto da mensagem (`assert "texto da mensagem" not in body`).
- [x] **F4.5.5** Kill-switch global bloqueia novas detecções em ≤ 60 s (cache de config) — ou imediatamente com invalidação explícita.

---

## Critérios de aceite da fase
- [x] Usuário novo **não** recebe insights até ativar; onboarding aparece uma única vez e funciona em dois dispositivos (fonte: servidor — `onboarding_eligible`).
- [x] Todas as ações da bolha têm efeito imediato e "Desfazer" (bloquear ⇒ "Desfazer"; pausar ⇒ "Reativar").
- [x] Admin controla modelos/caps/kill-switch sem reiniciar o backend (`meta` + `invalidate_config_cache()`).
- [x] Logs anonimizados; nenhum endpoint admin acessível a usuário comum (`test_proactive_admin.py`).
- [x] Suíte verde (9 testes novos; 177 proativos no total); build 0 erros; i18n completa nos 8 idiomas.

---

## Notas de implementação (F4)

- **Settings:** `GET /settings` devolve também `blocked_topics`, `stats{insights_30d, delivered_30d, know_more_30d, blocked_30d}`, `conversation_count` e `onboarding_eligible` (nunca visto **e** desligado **e** ≥ 3 conversas — calculado no servidor, então o onboarding aparece uma única vez em qualquer dispositivo). `quiet_hours` é validado (`HH:MM`, `start ≠ end`) mas só será consumido pelas notificações nativas (F6); a UI mostra o campo desabilitado com essa nota.
- **Desligar:** `PUT {enabled:false}` ⇒ `service.disable_user()` cancela as tasks do usuário (registro `_user_tasks` em `track_task(..., user_id=)`), expira `detected|researching|ready` com `error_code='user_disabled'` e devolve `disabled:{cancelled, expired}`; o histórico entregue é mantido. `run_pipeline` trata `CancelledError` marcando o insight como `failed:cancelled`.
- **Bolha:** "Não quero sobre isso" ⇒ `ack blocked` + toast com **Desfazer** (`DELETE /blocklist/{topic_hash}` remove da blocklist e volta os insights `blocked` daquele tópico para `seen`); "Pausar" ⇒ toast com **Reativar**; "Quero saber mais" registra `know_more_at` (ação `know_more`, status inalterado) — base da taxa `know_more / delivered`.
- **Admin:** `GET/PUT /admin-config` (todos os campos de `ProactiveConfig`, limites em `ADMIN_FIELD_LIMITS` devolvidos como `limits`; `""` limpa a chave e volta ao env/default). `enabled_global=false` ⇒ `apply_kill_switch()` (cancela tudo, expira pendentes de todos com `global_disabled`; `schedule_proactive_check` retorna `None` na hora — cache invalidado). `GET /logs` nunca inclui `synthesized_text`/mensagens (apenas `LOG_COLUMNS`, com `topic` truncado a 60 caracteres). `GET /admin-stats`: janelas 24 h/7 d, taxas `know_more`, `blocked`, `failure`, p50/p95 por etapa e `total_p95_ms`, `pending_now`, `blocklist_size`, `runtime{tasks_in_flight, presence}`.
- **UI:** aba **Assistente proativo** no `AdminPanel` (desktop e mobile) com `ProactiveSettings` para todos e `ProactiveAdminSettings` só para `role === 'admin'` (kill-switch com confirmação, seletores provider/modelo no padrão `EnhancerSettings`, campos numéricos com faixas, cards de stats, tabela de logs paginada). `ProactiveOnboarding` montado em `App.tsx` depois do `MemoryOnboarding` (espera o de memória ser dispensado).

