# 📋 05. Roadmap Operacional e Checklist de Subtarefas
**Multi+ / NexusLocal** · Planejamento Arquitetural

Este arquivo serve como o **checklist operacional definitivo** para a futura implementação prática do **Auto-Roteador Inteligente**. Todas as tarefas estão estruturadas de forma atômica e sequencial.

---

## 📌 Fase 1: Fundação do Classificador Local (< 2ms)
*Objetivo:* Construir o motor analítico determinístico com blindagem contra amnésia e context blindness.

- [x] **1.1**: Criar o arquivo `backend/ranking/smart_router.py` com as definições de `IntentKey`, `ComplexityTier` e `IntentClassificationResult`.
- [x] **1.2**: Implementar e pré-compilar as expressões regulares de extração de sinais (`_RE_CODE_SYNTAX`, `_RE_DEEP_THOUGHT`, `_RE_TRIVIAL_SHORT`).
- [x] **1.3**: Criar a função pura `classify_intent(prompt: str, attachments: list, web_search: bool, history: list, previous_intent: str = None) -> IntentClassificationResult`.
- [x] **1.4**: Implementar detecção de multimodalidade retrospectiva (avalia anexos do turno atual E imagens anteriores no histórico ativo).
- [x] **1.5**: Implementar algoritmo de **Histerese de Tópico (Topic Momentum)**: perguntas curtas (< 35 chars) em threads de código/raciocínio retêm a intenção técnica em vez de rebaixar para `TRIVIAL_QUICK`.
- [x] **1.6**: Criar suíte de testes unitários em `backend/tests/test_smart_router.py` cobrindo prompts isolados, histerese de tópicos e detecção retrospectiva.
- [x] **1.7**: Adicionar teste de benchmark garantindo tempo de execução inferior a 2 milissegundos por classificação.

---

## 📌 Fase 2: Matriz de Políticas e Seleção com Blindagem de 2ª Escala
*Objetivo:* Conectar o classificador ao ranking, cotas ativas, afinidade de cache e rotação de carga.

- [x] **2.1**: Adicionar colunas de auditoria na tabela `model_usage_log` em `backend/database.py` (`was_auto_routed`, `route_intent`, `route_confidence`, `route_latency_ms`, `route_policy`).
- [x] **2.2**: Criar tabela ou chave de configuração `router_policy` no banco (valores: `economical_free`, `balanced_smart`, `max_performance`).
- [x] **2.3**: Integrar consulta de sanidade: descartar modelos com `enabled == 0` (desativados pelo Auto-Switch) ou status `'exhausted'` / `'cooldown'`.
- [x] **2.4**: Implementar **Context Window Guard**: descartar modelos onde `context_length < estimated_history_tokens + 2048` para evitar erro HTTP 400.
- [x] **2.5**: Implementar **Afinidade de Modelo (Sticky Routing)**: manter o modelo do turno anterior se ele atender à intenção atual com score próximo, preservando o KV-Cache do provedor.
- [x] **2.6**: Implementar **Weighted Slot Rotation** em tarefas `TRIVIAL_QUICK` gratuitas (Groq, Cerebras, Cloudflare) para mitigar efeito Thundering Herd e rate limits (429).
- [x] **2.7**: Integrar a ordenação por `nexuslocal_score` calculada em `backend/ranking/scorer.py` para desempate entre modelos elegíveis.
- [x] **2.8**: Conectar o modelo selecionado ao motor resiliente em `backend/orchestration/resolve_request.py` e à cascata em 3 Tiers do Auto-Switch (`backend/ranking/failover.py`).

---

## 📌 Fase 3: Integração no Fluxo de Chat (WebSocket / Streaming)
*Objetivo:* Habilitar a resolução de rota no ciclo de vida de cada mensagem em tempo real.

