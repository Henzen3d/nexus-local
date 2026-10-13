# Ponto 3 — Executor Determinístico

**Status:** 🆕 Novo (não implementado)  
**Tempo Estimado:** 1h  
**Risco:** Baixo (camada adicional, não substitui LLM)

---

## 📋 Resumo

Criar uma camada de execução determinística que roda **ANTES** do LLM para operações previsíveis, evitando chamadas custosas quando o resultado pode ser calculado via código convencional.

---

## 🔍 Problema Identificado

```
Exemplo 1: Geração de imagem
┌────────────────────────────────────────────────────────┐
│ Usuário: "/imagem um logo simples"                     │
│                                                        │
│ ANTES:                                                 │
│ 1. LLM classifica (35ms)                               │
│ 2. LLM gera prompt (2-5s) ← DESNECESSÁRIO!            │
│ 3. FLUX gera imagem (3-8s)                             │
│                                                        │
│ DEPOIS:                                                │
│ 1. Executor determinístico detecta "logo simples"      │
│ 2. Gera SVG básico via código (5ms) ← SEM LLM!        │
│ 3. Só chama FLUX se executor falhar                    │
└────────────────────────────────────────────────────────┘

Exemplo 2: Validação de parâmetros
┌────────────────────────────────────────────────────────┐
│ Usuário: "Qual modelo usar para código?"               │
│                                                        │
│ ANTES:                                                 │
│ 1. LLM processa tudo (100-500ms)                      │
│                                                        │
│ DEPOIS:                                                │
│ 1. Regex detecta padrão "qual modelo usar para X"     │
│ 2. Lookup em tabela fixa (0.1ms)                       │
│ 3. Retorna resposta imediata                            │
└────────────────────────────────────────────────────────┘
```

---

## ✅ Solução

### 1. Camada de Executor Determinístico

