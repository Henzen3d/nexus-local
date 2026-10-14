# 🤖 Assistente Proativo — Visão Geral v2 (ajustada ao código real)

**Data:** 2026-10-13 · **Status:** planejamento aprovado para implementação futura · **Substitui/complementa:** `assistente-proativo-plano.md` (2026-10-07), `design-assistente-proativo.md`, `brainstorm-assistente-proativo.md`

> Esta v2 mantém a visão original (detectar interesse genuíno → pesquisar em background → contar como um amigo contaria) e corrige o que não batia com o repositório, além de fechar a decisão que estava em aberto: **como e quando o assistente fala com o usuário** (ver `01-decisao-entrega-e-presenca.md`).

---

## 1. Visão em uma frase

Quando o usuário demonstra **emoção + um assunto concreto** ("vi que Gabriel e Shirley vão tocar em Blumenau, tô muito animado!"), o Nexus pesquisa sozinho em segundo plano e, **no momento certo**, volta com um resumo curto, com fontes, como quem diz "fiquei curioso e fui ver". Se a pessoa saiu (almoço, trabalho, dormir), nada é disparado no vazio: o insight espera e aparece **quando ela volta**.

**Caso de uso de referência**
```
Usuário:  "Gente, vi que Gabriel e Shirley vão tocar em Balneário Camboriú, tô muito animado!"
(IA responde normalmente ao turno)
(…em background: detector 0.86 → pesquisa → síntese; usuário já foi almoçar → fica pendente)
(usuário volta 50 min depois e abre a tela inicial)
Cartão:   "✦ Enquanto você esteve fora, pesquisei sobre o show do Gabriel e Shirley em Balneário Camboriú."
          [Abrir conversa]  [Me conta aqui]  [Dispensar]
→ "Me conta aqui": o assistente inicia o chat novo:
IA:       "Oi! Fiquei curioso com o show e fui pesquisar: é dia 15/11 no Beach Park, portões às 19h,
           ingressos a partir de R$ 89 (fontes abaixo). Quer que eu veja como comprar ou como chegar?"
```

---

## 2. Decisões de produto (fechadas nesta v2)

| Decisão | Escolha | Motivo |
|---|---|---|
| Ativação | **Opt-in por usuário**, nas configurações, com cartão de onboarding na primeira vez (mesmo padrão de `MemoryOnboarding.tsx`) | Em deploy familiar, uma IA que "pesquisou por conta própria" sem aviso assusta. Quem liga, sabe o que está ligando. |
| Categorias do MVP | **eventos/shows, notícias, lançamentos/produtos, lugares/viagens** (as 4) | O classificador já devolve a categoria; restringir não reduz custo. O usuário pode desligar categorias individualmente. |
| Canal de entrega | **Híbrido guiado por presença**: a fonte da verdade é uma mensagem persistida na conversa de origem; toast, badge e cartão de retorno são só ponteiros | Nada se perde; permite "quer saber mais?"; respeita quem saiu. Detalhes em `01-decisao-entrega-e-presenca.md`. |
| "Me conta aqui" em chat novo | A conversa nova **referencia a conversa de origem** (link "veio de: *título*") e a 1ª mensagem é do assistente | Dá contexto e permite voltar; evita o modelo "alucinar" o porquê da pesquisa. |
| Web Push (notificação nativa PWA) | **Próxima fase** (`07-opcional-web-push-pwa.md`), fora do MVP | Exige VAPID, subscriptions e permissão do navegador; o cartão de retorno já cobre o cenário principal. |
| Playwright / browser headless | **Fora do MVP** | +300 MB de imagem e mais um processo; o Deep Reader (`web_search/reader.py`) cobre eventos/notícias, que são páginas estáticas. |
| Pessoas privadas | **Nunca pesquisadas** | O classificador marca `entity_type`; `pessoa_privada` ⇒ descarte. Elimina o maior risco de "creepy factor". |
| Persistência | Insights **são persistidos** (visíveis só ao dono, expurgo em 30 dias). Logs admin **sem** o texto da mensagem | Entrega no retorno exige persistência; privacidade preservada por escopo + anonimização. |
| Limites | 3 pesquisas/h/conversa · 10/dia/usuário · 1 pesquisa por tópico a cada **24 h** · máx. **3 pendentes** por usuário · 2 pesquisas simultâneas no servidor | O cooldown original de 5 min por tópico repesquisava o mesmo show na mensagem seguinte. |

