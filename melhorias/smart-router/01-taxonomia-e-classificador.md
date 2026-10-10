# 🧭 01. Taxonomia de Intenções e Motor de Classificação
**Multi+ / NexusLocal** · Planejamento Arquitetural

---

## 1. Taxonomia Canônica de Intenções

Para permitir uma distribuição cirúrgica de carga entre os modelos conectados ao NexusLocal, o sistema definirá **6 categorias primárias de intenção** e **3 níveis de complexidade**:

```
                       ┌────────────────────────────────────────┐
                       │        CLASSES DE INTENÇÃO (INTENT)    │
                       └───────────────────┬────────────────────┘
        ┌───────────────┬──────────────────┼─────────────────┬───────────────┐
        ▼               ▼                  ▼                 ▼               ▼
 ⚡ TRIVIAL      💻 CODE           🧠 REASONING      ✍️ CREATIVE    👁️ MULTIMODAL  🌐 WEB_RESEARCH
   (Rápido)      (Programação)      (Raciocínio)      (Redação)      (Visão/Anexo)   (Pesquisa)
```

| Categoria (`IntentKey`) | Descrição e Exemplos Típicos | Perfil Ideal de Modelo | Exemplos no NexusLocal |
| :--- | :--- | :--- | :--- |
| **`TRIVIAL_QUICK`** | Saudações (*"bom dia"*, *"olá"*), perguntas fáticas curtas, formatação de texto simples, traduções pontuais de palavras. | Throughput altíssimo (> 150 tok/s), custo zero, baixa latência. | Groq Llama 3.1 8B, SambaNova Llama 3.2 3B |
| **`CODE_ENGINEERING`** | Código, depuração de erros, stack traces, queries SQL, criação de APIs, refatoração e regex. | Especialista em raciocínio estruturado, contexto de código e precisão sintática. | Qwen 2.5 Coder 32B/7B, Groq Llama 3.3 70B, Claude 3.5 Sonnet |
| **`DEEP_REASONING`** | Problemas lógicos, equações matemáticas, enigmas, planejamento de sistemas, tomada de decisão com prós/contras complexos. | Modelos com capacidades nativas de reflexão (*Thinking* / Raciocínio Passo a Passo). | DeepSeek-R1, Gemini 2.0 Flash Thinking, QwQ-32B |
| **`CREATIVE_LONGFORM`** | Redação de artigos, e-mails executivos formais, criação literária, reescrita de tom, roteiros. | Modelos com alta fluência verbal, vocabulário rico e nuances de escrita natural. | Llama 3.3 70B, Gemini 2.5 Flash, Mistral Large |
| **`MULTIMODAL_VISION`** | O prompt contém imagens anexadas (fotos, prints, diagramas) ou PDFs escaneados. | Modelos com visão computacional ativa ou suporte via Vision Relay. | Gemini 2.0 Flash (Multimodal), Llama 3.2 11B Vision |
| **`WEB_RESEARCH`** | Perguntas sobre eventos em tempo real, notícias, cotações, dados após a data de corte ou toggle web ativo. | Modelos rápidos com forte habilidade de sintetizar snippets de busca. | Gemini 2.0 Flash, Groq Llama 3.3 70B |

---

## 2. Níveis de Complexidade (`ComplexityTier`)

Além da intenção, o roteador calcula a escala de profundidade exigida:

```
[ Tier 1: Leve ]   ➔ Pergunta direta (< 150 caracteres), resposta objetiva.
[ Tier 2: Médio ]  ➔ Pergunta com contexto moderado ou instruções de múltiplos passos.
[ Tier 3: Pesado ] ➔ Análise profunda, código longo, arquivos anexos ou raciocínio encadeado.
```

---

## 3. Pipeline de Classificação em 2 Estágios

Para cumprir a exigência inegociável de **execução ultrarrápida (< 2ms)** sem sobrecarregar a CPU nem chamar APIs externas:

