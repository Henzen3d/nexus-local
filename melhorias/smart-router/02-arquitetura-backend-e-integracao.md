# 🧭 02. Arquitetura de Backend e Integração com Failover
**Multi+ / NexusLocal** · Planejamento Arquitetural

---

## 1. Visão Geral da Arquitetura de Backend

O **Smart Intent Router** será integrado de forma não invasiva como uma camada pré-processadora dentro de [`backend/ranking/`](file:///j:/Arquivos%20Osmar/Multi+/backend/ranking/), reaproveitando 100% da inteligência já existente:

```
                            chat.py (WebSocket / Streaming)
                                           │
                                           ▼
                    ¿ Modelo solicitado é "auto" ou None ?
                                     ├── NÃO ──► resolve_request normal
                                     │
                                    SIM
                                     │
                                     ▼
                   backend/ranking/smart_router.py
                   ├── 1. classify_intent(prompt, attachments, web_search)
                   │      └── Retorna IntentClassificationResult (< 2ms)
                   │
                   ├── 2. select_best_model(intent_result, policy, db)
                   │      ├── Filtra por categoria e cota disponível
                   │      └── Pede desempate ao NexusLocal Score (scorer.py)
                   │
                   └── 3. Envia evento ws: 'auto_route_decision'
                                     │
                                     ▼
                   backend/ranking/failover.py (Rede de Segurança)
                   └── resolve_model_with_failover(model_id_escolhido)
```

---

## 2. As 3 Políticas de Roteamento Configuráveis (`RoutingPolicy`)

O usuário poderá escolher no painel de configurações a estratégia de equilíbrio entre economia de cota e força bruta:

| Política | Filosofia de Seleção | Comportamento Prático |
| :--- | :--- | :--- |
| **`ECONOMICAL_FREE`**<br>*(Economia Máxima)* | Prioridade absoluta para modelos gratuitos (`is_free = 1`) e provedores sem custo por token. | Tarefas triviais e gerais vão para Groq 8B / Cerebras 8B / Cloudflare. Código vai para Qwen Coder Free ou Llama 70B Free. Modelos pagos só são acionados se não houver alternativa gratuita ativa. |
| **`BALANCED_SMART`**<br>*(Padrão Recomendado)* | O melhor dos dois mundos: velocidade extrema no que é simples, profundidade no que é complexo. | Saudações e resumos curtos usam Groq 8B ou Cerebras instantâneo. Código complexo e raciocínio vão diretamente para modelos de 70B ou DeepSeek-R1. |
| **`MAX_PERFORMANCE`**<br>*(Qualidade Sem Limites)* | Busca o maior `quality_score` absoluto do ranking para a tarefa detectada, independentemente de custo ou velocidade. | Todo código vai para o melhor modelo de programação registrado (ex: Claude 3.5 Sonnet ou Qwen 2.5 Coder 32B); toda reflexão vai para DeepSeek-R1 ou Gemini Thinking. |

---

## 3. Matriz de Mapeamento: Intenção ➔ Famílias Candidatas

O roteador consultará a tabela `model_families` e `models` para selecionar o candidato ideal:

```python
# Mapeamento canônico sugerido de famílias por intenção
INTENT_FAMILY_MAPPING = {
    IntentKey.TRIVIAL_QUICK: [
        "llama-3.1-8b",
        "llama-3.2-3b",
        "gemma-2-9b"
    ],
    IntentKey.CODE_ENGINEERING: [
        "qwen-2.5-coder-32b",
        "deepseek-coder",
        "llama-3.3-70b",
        "claude-3.5-sonnet"
    ],
    IntentKey.DEEP_REASONING: [
        "deepseek-r1",
        "gemini-2.0-flash-thinking",
        "qwq-32b"
    ],
    IntentKey.CREATIVE_LONGFORM: [
        "llama-3.3-70b",
        "gemini-2.5-flash",
        "mistral-large"
    ],
    IntentKey.MULTIMODAL_VISION: [
        "gemini-2.0-flash",
        "llama-3.2-11b-vision"
    ],
    IntentKey.WEB_RESEARCH: [
        "gemini-2.0-flash",
        "llama-3.3-70b"
    ]
}
```

---

## 4. Algoritmo de Seleção Avançado (Blindado contra Falhas de 2ª Escala)

Quando o classificador aponta uma intenção e complexidade, a seleção executa os seguintes passos:

1. **Filtro de Sanidade e Cooldown (Integração com Auto-Switch):**
   * Descarta modelos com `enabled == 0` (desativados por erro 402/404 fatal).
   * Descarta modelos com status `'exhausted'` ou `'cooldown'` ativo na tabela `model_quota_status`.
2. **Filtro Rígido de Janela de Contexto (Context Window Guard):**
   * Descarta modelos onde `m.context_length < (estimated_history_tokens + 2048)`.
   * Impede erros fatais de *“context length exceeded (400)”* em conversas longas.
3. **Filtro de Multimodalidade Retrospectiva:**
   * Se a conversa possui imagens anexadas no histórico ou na mensagem atual, descarta modelos puramente textuais sem suporte de visão ou relay.
4. **Incentivo de Afinidade de Modelo (Sticky Routing / KV Cache Protector):**
   * Se o modelo usado no **turno anterior** suportar a intenção atual e tiver score aceitável (delta <= 15% do melhor candidato):
   * **Mantém o mesmo modelo e provedor!** Evita a destruição contínua do KV Cache do provedor e reduz a latência de primeiro token (TTFT).
5. **Filtro de Política:**
   * Se `policy == 'ECONOMICAL_FREE'`, restringe a busca aos modelos com `is_free == 1`. Se nenhum estiver ativo, transborda para o modelo pago mais barato.
6. **Balanceamento Anti-Thundering Herd (Weighted Slot Rotation):**
   * Para a classe `TRIVIAL_QUICK` ou `GENERAL_CHAT` (que concentra 75% dos turnos), caso haja 2 ou mais modelos gratuitos com pontuação próxima, aplica uma rotação circular (Groq ➔ Cerebras ➔ Cloudflare) para não esgotar o limite de RPM/TPM de um único provedor gratuito.
7. **Ordenação por NexusLocal Score:**
   * Ordena os modelos remanescentes pelo `nexuslocal_score` decrescente ([`backend/ranking/scorer.py`](file:///j:/Arquivos%20Osmar/Multi+/backend/ranking/scorer.py)).
8. **Preset de Parâmetros Adaptativos:**
   * Injeta a temperatura adequada para a tarefa (`0.1 - 0.2` para código, `0.6` para raciocínio, `0.7` para escrita) no payload da chamada.

---

## 5. Evento de WebSocket e Simbiose com a Cascata do Auto-Switch

Ao iniciar a resposta com o Auto-Roteador ativado, o backend despacha o frame de metadados para o cliente:

```json
{
  "type": "auto_route_decision",
  "chosen_model_id": "groq/llama-3.3-70b-versatile",
  "chosen_model_name": "Llama 3.3 70B",
  "provider_id": "groq",
  "intent": "code_engineering",
  "reason_pt": "Código & Programação (Continuidade)",
  "confidence": 0.94,
  "policy": "balanced_smart",
  "temperature": 0.2,
  "decision_latency_ms": 1.4
}
```

### O que acontece se o modelo escolhido falhar? (Transbordo Silencioso)
O Smart Router atua como o **Seletor de Ingress (Ponto de Partida)**. Caso a chamada HTTP ao modelo escolhido falhe com 402, 400 ou 429:
1. O motor de **Auto-Switch** ([`melhorias/auto-switch/`](file:///j:/Arquivos%20Osmar/Multi+/melhorias/auto-switch/)) entra em ação sem derrubar o WebSocket.
2. Aciona imediatamente a nova cascata:
   * **Tier 0:** Outro modelo disponível do mesmo provedor.
   * **Tier 1:** Outro provedor da mesma família de modelos.
   * **Tier 2:** Próximo melhor modelo do ranking geral.
3. Se o modelo falhou antes do primeiro token, o frontend atualiza suavemente o badge para o novo modelo (*Ghost Switch*), sem gerar mensagens de erro na tela.
