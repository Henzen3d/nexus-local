# Ponto 4 — Validação e Recuperação

**Status:** 🆕 Novo (não implementado)  
**Tempo Estimado:** 45 min  
**Risco:** Baixo (camada adicional de segurança)

---

## 📋 Resumo

Sistema de validação de resultados e recuperação de erros que verifica cada ação, detecta estados inesperados e escala para modelo mais capaz quando necessário. Operações irreversíveis exigem autorização explícita.

---

## 🔍 Problema Identificado

```
Cenário atual:
┌────────────────────────────────────────────────────────┐
│ 1. LLM gera resposta                                   │
│ 2. Resposta é persistida no DB                         │
│ 3. Usuário recebe resposta                             │
│                                                        │
│ PROBLEMA:                                              │
│ - E se a resposta estiver errada?                      │
│ - E se o modelo alucinar?                              │
│ - E se operação irreversível for executada?            │
│ - Não há verificação pós-execução                      │
└────────────────────────────────────────────────────────┘
```

---

## ✅ Solução

### 1. Validador de Resultados

```python
# backend/validation/result_validator.py (NOVO)
import re
from typing import Any, Dict, List, Optional
from dataclasses import dataclass
from enum import Enum

class ValidationLevel(Enum):
    PASS = "pass"
    WARN = "warn"
    FAIL = "fail"
    ESCALATE = "escalate"

@dataclass
class ValidationResult:
    level: ValidationLevel
    message: str
    suggestions: List[str] = None
    requires_auth: bool = False

class ResultValidator:
    """
    Valida resultados de operações antes de retornar ao usuário.
    """
    
    # Padrões de detecção de problemas
    HALLUCINATION_PATTERNS = [
        r"segundo\s+a\s+fonte\s+inexistente",
        r"eu\s+não\s+tenho\s+acesso",
        r"eu\s+não\s+posso\s+ver",
        r"não\s+tenho\s+informação\s+sobre",
    ]
    
    INCOMPLETE_PATTERNS = [
        r" ...\s*$",
        r" \.\.\.$",
        r"código incompleto",
        r"resposta truncada",
    ]
    
    def __init__(self):
        self._compiled_hallucination = [
            re.compile(p, re.IGNORECASE) for p in self.HALLUCINATION_PATTERNS
        ]
        self._compiled_incomplete = [
            re.compile(p, re.IGNORECASE) for p in self.INCOMPLETE_PATTERNS
        ]
    
    async def validate(
        self,
        result: Any,
        operation: str,
        context: Dict[str, Any]
    ) -> ValidationResult:
        """
        Valida resultado de operação.
        
        Args:
            result: Resultado da operação
            operation: Nome da operação ('chat', 'image_gen', 'code_gen', etc)
            context: Contexto da requisição
        
        Returns:
            ValidationResult com nível e sugestões
        """
        # 1. Validação básica de tipo
        if result is None:
            return ValidationResult(
                level=ValidationLevel.FAIL,
                message="Resultado nulo retornado",
                suggestions=["Retry operação", "Verificar logs"]
            )
        
        # 2. Validação para chat
        if operation == "chat":
            return await self._validate_chat(result, context)
        
        # 3. Validação para geração de imagem
        if operation == "image_gen":
            return await self._validate_image(result, context)
        
        # 4. Validação para código
        if operation == "code_gen":
            return await self._validate_code(result, context)
        
        # Default: pass
        return ValidationResult(
            level=ValidationLevel.PASS,
            message="Validação passada"
        )
    
    async def _validate_chat(self, result: str, context: Dict) -> ValidationResult:
        """Valida resposta de chat."""
        
        # Check hallucination
        for pattern in self._compiled_hallucination:
            if pattern.search(result):
                return ValidationResult(
                    level=ValidationLevel.WARN,
                    message="Possível alucinação detectada",
                    suggestions=[
                        "Reformular pergunta",
                        "Adicionar mais contexto",
                        "Usar web search"
                    ]
                )
        
        # Check incomplete
        for pattern in self._compiled_incomplete:
            if pattern.search(result):
                return ValidationResult(
                    level=ValidationLevel.WARN,
                    message="Resposta parece incompleta",
                    suggestions=["Pedir para completar"]
                )
        
        # Check length (muito curta pode ser erro)
        if len(result.strip()) < 10:
            return ValidationResult(
                level=ValidationLevel.WARN,
                message="Resposta muito curta",
                suggestions=["Verificar se modelo retornou erro"]
            )
        
        return ValidationResult(
            level=ValidationLevel.PASS,
            message="Resposta válida"
        )
    
    async def _validate_image(self, result: Dict, context: Dict) -> ValidationResult:
        """Valida geração de imagem."""
        
        if "url" not in result or not result["url"]:
            return ValidationResult(
                level=ValidationLevel.FAIL,
                message="URL da imagem não retornada",
                suggestions=["Retry geração"]
            )
        
        if "status" in result and result["status"] == "error":
            return ValidationResult(
                level=ValidationLevel.FAIL,
                message=f"Erro na geração: {result.get('error', 'unknown')}",
                suggestions=["Verificar prompt", "Try different model"]
            )
        
        return ValidationResult(
            level=ValidationLevel.PASS,
            message="Imagem gerada com sucesso"
        )
    
    async def _validate_code(self, result: str, context: Dict) -> ValidationResult:
        """Valida código gerado."""
        
        # Check syntax básica (para Python)
        if context.get("language") == "python":
            try:
                compile(result, "<string>", "exec")
                return ValidationResult(
                    level=ValidationLevel.PASS,
                    message="Sintaxe Python válida"
                )
            except SyntaxError as e:
                return ValidationResult(
                    level=ValidationLevel.FAIL,
                    message=f"Erro de sintaxe: {e}",
                    suggestions=["Corrigir código", "Reformular pedido"]
                )
        
        return ValidationResult(
            level=ValidationLevel.PASS,
            message="Código validado"
        )

# Validator singleton
validator = ResultValidator()
```