```
                                  Prompt & Metadados
                                          │
                                          ▼
┌─────────────────────────────────────────────────────────────────────────────────┐
│                           ESTÁGIO 1: Filtros Determinísticos                    │
│                                                                                 │
│  [A] Análise de Anexos:                                                         │
│      Se attachment.type == 'image' ➔ Força MULTIMODAL_VISION imediato.          │
│                                                                                 │
│  [B] Análise de Toggle Web:                                                     │
│      Se webSearchActive == True ➔ Prioriza WEB_RESEARCH.                        │
│                                                                                 │
│  [C] Heurística Trivial Instantânea:                                            │
│      Se len(prompt) < 25 chars E match em saudações/curtas                      │
│      ➔ TRIVIAL_QUICK com confiança 1.0 (tempo: 0.1ms).                          │
└────────────────────────────────────────┬────────────────────────────────────────┘
                                         │ (Se não for determinístico)
                                         ▼
┌─────────────────────────────────────────────────────────────────────────────────┐
│                           ESTÁGIO 2: Extrator de Sinais Léxicos                 │
│                                                                                 │
│  Regex de Código:                                                               │
│    • Presença de ```, def, class, import, function, const, SELECT, WHERE,       │
│      curl, traceback, error line, =>, {}, [], !=                                │
│                                                                                 │
│  Regex de Raciocínio & Matemática:                                              │
│    • calcule, prove, deduza, probabilidade, equação, teorema, lógica,           │
│      enigma, compare detalhadamente, analise criticamente                       │
│                                                                                 │
│  Extensão do Texto e Histórico:                                                 │
│    • tokens estimados > 800 ou conversa longa ➔ Aumenta ComplexityTier          │
└────────────────────────────────────────┬────────────────────────────────────────┘
                                         │
                                         ▼
                              Resultado da Classificação
```

---

## 4. Estrutura de Dados do Resultado

Contrato Python a ser instanciado em [`backend/ranking/smart_router.py`](file:///j:/Arquivos%20Osmar/Multi+/backend/ranking/smart_router.py):

```python
from dataclasses import dataclass, field
from enum import Enum
from typing import List, Optional

class IntentKey(str, Enum):
    TRIVIAL_QUICK = "trivial_quick"
    CODE_ENGINEERING = "code_engineering"
    DEEP_REASONING = "deep_reasoning"
    CREATIVE_LONGFORM = "creative_longform"
    MULTIMODAL_VISION = "multimodal_vision"
    WEB_RESEARCH = "web_research"
    GENERAL_CHAT = "general_chat"

class ComplexityTier(int, Enum):
    LIGHT = 1
    MEDIUM = 2
    HEAVY = 3

@dataclass
class IntentClassificationResult:
    """Resultado da inferência rápida de intenção antes do envio da requisição."""
    intent: IntentKey
    complexity: ComplexityTier
    confidence: float                     # 0.0 a 1.0
    matched_signals: List[str]            # Ex: ['code_fence', 'sql_keywords', 'long_context']
    reason_label_pt: str                  # Ex: "Tarefa de Código & Programação"
    suggested_family: Optional[str] = None # Ex: "qwen-2.5-coder" ou "deepseek-r1"
    processing_time_ms: float = 0.0
```

---

## 5. Tabela de Sinais e Expressões Regulares de Detecção

Para assegurar eficiência máxima, as expressões são pré-compiladas em memória durante o boot do servidor:

```python
# Sinais de Código
_RE_CODE_BLOCKS = re.compile(r"```[a-zA-Z]*\n[\s\S]*?```", re.MULTILINE)
_RE_CODE_SYNTAX = re.compile(
    r"\b(def|class|import|return|function|const|let|var|public|private|struct|"
    r"impl|fn|async\s+def|SELECT\s+.*FROM|WHERE\s+|INSERT\s+INTO|UPDATE\s+.*SET|"
    r"console\.log|print\(|Traceback|NullPointerException|TypeError|ValueError)\b",
    re.IGNORECASE
)

# Sinais de Raciocínio & Dedução
_RE_DEEP_THOUGHT = re.compile(
    r"\b(calcule|resolva\s+o\s+problema|prove\s+que|demonstre|enigma|teorema|"
    r"probabilidade|an[aá]lise\s+cr[ií]tica|vantagens\s+e\s+desvantagens|deduza|"
    r"fa[cç]a\s+uma\s+an[aá]lise\s+l[oó]gica|passo\s+a\s+passo\s+detalhado)\b",
    re.IGNORECASE
)

# Sinais Triviais / Rápidos
_RE_TRIVIAL_SHORT = re.compile(
    r"^(oi|ol[aá]|bom\s+dia|boa\s+tarde|boa\s+noite|valeu|obrigad[oa]|tchau|"
    r"ok|beleza|sim|n[aã]o|como\s+vai|tudo\s+bem\??)\s*$",
    re.IGNORECASE
)
```
