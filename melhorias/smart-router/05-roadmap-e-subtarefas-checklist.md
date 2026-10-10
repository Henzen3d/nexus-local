# 📋 05. Roadmap Operacional e Checklist de Subtarefas
**Multi+ / NexusLocal** · Planejamento Arquitetural

Este arquivo serve como o **checklist operacional definitivo** para a futura implementação prática do **Auto-Roteador Inteligente**. Todas as tarefas estão estruturadas de forma atômica e sequencial.

---

## 📌 Fase 1: Fundação do Classificador Local (< 2ms)
*Objetivo:* Construir o motor analítico determinístico sem dependências de rede externa.

- [ ] **1.1**: Criar o arquivo `backend/ranking/smart_router.py` com as definições de `IntentKey`, `ComplexityTier` e `IntentClassificationResult`.
- [ ] **1.2**: Implementar e pré-compilar as expressões regulares de extração de sinais (`_RE_CODE_SYNTAX`, `_RE_DEEP_THOUGHT`, `_RE_TRIVIAL_SHORT`).
- [ ] **1.3**: Criar a função pura `classify_intent(prompt: str, attachments: list, web_search: bool, history_turns: int) -> IntentClassificationResult`.
- [ ] **1.4**: Implementar detecção automática de multimodalidade baseada na presença de anexos (imagem/PDF).
- [ ] **1.5**: Criar suíte de testes unitários em `backend/tests/test_smart_router.py` cobrindo 20 prompts típicos (código, lógica, saudações, traduções).
- [ ] **1.6**: Adicionar teste de benchmark garantindo tempo de execução inferior a 2 milissegundos por classificação.

---

## 📌 Fase 2: Matriz de Políticas e Integração com Banco de Dados
*Objetivo:* Conectar o classificador ao ranking de modelos e ao estado de cotas em tempo real.

- [ ] **2.1**: Adicionar colunas de auditoria na tabela `model_usage_log` em `backend/database.py` (`was_auto_routed`, `route_intent`, `route_confidence`, `route_latency_ms`, `route_policy`).
- [ ] **2.2**: Criar tabela ou chave de configuração `router_policy` no banco (valores: `economical_free`, `balanced_smart`, `max_performance`).
- [ ] **2.3**: Implementar a função `select_best_model(intent_res, policy, db)` em `backend/ranking/smart_router.py`.
- [ ] **2.4**: Integrar a consulta de disponibilidade ativa com a tabela `model_quota_status` (descartar modelos com status `exhausted`).
- [ ] **2.5**: Integrar a ordenação por `nexuslocal_score` calculada em `backend/ranking/scorer.py` para desempate entre modelos elegíveis.
- [ ] **2.6**: Conectar o modelo selecionado à cascata de failover em `backend/ranking/failover.py` para garantir que falhas subsequentes acionem o fallback automático.

---

## 📌 Fase 3: Integração no Fluxo de Chat (WebSocket / Streaming)
*Objetivo:* Habilitar a resolução de rota no ciclo de vida de cada mensagem em tempo real.

- [ ] **3.1**: Modificar `backend/routers/chat.py` para interceptar quando `requested_model_id == "auto"` ou `None`.
- [ ] **3.2**: Emitir evento WebSocket `auto_route_decision` contendo modelo escolhido, intenção, rótulo em português, confiança e latência antes de iniciar os chunks de texto.
- [ ] **3.3**: Garantir preservação de contexto quando a conversa envolver projetos com RAG ou memórias ativas injetadas.
- [ ] **3.4**: Criar testes de integração verificando se o chat responde normalmente com o modo `auto` ativo.
- [ ] **3.5**: Testar cenário de failover imediato caso o modelo escolhido pelo roteador retorne HTTP 429 durante a inicialização.

---

## 📌 Fase 4: Interface do Usuário (UI/UX) e Transparência
*Objetivo:* Disponibilizar o modo Auto com clareza radical e facilidade de controle no frontend.

- [ ] **4.1**: Atualizar `ModelSelector.tsx` adicionando a opção nobre `🎯 Auto (Roteamento Inteligente)` fixada no topo do seletor.
- [ ] **4.2**: Atualizar `useStore.ts` para suportar `selectedModelId = 'auto'` e persistir no `localStorage`.
- [ ] **4.3**: Criar o componente `AutoRouteBadge.tsx` para ser exibido ao lado do avatar/nome da IA em `MessageBubble.tsx`.
- [ ] **4.4**: Implementar tooltip detalhado no hover do badge explicando a intenção detectada, a confiança e o motivo da escolha.
- [ ] **4.5**: Adicionar chaves de tradução no i18n (`pt-BR`, `en-US`, `es-ES`) para todas as intenções e rótulos do roteador.
- [ ] **4.6**: Criar aba ou seção "Roteamento Inteligente" no painel de configurações para alternar as políticas (`Econômica`, `Equilibrada`, `Performance`).

---

## 📌 Fase 5: Métricas, Dashboard e Homologação Final
*Objetivo:* Visualizar o valor entregue e auditar a precisão das rotas executadas.

- [ ] **5.1**: Criar endpoint analítico `GET /api/dashboard/auto-router/stats` em `backend/routers/dashboard.py`.
- [ ] **5.2**: Adicionar card de visualização de "Distribuição de Tarefas por Intenção" no componente `UsageDashboard.tsx`.
- [ ] **5.3**: Exibir indicador de estimativa de tokens preservados e throughput médio atingido.
- [ ] **5.4**: Realizar bateria de testes manuais com usuários reais (turnos com perguntas simples, código complexo e análise de imagens).
- [ ] **5.5**: Validar que a compilação do TypeScript (`npm run build`) e os testes backend (`pytest`) continuam com 100% de sucesso.