### 2. Sistema de Recuperação com Escalação

```python
# backend/recovery/escalation.py (NOVO)
import logging
from typing import Optional, Dict, Any
from dataclasses import dataclass
from enum import Enum

logger = logging.getLogger(__name__)

class EscalationLevel(Enum):
    NONE = "none"
    RETRY = "retry"
    FALLBACK_MODEL = "fallback_model"
    HUMAN_APPROVAL = "human_approval"

@dataclass
class RecoveryAction:
    level: EscalationLevel
    action: str
    details: Dict[str, Any] = None

class EscalationManager:
    """
    Gerencia recuperação de erros e escalação para modelos mais capazes.
    """
    
    # Mapeamento de erros para ações de recuperação
    ERROR_HANDLERS = {
        "rate_limit": RecoveryAction(
            level=EscalationLevel.RETRY,
            action="wait_and_retry",
            details={"delay_seconds": 5}
        ),
        "timeout": RecoveryAction(
            level=EscalationLevel.RETRY,
            action="retry_with_timeout",
            details={"timeout_seconds": 30}
        ),
        "invalid_response": RecoveryAction(
            level=EscalationLevel.FALLBACK_MODEL,
            action="fallback_to_better_model",
            details={}
        ),
        "hallucination_detected": RecoveryAction(
            level=EscalationLevel.FALLBACK_MODEL,
            action="retry_with_web_search",
            details={}
        ),
        "irreversible_operation": RecoveryAction(
            level=EscalationLevel.HUMAN_APPROVAL,
            action="request_user_confirmation",
            details={}
        ),
    }
    
    def __init__(self, db):
        self.db = db
        self._failed_models = set()
    
    async def handle_error(
        self,
        error: Exception,
        context: Dict[str, Any]
    ) -> RecoveryAction:
        """
        Decide ação de recuperação baseada no erro.
        """
        error_type = self._classify_error(error)
        
        if error_type in self.ERROR_HANDLERS:
            action = self.ERROR_HANDLERS[error_type]
            logger.warning(
                f"Erro classificado como {error_type}. "
                f"Ação: {action.action}, Nível: {action.level.value}"
            )
            return action
        
        # Default: fallback para modelo mais capaz
        return RecoveryAction(
            level=EscalationLevel.FALLBACK_MODEL,
            action="fallback_to_better_model",
            details={"original_error": str(error)}
        )
    
    def _classify_error(self, error: Exception) -> str:
        """Classifica tipo de erro."""
        error_str = str(error).lower()
        
        if "rate limit" in error_str or "429" in error_str:
            return "rate_limit"
        if "timeout" in error_str:
            return "timeout"
        if "hallucination" in error_str or "alucina" in error_str:
            return "hallucination_detected"
        if "irreversible" in error_str or "dele" in error_str:
            return "irreversible_operation"
        
        return "unknown"
    
    async def should_request_approval(
        self,
        operation: str,
        context: Dict[str, Any]
    ) -> bool:
        """
        Verifica se operação irreversível precisa de autorização do usuário.
        """
        irreversible_operations = [
            "delete_conversation",
            "delete_message",
            "reset_model_quota",
            "change_system_config",
        ]
        
        if operation in irreversible_operations:
            return True
        
        return False
```

