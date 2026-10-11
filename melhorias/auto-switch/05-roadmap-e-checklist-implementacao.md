# 📋 05. Roadmap de Implementação e Checklist de Tarefas
**NexusLocal / Multi+** · Plano de Execução em 4 Ondas (Waves)

---

## 1. Visão Geral das Ondas de Entrega

O plano de implementação é dividido em 4 fases sequenciais e complementares, projetadas para manter o sistema funcional e testável a cada incremento.

```
┌─────────────────────────┐     ┌─────────────────────────┐
│         WAVE 1          │ ──> │         WAVE 2          │
│ Classificador de Erros  │     │ Cascata Tier-0          │
│ & Cooldown Temporário   │     │ & Loop de Streaming     │
└─────────────────────────┘     └─────────────────────────┘
             │                               │
             ▼                               ▼
┌─────────────────────────┐     ┌─────────────────────────┐
│         WAVE 3          │ ──> │         WAVE 4          │
│ Auto-Switch UI/UX       │     │ Diagnóstico em 1 Clique │
│ & Badge de Transição    │     │ & Testes Automatizados  │
└─────────────────────────┘     └─────────────────────────┘
```

---

## 2. Checklist Detalhado por Fase

### 🌊 Wave 1: Classificador de Erros e Política de Cooldown
*Objetivo: Ensinar o backend a diferenciar falhas permanentes de saldo de indisponibilidades temporárias de nós computacionais.*

- [ ] **1.1. Criar o módulo `backend/orchestration/error_classifier.py`:**
  - Implementar o enum `ErrorSeverity` (`FATAL`, `TEMPORARY`, `UNKNOWN`).
  - Mapear códigos de status HTTP (402, 404 vs 400, 429, 503).
  - Incluir strings textuais: `"insufficient_quota"`, `"insufficient_balance"`, `"model_unavailable"`, `"currently unavailable"`.
- [ ] **1.2. Aprimorar `check_and_deactivate_model` em `backend/database.py`:**
  - Garantir que erros 402 e `insufficient_balance` desativem o modelo com `UPDATE models SET enabled = 0, confirmed_free = 0 WHERE id = ?`.
  - Adicionar log explícito de desativação com motivo estruturado.
- [ ] **1.3. Implementar `mark_model_cooldown` em `backend/ranking/quota_tracker.py` ou `database.py`:**
  - Gravar `status = 'cooldown'` e `exhausted_until = datetime('now', '+10 minutes')`.
  - Garantir que após os 10 minutos o modelo volte automaticamente a ser considerado disponível sem intervenção manual.
- [ ] **1.4. Testes Unitários de Classificação de Erro:**
  - Criar `backend/tests/test_error_classifier.py` cobrindo cenários reais:
    - LLM7.io Minimax M3 (HTTP 402) ➔ `FATAL`.
    - LLM7.io Minimax 2.7 (HTTP 400 `model_unavailable`) ➔ `TEMPORARY`.
    - Groq Rate Limit (HTTP 429) ➔ `TEMPORARY`.
    - Cloudflare function not found (HTTP 404) ➔ `FATAL`.

---

### 🌊 Wave 2: Cascata Tier-0 (Mesmo Provedor) e Loop Resiliente
*Objetivo: Fazer o chat pular de modelo sozinho dentro do mesmo provedor sem quebrar a requisição do WebSocket.*

- [ ] **2.1. Implementar o Tier 0 em `backend/ranking/failover.py`:**
  - Criar a função interna `_get_next_model_same_provider(requested_model_id, db, exclude_model_ids)`.
  - Ordenar modelos alternativos do mesmo provedor por ranking de qualidade ou tamanho de contexto.
  - Atualizar `resolve_model_with_failover` para consultar Tier 0 antes do Tier 1 e Tier 2.
- [ ] **2.2. Refatorar o loop de streaming em `backend/orchestration/resolve_request.py`:**
  - Modificar o bloco `while attempt < _MAX_FAILOVER_ATTEMPTS`:
    - Não abortar em `except Exception`.
    - Chamar o `ErrorClassifier`.
    - Se fatal: desativa e notifica.
    - Se temporário: entra em cooldown e notifica.
    - Se tokens parciais foram emitidos antes da queda: enviar evento `stream_rollback` e zerar buffer.
    - Continuar o loop na mesma requisição para instanciar o próximo modelo.
- [ ] **2.3. Eventos WebSocket Estruturados:**
  - Emitir `failover_notice` enriquecido com `original_model`, `fallback_model`, `fallback_model_id`, `provider_id` e `reason`.
  - Emitir `model_auto_disabled` quando um modelo for desligado do banco.
