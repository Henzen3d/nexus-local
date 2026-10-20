# NexusLocal — Golden Prompt: Ancoragem Temporal, Precedência da Web e Auto-Pesquisa

**Para:** Hermes (orquestrador) + agy (executor).
**Objetivo:** Garantir que as respostas dos modelos sejam temporalmente ancoradas no presente (ano corrente), que os dados da busca web superem qualquer alucinação de corte de treinamento (*cutoff*), que a busca web seja disparada automaticamente em perguntas factuais e que a interface renderize perfeitamente todos os badges.

---

## 🚨 Regras Férreas do Projeto (AGENTS.md)
1. **Ambiente Docker no Host:** Sem PM2/systemd. A porta 8000 é do Portainer; API do backend roda internamente no container `nexus_backend`.
2. **Zero Testes no Banco Vivo:** NUNCA rodar pytest ou scripts contra `nexuslocal.db`. Testes somente em SQLite descartável temporário.
3. **Sem GitNexus:** Proibido comandos de reindexação semântica no prompt de deploy.
4. **Portão de Qualidade:** `./judge.sh` 100% verde antes de qualquer merge. TypeScript estrito e i18n rigoroso (pt-BR, en-US, es-ES).

---

## 📋 Fatos Observados & Diagnóstico Técnico

- **FATO-1 (Crítico - Temporal Grounding):** Modelos têm corte de conhecimento em 2024/2025. O `BASE_SYSTEM_PROMPT` em `backend/orchestration/build_context.py` não injeta a data atual do sistema. O modelo assume que estamos no ano do seu corte e rejeita resultados da web de 2026 como "conteúdo futuro ou simulado".
- **FATO-2 (Crítico - Precedência Epistêmica da Web):** O bloco `<dados_web>` em `formatter.py` e `chat.py` não contém diretriz forte de autoridade factual sobre o corte do modelo. O modelo precisa ser instruído de que os dados web representam a realidade presente e devem ter prevalência sobre seu treinamento prévio.
- **FATO-3 (Alto - Auto-Trigger de Busca Web):** `smart_router.py` possui `IntentKey.WEB_RESEARCH`, mas não o classifica em perguntas dinâmicas. Além disso, `web_search_config.heuristic_enabled` fica em 0 por padrão, e `heuristics.py` tem lacunas (ex.: cobre "quem é", mas não "quem são", "quais são", "como está").
- **FATO-4 (Médio - I18n Failover Badge):** Chave `chat.failover` ausente em `pt-BR.json`, `en-US.json` e `es-ES.json`, exibindo a string crua `chat.failover` ao lado da bolha de mensagem.

---

## 🛠️ Backlog de Execução (Um branch por item)

### Q1 — Ancoragem Temporal no System Prompt (`melhoria/grounding-Q1-data-sistema`)
- **O que fazer:**
  1. Em `backend/orchestration/build_context.py`, introduzir injeção dinâmica de data, dia da semana, mês e ano corrente no início do `BASE_SYSTEM_PROMPT_TEMPLATE`:
     ```text
     CONTEXTO TEMPORAL:
     - Data atual do sistema: {current_date_str} (Ano: {current_year}).
     - Quaisquer menções a "hoje", "este ano", "atualmente" ou "recente" referem-se estritamente ao ano de {current_year}.
     ```
  2. Adicionar instrução anti-alucinação de corte:
     ```text
     - Seu conhecimento pré-treinado possui uma data de corte no passado. Eventos, fatos e datas referentes a {current_year} pertencem à realidade presente e NÃO devem ser considerados "conteúdo futuro", "simulado" ou "hipotético".
     ```
  3. Propagar a data atual em `resolve_project_context` e no montador de turnos em `backend/routers/chat.py`.
- **Verificação:** Teste unitário em `test_system_prompt_temporal.py` garantindo que o ano corrente é injetado e reconhecido.

### Q2 — Precedência Epistêmica dos Dados da Web (`melhoria/grounding-Q2-precedencia-web`)
- **O que fazer:**
  1. Em `backend/web_search/formatter.py` e na instrução de web search em `backend/routers/chat.py`:
     - Instruir explicitamente o modelo que os fatos contidos em `<dados_web>` têm autoridade máxima sobre a memória interna do modelo.
     - Mandar o modelo extrair ativamente fatos que constam em títulos, subtítulos e trechos extraídos pelo Deep Reader.
     - Proibir categoricamente que o modelo afirme que os fatos da web são "simulações de teste de sites de notícias".
- **Verificação:** Teste de síntese com fixture real das eleições de 2026 (notícias TSE/G1 com Lula e Flávio Bolsonaro), validando que a resposta do LLM extrai e cita ambos os candidatos sem taxar a notícia de simulação.

### Q3 — Auto-Ativação Inteligente de Busca Web (`melhoria/grounding-Q3-auto-busca`)
- **O que fazer:**
  1. No Smart Router (`backend/ranking/smart_router.py`):
     - Mapear a intenção `IntentKey.WEB_RESEARCH` para disparar sinais automáticos quando houver perguntas factuais dependentes de tempo ("quem é o atual", "quem são os candidatos este ano", "cotação hoje", "últimas notícias", "resultado do jogo").
  2. Em `backend/web_search/heuristics.py`:
     - Expandir padrões regex para incluir plurais (`"quem são"`, `"quais são"`, `"como estão"`, `"resultado das"`, `"eleições deste ano"`).
  3. No banco de dados (`backend/database.py`):
     - Migração incremental garantindo que `heuristic_enabled` passe para 1 por padrão para novos bancos e migre com segurança bancos existentes.
- **Verificação:** Testes de intenção em `test_smart_router_web_search.py` validando que perguntas factuais de atualidade ativam a pesquisa automaticamente.

### Q4 — Correção I18n do Badge de Failover (`melhoria/grounding-Q4-i18n-failover`)
- **O que fazer:**
  1. Adicionar `"failover": "Failover"` em `pt-BR.json`, `en-US.json` e `es-ES.json` sob a chave `"chat"`.
  2. Ajustar [MessageBubble.tsx](file:///j:/Arquivos%20Osmar/Multi+/frontend/src/components/MessageBubble.tsx) para incluir fallback seguro `{t('chat.failover', 'Failover')}`.
  3. Rodar `npm run check:i18n` para validar paridade dos 8 idiomas.
- **Verificação:** Teste visual e probe de renderização sem renderizar chaves literais sem tradução.

---

## 🚦 Critérios de Aceite e Validação Final

1. `npx tsc --noEmit` com 0 erros de tipagem.
2. `npm run build` do frontend sem falhas.
3. Testes do backend pytest 100% verdes em banco isolado temporário.
4. Simulação com o caso de teste original: pergunta "Quem são os candidatos do segundo turno este ano?" respondida com base nas notícias reais da web, sem descartá-las como fictícias e sem erros de badge.