```python
# backend/executor/deterministic.py (NOVO)
import re
from typing import Optional, Dict, Any
from dataclasses import dataclass

@dataclass
class DeterministicResult:
    """Resultado de execução determinística."""
    success: bool
    result: Any
    method: str  # "regex", "lookup", "calc", "code"
    latency_ms: float

class DeterministicExecutor:
    """
    Executa operações previsíveis sem LLM.
    
    Ordem de prioridade:
    1. Regex patterns (mais rápido)
    2. Lookup tables (médio)
    3. Cálculos matemáticos (rápido)
    4. Geração de código/template (variável)
    """
    
    def __init__(self):
        self._compiled_patterns = self._compile_patterns()
        self._lookup_tables = self._load_lookup_tables()
    
    def _compile_patterns(self) -> Dict[str, re.Pattern]:
        """Pre-compile regex patterns para performance."""
        return {
            "image_simple": re.compile(
                r"/(?:imagem|img|image)\s+(um?\s+)?(?:logo|ícone|icone|símbolo|symbol)",
                re.IGNORECASE
            ),
            "model_lookup": re.compile(
                r"qual\s+(melhor|bom)\s+modelo\s+para\s+(\w+)",
                re.IGNORECASE
            ),
            "math_calc": re.compile(
                r"(?:calc|calcular|quanto é|quanto seria)\s+([0-9\s+\-*/().]+)",
                re.IGNORECASE
            ),
        }
    
    def _load_lookup_tables(self) -> Dict[str, Dict[str, str]]:
        """Carrega tabelas de lookup para respostas fixas."""
        return {
            "model_recommendation": {
                "código": "qwen-2.5-coder-32b",
                "python": "qwen-2.5-coder-32b",
                "javascript": "qwen-2.5-coder-32b",
                "raciocínio": "deepseek-r1",
                "matemática": "deepseek-r1",
                "criativo": "llama-3.3-70b",
                "texto": "gemini-2.0-flash",
            },
            "image_templates": {
                "logo": "<svg>...</svg>",
                "icone": "<svg>...</svg>",
            }
        }
    
    async def execute(self, prompt: str, context: Dict[str, Any]) -> Optional[DeterministicResult]:
        """
        Tenta executar de forma determinística.
        
        Returns:
            DeterministicResult se sucesso, None se precisar de LLM.
        """
        import time
        start = time.perf_counter()
        
        # 1. Tenta regex patterns
        for name, pattern in self._compiled_patterns.items():
            match = pattern.search(prompt)
            if match:
                result = await self._handle_regex(name, match, context)
                if result:
                    return DeterministicResult(
                        success=True,
                        result=result,
                        method="regex",
                        latency_ms=(time.perf_counter() - start) * 1000
                    )
        
        # 2. Tenta lookup tables
        lookup_result = await self._handle_lookup(prompt, context)
        if lookup_result:
            return DeterministicResult(
                success=True,
                result=lookup_result,
                method="lookup",
                latency_ms=(time.perf_counter() - start) * 1000
            )
        
        # 3. Tenta cálculos
        calc_result = await self._handle_calculation(prompt)
        if calc_result:
            return DeterministicResult(
                success=True,
                result=calc_result,
                method="calc",
                latency_ms=(time.perf_counter() - start) * 1000
            )
        
        # Nenhum pattern bateu, retorna None para LLM
        return None
    
    async def _handle_regex(self, name: str, match: re.Match, context: Dict) -> Optional[Any]:
        """Lida com matches de regex."""
        if name == "image_simple":
            # Gera SVG básico para logos/ícones
            return self._generate_simple_svg(context.get("theme", "default"))
        
        if name == "model_lookup":
            # Retorna modelo recomendado da lookup table
            category = match.group(2).lower()
            return self._lookup_tables["model_recommendation"].get(category)
        
        return None
    
    async def _handle_lookup(self, prompt: str, context: Dict) -> Optional[Any]:
        """Lida com lookup em tabelas."""
        # Ex: busca por nome de modelo
        lower_prompt = prompt.lower()
        
        for model_name, model_id in self._lookup_tables["model_recommendation"].items():
            if model_name in lower_prompt:
                return model_id
        
        return None
    
    async def _handle_calculation(self, prompt: str) -> Optional[float]:
        """Lida com cálculos matemáticos simples."""
        match = self._compiled_patterns["math_calc"].search(prompt)
        if match:
            try:
                expression = match.group(1)
                # Usa eval seguro (apenas operadores matemáticos)
                allowed = set("0123456789+-*/.() ")
                if all(c in allowed for c in expression):
                    return eval(expression)  # Seguro pois validamos chars
            except Exception:
                pass
        return None
    
    def _generate_simple_svg(self, theme: str = "default") -> str:
        """Gera SVG básico para logos/ícones."""
        svgs = {
            "logo": '''<svg width="100" height="100" viewBox="0 0 100 100">
                <circle cx="50" cy="50" r="45" fill="#4F46E5"/>
                <text x="50" y="60" text-anchor="middle" fill="white" font-size="24">NL</text>
            </svg>''',
            "icone": '''<svg width="24" height="24" viewBox="0 0 24 24">
                <path d="M12 2L2 7l10 5 10-5-10-5zM2 17l10 5 10-5M2 12l10 5 10-5" 
                      stroke="currentColor" fill="none" stroke-width="2"/>
            </svg>'''
        }
        return svgs.get(theme, svgs["logo"])
```

### 2. Integração com Smart Router

