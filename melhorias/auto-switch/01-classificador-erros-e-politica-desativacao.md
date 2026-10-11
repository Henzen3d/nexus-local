# 🏷️ 01. Classificador de Erros e Política de Desativação
**NexusLocal / Multi+** · Especificação Técnica do Mecanismo de Erros

---

## 1. Motivação e Objetivos

Para que o motor de auto-switch tome decisões acertadas sem intervenção humana, ele precisa distinguir com precisão milimétrica:
1. **O que é uma incapacidade permanente do modelo/conta** (ex: o modelo passou a ser pago, a conta não tem saldo, o endpoint foi descontinuado).
2. **O que é uma indisponibilidade temporária de infraestrutura** (ex: a máquina no provedor está reiniciando, há pico momentâneo de tráfego, ou a cota de RPM por minuto foi atingida).

Desativar um modelo permanentemente quando ele apenas sofreu um soluço momentâneo de rede é um erro grave de disponibilidade. Por outro lado, manter ativo um modelo que exige cartão de crédito ou plano pago gera frustração contínua a cada interação.

---

## 2. Taxonomia Formal de Erros

O classificador analisa tanto o **código HTTP retornado** quanto o **corpo JSON / texto da mensagem de erro** emitida pelo provedor.

```
                                      ┌────────────────────────┐
                                      │ Erro Capturado na API  │
                                      └───────────┬────────────┘
                                                  │
               ┌──────────────────────────────────┴──────────────────────────────────┐
               ▼                                                                     ▼
     [CATEGORIA A: FATAL]                                                  [CATEGORIA B: TEMPORÁRIO]
  • HTTP 402 (Payment Required)                                         • HTTP 429 (Rate Limit / Quota TPM)
  • HTTP 404 (Model Not Found)                                          • HTTP 400 ("model_unavailable")
  • "insufficient_quota" / "insufficient_balance"                       • HTTP 503 (Service Unavailable)
  • "billing_limit_reached" / "upgrade for access"                      • HTTP 502 / 504 (Bad Gateway / Timeout)
  • "requires a subscription"                                           • "overloaded" / "temporarily unavailable"
               │                                                                     │
               ▼                                                                     ▼
  [Ação: DESATIVAÇÃO PERMANENTE]                                        [Ação: COOLDOWN TEMPORÁRIO]
  • models.enabled = 0                                                  • model_quota_status.status = 'cooldown'
  • models.confirmed_free = 0                                           • cooldown_until = datetime('now', '+10m')
  • Dispara WS: 'model_auto_disabled'                                   • models.enabled PERMANECE = 1
  • Oculta do seletor de modelos                                        • Retorna automaticamente após o prazo
```

### 2.1. Categoria A: Erros Fatais (Desativação Permanente)

Um erro é classificado como **FATAL** quando não há perspectiva razoável de que uma nova requisição automática com a mesma chave vá funcionar sem uma ação administrativa prévia (como recarregar créditos ou assinar um plano).

| Código HTTP | Padrões de Texto (Case-Insensitive) | Provedores Típicos | Ação Executada |
| :--- | :--- | :--- | :--- |
| **402** | `"insufficient_quota"`, `"insufficient_balance"`, `"insufficient balance"`, `"payment required"`, `"credit balance is too low"`, `"billing_limit_reached"`, `"requires a subscription"`, `"upgrade for access"`, `"ollama.com/upgrade"` | LLM7.io, OpenRouter, SambaNova, Ollama Cloud, Hugging Face, SiliconFlow | `UPDATE models SET enabled = 0, confirmed_free = 0 WHERE id = ?`<br>Emite evento WS `model_auto_disabled`. |
| **404** | `"model not found"`, `"model_not_found"`, `"invalid model"`, `"invalid_model"`, `"function '"`, `"404 page not found"`, `"unknown model"` | Cloudflare Workers AI, Groq, DeepSeek, Together AI | `UPDATE models SET enabled = 0 WHERE id = ?`<br>Emite evento WS `model_auto_disabled`. |
| **403** | `"access_denied"`, `"unauthorized for this model"`, `"permission_denied"`, `"plan does not allow this model"` | NVIDIA NIM, OpenRouter, Cohere | `UPDATE models SET enabled = 0 WHERE id = ?` |