- [ ] **2.4. Teste de Integração de Transbordo Contínuo:**
  - Criar `backend/tests/test_auto_switch_stream.py` simulando uma sequência de falhas:
    - Modelo A retorna 402 ➔ Modelo B retorna 400 ➔ Modelo C retorna 200 OK.
    - Validar que a resposta final do Modelo C é entregue no mesmo stream sem erros na saída.

---

### 🌊 Wave 3: Interface do Usuário (UI/UX) e Auto-Alinhamento
*Objetivo: Apresentar a resposta com elegância, eliminar telas vermelhas e alinhar o seletor ativo automaticamente.*

- [ ] **3.1. Tratar eventos no hook `frontend/src/hooks/useChat.ts`:**
  - Adicionar tratamento para `case 'failover_notice':`:
    - Atualizar `s.setCurrentModelId(msg.fallback_model_id)`.
    - Associar metadados de failover à mensagem corrente.
  - Adicionar tratamento para `case 'model_auto_disabled':`:
    - Remover ou marcar como inativo o modelo na lista local do Zustand sem dar F5 na página.
- [ ] **3.2. Criar o componente `FailoverBadge.tsx` em `frontend/src/components/`:**
  - Renderizar pílula discreta no topo da mensagem: `🔄 Alternado de X ➔ Y`.
  - Adicionar popover/tooltip explicativo ao clicar ou passar o mouse.
- [ ] **3.3. Badges de Saúde no Seletor de Modelos:**
  - Indicar visualmente modelos em cooldown temporário (🟡) com tempo restante.
  - Ocultar modelos desativados por padrão no dropdown diário do chat.
- [ ] **3.4. Testes de Interface e Acessibilidade:**
  - Validar contraste das cores nos temas Dark Mode e Light Mode.
  - Testar auto-atualização do seletor no campo de envio do composer.

---

### 🌊 Wave 4: Diagnóstico de Saúde em 1 Clique e Auditoria
*Objetivo: Permitir que o usuário teste todos os modelos de um provedor em 3 segundos antes de usar o chat.*

- [ ] **4.1. Criar o endpoint `POST /api/admin/providers/{provider_id}/health-check`:**
  - Teste paralelo concorrente (max 5 requisições simultâneas).
  - Chamadas ultra-leves de 1 token com prompt `"ping"`.
  - Auto-desativação automática dos modelos com 402 ou 404.
  - Cooldown automático para modelos com 400.
- [ ] **4.2. Adicionar o botão "🔍 Diagnosticar Saúde" em `AdminPanel.tsx`:**
  - Botão de 1 clique no cabeçalho do card de cada provedor.
  - Estado de loading com spinner durante a varredura.
- [ ] **4.3. Criar o Modal de Relatório de Diagnóstico:**
  - Lista de modelos verdes (saudáveis com latência em ms), amarelos (cooldown) e vermelhos (desativados).
  - Botão de reativação manual rápida para casos onde o usuário adicionou créditos na conta.
- [ ] **4.4. Validação Geral e Documentação de Entrega:**
  - Atualizar `README.md` e `DOCUMENTATION.md` com o novo motor de resiliência.

---

## 3. Critérios Formais de Aceitação (UAT)

Para considerar o épico concluído, o seguinte cenário de teste deve passar com 100% de sucesso:

### Cenário de Teste UAT (Reprodução do caso LLM7.io):
1. **Configuração:** O provedor `LLM7.io` possui 3 modelos cadastrados:
   - `llm7/minimax-m3` (simulado ou real com retorno 402).
   - `llm7/minimax-m2.7` (simulado ou real com retorno 400 `model_unavailable`).
   - `llm7/gpt-oss-20b` (saudável, retorno 200).
2. **Ação do Usuário:** O usuário seleciona `LLM7.io` e `Minimax M3` no seletor de modelos e digita `"oi"`.
3. **Comportamento Esperado:**
   - **Zero cliques adicionais:** O usuário NÃO precisa trocar de modelo nem redigitar o prompt.
   - **Zero cards vermelhos:** Nenhum bloco de `chat.generationError` é exibido.
   - **Resposta completa:** O assistente responde: *"Bom dia, Osmar!"* (vindo do GPT Oss:20b).
   - **Pílula de transição visível:** Mensagem exibe `🔄 Alternado de Minimax M3 ➔ GPT Oss:20b`.
   - **Banco atualizado:** `Minimax M3` está com `enabled = 0`. `Minimax 2.7` está com `status = 'cooldown'` (10 min).
   - **Seletor alinhado:** O seletor ativo da conversa mudou automaticamente para `GPT Oss:20b`. A próxima mensagem já vai direto para ele.