```python
# backend/ranking/smart_router.py (modificado)
from backend.executor.deterministic import DeterministicExecutor

# Instância global (singleton)
_executor = DeterministicExecutor()

def classify_intent(prompt, ...):
    # ── NOVO: Tenta executor determinístico primeiro ───────
    exec_result = await _executor.execute(prompt, {
        "context": context,
        "user_id": user_id,
    })
    
    if exec_result:
        logger.info(f"Deterministic exec: {exec_result.method} in {exec_result.latency_ms:.1f}ms")
        return IntentClassificationResult(
            intent=IntentKey.TRIVIAL_QUICK,  # Ou outro baseado no resultado
            complexity=ComplexityTier.LIGHT,
            confidence=1.0,
            matched_signals=[f"deterministic_{exec_result.method}"],
            reason_label_pt="Execução Determinística",
            suggested_family=exec_result.result if isinstance(exec_result.result, str) else "qwen-2.5-coder-32b",
            processing_time_ms=exec_result.latency_ms,
            is_deterministic=True,  # Flag para downstream
            deterministic_result=exec_result.result,
        )
    
    # ── Fallback: lógica original ──────────────────────────
    # ... regex, queries SQL, etc.
```

---

## 📊 Métricas Esperadas

| Tipo de Operação | Antes (LLM) | Depois (Determinístico) | Economia |
|------------------|-------------|------------------------|----------|
| Logo/ícone simples | 3000-5000ms | 5ms | **99.8%** |
| Lookup de modelo | 100-500ms | 0.1ms | **99.9%** |
| Cálculo matemático | 100-500ms | 0.5ms | **99.5%** |
| Operação complexa | 100-500ms | 100-500ms | 0% (fallback LLM) |

---

## 🧪 Testes Requeridos

```python
# tests/test_deterministic_executor.py
import pytest
from backend.executor.deterministic import DeterministicExecutor

@pytest.mark.asyncio
async def test_image_simple_logo():
    """Deve gerar SVG para pedido de logo simples."""
    executor = DeterministicExecutor()
    result = await executor.execute("/imagem um logo simples", {})
    
    assert result is not None
    assert result.success
    assert result.method == "regex"
    assert result.latency_ms < 10
    assert "<svg>" in result.result

@pytest.mark.asyncio
async def test_model_lookup():
    """Deve retornar modelo recomendado via lookup."""
    executor = DeterministicExecutor()
    result = await executor.execute("qual melhor modelo para python", {})
    
    assert result is not None
    assert result.success
    assert result.method == "regex"
    assert result.result == "qwen-2.5-coder-32b"

@pytest.mark.asyncio
async def test_math_calculation():
    """Deve calcular expressão matemática."""
    executor = DeterministicExecutor()
    result = await executor.execute("quanto é 2+2", {})
    
    assert result is not None
    assert result.success
    assert result.method == "calc"
    assert result.result == 4

@pytest.mark.asyncio
async def test_complex_request_fallback():
    """Requests complexos devem retornar None (fallback LLM)."""
    executor = DeterministicExecutor()
    result = await executor.execute("escreva um artigo sobre inteligencia artificial", {})
    
    assert result is None  # Deve fallback para LLM
```

---

## 📝 Checklist de Implementação

- [ ] Criar `backend/executor/deterministic.py`
- [ ] Implementar `DeterministicExecutor` class
- [ ] Adicionar patterns de regex para casos comuns
- [ ] Integrar com `smart_router.py`
- [ ] Adicionar testes em `test_deterministic_executor.py`
- [ ] Rodar `pytest tests/test_deterministic_executor.py`
- [ ] Verificar que todos os testes passam
- [ ] Commit: `feat(executor): add deterministic execution layer`

---

## ⚠️ Riscos e Mitigações

| Risco | Probabilidade | Impacto | Mitigação |
|-------|---------------|---------|-----------|
| Falso positivo (pattern muito amplo) | Média | Baixo | Lista pequena e específica de patterns |
| Segurança (eval de expressão) | Baixa | Alto | Validação rigorosa de chars permitidos |
| Manutenção (patterns desatualizados) | Média | Baixo | Documentação clara, revisão trimestral |
| Performance (compilação de regex) | Nula | N/A | Patterns pré-compilados em __init__ |

---

*Documento criado: 2026-10-13*
*Responsável: Hermes Agent*
*Status: Pendente (novo)*