### 2.2. Categoria B: Erros Temporários (Cooldown Reversível)

Um erro é classificado como **TEMPORÁRIO** quando o modelo é válido e a conta possui permissão, mas o servidor está incapaz de atender no exato segundo da requisição.

| Código HTTP | Padrões de Texto (Case-Insensitive) | Provedores Típicos | Tempo Padrão de Cooldown | Ação Executada |
| :--- | :--- | :--- | :--- | :--- |
| **400** | `"model '...' is currently unavailable"`, `"model_unavailable"`, `"temporarily unavailable"`, `"service is overloaded"` | LLM7.io, FreeTheAI, LongCat, Agnes | **10 minutos** | Grava em `model_quota_status` com status `cooldown`. Não altera `models.enabled`. |
| **429** | `"rate_limit_exceeded"`, `"too many requests"`, `"tpm limit"`, `"rpm limit"`, `"quota exceeded for current window"` | Groq, Gemini, OpenRouter, Cerebras | **Header `Retry-After`** ou **5 minutos** | Atualiza `model_quota_status` com status `exhausted` e `exhausted_until`. |
| **503 / 502 / 504** | `"service unavailable"`, `"bad gateway"`, `"gateway timeout"`, `"backend connection failed"` | Todos os provedores | **5 minutos** | Grava status `cooldown`. |
| **Timeout / Network** | `httpx.ConnectTimeout`, `httpx.ReadTimeout`, `RemoteProtocolError` | Redes locais e VPNs | **3 minutos** | Grava status `cooldown`. |

---

## 3. Modelo de Dados e Banco SQLite

Para suportar o ciclo de vida de cooldown e desativação sem conflitos, a tabela `model_quota_status` e a função `check_and_deactivate_model` são ampliadas.

### 3.1. Esquema Atualizado de `model_quota_status`

```sql
CREATE TABLE IF NOT EXISTS model_quota_status (
    model_id            TEXT PRIMARY KEY REFERENCES models(id) ON DELETE CASCADE,
    status              TEXT DEFAULT 'available',     -- 'available' | 'exhausted' | 'cooldown' | 'fatal_disabled'
    exhausted_until     TEXT,                         -- ISO datetime até quando o cooldown/rate limit vigora
    consecutive_errors  INTEGER DEFAULT 0,            -- Contador de falhas consecutivas
    last_error_code     INTEGER,                      -- Ex: 402, 400, 429
    last_error_msg      TEXT,                         -- Detalhe da mensagem de erro
    last_error_at       TEXT,                         -- Timestamp ISO do último erro
    confirmed_free      INTEGER DEFAULT 0,
    registry_source     TEXT
);
```

### 3.2. Função do Cooldown Reversível no Backend

```python
async def mark_model_cooldown(
    model_id: str, 
    db: aiosqlite.Connection, 
    cooldown_seconds: int = 600, 
    error_msg: str = "",
    error_code: int = 400
) -> None:
    """
    Coloca o modelo em quarentena temporária sem desativá-lo permanentemente.
    Após expirar o cooldown_seconds, o modelo volta automaticamente a ser considerado 'available'.
    """
    exhausted_until = (
        datetime.utcnow() + timedelta(seconds=cooldown_seconds)
    ).isoformat()
    
    await db.execute("""
        INSERT INTO model_quota_status (
            model_id, status, exhausted_until, consecutive_errors, 
            last_error_code, last_error_msg, last_error_at
        ) VALUES (?, 'cooldown', ?, 1, ?, ?, datetime('now'))
        ON CONFLICT(model_id) DO UPDATE SET
            status = 'cooldown',
            exhausted_until = excluded.exhausted_until,
            consecutive_errors = model_quota_status.consecutive_errors + 1,
            last_error_code = excluded.last_error_code,
            last_error_msg = excluded.last_error_msg,
            last_error_at = excluded.last_error_at
    """, (model_id, exhausted_until, error_code, error_msg[:500]))
    await db.commit()
    logger.info(f"⏳ Modelo '{model_id}' entrou em cooldown temporário até {exhausted_until} ({error_msg[:60]})")
```

