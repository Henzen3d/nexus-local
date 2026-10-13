# Plano 21: Pré-Filtro de Scripts Unicode e Densidade Estrutural em Microssegundos
**Conceito inspirado no módulo `laya.lang.analyse` do Laya**

**Status:** 📋 Proposta de Plano  
**Prioridade:** Média (P2)  
**Tempo Estimado:** 35 min  
**Risco:** Muito Baixo  

---

## 📋 1. Resumo e Motivação

No framework **Laya** (*NandhaKishorM/laya*), o subsistema `Router` executa uma análise preliminar em Python puro chamada `laya.lang.analyse` que custa **menos de 0.05ms** antes de qualquer chamada a encoders ou regexes pesadas. Essa análise avalia duas variáveis cruciais:
1. **Perfil de Scripts Unicode**: Mede faixas de caracteres de forma determinística para evitar modelos que colapsam em idiomas não-latinos.
2. **Short-circuiting Estrutural**: Descarta avaliações redundantes se a assinatura do texto já denunciar sua natureza em microssegundos.

No **NexusLocal**, o classificador de intenções atualmente submete todas as mensagens a uma esteira sequencial de regexes (`_RE_CODE_BLOCKS`, `_RE_CODE_SYNTAX`, `_RE_CODE_KEYWORDS`, `_RE_DEEP_THOUGHT`, `_RE_CREATIVE`). 
Em mensagens grandes ou não-latinas, rodar múltiplas regexes de dezenas de termos pode consumir de 2ms a 6ms de CPU sem necessidade.

---

## 🔍 2. Problema Atual no NexusLocal

```
Cenário Atual:
┌────────────────────────────────────────────────────────┐
│ Usuário envia: JSON puro de 4.000 caracteres           │
│ ou texto em Japonês/Cirílico                           │
└──────────────────────────┬─────────────────────────────┘
                           │
                           ▼
┌────────────────────────────────────────────────────────┐
│ Percorre 5 regexes extensas com dezenas de alternativas │
│ ➔ Varredura repetida de string na memória               │
│ ➔ Nenhuma garantia de suporte multilíngue do modelo    │
│ ➔ Latência: 2ms a 5ms                                   │
└────────────────────────────────────────────────────────┘
```

---

## ✅ 3. Solução Proposta: Pré-Filtro em Microssegundos (Zero Model)

Adicionar uma função de profiling preliminar em Python puro (`fast_text_profile`) executada antes das expressões regulares.

### Componentes da Análise:

#### A. Detector de Densidade Sintática / Payload Estrutural (< 0.01ms):
Textos de código, JSON, YAML e dumps de banco possuem alta densidade de pontuação técnica:
```python
_SYNTAX_CHARS = set("{}[];()=><|&%$#@~`\"'\\/:+\t")
```
Se a densidade dessa pontuação for superior a **12%** do texto e o texto tiver mais de 80 caracteres:
* O sistema identifica imediatamente como payload de código ou estruturado (`structural_syntax_density`).
* **Short-circuit**: Pula a execução de regexes lexicais secundárias e classifica como `CODE_ENGINEERING` em **< 0.02ms**.

#### B. Detector de Scripts Não-Latinos por Faixas Unicode (< 0.01ms):
Examina os primeiros 500 caracteres contra intervalos Unicode:
* `0x0400 - 0x04FF`: Cirílico
* `0x0600 - 0x06FF`: Árabe / Persa
* `0x4E00 - 0x9FFF`: CJK (Chinês / Japonês / Coreano)
* `0x0900 - 0x097F`: Devanagari (Hindi)

Se mais de **15%** dos caracteres pertencerem a scripts não-latinos:
* Adiciona o sinal `"non_latin_script"`.
* O `select_best_model` filtra modelos conhecidos por baixa competência em scripts não-latinos (como alguns checkpoints Llama 8B antigos) e direciona para modelos com treinamento multilíngue maciço (`gemini-2.0-flash` ou `qwen-2.5-coder`).

### Onde Aplicar:
* **`backend/ranking/smart_router.py`**:
  No início de `classify_intent()`, antes das regexes do Estágio 2.

```python
def fast_text_profile(text: str) -> dict:
    """Perfilamento em Python puro em < 0.02ms inspirado no Laya."""
    if not text:
        return {"syntax_density": 0.0, "is_non_latin": False}
    
    sample = text[:1000]
    total = len(sample)
    if total == 0:
        return {"syntax_density": 0.0, "is_non_latin": False}
    
    syntax_count = sum(1 for ch in sample if ch in _SYNTAX_CHARS)
    non_latin_count = sum(1 for ch in sample if ord(ch) > 0x024F and ord(ch) not in (0x2018, 0x2019, 0x201C, 0x201D))
    
    return {
        "syntax_density": syntax_count / total,
        "is_non_latin": (non_latin_count / total) > 0.15,
    }
```

---

## ⚡ 4. Ganhos Esperados

* **Short-Circuit em Payloads de Código**: JSONs, logs e scripts não passam por regexes textuais, decidindo em **0.02ms**.
* **Blindagem Multilíngue**: Zero alucinações e zero respostas truncadas quando usuários conversam em scripts asiáticos ou do leste europeu.
* **Custo Computacional Zero**: Apenas operações de contagem de inteiros em CPython, sem alocação pesada de memória.