### 3. Integração com Chat Flow

```python
# backend/routers/chat.py (modificado)
from backend.validation.result_validator import validator
from backend.recovery.escalation import EscalationManager

async def _process_turn(...):
    # ... código existente ...
    
    # ── NOVO: Valida resultado antes de persistir ───────────
    validation_result = await validator.validate(
        full_response,
        operation="chat",
        context={
            "language": req.get("language", "pt-BR"),
            "model_id": model_id,
        }
    )
    
    if validation_result.level == "fail":
        logger.error(f"Validação falhou: {validation_result.message}")
        await ws.send_json({
            "type": "validation_error",
            "message": validation_result.message,
            "suggestions": validation_result.suggestions,
        })
        # Pode retry ou escalar
    
    elif validation_result.level == "warn":
        logger.warning(f"Validação warn: {validation_result.message}")
        # Continua, mas loga
   
    # ── NOVO: Salva resultado após validação ────────────────
    assistant_msg_id = await save_assistant_message(
        db, conversation_id, full_response, model_id, provider_id,
        relay_used, relay_model_id,
    )
    
    # ... resto do código ...
```

---

## 📊 Métricas Esperadas

| Métrica | Antes | Depois | Variação |
|---------|-------|--------|----------|
| Respostas com alucinação detectada | 0% | ~5% | **+5%** (detecção) |
| Respostas inválidas entregues | ~2% | ~0.5% | **-75%** |
| Tempo adicional por request | 0ms | ~5ms | **+5ms** (aceitável) |
| User complaints (estimado) | Alta | Baixa | **-60%** |

---

## 🧪 Testes Requeridos

```python
# tests/test_result_validator.py
import pytest
from backend.validation.result_validator import ResultValidator

@pytest.mark.asyncio
async def test_hallucination_detection():
    """Deve detectar alucinação."""
    validator = ResultValidator()
    result = await validator.validate(
        "Segundo a fonte inexistente X, oBrasil é a maior economia",
        "chat",
        {}
    )
    assert result.level == "warn"
    assert "alucinação" in result.message.lower()

@pytest.mark.asyncio
async def test_incomplete_detection():
    """Deve detectar resposta incompleta."""
    validator = ResultValidator()
    result = await validator.validate(
        "O processo de aprendizagem é complexo...",
        "chat",
        {}
    )
    assert result.level == "warn"
    assert "incompleta" in result.message.lower()

@pytest.mark.asyncio
async def test_valid_response():
    """Deve passar resposta válida."""
    validator = ResultValidator()
    result = await validator.validate(
        "O Brasil é o maior país da América do Sul em área territorial.",
        "chat",
        {}
    )
    assert result.level == "pass"

@pytest.mark.asyncio
async def test_python_syntax_validation():
    """Deve validar sintaxe Python."""
    validator = ResultValidator()
    
    # Código válido
    result = await validator.validate(
        "def hello():\n    print('world')",
        "code_gen",
        {"language": "python"}
    )
    assert result.level == "pass"
    
    # Código inválido
    result = await validator.validate(
        "def hello(\n    print('world')",
        "code_gen",
        {"language": "python"}
    )
    assert result.level == "fail"
```

---

## 📝 Checklist de Implementação

- [ ] Criar `backend/validation/result_validator.py`
- [ ] Criar `backend/recovery/escalation.py`
- [ ] Modificar `chat.py` para usar validador
- [ ] Adicionar testes em `test_result_validator.py`
- [ ] Rodar `pytest tests/test_result_validator.py`
- [ ] Verificar que todos os testes passam
- [ ] Commit: `feat(validation): add result validation and recovery system`

---

*Documento criado: 2026-10-13*
*Responsável: Hermes Agent*
*Status: Pendente (novo)*