---

## 3. O que o código já oferece (reaproveitar)

| Necessidade | Já existe | Onde |
|---|---|---|
| Hook pós-turno em background | padrão idêntico ao da extração de memória | `backend/routers/chat.py::_process_turn` → `asyncio.create_task(extract_user_memory_background(...))` (após o `stream_end`) |
| Modelo "leve" para detector/síntese | waterfall extrator → enhancer → modelo do chat | `backend/memory.py::_get_extractor_provider_and_model` |
| Busca web | Brave / DuckDuckGo + config global | `backend/web_search/providers.py::resolve_and_execute_search`, `get_web_search_config` |
| Planejador de consultas e leitura de páginas | planner + Deep Reader com **anti-SSRF** (auditoria) | `web_search/planner.py::plan_search_queries`, `web_search/reader.py::fetch_page_content` |
| Formatação de fontes | já usado pela busca do chat | `web_search/formatter.py::format_search_results`, UI `SourceShelf.tsx` |
| Push servidor → usuário conectado | registro de sockets por usuário, usado pelo worker de imagem | `routers/chat.py::notify_user_sockets`, `image_gen/worker.py::_safe_notify_sockets` |
| Regra "mesma conversa injeta / outra conversa toast" | implementada para `image_ready` | `frontend/src/store/useStore.ts::handleImageReady` |
| Heartbeat e visibilidade da aba | ping/pong + `visibilitychange` reconecta | `frontend/src/hooks/useChat.ts` (L75–99, L355–377) |
| Toast global | existe, mas 1 slot, sem ação, efêmero | `useStore.toast/showToast`, `App.tsx::Toast` |
| Tela inicial (chat vazio) | saudação dinâmica — ponto natural do cartão de retorno | `ChatWindow.tsx` (`getRandomGreeting`, bloco `isEmpty`) |
| Config global chave/valor (admin) | tabela `meta` + `_get_meta` | `backend/memory.py::_get_meta` (L686) |
| Jobs periódicos | `run_*_job` com referências guardadas em `app.state.background_tasks` | `backend/main.py` |
| Migrações | blocos `try/except ALTER TABLE` em `init_db` + índices após o bloco | `backend/database.py` (regra do AGENTS.md) |
| Controle de acesso | `get_current_user` / `require_admin` | `backend/auth.py` |
| Testes isolados | `conftest.py` com `DB_PATH` temporário | `backend/tests/conftest.py` |

---

## 4. Correções ao plano original

1. `backend/orchestration/handle_message.py` **não existe** → o hook entra em `routers/chat.py::_process_turn`.
2. `backend/routers/__init__.py` não registra routers → registrar em `backend/main.py` (`app.include_router(proactive_router)`).
3. Detector por regex (`r'\b[a-zA-Z]+ [a-zA-Z]+\b'` para "pessoa", lista fixa de cidades) é frágil → regex vira **porteiro barato** (estágio 1); a decisão é do **modelo utilitário com JSON** (estágio 2).
4. Cache "em JSON local" → tabela SQLite (`proactive_insights` já guarda o resultado; chave de tópico com TTL 24 h).
5. "Dados não salvos" × "logs admin" × "entrega quando voltar" eram incompatíveis → persistência com escopo por usuário + expurgo + logs anonimizados.
6. Entrega "mesma janela / nova mensagem" estava subespecificada → máquina de estados de presença (`01-decisao-entrega-e-presenca.md`).
7. Estimativa de 14 h não cobria presença, fila, retorno, controles e testes → **~38 h** no MVP (F1–F5), +8 h com Web Push.

---

## 5. Arquitetura (resumo)

