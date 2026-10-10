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
| **`ECONOMICAL_FREE`**<br>*(Economia Máxima)* | Prioridade absoluta para modelos gratuitos (`is_free = 1`) e provedores sem custo por token. | Tarefas triviais e gerais vão para Groq 8B / SambaNova. Código vai para Qwen Coder Free ou Llama 70B Free. Modelos pagos só são acionados se não houver alternativa gratuita ativa. |
| **`BALANCED_SMART`**<br>*(Padrão Recomendado)* | O melhor dos dois mundos: velocidade extrema no que é simples, profundidade no que é complexo. | Saudações e resumos curtos usam Groq 8B instantâneo. Código complexo e raciocínio vão diretamente para modelos de 70B ou DeepSeek-R1. |
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

## 4. Algoritmo de Seleção e Desempate

Quando o classificador aponta uma intenção (ex: `CODE_ENGINEERING`):
1. **Filtro de Cota:** Descarta qualquer modelo cujo `status == 'exhausted'` na tabela `model_quota_status`.
2. **Filtro de Política:** Se `policy == 'ECONOMICAL_FREE'`, prioriza os modelos onde `is_free == 1`.
3. **Ordenação por Score:** Ordena os modelos elegíveis pelo `nexuslocal_score` decrescente (calculado por [`backend/ranking/scorer.py`](file:///j:/Arquivos%20Osmar/Multi+/backend/ranking/scorer.py)).
4. **Fallback Universal:** Se nenhum modelo específico da intenção estiver disponível ou cadastrado, seleciona o modelo global número 1 do ranking geral que esteja `available`.

---

## 5. Evento de WebSocket e Transparência em Tempo Real

Ao iniciar a resposta com o Auto-Roteador ativado, o backend despacha imediatamente um frame de metadados para o cliente:

```json
{
  "type": "auto_route_decision",
  "chosen_model_id": "groq/llama-3.3-70b-versatile",
  "chosen_model_name": "Llama 3.3 70B",
  "provider_id": "groq",
  "intent": "code_engineering",
  "reason_pt": "Identificado bloco de código e depuração",
  "confidence": 0.94,
  "policy": "balanced_smart",
  "decision_latency_ms": 1.4
}
```

Se o modelo escolhido sofrer um *Rate Limit* (HTTP 429) no meio da transmissão ou na abertura, a cascata de failover já existente entra em ação e emite o evento `failover_notice` logo em seguida, sem interrupção do chat.
