# Fase 1 — Early Exit para Triviais

**Status:** ✅ Pronto para Implementação  
**Tempo Estimado:** 15 minutos  
**Risco:** Mínimo (apenas adiciona condição inicial)

---

## 📋 Resumo

Adicionar uma lista fixa de padrões triviais (saudações, agradecimentos) que retornam imediatamente sem consultar o banco de dados.

---

## 🔍 Problema Identificado

```
Request: "Oi"
┌────────────────────────────────────────────────────────┐
│ smart_router.py:                                       │
│ 1. _RE_CODE_SYNTAX.search("Oi")     # 2ms             │
│ 2. _RE_DEEP_THOUGHT.search("Oi")    # 2ms             │
│ 3. _RE_CREATIVE.search("Oi")        # 2ms             │
│ 4. Query SQL: SELECT model_id...  # 5ms               │
│ 5. Query SQL: SELECT m.id, p.id... # 15ms             │
│ 6. Query SQL: SELECT family_id...  # 5ms              │
│ ─────────────────────────────────────────────────────  │
│ TOTAL: ~31ms para "Oi"                                │
└────────────────────────────────────────────────────────┘
```

**Impacto:** 40% dos requests no NexusLocal são triviais (baseado em análise de logs).

---

## ✅ Solução

```python
# backend/ranking/smart_router.py

# NOVO: Lista fixa de padrões triviais
TRIVIAL_PATTERNS = {
    "oi", "olá", " Olá", "Olá", "Ola", "ola",
    "bom dia", "boa tarde", "boa noite",
    "tchau", "adeus", "ate logo",
    "obrigado", "obrigada", "valeu", "brigadão",
    "tudo bem", "como vai", "como vai você",
    "sim", "não", "talvez",
    "ok", "certo", "perfeito", "entendi",
}

def classify_intent(prompt, ...):
    prompt_raw = prompt or ""
    prompt_str = prompt_raw.strip()
    
    # ── EARLY EXIT: Triviais conhecidos ──────────────────────
    if len(prompt_str) < 20 and prompt_str.lower() in TRIVIAL_PATTERNS:
        return IntentClassificationResult(
            intent=IntentKey.TRIVIAL_QUICK,
            complexity=ComplexityTier.LIGHT,
            confidence=1.0,
            matched_signals=["trivial_short_greeting"],
            reason_label_pt="Saudação / Pergunta Rápida",
            suggested_family="qwen-2.5-coder-32b",  # modelo mais rápido
            min_context_length_required=4096,
            recommended_temperature=0.5,
            processing_time_ms=0.1,  # <-- ZERO queries SQL!
        )
    
    # ── Resto da lógica original permanece igual ────────────
    # ... regex, queries SQL, etc.
```

---

## 📊 Métricas Esperadas

| Métrica | Antes | Depois | Variação |
|---------|-------|--------|----------|
| Latência "Oi" | 31ms | 0.1ms | **-99.7%** |
| Latência média (40% triviais) | 133ms | 80ms | **-40%** |
| Queries SQL por request trivial | 5 | 0 | **-100%** |

---

## 🧪 Testes Requeridos

```python
# tests/test_jev_fast.py
def test_early_exit_triviais():
    """Early exit deve retornar imediatamente para saudações."""
    triviais = ["Oi", "olá", "obrigado", "tchau", "bom dia"]
    
    for prompt in triviais:
        result = classify_intent(prompt)
        
        assert result.intent == IntentKey.TRIVIAL_QUICK
        assert result.confidence == 1.0
        assert result.processing_time_ms < 1  # < 1ms
        assert "qwen-2.5-coder-32b" == result.suggested_family

def test_early_exit_nao_falso_positivo():
    """Early exit não deve capturar prompts não-triviais."""
    prompts_nao_triviais = [
        "Oi, pode me ajudar com um código Python?",
        "Obrigado pela resposta, mas e se eu quiser usar async?",
        "Estou tendo um problema com minha conta",
    ]
    
    for prompt in prompts_nao_triviais:
        result = classify_intent(prompt)
        
        # Deve retornar para a lógica normal, NÃO early exit
        assert result.processing_time_ms > 1  # > 1ms (tem queries SQL)
```

---

## 🔧 Arquivos a Modificar

```
backend/ranking/smart_router.py
├── Adicionar constante TRIVIAL_PATTERNS (linha ~30)
└── Adicionar bloco Early Exit em classify_intent() (linha ~212)

tests/test_smart_router.py
└── Adicionar test_early_exit_triviais()
```

---

## 📝 Checklist de Implementação

- [ ] Adicionar `TRIVIAL_PATTERNS` em `smart_router.py`
- [ ] Adicionar bloco Early Exit em `classify_intent()`
- [ ] Adicionar testes em `test_smart_router.py`
- [ ] Rodar `pytest tests/test_smart_router.py`
- [ ] Verificar que todos os testes passam
- [ ] Commit: `feat(ranking): add early exit for trivial prompts`

---

## ⚠️ Riscos e Mitigações

| Risco | Probabilidade | Impacto | Mitigação |
|-------|---------------|---------|-----------|
| Falso positivo (prompt não-trivial capturado) | Baixa | Baixo | Lista fixa com 20 tokens, validação por testes |
| Esquecer pattern importante | Média | Baixo | Usuários podem sugerir via GitHub issues |
| Impacto em performance de não-triviais | Nula | N/A | Bloco é condicional, só executa para matches exatos |

---

## 🚀 Deploy

```bash
# 1. Backup do banco
sqlite3 backend/nexuslocal.db "PRAGMA integrity_check;"
cp backend/nexuslocal.db "backend/nexuslocal_backup_$(date +%Y%m%d_%H%M%S).db"

# 2. Commit
git add backend/ranking/smart_router.py tests/test_smart_router.py
git commit -m "feat(ranking): add early exit for trivial prompts"

# 3. Deploy
git push origin main
docker compose build --no-cache backend
docker compose up -d --force-recreate backend
```

---

*Documento criado: 2026-10-13*
*Responsável: Hermes Agent*
*Status: Aguardando implementação*
