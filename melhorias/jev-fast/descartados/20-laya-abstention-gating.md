# Plano 20: Abstention Gating & Confiança Calibrada no Smart Router
**Conceito inspirado no mecanismo de abstenção do Laya (`min_confidence`)**

**Status:** 📋 Proposta de Plano  
**Prioridade:** Alta (P1)  
**Tempo Estimado:** 40 min  
**Risco:** Muito Baixo  

---

## 📋 1. Resumo e Motivação

No framework **Laya** (*NandhaKishorM/laya*), um dos pilares de confiabilidade é o **Abstention Gating** controlado pelo parâmetro `min_confidence` (default `0.75`). Quando o modelo avalia uma intenção ou decisão mas a probabilidade da classe vencedora é fraca ou difusa, o sistema não "chuta" uma escolha forçada; ele ativa o estado de abstenção (`abstention: true`) e recai com segurança sobre o modelo equilibrado padrão (*safe fallback*).

No **NexusLocal**, o classificador de intenções (`backend/ranking/smart_router.py`) possui categorias especializadas extremas:
1. **Raciocínio Profundo (`DEEP_REASONING`)**: Modelos de raciocínio tipo `deepseek-r1` ou `gemini-2.0-flash-thinking` (latência alta de 3 a 8 segundos pensando).
2. **Engenharia de Código (`CODE_ENGINEERING`)**: Modelos focados em sintaxe como `qwen-2.5-coder-32b`.
3. **Trivial Rápido (`TRIVIAL_QUICK`)**: Modelos pequenos de 3B a 8B.

Quando um usuário faz uma pergunta ambígua ou conceitual sem sinais nítidos (ex: *"Qual a diferença entre ética e moral?"* ou *"Como a água ferve?"*), um classificador heurístico pode disparar um gatilho fraco de dedução lógica e escolher um modelo pesado de raciocínio desnecessariamente, atrasando a resposta em vários segundos.

---

## 🔍 2. Problema Atual no NexusLocal

```
Cenário Atual com Prompts Ambíguos:
┌────────────────────────────────────────────────────────┐
│ Usuário pergunta: "Qual a melhor estratégia para mim?" │
└──────────────────────────┬─────────────────────────────┘
                           │
                           ▼
┌────────────────────────────────────────────────────────┐
│ Smart Router detecta palavra "estratégia"              │
│ ➔ Confiança baixa (~0.60), mas força DEEP_REASONING     │
│ ➔ Aciona modelo de 600B com thinking tokens            │
│ ➔ Resultado: Usuário espera 8 segundos sem necessidade │
└────────────────────────────────────────────────────────┘
```

---

## ✅ 3. Solução Proposta: Abstention Gating

Introduzir um limiar calibrado de abstenção (`ABSTENTION_THRESHOLD = 0.72`) na decisão final do `classify_intent` e `select_best_model`.

### Lógica do Gating:
1. O classificador extrai os sinais lexicais e calcula a confiança `confidence` (0.0 a 1.0).
2. **Gatilho de Abstenção**:
   - Se `intent in (IntentKey.DEEP_REASONING, IntentKey.CODE_ENGINEERING)` E `confidence < ABSTENTION_THRESHOLD`:
     - O sistema registra o sinal: `"abstention_gated_fallback"`.
     - Sobrescreve a intenção para `IntentKey.GENERAL_CHAT`.
     - Ajusta a família sugerida para o cluster mais versátil e rápido da política ativa (ex: `llama-3.3-70b` ou `gemini-2.0-flash`).
     - Define a temperatura padrão segura (`0.5`).
3. O payload enviado via WebSocket (`auto_route_decision`) informa transparência com o campo `"abstention_fired": true`, permitindo ao frontend auditar que o roteamento optou pela estabilidade.

### Onde Aplicar:
* **`backend/ranking/smart_router.py`**:
  No final de `classify_intent()` antes de retornar `IntentClassificationResult`, e na validação de pool em `select_best_model()`.

```python
ABSTENTION_CONFIDENCE_THRESHOLD = 0.72

# Se os sinais forem fracos para categorias extremas, aplica abstenção segura
if intent in (IntentKey.DEEP_REASONING, IntentKey.CODE_ENGINEERING) and confidence < ABSTENTION_CONFIDENCE_THRESHOLD:
    signals.append("abstention_gated_general")
    intent = IntentKey.GENERAL_CHAT
    label = "Conversação Geral (Abstenção Segura)"
    family = "llama-3.3-70b"
    temp = 0.5
    complexity = ComplexityTier.MEDIUM
```

---

## ⚡ 4. Ganhos Esperados

* **Eliminação de Falsos-Positivos de Thinking**: Redução de até **70% nas chamadas acidentais a modelos "Thinking/R1"** em perguntas conceituais simples, economizando 4 a 7 segundos de tempo de resposta.
* **Prevenção de Falsos-Positivos Trivial**: Impede que perguntas conceituais sejam roteadas para modelos 3B incapazes de argumentação refinada.
* **Consistência de UX**: O usuário sempre recebe respostas ágeis e equilibradas quando o comando não for expressamente técnico.

---

## 🛡️ 5. Casos de Borda e Segurança

* **Comandos Explícitos**: Se o usuário usar termos mandatórios como *"pense passo a passo"*, *"prove matematicamente"* ou blocos de código com markdown (```` ``` ````), o score de confiança sobe para `>= 0.90`, ignorando o gate de abstenção e garantindo a rota profunda quando realmente solicitada.
