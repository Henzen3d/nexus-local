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
| **`TRIVIAL_QUICK`** | Saudações (*"bom dia"*, *"olá"*), perguntas fáticas curtas, formatação de texto simples, traduções pontuais de palavras isoladas. | Throughput altíssimo (> 150 tok/s), custo zero, baixa latência. | Groq Llama 3.1 8B, Cerebras Llama 3.1 8B, Cloudflare Llama 3.1 8B |
| **`CODE_ENGINEERING`** | Código, depuração de erros, stack traces, queries SQL, criação de APIs, refatoração e regex. | Especialista em raciocínio estruturado, contexto de código e precisão sintática. | Qwen 2.5 Coder 32B/7B, Groq Llama 3.3 70B, Claude 3.5 Sonnet |
| **`DEEP_REASONING`** | Problemas lógicos, equações matemáticas, enigmas, planejamento de sistemas, tomada de decisão com prós/contras complexos. | Modelos com capacidades nativas de reflexão (*Thinking* / Raciocínio Passo a Passo). | DeepSeek-R1, Gemini 2.0 Flash Thinking, QwQ-32B |
| **`CREATIVE_LONGFORM`** | Redação de artigos, e-mails executivos formais, criação literária, reescrita de tom, roteiros. | Modelos com alta fluência verbal, vocabulário rico e nuances de escrita natural. | Llama 3.3 70B, Gemini 2.5 Flash, Mistral Large |
| **`MULTIMODAL_VISION`** | O prompt contém imagens anexadas (fotos, prints, diagramas) ou o histórico ativo refere imagens anteriores. | Modelos com visão computacional ativa ou suporte via Vision Relay. | Gemini 2.0 Flash (Multimodal), Llama 3.2 11B Vision |
| **`WEB_RESEARCH`** | Perguntas sobre eventos em tempo real, notícias, cotações, dados após a data de corte ou toggle web ativo. | Modelos rápidos com forte habilidade de sintetizar snippets de busca. | Gemini 2.0 Flash, Groq Llama 3.3 70B |

---

## 2. Níveis de Complexidade (`ComplexityTier`)

Além da intenção, o roteador calcula a escala de profundidade exigida:

```
[ Tier 1: Leve ]   ➔ Pergunta direta (< 150 caracteres), resposta objetiva e sem inércia pesada prévia.
[ Tier 2: Médio ]  ➔ Pergunta com contexto moderado ou instruções de múltiplos passos.
[ Tier 3: Pesado ] ➔ Análise profunda, código longo, arquivos anexos ou raciocínio encadeado.
```

---

## 3. Pipeline de Classificação em 3 Estágios (Blindado contra Falhas de 2ª Escala)

Para cumprir a exigência inegociável de **execução ultrarrápida (< 2ms)** sem cometer erros clássicos de amnésia ou quebra de contexto:

```
                          Prompt Atual + Histórico de Mensagens + Metadados
                                                  │
                                                  ▼
┌────────────────────────────────────────────────────────────────────────────────────────┐
│             ESTÁGIO 0: Histerese de Tópico & Memória de Sessão (Anti-Amnésia)          │
│                                                                                        │
│  [A] Multimodalidade Retrospectiva:                                                    │
│      Se attachment.type == 'image' OU history_has_unresolved_images == True            │
│      ➔ Força MULTIMODAL_VISION (evita quebrar turnos subsequentes sobre a foto).       │
│                                                                                        │
│  [B] Inércia de Contexto Técnico (Topic Momentum):                                     │
│      Se prompt atual é curto (< 35 chars, ex: "e no Windows?", "como corrijo isso?")   │
│      E histórico recente está classificado como CODE_ENGINEERING ou DEEP_REASONING     │
│      ➔ Mantém a classe técnica! NÃO rebaixa para TRIVIAL_QUICK.                        │
└────────────────────────────────────────┬───────────────────────────────────────────────┘
                                         │ (Se não interceptado por inércia)
                                         ▼
┌────────────────────────────────────────────────────────────────────────────────────────┐
│             ESTÁGIO 1: Filtros Determinísticos Instantâneos (< 0.2ms)                  │
│                                                                                        │
│  [C] Análise de Toggle Web:                                                            │
│      Se webSearchActive == True ➔ Prioriza WEB_RESEARCH.                               │
│                                                                                        │
│  [D] Heurística Trivial Pura:                                                          │
│      Se conversa é nova (turn == 1) E match em saudações/fáticas                       │
│      ➔ TRIVIAL_QUICK com confiança 1.0.                                                │
└────────────────────────────────────────┬───────────────────────────────────────────────┘
                                         │ (Se não for determinístico)
                                         ▼
┌────────────────────────────────────────────────────────────────────────────────────────┐
│             ESTÁGIO 2: Extrator de Sinais Léxicos e Restrições de Contexto             │
│                                                                                        │
│  Regex de Código:                                                                      │
│    • ```, def, class, import, function, const, SELECT, WHERE, curl, traceback, etc.    │
│                                                                                        │
│  Regex de Raciocínio & Matemática:                                                     │
│    • calcule, prove, deduza, probabilidade, equação, teorema, analise criticamente     │
│                                                                                        │
│  Cálculo de Restrição de Janela (Context Window Guard):                                │
│    • Estima total_tokens = len(prompt + history) // 3.5                                │
│    • Exige: model.context_length >= estimated_tokens + 2048                            │
└────────────────────────────────────────┬───────────────────────────────────────────────┘
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
    """Resultado da inferência rápida de intenção com blindagem de segunda escala."""
    intent: IntentKey
    complexity: ComplexityTier
    confidence: float                     # 0.0 a 1.0
    matched_signals: List[str]            # Ex: ['topic_momentum_code', 'sql_keywords']
    reason_label_pt: str                  # Ex: "Código & Programação (Continuidade)"
    suggested_family: Optional[str] = None # Ex: "qwen-2.5-coder" ou "deepseek-r1"
    
    # Parâmetros de mitigação de 2ª escala:
    min_context_length_required: int = 4096 # Garante que o modelo suporte o histórico
    inherited_from_history: bool = False    # True se preservou a inércia do tópico anterior
    recommended_temperature: float = 0.2    # 0.1-0.2 para código; 0.6 para reasoning; 0.7 para criativo
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
