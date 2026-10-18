# Mapeamento do Sistema de Failover, Quotas e Classificação de Erros
**Data:** 18 de Outubro de 2026  
**Contexto:** NexusLocal / Multi+  
**Branch:** `melhoria/failover-cascata-quotas`

---

## 1. Visão Geral da Arquitetura Atual

O fluxo de resiliência e roteamento de requisições LLM no NexusLocal é composto por 4 componentes principais:

```
[WebSocket resolve_and_stream] 
       │
       ▼
[resolve_model_with_failover] ───► Tier 1 (Famílias: _get_family_for_model)
       │                         └──► Tier 2 (Ranking Geral: _get_next_best_ranked_model)
       ▼
[Provider Execution (stream_chat)]
       │
       ├──► 0 Tokens gerados (Silent Failure) ──► Retry loop no resolve_request.py
       │
       ├──► HTTP Error (404, 402, 429, etc.)
       │        ├──► check_and_deactivate_model (database.py)
       │        └──► mark_model_exhausted (quota.py)
```

---

## 2. Diagnóstico dos Pontos Críticos Mapeados

### 2.1 `backend/database.py:3711` — `check_and_deactivate_model`
- **Comportamento Atual:**  
  A função verifica uma lista estática de substrings (`deactivate_triggers`), incluindo `"model not found"`, `"not found"`, `"not_found"`, `"404 page not found"`, `"requires a subscription"`, `"billing limit"`, etc.
  Quando qualquer trigger dá match, a função executa:
  ```python
  await db.execute("UPDATE models SET enabled = 0, confirmed_free = 0 WHERE id = ?", (model_id,))
  logger.error("🚫 Model '%s' automatically disabled due to billing/subscription error: %s", model_id, error_msg)
  ```
- **Problema Identificado (F1):**  
  Quando o Gemini ou outro provedor retorna HTTP 404 (`"This model models/gemini-2.5-pro is no longer available to new users. Please update your code to use models/gemini-3.1-pro-preview"`), o modelo é desativado com a mensagem equivocada de `billing/subscription error`.
  Além disso, não há distinção entre modelo aposentado (`model_deprecated` / `model_not_found`) e erro financeiro/quota, e a sugestão dada pela API (`models/gemini-3.1-pro-preview`) é descartada sem extração nem logging estruturado.

### 2.2 `backend/providers/base.py:704` — Tratamento de Erros nos Providers
- **Comportamento Atual:**  
  Em `GeminiProvider.stream_chat`:
  - Se `response.status_code == 429`, lança `RateLimitError(retry_after=...)`.
  - Se `response.status_code != 200`, lança `RuntimeError(f"[Gemini Native] API error {response.status_code}: {body.decode()}")`.
  - Não classifica HTTP 404 com `"no longer available"` especificamente.
  Em `OpenAICompatProvider`:
  - Erros HTTP da API OpenAI-compat lançam exceptions com o payload bruto retornado pelo servidor.

### 2.3 `backend/orchestration/resolve_request.py:345, 486` — Orquestração e Silent Failure (0 Tokens)
- **Comportamento Atual:**  
  - Linha 345: Se `full_response.strip()` for vazio após a iteração do stream:
    ```python
    logger.warning("Modelo '%s' (provedor '%s') não gerou nenhum token de resposta. Acionando failover cascade...", current_model_id, current_provider_id)
    attempted_model_ids.add(current_model_id)
    continue
    ```
- **Problemas Identificados (F2):**  
  1. **Cross-provider loop:** O `attempted_model_ids` só guarda o `current_model_id` exato (ex.: `openrouter/nvidia/nemotron-3-ultra-550b-a55b:free`). Se existir o mesmo modelo em outro provider (ex.: `nvidia/nvidia/nemotron-3-ultra-550b-a55b`), a próxima tentativa na cascata pode selecioná-lo e falhar de novo silenciosamente.
  2. **Ausência de Cooldown:** Como 0 tokens não chama `mark_model_exhausted` nem aplica cooldown no banco, 20 segundos depois a próxima requisição de um usuário seleciona o mesmo modelo que acabou de falhar.

### 2.4 `backend/ranking/failover.py:291-354` — Falha no Tier 1 (Match de Famílias)
- **Comportamento Atual:**  
  - Linha 297: `_get_family_for_model(requested_model_id, db)` busca diretamente em `model_family_members WHERE model_id = ?`.
- **Problema Identificado (F2):**  
  Modelos com IDs com prefixos de provedores duplicados ou compostos (ex.: `nvidia/nvidia/...`, `openrouter/nvidia/...`) ou com sufixos `:free` não batem com as entradas cadastradas nas tabelas de famílias (`model_family_members`).
  Resultado: Cai sempre direto no log `"Modelo '...' não pertence a nenhuma família. Indo direto para Tier 2 (ranking geral)..."`, invalidando o Tier 1.

### 2.5 `backend/ranking/quota.py:33, 142` — HTTP 402 e Gestão de Quotas
- **Comportamento Atual:**  
  - `mark_model_exhausted(model_id, db, retry_after, error_msg)` grava `status='exhausted'` com `estimated_reset_at = now + timedelta(hours=1)` caso `retry_after` não seja fornecido.
  - Mas em `resolve_request.py` (linha 413-485), o erro HTTP 402 com `"Usage limit reached"` (como o retornado pelo LongCat) é tratado genericamente como exception comum (`next_failover_reason = "error"`), sem invocar o cooldown de quota longa.
- **Problema Identificado (F3):**  
  O modelo com 402 não recebe status de `exhausted` nem cooldown de pelo menos 1 hora, reaparecendo como candidato no Tier 2 nas requisições seguintes.

---

## 3. Plano de Implementação por Etapa

| Etapa | Foco | Ações Principais |
|---|---|---|
| **F1** | 404 Deprecated vs Billing | 1. Classificar 404 com `"no longer available"`, `"deprecated"` etc. como `model_deprecated` / `model_not_found`.<br>2. Extrair substituto via regex (ex.: `models/gemini-3.1-pro-preview`) e logar.<br>3. Criar teste unitário específico. |
| **F2** | 0 Tokens, Cooldown & Tier 1 | 1. Implementar `canonical_model_id` (strip prefixos/sufixos).<br>2. Bloquear canonical ID cross-provider no failover em caso de 0 tokens.<br>3. Registrar cooldown para modelo com 0 tokens.<br>4. Ajustar Tier 1 (`failover.py`) para utilizar canonical matching.<br>5. Criar testes unitários cobrindo os 3 cenários. |
| **F3** | HTTP 402 Quota LongCat | 1. Detectar 402 / `"Usage limit reached"` e acionar cooldown de quota (mínimo 1h) via `mark_model_exhausted`.<br>2. Criar teste unitário específico. |