---

## 4. O Componente `ErrorClassifier`

O classificador centraliza toda a inteligência de categorização em uma única classe estática reutilizável no backend:

```python
from enum import Enum
from typing import Tuple

class ErrorSeverity(str, Enum):
    FATAL = "fatal"          # Desativação permanente (models.enabled = 0)
    TEMPORARY = "temporary"  # Cooldown temporário (status = 'cooldown')
    UNKNOWN = "unknown"      # Trata como temporário de curto prazo

class ErrorClassifier:
    FATAL_STATUS_CODES = {402, 404}
    
    FATAL_PHRASES = (
        "insufficient_quota",
        "insufficient_balance",
        "insufficient balance",
        "payment required",
        "credit balance is too low",
        "billing_limit_reached",
        "requires a subscription",
        "upgrade for access",
        "ollama.com/upgrade",
        "invalid_model",
        "invalid model",
        "model not found",
        "model_not_found",
        "function '",
        "404 page not found",
        "access_denied",
    )
    
    TEMPORARY_PHRASES = (
        "currently unavailable",
        "model_unavailable",
        "temporarily unavailable",
        "service is overloaded",
        "rate limit",
        "too many requests",
        "capacity exceeded",
        "try again later",
    )

    @classmethod
    def classify(cls, error_msg: str, status_code: int | None = None) -> Tuple[ErrorSeverity, str]:
        err_lower = error_msg.lower()
        
        # 1. Checagem por Status Code explícito
        if status_code in cls.FATAL_STATUS_CODES:
            return ErrorSeverity.FATAL, f"HTTP {status_code}: Requer pagamento ou modelo inexistente"
            
        if status_code in (429, 502, 503, 504):
            return ErrorSeverity.TEMPORARY, f"HTTP {status_code}: Instabilidade ou limite temporário"

        # 2. Busca por gatilhos fatais no texto do erro
        for phrase in cls.FATAL_PHRASES:
            if phrase in err_lower:
                return ErrorSeverity.FATAL, f"Gatilho fatal detectado: '{phrase}'"

        # 3. Busca por gatilhos temporários
        for phrase in cls.TEMPORARY_PHRASES:
            if phrase in err_lower:
                return ErrorSeverity.TEMPORARY, f"Instabilidade temporária: '{phrase}'"

        # 4. Fallback padrão seguro
        if "400" in error_msg and ("unavailable" in err_lower or "model" in err_lower):
            return ErrorSeverity.TEMPORARY, "Modelo temporariamente indisponível no provedor"

        return ErrorSeverity.TEMPORARY, "Falha de execução tratada como temporária"
```

---

## 5. Eventos WebSocket Notificados para a Interface

Quando uma decisão é tomada pelo classificador durante a execução da mensagem, o backend notifica o cliente conectado via WebSocket com eventos estruturados:

### Evento 1: Desativação Permanente de Modelo
```json
{
  "type": "model_auto_disabled",
  "model_id": "llm7/minimax-m3",
  "provider_id": "llm7",
  "display_name": "Minimax M3",
  "reason": "HTTP 402: Insufficient balance. Please top up your balance to continue."
}
```

### Evento 2: Entrada em Cooldown Temporário
```json
{
  "type": "model_cooldown",
  "model_id": "llm7/minimax-m2.7",
  "provider_id": "llm7",
  "display_name": "Minimax M2.7",
  "duration_seconds": 600,
  "reason": "Model 'minimax-m2.7' is currently unavailable."
}
```

Esses eventos permitem que a interface do usuário reaja instantaneamente, ajustando dropdowns e badges sem recarregar a tela.