- [x] **3.1**: Modificar `backend/routers/chat.py` para interceptar quando `requested_model_id == "auto"` ou `None`.
- [x] **3.2**: Injetar preset de parâmetros adaptativos (`temperature`, `max_tokens`) ajustado para o tipo de tarefa (`0.1-0.2` para código, `0.6` para raciocínio, `0.7` para criativo).
- [x] **3.3**: Emitir evento WebSocket `auto_route_decision` contendo modelo escolhido, intenção, rótulo em português, confiança e latência antes dos primeiros tokens.
- [x] **3.4**: Garantir preservação de contexto quando a conversa envolver projetos com RAG ou memórias ativas injetadas.
- [x] **3.5**: Testar cenário de falha imediata na largada (402, 400 ou 429), validando se o motor de Auto-Switch executa o failover silencioso (*Ghost Switch*) sem quebra do WebSocket.

---

## 📌 Fase 4: Interface do Usuário (UI/UX) e Transparência
*Objetivo:* Disponibilizar o modo Auto com clareza radical e facilidade de controle no frontend.

- [x] **4.1**: Atualizar `ModelSelector.tsx` adicionando a opção nobre `🎯 Auto (Roteamento Inteligente)` fixada no topo do seletor.
- [x] **4.2**: Atualizar `useStore.ts` para suportar `selectedModelId = 'auto'` e persistir no `localStorage`.
- [x] **4.3**: Criar o componente `AutoRouteBadge.tsx` para ser exibido ao lado do avatar/nome da IA em `MessageBubble.tsx`.
- [x] **4.4**: Implementar tooltip detalhado no hover do badge explicando a intenção detectada, a confiança e o motivo da escolha.
- [x] **4.5**: Adicionar chaves de tradução no i18n (`pt-BR`, `en-US`, `es-ES`) para todas as intenções e rótulos do roteador.
- [x] **4.6**: Criar aba ou seção "Roteamento Inteligente" no painel de configurações para alternar as políticas (`Econômica`, `Equilibrada`, `Performance`).

---

## 📌 Fase 5: Métricas, Dashboard e Homologação Final
*Objetivo:* Visualizar o valor entregue e auditar a precisão das rotas executadas.

- [x] **5.1**: Criar endpoint analítico `GET /api/dashboard/auto-router/stats` em `backend/routers/dashboard.py`.
- [x] **5.2**: Adicionar card de visualização de "Distribuição de Tarefas por Intenção" no componente `UsageDashboard.tsx`.
- [x] **5.3**: Exibir indicador de estimativa de tokens preservados e throughput médio atingido.
- [x] **5.4**: Realizar bateria de testes manuais com usuários reais (turnos com perguntas simples, código complexo e análise de imagens).
- [x] **5.5**: Validar que a compilação do TypeScript (`npm run build`) e os testes backend (`pytest`) continuam com 100% de sucesso.

---

## 📌 Fase 6: Calibração 2026 (Perfil de Modelos + Seleção por Fit)
*Objetivo:* Corrigir a seleção "sempre o mesmo modelo" com o catálogo gratuito atual e garantir troca de modelo por mensagem. Detalhes em [06-diagnostico-e-calibracao-2026.md](06-diagnostico-e-calibracao-2026.md).

- [x] **6.1**: Criar `backend/ranking/model_profile.py` (porte, raciocínio, especialidade, visão, velocidade, qualidade-base) — função pura e cacheada.
- [x] **6.2**: Substituir o pool por família + "60 para todos" pela pontuação de adequação (`score_candidate`/`rank_candidates`) por intenção × complexidade × política.
- [x] **6.3**: Sticky Routing condicionado à adequação (tolerâncias 2,5 / 4 / 8 pts) e sinal `model_switch`.
- [x] **6.4**: Estimador léxico de complexidade, perguntas analíticas sem palavras-chave → raciocínio, palavras-chave em inglês.
- [x] **6.5**: Esforço de raciocínio adaptativo no modo Auto (LIGHT → low, HEAVY → high; sem parâmetro em modelos sem dial).
- [x] **6.6**: Endpoint `POST /api/dashboard/auto-router/preview` + seção "Testar o roteador" no painel (i18n pt-BR/en-US/es-ES).
- [x] **6.7**: Testes com banco temporário e catálogo realista (`test_smart_router_calibration.py`); suíte anterior verde; `npm run build` sem erros.