```
 turno normal termina (stream_end)
          │  schedule_proactive_check()   ← só se usuário opt-in e turno sem web search
          ▼
 ┌─ backend/proactive ──────────────────────────────────────────────────────────┐
 │ detector.py   estágio 1 porteiro (0 ms) ─► estágio 2 LLM utilitário (JSON)  │
 │ service.py    rate limits · cooldown por tópico · semáforo(2) · timeout 45 s │
 │ researcher.py busca (Brave/DDG) + Deep Reader (2 páginas) + cache 24 h      │
 │ synthesizer.py "amigo que pesquisou": ≤3 frases + gancho + ≤3 fontes (JSON)  │
 │ presence.py   estado por usuário: active / idle / hidden / offline          │
 │ delivery.py   grava messages(kind='proactive') e escolhe canal              │
 └──────────────┬───────────────────────────────────────────────────────────────┘
                ▼
   WS: proactive_insight · proactive_pending · proactive_status
   REST: /api/proactive/{pending, insights/{id}/ack, insights/{id}/expand, settings, admin-config, logs}
                ▼
 ┌─ frontend ───────────────────────────────────────────────────────────────────┐
 │ usePresence · useProactive · ProactiveBubble · ProactiveWelcomeCard          │
 │ toast com ação · badge ✦ na sidebar · ProactiveSettings · onboarding opt-in  │
 └──────────────────────────────────────────────────────────────────────────────┘
```

**Novas tabelas:** `proactive_insights`, `proactive_user_settings`, `proactive_topic_blocklist`. **Colunas novas:** `messages.kind` (`'normal' | 'proactive'`), `messages.proactive_insight_id`, `conversations.origin_insight_id`.

---

## 6. Fases e estimativas

| Fase | Arquivo | Entrega | Estimativa |
|---|---|---|---|
| F1 | `02-fase-1-spike-detector.md` | detector validado offline (≥ 0,85 precisão, ≤ 5 % FP) | 4 h |
| F2 | `03-fase-2-nucleo-pipeline.md` | pipeline completo + entrega inline/toast + bolha | 10 h |
| F3 | `04-fase-3-presenca-fila-retorno.md` | presença, fila `pending`, cartão de retorno, "Me conta aqui", expiração | 10 h |
| F4 | `05-fase-4-controles-e-admin.md` | opt-in, onboarding, botões da bolha, blocklist, bloco admin, logs | 6 h |
| F5 | `06-fase-5-qualidade-e-rollout.md` | testes, expurgo, deploy, semana de teste com a família | 8 h |
| F6 (opcional) | `07-opcional-web-push-pwa.md` | notificação nativa com app fechado | 8 h |

**Ordem obrigatória:** F1 → F2 → F3 → F4 → F5. F1 é barata e decide se vale seguir. O checklist consolidado está em `ROADMAP-CHECKLIST.md`.

---

## 7. Critérios de sucesso do MVP

**Técnicos**
- [ ] Detector: precisão ≥ 0,85 e falsos positivos ≤ 5 % no dataset gold (60 mensagens).
- [ ] Insight pronto em ≤ 45 s (p95) a partir do `stream_end`; overhead no turno principal ≤ 5 ms (só agenda a task).
- [ ] Nenhuma entrega durante streaming ou digitação; nenhum insight vencido entregue.
- [ ] Zero vazamento entre usuários (todas as queries filtram `user_id`; testes de IDOR como na auditoria).
- [ ] Suíte verde no DB temporário; `npm run build` com 0 erros de TypeScript.

**De experiência**
- [ ] Na semana de teste com a família: nenhum relato de "spam"; ≥ 1 "Quero saber mais" por usuário ativo; ninguém desliga por incômodo.
- [ ] O usuário sempre entende **por que** o assistente pesquisou (frase de transparência + fontes).

---

## 8. Riscos específicos

| Risco | Mitigação |
|---|---|
| "A IA não para de falar" | opt-in; 3/h/conversa; 10/dia; 24 h/tópico; máx. 3 pendentes; botão "Não quero sobre isso" |
| Sensação de vigilância | nunca pessoas privadas; transparência na bolha; fontes visíveis; desligar em 1 clique; só as últimas 3 mensagens vão ao classificador |
| Custo/TPM em provedores gratuitos | modelo utilitário (mesmo waterfall da memória); cache 24 h; semáforo 2; só 2 páginas lidas; cap diário |
| Poluir o contexto do chat | `kind='proactive'` entra no histórico (necessário para "quer saber mais") mas é **excluído** da extração de memória e do Dream; poda de histórico já limita o tamanho |
| Insight velho ("o show foi ontem") | `expires_at` por categoria + checagem no instante da entrega |
| Concorrência com memória/Dream | semáforo + agendamento com prioridade baixa (depois do `extract_user_memory_background`) |
| Falha silenciosa que ninguém nota | logs admin anonimizados com contadores por etapa (`detected/researching/ready/delivered/failed`) |
