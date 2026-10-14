"""
backend/ranking/smart_router.py
Motor de Classificação de Intenções e Auto-Roteamento Inteligente (NexusLocal Smart Router).

Implementa:
- Taxonomia canônica de 6 intenções primárias + general_chat
- Níveis de complexidade (LIGHT, MEDIUM, HEAVY) com estimador léxico de complexidade
- Classificação ultrarrápida (< 2ms) com pré-compilação de regex (PT-BR + EN)
- Histerese de tópico (Topic Momentum) e blindagem contra amnésia
- Detecção retrospectiva de multimodalidade
- Context Window Guard (< model.context_length)
- Seleção por "fit" (adequação) por intenção × complexidade × perfil do modelo
  (tamanho, raciocínio, especialidade, velocidade) — ver backend/ranking/model_profile.py
- Afinidade de modelo (Sticky Routing / KV Cache Protector) condicionada à adequação
- Rotação ponderada de slots contra Thundering Herd
- Esforço de raciocínio adaptativo (LIGHT → low, HEAVY → high) quando o modelo tem dial
- Políticas: economical_free, balanced_smart, max_performance

Referência: melhorias/smart-router/06-diagnostico-e-calibracao-2026.md
"""

from __future__ import annotations

import json
import re
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import List, Optional, Dict, Any, Tuple

import aiosqlite
from backend.logging_config import get_logger
from backend.orchestration.build_context import clean_model_display_name
from backend.ranking.model_profile import (
    ModelProfile,
    profile_model,
    REASONING_ALWAYS_ON,
    REASONING_DIAL,
    REASONING_HYBRID,
    REASONING_NONE,
    SIZE_FRONTIER,
)
from backend.reasoning.families import VALID_REASONING_LEVELS

logger = get_logger(__name__)


# ── Taxonomia de Intenções ───────────────────────────────────────────────────

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


class RoutingPolicy(str, Enum):
    ECONOMICAL_FREE = "economical_free"
    BALANCED_SMART = "balanced_smart"
    MAX_PERFORMANCE = "max_performance"


@dataclass
class IntentClassificationResult:
    """Resultado da inferência ultrarrápida de intenção com blindagem de 2ª escala."""
    intent: IntentKey
    complexity: ComplexityTier
    confidence: float                          # 0.0 a 1.0
    matched_signals: List[str]                 # Ex: ['topic_momentum_code', 'sql_keywords']
    reason_label_pt: str                       # Ex: "Código & Programação (Continuidade)"
    suggested_family: Optional[str] = None
    min_context_length_required: int = 4096
    inherited_from_history: bool = False
    recommended_temperature: float = 0.2
    processing_time_ms: float = 0.0
    complexity_score: float = 0.0              # 0.0 a 1.0 (estimador léxico)


@dataclass
class AutoRouteDecision:
    """Decisão final de roteamento de modelo e parâmetros adaptativos."""
    chosen_model_id: str
    chosen_model_name: str
    provider_id: str
    intent: IntentKey
    reason_pt: str
    confidence: float
    policy: str
    temperature: float
    decision_latency_ms: float
    matched_signals: List[str] = field(default_factory=list)
    # Campos adicionados na calibração 2026 (retrocompatíveis)
    complexity: int = ComplexityTier.MEDIUM.value
    fit_score: float = 0.0
    reasoning_effort: Optional[str] = None       # None = não enviar dial (modelo sem controle)
    model_tags: List[str] = field(default_factory=list)
    alternatives: List[Dict[str, Any]] = field(default_factory=list)


# ── Expressões Regulares Pré-Compiladas (< 0.2ms) ───────────────────────────

# Sinais de Código
_RE_CODE_BLOCKS = re.compile(r"```[a-zA-Z0-9_\-\+\#]*\n[\s\S]*?```", re.MULTILINE)
_RE_CODE_SYNTAX = re.compile(
    r"\b(def|class|import|return|function|const|let|var|public|private|protected|"
    r"struct|impl|fn|async\s+def|SELECT\s+[\s\S]*?FROM|WHERE\s+|INSERT\s+INTO|UPDATE\s+[\s\S]*?SET|"
    r"DELETE\s+FROM|console\.log|print\(|Traceback|NullPointerException|TypeError|ValueError|"
    r"IndexError|KeyError|AttributeError|Exception|dockerfile|kubernetes|terraform|regex|"
    r"fastapi|express|react|vue|angular|svelte|django|flask|spring|sql|graphql|typescript|"
    r"javascript|python|golang|rust|c\+\+|csharp|swift|kotlin|php|html|css|json|yaml|"
    r"pandas|numpy|scikit-learn|sklearn|tensorflow|keras|pytorch|torch|transformers|huggingface|"
    r"nltk|spacy|opencv|matplotlib|seaborn|jupyter)\b",
    re.IGNORECASE,
)
_RE_CODE_KEYWORDS = re.compile(
    r"\b(código|função|script|bug|debug|erro|stacktrace|refatore|refatorar|compilar|"
    r"api|endpoint|backend|frontend|query|banco\s+de\s+dados|repositório|git\s+commit|"
    r"pull\s+request|npm\s+run|pip\s+install|classe|variável|parâmetro|"
    r"algoritmo|algoritmos|aprendizado\s+de\s+máquina|machine\s+learning|deep\s+learning|"
    r"processamento\s+de\s+linguagem\s+natural|nlp|rede\s+neural|redes\s+neurais|"
    r"dataset|conjunto\s+de\s+dados|pipeline|sistema\s+de\s+recomendação|classificador|"
    r"treinamento\s+de\s+modelo|engenharia\s+de\s+software|arquitetura\s+de\s+software|"
    r"desenvolva\s+um\s+algoritmo|desenvolva\s+um\s+modelo|desenvolva\s+um\s+sistema|"
    r"implemente\s+um\s+algoritmo|implemente\s+um\s+modelo|implementar\s+em\s+código|"
    # Inglês
    r"source\s+code|code\s+review|refactor|stack\s+trace|unit\s+tests?|compile|"
    r"deploy|docker\s+compose|microservices?|database\s+schema|rest\s+api|"
    r"write\s+a\s+(function|script|program|class|query)|fix\s+(this|the)\s+(bug|error|code)|"
    r"implement\s+(a|an|the)\s+(function|algorithm|api|class|parser))\b",
    re.IGNORECASE,
)

# Sinais FORTES de Raciocínio Profundo & Dedução (PT + EN)
_RE_DEEP_THOUGHT = re.compile(
    r"\b(calcule|resolva\s+o\s+problema|prove\s+que|demonstre|enigma|teorema|"
    r"probabilidade|an[aá]lise\s+cr[ií]tica|vantagens\s+e\s+desvantagens|deduza|"
    r"fa[cç]a\s+uma\s+an[aá]lise\s+l[oó]gica|passo\s+a\s+passo\s+detalhado|derive|"
    r"equa[cç][aã]o|hip[oó]tese|premissa|contradi[cç][aã]o|racioc[ií]nio|"
    r"otimiza[cç][aã]o\s+matem[aá]tica|jogos\s+de\s+l[oó]gica|paradoxo|"
    r"pr[oó]s\s+e\s+contras|trade-?offs?|viabilidade|an[aá]lise\s+de\s+viabilidade|"
    r"plano\s+de\s+(neg[oó]cios?|a[cç][aã]o|estudos?)|planejamento\s+estrat[eé]gico|"
    r"estrat[eé]gia\s+(de|para)|compare\s+(e|as|os|detalhadamente)|comparativo\s+(entre|de)|"
    r"explique\s+(detalhadamente|em\s+detalhes|em\s+profundidade)|justifique|argumente|"
    r"qual\s+(a|[eé]\s+a)\s+melhor\s+(forma|maneira|estrat[eé]gia|op[cç][aã]o|abordagem)|"
    r"an[aá]lise\s+(de\s+)?(riscos?|cen[aá]rios?|impacto|custo[\s-]benef[ií]cio)|"
    # Inglês
    r"calculate|solve\s+(this|the)\s+problem|prove\s+that|theorem|probability|"
    r"step[\s-]by[\s-]step|pros\s+and\s+cons|feasibility|think\s+through|"
    r"critical\s+analysis|risk\s+analysis|business\s+plan|what\s+is\s+the\s+best\s+(way|approach|strategy)|"
    r"compare\s+and\s+contrast|explain\s+in\s+depth|logical\s+reasoning|hypothesis)\b",
    re.IGNORECASE,
)

# Pistas FRACAS de análise (somam ao estimador de complexidade; não decidem sozinhas)
_RE_ANALYTIC_CUES = re.compile(
    r"\b(analise|analisar|avalie|avaliar|compare|comparar|explique\s+por\s+qu[eê]|por\s+qu[eê]|porque|"
    r"consequ[eê]ncias?|implica[cç][oõ]es|cen[aá]rios?|simule|otimize|maximiz\w*|minimiz\w*|"
    r"estrat[eé]gi\w*|planej\w*|decis[aã]o|decidir|dilema|riscos?|benef[ií]cios|impactos?|"
    r"considerando|levando\s+em\s+conta|dado\s+que|supondo|se\s+.{3,40}\s+ent[aã]o|"
    r"requisitos?|restri[cç][oõ]es|or[cç]amento|proje[cç][aã]o|previs[aã]o|tend[eê]ncias?|"
    r"detalhad\w+|aprofund\w+|completo|abrangente|minucios\w+|"
    r"analy[sz]e|evaluate|assess|strategy|strategic|scenario|trade-?off|implications?|"
    r"consequences?|constraints?|budget|forecast|in\s+detail|comprehensive|thorough|why\s+does|why\s+is)\b",
    re.IGNORECASE,
)

# Expressões matemáticas / numéricas (reforço de complexidade)
_RE_MATH = re.compile(
    r"(\d+(?:[.,]\d+)?\s*[\+\-\*/×÷\^%=]\s*\d+(?:[.,]\d+)?|\bR\$\s?\d|\d+\s?%|\b\d{2,}\s?(mil|milh[oõ]es|bilh[oõ]es|k)\b|"
    r"\b(juros|taxa|percentual|m[eé]dia|desvio\s+padr[aã]o|regress[aã]o|integral|derivada|matriz|vetor)\b)",
    re.IGNORECASE,
)

# Sinais Triviais / Rápidos (PT + EN)
_RE_TRIVIAL_SHORT = re.compile(
    r"^(oi|ol[aá]|bom\s+dia|boa\s+tarde|boa\s+noite|valeu|obrigad[oa]|tchau|"
    r"ok|beleza|sim|n[aã]o|como\s+vai|tudo\s+bem|e\s+a[ií]|obrigado\s+pela\s+ajuda|"
    r"perfeito|entendi|combinado|legal|show|massa|boa|at[eé]\s+mais|at[eé]\s+logo|"
    r"ol[aá][,\s]+(bom\s+dia|boa\s+tarde|boa\s+noite|tudo\s+bem|como\s+vai)|"
    r"oi[,\s]+(bom\s+dia|boa\s+tarde|boa\s+noite|tudo\s+bem|como\s+vai)|"
    r"hi|hello|hey|thanks|thank\s+you|good\s+(morning|afternoon|evening|night)|bye|yes|no|"
    r"hi[,\s]+(there|everyone|good\s+morning)|hello[,\s]+(there|good\s+morning))[!\?\.\s]*$",
    re.IGNORECASE,
)

# Sinais de Redação & Criatividade Longform (PT + EN)
_RE_CREATIVE = re.compile(
    r"\b(escreva\s+uma?\s+redação|artigo|e-?mail\s+formal|redija|roteiro|poema|conto|"
    r"reescreva\s+com\s+tom|crônica|storytelling|discurso|copywriting|narrativa|"
    r"carta\s+de\s+apresentação|proposta\s+comercial|ensaio|biografia|"
    r"hist[oó]ria\s+(curta|infantil|de\s+terror|de\s+fic[cç][aã]o)|post\s+para\s+(o\s+)?(blog|linkedin|instagram)|"
    r"legenda\s+para|slogan|letra\s+de\s+m[uú]sica|monólogo|di[aá]logo\s+entre|"
    r"write\s+(a|an)\s+(poem|story|short\s+story|essay|article|blog\s+post|cover\s+letter|speech|script)|"
    r"rewrite\s+(this|the)\s+(text|paragraph|email)|creative\s+writing|screenplay|newsletter)\b",
    re.IGNORECASE,
)

_RE_ENUMERATION = re.compile(r"(?m)^\s*(?:[-*•]|\d+[.)])\s+\S")

# Preferências de família por intenção (bônus leve de afinidade; o perfil do
# modelo faz o trabalho pesado). Substrings casadas contra id/nome em minúsculas.
INTENT_FAMILY_MAPPING: Dict[IntentKey, List[str]] = {
    IntentKey.TRIVIAL_QUICK: [
        "llama-3.1-8b", "llama3.1-8b", "gemma-3-12b", "gemma3:12b", "qwen3-8b", "ministral-8b",
        "gemini-2.5-flash-lite", "gemini-2.0-flash-lite", "gpt-oss-20b", "gpt-oss:20b",
    ],
    IntentKey.CODE_ENGINEERING: [
        "qwen3-coder", "qwen2.5-coder", "qwen-2.5-coder", "kimi-k2.7-code", "devstral", "codestral",
        "deepseek-v3", "deepseek-v4", "glm-5", "kimi-k2", "claude", "gpt-5",
    ],
    IntentKey.DEEP_REASONING: [
        "deepseek-r1", "deepseek-reasoner", "qwq", "gpt-oss-120b", "gpt-oss:120b", "gemini-2.5-pro",
        "gemini-3", "glm-5", "kimi-k2", "magistral", "deepseek-v3.2", "deepseek-v4", "minimax-m",
    ],
    IntentKey.CREATIVE_LONGFORM: [
        "kimi-k2", "gemini-2.5-flash", "gemini-3-flash", "llama-3.3-70b", "llama-4-maverick",
        "mistral-large", "mistral-medium", "deepseek-v3", "glm-4.7", "claude",
    ],
    IntentKey.MULTIMODAL_VISION: [
        "gemini", "llama-4", "qwen3-vl", "qwen3.5", "pixtral", "gemma-3-27b", "kimi-k2.5", "kimi-k2.6",
    ],
    IntentKey.WEB_RESEARCH: [
        "gemini-2.5-flash", "gemini-3-flash", "llama-3.3-70b", "gpt-oss-120b", "kimi-k2", "llama-4-scout",
    ],
    IntentKey.GENERAL_CHAT: [
        "llama-3.3-70b", "gemini-2.5-flash", "gpt-oss-120b", "kimi-k2", "qwen3-32b", "llama-4-scout",
    ],
}

# Rotação circular global para mitigação de Thundering Herd em tarefas triviais gratuitas
_SLOT_ROTATION_COUNTER = 0


# ── Motor de Classificação Pura (< 2ms) ──────────────────────────────────────

def _history_has_images(history: Optional[List[Dict[str, Any]]]) -> bool:
    """Verifica se há imagens pendentes ou referenciadas no histórico ativo."""
    if not history:
        return False
    for msg in history:
        content = msg.get("content")
        if isinstance(content, list):
            for part in content:
                if isinstance(part, dict) and (part.get("type") in ("image", "image_url") or "image_url" in part):
                    return True
        elif isinstance(content, str):
            if "[imagem anexada:" in content.lower() or "[arquivo anexado:" in content.lower():
                return True
        if msg.get("has_image") or msg.get("relay_used"):
            return True
    return False


def _history_has_technical_context(history: Optional[List[Dict[str, Any]]]) -> Optional[IntentKey]:
    """Inspeciona as últimas mensagens para detectar tópico técnico em andamento."""
    if not history:
        return None
    for msg in reversed(history[-4:]):
        content = msg.get("content")
        if isinstance(content, str):
            if _RE_CODE_BLOCKS.search(content) or _RE_CODE_SYNTAX.search(content):
                return IntentKey.CODE_ENGINEERING
            if _RE_DEEP_THOUGHT.search(content):
                return IntentKey.DEEP_REASONING
    return None


def estimate_complexity(prompt: str) -> Tuple[float, List[str]]:
    """
    Estimador léxico de complexidade (0.0–1.0), puro e determinístico.

    Combina tamanho, número de perguntas, enumerações, pistas analíticas,
    expressões numéricas/matemáticas e restrições explícitas. Não decide a
    intenção sozinho: alimenta o tier de complexidade e o roteamento de
    perguntas "pesadas" sem palavras-chave fortes.
    """
    p = (prompt or "").strip()
    if not p:
        return 0.0, []
    cues: List[str] = []
    score = 0.0

    n = len(p)
    if n >= 1200:
        score += 0.50
        cues.append("length:xl")
    elif n >= 500:
        score += 0.40
        cues.append("length:l")
    elif n >= 200:
        score += 0.25
        cues.append("length:m")
    elif n >= 60:
        score += 0.10

    q_marks = p.count("?")
    if q_marks >= 3:
        score += 0.25
        cues.append("multi_question")
    elif q_marks >= 2:
        score += 0.15
        cues.append("multi_question")

    if len(_RE_ENUMERATION.findall(p)) >= 2:
        score += 0.15
        cues.append("enumeration")

    analytic = {m.group(0).lower() for m in _RE_ANALYTIC_CUES.finditer(p)}
    if analytic:
        score += min(0.40, 0.12 * len(analytic))
        cues.append(f"analytic_cues:{len(analytic)}")

    math_hits = len(_RE_MATH.findall(p))
    if math_hits >= 2:
        score += 0.15
        cues.append("math_expressions")
    elif math_hits == 1:
        score += 0.07

    return min(1.0, round(score, 3)), cues


def _tier_from_score(score: float) -> ComplexityTier:
    if score >= 0.6:
        return ComplexityTier.HEAVY
    if score >= 0.3:
        return ComplexityTier.MEDIUM
    return ComplexityTier.LIGHT


def classify_intent(
    prompt: str,
    attachments: Optional[List[Any]] = None,
    web_search: bool = False,
    history: Optional[List[Dict[str, Any]]] = None,
    previous_intent: Optional[str] = None,
) -> IntentClassificationResult:
    """
    Classifica deterministicamente a intenção do usuário em tempo ultra-baixo (< 2ms).
    Aplica blindagens contra amnésia (retrospecção multimodal e histerese de tópico).
    """
    t_start = time.perf_counter()
    prompt_raw = prompt or ""
    prompt_str = prompt_raw.strip()
    history = history or []
    attachments = attachments or []
    signals: List[str] = []

    # Cálculo da estimativa de tamanho de contexto (Context Window Guard)
    history_chars = sum(
        len(m.get("content", "")) if isinstance(m.get("content"), str) else 200
        for m in history
    )
    total_chars = len(prompt_str) + history_chars
    estimated_tokens = int(total_chars / 3.5)
    min_context_required = max(4096, estimated_tokens + 2048)

    def _done(**kwargs) -> IntentClassificationResult:
        t_end = time.perf_counter()
        kwargs.setdefault("min_context_length_required", min_context_required)
        kwargs.setdefault("matched_signals", signals)
        return IntentClassificationResult(
            processing_time_ms=round((t_end - t_start) * 1000, 3),
            **kwargs,
        )

    # ─────────────────────────────────────────────────────────────────────────
    # ESTÁGIO 0: Histerese de Tópico & Memória de Sessão (Anti-Amnésia)
    # ─────────────────────────────────────────────────────────────────────────

    # [0.A] Multimodalidade Retrospectiva
    has_current_attachment = bool(attachments)
    has_history_images = _history_has_images(history)

    if has_current_attachment or has_history_images:
        signal = "attachment_current" if has_current_attachment else "retrospective_vision_history"
        signals.append(signal)
        cscore, _ = estimate_complexity(prompt_str)
        return _done(
            intent=IntentKey.MULTIMODAL_VISION,
            complexity=ComplexityTier.HEAVY if cscore >= 0.6 else ComplexityTier.MEDIUM,
            confidence=0.98,
            reason_label_pt="Imagens & Visão Multimodal",
            suggested_family="gemini-2.5-flash",
            inherited_from_history=has_history_images and not has_current_attachment,
            recommended_temperature=0.4,
            complexity_score=cscore,
        )

    # [0.B] Topic Momentum (Inércia de Contexto Técnico)
    # Perguntas curtas (< 35 caracteres) em conversas técnicas retêm o modelo especialista
    if 0 < len(prompt_str) < 35:
        prev_key: Optional[IntentKey] = None
        if previous_intent:
            try:
                prev_key = IntentKey(previous_intent)
            except ValueError:
                pass
        if not prev_key:
            prev_key = _history_has_technical_context(history)

        if prev_key in (IntentKey.CODE_ENGINEERING, IntentKey.DEEP_REASONING) and not _RE_TRIVIAL_SHORT.match(prompt_str):
            signals.append(f"topic_momentum_{prev_key.value}")
            label = (
                "Código & Programação (Continuidade)"
                if prev_key == IntentKey.CODE_ENGINEERING
                else "Raciocínio Lógico (Continuidade)"
            )
            family = "qwen3-coder" if prev_key == IntentKey.CODE_ENGINEERING else "deepseek-r1"
            temp = 0.2 if prev_key == IntentKey.CODE_ENGINEERING else 0.6
            return _done(
                intent=prev_key,
                complexity=ComplexityTier.LIGHT,
                confidence=0.92,
                reason_label_pt=label,
                suggested_family=family,
                inherited_from_history=True,
                recommended_temperature=temp,
            )

    # ─────────────────────────────────────────────────────────────────────────
    # ESTÁGIO 1: Filtros Determinísticos Instantâneos (< 0.2ms)
    # ─────────────────────────────────────────────────────────────────────────

    # [1.A] Análise de Toggle Web
    if web_search:
        signals.append("web_search_active")
        cscore, _ = estimate_complexity(prompt_str)
        return _done(
            intent=IntentKey.WEB_RESEARCH,
            complexity=ComplexityTier.HEAVY if cscore >= 0.6 else ComplexityTier.MEDIUM,
            confidence=0.96,
            reason_label_pt="Síntese & Pesquisa Web",
            suggested_family="gemini-2.5-flash",
            recommended_temperature=0.5,
            complexity_score=cscore,
        )

    # [1.B] Heurística Trivial Pura
    if _RE_TRIVIAL_SHORT.match(prompt_str):
        signals.append("trivial_short_greeting")
        return _done(
            intent=IntentKey.TRIVIAL_QUICK,
            complexity=ComplexityTier.LIGHT,
            confidence=1.0,
            reason_label_pt="Saudação / Pergunta Rápida",
            suggested_family="llama-3.1-8b",
            recommended_temperature=0.5,
        )

    # ─────────────────────────────────────────────────────────────────────────
    # ESTÁGIO 2: Extrator de Sinais Léxicos e Estimador de Complexidade
    # ─────────────────────────────────────────────────────────────────────────
    cscore, ccues = estimate_complexity(prompt_str)

    # Código & Programação
    has_code_block = bool(_RE_CODE_BLOCKS.search(prompt_str))
    code_syntax_match = _RE_CODE_SYNTAX.search(prompt_str)
    code_kw_match = _RE_CODE_KEYWORDS.search(prompt_str)

    if has_code_block or code_syntax_match or code_kw_match:
        if has_code_block:
            signals.append("code_markdown_blocks")
        if code_syntax_match:
            signals.append(f"code_syntax:{code_syntax_match.group(0)}")
        if code_kw_match:
            signals.append(f"code_keyword:{code_kw_match.group(0)}")

        complexity = (
            ComplexityTier.HEAVY
            if (len(prompt_str) > 400 or has_code_block or cscore >= 0.5)
            else ComplexityTier.MEDIUM
        )
        return _done(
            intent=IntentKey.CODE_ENGINEERING,
            complexity=complexity,
            confidence=0.95,
            reason_label_pt="Código & Engenharia",
            suggested_family="qwen3-coder",
            recommended_temperature=0.2,
            complexity_score=cscore,
        )

    # Raciocínio Profundo & Dedução Lógica (sinais fortes)
    thought_match = _RE_DEEP_THOUGHT.search(prompt_str)
    if thought_match:
        signals.append(f"deep_thought:{thought_match.group(0)}")
        complexity = (
            ComplexityTier.HEAVY if (len(prompt_str) > 300 or cscore >= 0.45) else ComplexityTier.MEDIUM
        )
        return _done(
            intent=IntentKey.DEEP_REASONING,
            complexity=complexity,
            confidence=0.92,
            reason_label_pt="Raciocínio & Dedução",
            suggested_family="deepseek-r1",
            recommended_temperature=0.6,
            complexity_score=cscore,
        )

    # Redação & Criatividade Longform
    creative_match = _RE_CREATIVE.search(prompt_str)
    if creative_match:
        signals.append(f"creative_intent:{creative_match.group(0)}")
        complexity = (
            ComplexityTier.HEAVY if (len(prompt_str) > 300 or cscore >= 0.45) else ComplexityTier.MEDIUM
        )
        return _done(
            intent=IntentKey.CREATIVE_LONGFORM,
            complexity=complexity,
            confidence=0.89,
            reason_label_pt="Redação & Conteúdo Criativo",
            suggested_family="kimi-k2",
            recommended_temperature=0.7,
            complexity_score=cscore,
        )

    # Pergunta analítica pesada sem palavras-chave fortes → raciocínio
    analytic_cue_count = 0
    for c in ccues:
        if c.startswith("analytic_cues:"):
            analytic_cue_count = int(c.split(":", 1)[1])
    if cscore >= 0.55 or (analytic_cue_count >= 2 and len(prompt_str) >= 120):
        signals.append(f"complexity_high:{cscore}")
        signals.extend(ccues)
        return _done(
            intent=IntentKey.DEEP_REASONING,
            complexity=ComplexityTier.HEAVY if cscore >= 0.6 else ComplexityTier.MEDIUM,
            confidence=0.85,
            reason_label_pt="Análise & Raciocínio",
            suggested_family="deepseek-v3.2",
            recommended_temperature=0.5,
            complexity_score=cscore,
        )

    # Fallback rápido para conversas gerais ou perguntas curtas
    if len(prompt_str) < 48 and cscore < 0.3:
        signals.append("short_general_query")
        return _done(
            intent=IntentKey.TRIVIAL_QUICK,
            complexity=ComplexityTier.LIGHT,
            confidence=0.82,
            reason_label_pt="Pergunta Curta / Direta",
            suggested_family="llama-3.1-8b",
            recommended_temperature=0.5,
            complexity_score=cscore,
        )

    signals.append("general_conversation")
    tier = _tier_from_score(cscore)
    if tier == ComplexityTier.LIGHT:
        tier = ComplexityTier.MEDIUM
    if tier == ComplexityTier.HEAVY:
        signals.append("general_heavy")
        signals.extend(ccues)
    return _done(
        intent=IntentKey.GENERAL_CHAT,
        complexity=tier,
        confidence=0.82,
        reason_label_pt="Conversação Geral" if tier != ComplexityTier.HEAVY else "Conversação Elaborada",
        suggested_family="llama-3.3-70b",
        recommended_temperature=0.5,
        complexity_score=cscore,
    )


# ── Cache de Modelos em Memória (JEV Fast Model Cache) ─────────────────────
_MODEL_CACHE: Optional[List[Dict[str, Any]]] = None
_MODEL_CACHE_TIME: float = 0.0
_MODEL_CACHE_TTL: float = 30.0  # 30 segundos de vida útil em RAM


def invalidate_model_cache() -> None:
    """Invalida o cache de modelos em memória (chamado em failover ou admin)."""
    global _MODEL_CACHE, _MODEL_CACHE_TIME
    _MODEL_CACHE = None
    _MODEL_CACHE_TIME = 0.0


def is_trivial_greeting(prompt: str) -> bool:
    """Verifica instantaneamente (<0.01ms) se o prompt é uma saudação trivial pura."""
    if not prompt:
        return False
    p = prompt.strip()
    return len(p) <= 35 and bool(_RE_TRIVIAL_SHORT.match(p))


def get_default_quality_score(model_id: str, model_name: str, provider_id: str = "") -> float:
    """
    Qualidade estimada para modelos sem ranking real.
    Delegado ao perfil heurístico por família/geração/tamanho (model_profile.py),
    que cobre o catálogo gratuito de 2026 e substitui o antigo "60 para todos".
    """
    pid = provider_id or (model_id.split("/", 1)[0] if "/" in (model_id or "") else "")
    return profile_model(model_id or "", model_name or "", pid).baseline_quality


# ── Esforço de raciocínio adaptativo ─────────────────────────────────────────

_LEVEL_INDEX = {lvl: i for i, lvl in enumerate(VALID_REASONING_LEVELS)}


def _nearest_level(target: str, allowed: List[str], prefer_higher: bool) -> Optional[str]:
    """Aproxima `target` ao nível permitido mais próximo na escala interna."""
    if not allowed:
        return None
    if target in allowed:
        return target
    t_idx = _LEVEL_INDEX.get(target)
    if t_idx is None:
        return None
    best = None
    best_dist = None
    for lvl in allowed:
        idx = _LEVEL_INDEX.get(lvl)
        if idx is None:
            continue
        dist = abs(idx - t_idx)
        if best_dist is None or dist < best_dist or (
            dist == best_dist and ((idx > t_idx) if prefer_higher else (idx < t_idx))
        ):
            best, best_dist = lvl, dist
    return best


def recommend_reasoning_effort(
    intent: IntentKey,
    complexity: ComplexityTier,
    user_level: Optional[str],
    reasoning_control: Optional[str],
    allowed_levels: Optional[List[str]],
) -> Optional[str]:
    """
    Esforço de raciocínio adaptativo para o modo Auto.

    - Modelos sem dial (none/always_on) → None (não envia parâmetro, sem aviso na UI).
    - LIGHT → 'low'; MEDIUM → nível configurado em Auto (padrão 'medium');
      HEAVY / raciocínio profundo → 'high' (ou o nível do usuário, se maior).
    - O resultado é aproximado aos níveis aceitos pelo modelo.
    """
    ctrl = (reasoning_control or "").strip().lower()
    if ctrl in ("", "none", "unset", REASONING_ALWAYS_ON):
        return None
    allowed = [lvl for lvl in (allowed_levels or []) if lvl in _LEVEL_INDEX]
    if not allowed:
        return None

    base = (user_level or "medium").strip().lower()
    if base not in _LEVEL_INDEX:
        base = "medium"

    def _max(a: str, b: str) -> str:
        return a if _LEVEL_INDEX[a] >= _LEVEL_INDEX[b] else b

    def _min(a: str, b: str) -> str:
        return a if _LEVEL_INDEX[a] <= _LEVEL_INDEX[b] else b

    if intent == IntentKey.TRIVIAL_QUICK:
        target = _min(base, "low")
    elif intent == IntentKey.DEEP_REASONING:
        target = _max(base, "high") if complexity == ComplexityTier.HEAVY else _max(base, "medium")
    elif intent == IntentKey.CODE_ENGINEERING:
        target = _max(base, "high") if complexity == ComplexityTier.HEAVY else base
    elif intent == IntentKey.CREATIVE_LONGFORM:
        target = _min(base, "low") if complexity != ComplexityTier.HEAVY else _min(base, "medium")
    else:  # GENERAL_CHAT, WEB_RESEARCH, MULTIMODAL_VISION
        if complexity == ComplexityTier.LIGHT:
            target = _min(base, "low")
        elif complexity == ComplexityTier.HEAVY:
            target = _max(base, "high")
        else:
            target = base

    return _nearest_level(target, allowed, prefer_higher=(complexity == ComplexityTier.HEAVY))


# ── Pontuação de adequação (fit) por intenção ────────────────────────────────

_TIER_BONUS: Dict[IntentKey, Tuple[int, int, int, int, int]] = {
    # (nano, small, medium, large, frontier)
    IntentKey.TRIVIAL_QUICK: (12, 15, 8, 0, -6),
    IntentKey.GENERAL_CHAT: (-18, -6, 4, 10, 10),
    IntentKey.DEEP_REASONING: (-30, -15, 0, 10, 14),
    IntentKey.CODE_ENGINEERING: (-30, -12, 2, 9, 12),
    IntentKey.CREATIVE_LONGFORM: (-25, -10, 2, 10, 12),
    IntentKey.WEB_RESEARCH: (-20, -8, 2, 8, 10),
    IntentKey.MULTIMODAL_VISION: (-15, -5, 3, 8, 10),
}
_GENERAL_HEAVY_TIER_BONUS = (-30, -15, 0, 10, 14)

_REASONING_BONUS: Dict[str, Dict[str, int]] = {
    "deep": {REASONING_ALWAYS_ON: 16, REASONING_DIAL: 15, REASONING_HYBRID: 10, REASONING_NONE: 0},
    "general_heavy": {REASONING_ALWAYS_ON: 6, REASONING_DIAL: 8, REASONING_HYBRID: 5, REASONING_NONE: 0},
    "code": {REASONING_ALWAYS_ON: 2, REASONING_DIAL: 4, REASONING_HYBRID: 3, REASONING_NONE: 0},
    "trivial": {REASONING_ALWAYS_ON: -25, REASONING_DIAL: -3, REASONING_HYBRID: 0, REASONING_NONE: 0},
    "general": {REASONING_ALWAYS_ON: -12, REASONING_DIAL: 0, REASONING_HYBRID: 0, REASONING_NONE: 0},
    "creative": {REASONING_ALWAYS_ON: -10, REASONING_DIAL: 0, REASONING_HYBRID: 0, REASONING_NONE: 0},
    "web": {REASONING_ALWAYS_ON: -8, REASONING_DIAL: 0, REASONING_HYBRID: 0, REASONING_NONE: 0},
    "vision": {REASONING_ALWAYS_ON: -6, REASONING_DIAL: 0, REASONING_HYBRID: 0, REASONING_NONE: 0},
}

_COST_PENALTY: Dict[str, Tuple[int, int, int]] = {
    # (LIGHT, MEDIUM, HEAVY) aplicado a modelos NÃO gratuitos
    RoutingPolicy.ECONOMICAL_FREE.value: (35, 30, 20),
    RoutingPolicy.BALANCED_SMART.value: (15, 8, 3),
    RoutingPolicy.MAX_PERFORMANCE.value: (0, 0, 0),
}


def score_candidate(
    model: Dict[str, Any],
    profile: ModelProfile,
    intent: IntentKey,
    complexity: ComplexityTier,
    policy: str,
) -> Tuple[float, Dict[str, float]]:
    """
    Calcula a adequação (fit) de um modelo para a intenção/complexidade/política.
    Função pura: retorna (fit, breakdown) — o breakdown alimenta o modo "Testar roteador".
    """
    q = float(model.get("quality_score") or profile.baseline_quality)
    tier = profile.size_tier
    breakdown: Dict[str, float] = {}

    if intent == IntentKey.TRIVIAL_QUICK:
        fit = 0.25 * q + 45.0 * profile.speed_score + _TIER_BONUS[intent][tier]
        fit += _REASONING_BONUS["trivial"][profile.reasoning_mode]
        if policy == RoutingPolicy.MAX_PERFORMANCE.value:
            fit += 0.15 * q
        breakdown["speed"] = round(45.0 * profile.speed_score, 1)
    elif intent == IntentKey.GENERAL_CHAT and complexity == ComplexityTier.HEAVY:
        fit = 0.65 * q + _GENERAL_HEAVY_TIER_BONUS[tier]
        fit += _REASONING_BONUS["general_heavy"][profile.reasoning_mode]
    elif intent == IntentKey.GENERAL_CHAT:
        fit = 0.6 * q + _TIER_BONUS[intent][tier] + 6.0 * profile.speed_score
        fit += _REASONING_BONUS["general"][profile.reasoning_mode]
    elif intent == IntentKey.DEEP_REASONING:
        fit = 0.6 * q + _TIER_BONUS[intent][tier]
        fit += _REASONING_BONUS["deep"][profile.reasoning_mode]
        if complexity == ComplexityTier.HEAVY and tier == SIZE_FRONTIER:
            fit += 4.0
    elif intent == IntentKey.CODE_ENGINEERING:
        fit = 0.6 * q + _TIER_BONUS[intent][tier]
        fit += _REASONING_BONUS["code"][profile.reasoning_mode]
        if profile.is_coder:
            fit += 14.0
            breakdown["coder"] = 14.0
        if complexity == ComplexityTier.HEAVY:
            if tier == SIZE_FRONTIER:
                fit += 3.0
            if int(model.get("context_length") or 0) >= 65536:
                fit += 3.0
    elif intent == IntentKey.CREATIVE_LONGFORM:
        fit = 0.6 * q + _TIER_BONUS[intent][tier]
        fit += _REASONING_BONUS["creative"][profile.reasoning_mode]
        if profile.is_coder:
            fit -= 6.0
        if int(model.get("context_length") or 0) >= 32768:
            fit += 2.0
    elif intent == IntentKey.WEB_RESEARCH:
        fit = 0.6 * q + _TIER_BONUS[intent][tier] + 8.0 * profile.speed_score
        fit += _REASONING_BONUS["web"][profile.reasoning_mode]
        ctx = int(model.get("context_length") or 0)
        if ctx >= 131072:
            fit += 7.0
        elif ctx >= 65536:
            fit += 5.0
    else:  # MULTIMODAL_VISION
        fit = 0.65 * q + _TIER_BONUS[intent][tier]
        fit += _REASONING_BONUS["vision"][profile.reasoning_mode]
        if not profile.is_vision:
            fit -= 40.0

    breakdown["quality"] = round(q, 1)
    breakdown["tier"] = float(_TIER_BONUS[intent][tier] if not (
        intent == IntentKey.GENERAL_CHAT and complexity == ComplexityTier.HEAVY
    ) else _GENERAL_HEAVY_TIER_BONUS[tier])

    # Follow-ups curtos (LIGHT) em intenções pesadas: leve preferência por velocidade
    if complexity == ComplexityTier.LIGHT and intent not in (IntentKey.TRIVIAL_QUICK,):
        fit += 4.0 * profile.speed_score

    # Afinidade de família (bônus leve)
    text = f"{model.get('id', '')} {model.get('name', '')}".lower()
    if any(f in text for f in INTENT_FAMILY_MAPPING.get(intent, [])):
        fit += 3.0
        breakdown["family"] = 3.0

    # Política: custo
    if not model.get("is_free"):
        penalty = _COST_PENALTY.get(policy, _COST_PENALTY[RoutingPolicy.BALANCED_SMART.value])[
            max(0, min(2, int(complexity) - 1))
        ]
        fit -= penalty
        breakdown["cost"] = -float(penalty)
    if policy == RoutingPolicy.ECONOMICAL_FREE.value and complexity != ComplexityTier.HEAVY:
        fit += 6.0 * profile.speed_score

    # Saúde / cota
    status = str(model.get("quota_status") or "available")
    if status not in ("available", "exhausted", "cooldown"):
        fit -= 8.0
        breakdown["health"] = -8.0

    # Modelos não conversacionais (embedding, OCR, TTS…) nunca devem ganhar
    if not profile.is_chat_capable:
        fit -= 100.0
        breakdown["non_chat"] = -100.0

    return round(fit, 2), breakdown


def _row_profile(m: Dict[str, Any]) -> ModelProfile:
    return profile_model(
        m.get("id", ""),
        m.get("name", ""),
        m.get("provider_id", ""),
        m.get("reasoning_control"),
        int(m.get("supports_vision") or 0),
    )


def _parse_levels(raw: Any) -> List[str]:
    if not raw:
        return []
    if isinstance(raw, list):
        return [str(x) for x in raw]
    try:
        data = json.loads(raw)
        return [str(x) for x in data] if isinstance(data, list) else []
    except Exception:
        return []


async def load_routing_catalog(db: aiosqlite.Connection) -> List[Dict[str, Any]]:
    """
    Carrega o catálogo roteável (modelos habilitados de provedores habilitados) com
    ranking, cota e capacidades. Usa o JEV Fast Model Cache (TTL 30s); estados voláteis
    (provedor habilitado / cota) são sempre consultados em tempo real.
    """
    global _MODEL_CACHE, _MODEL_CACHE_TIME
    now = time.monotonic()
    if _MODEL_CACHE is not None and (now - _MODEL_CACHE_TIME) < _MODEL_CACHE_TTL:
        models_data = [dict(m) for m in _MODEL_CACHE]
    else:
        query = """
            SELECT m.id, m.provider_id, m.name, m.display_name, m.context_length,
                   COALESCE(m.confirmed_free, 0) as confirmed_free,
                   COALESCE(p.is_free, 0) as prov_is_free,
                   mr.nexuslocal_score,
                   mr.quality_score,
                   COALESCE(mqs.status, 'available') as quota_status,
                   COALESCE(m.supports_vision, 0) as supports_vision,
                   COALESCE(m.reasoning_control, 'none') as reasoning_control,
                   m.reasoning_levels,
                   COALESCE(p.is_local, 0) as prov_is_local
            FROM models m
            JOIN providers p ON p.id = m.provider_id
            LEFT JOIN model_rankings mr ON mr.model_id = m.id
            LEFT JOIN model_quota_status mqs ON mqs.model_id = m.id
            WHERE m.enabled = 1 AND p.enabled = 1
        """
        async with db.execute(query) as cur:
            rows = await cur.fetchall()

        if not rows:
            raise ValueError("Nenhum modelo habilitado encontrado no sistema.")

        models_data = []
        for r in rows:
            prof = profile_model(r[0], r[2], r[1], r[11], int(r[10] or 0))
            rank_q = float(r[8]) if r[8] is not None else None
            rank_n = float(r[7]) if r[7] is not None else None
            has_ranking = rank_q is not None and rank_q > 50.0
            quality = rank_q if has_ranking else prof.baseline_quality
            nexus = rank_n if (rank_n is not None and rank_n > 50.0) else quality
            models_data.append({
                "id": r[0],
                "provider_id": r[1],
                "name": r[2],
                "display_name": clean_model_display_name(r[3], r[1]),
                "context_length": r[4] or 8192,
                "confirmed_free": r[5],
                "prov_is_free": r[6],
                "is_free": 1 if (r[5] == 1 or r[6] == 1 or r[13] == 1) else 0,
                "nexuslocal_score": nexus,
                "quality_score": quality,
                "has_ranking": has_ranking,
                "quota_status": r[9],
                "supports_vision": r[10],
                "reasoning_control": r[11] or "none",
                "reasoning_levels": _parse_levels(r[12]),
                "is_local": r[13],
                "tags": list(prof.tags()),
            })
        _MODEL_CACHE = models_data
        _MODEL_CACHE_TIME = now

    # Quota e ativação de provedores são estados voláteis; mantê-los em tempo real mesmo
    # enquanto o join do catálogo/ranking está em cache (TTL 30s).
    async with db.execute("SELECT id FROM providers WHERE enabled = 1") as cur:
        enabled_provider_ids = {row[0] for row in await cur.fetchall()}
    models_data = [m for m in models_data if m["provider_id"] in enabled_provider_ids]

    async with db.execute("SELECT model_id, status FROM model_quota_status") as cur:
        quota_status_by_model = {row[0]: row[1] for row in await cur.fetchall()}
    for model in models_data:
        model["quota_status"] = quota_status_by_model.get(model["id"], "available")
    return models_data


def _decision(
    chosen: Dict[str, Any],
    intent_result: IntentClassificationResult,
    policy_str: str,
    reason_pt: str,
    signals: List[str],
    latency_ms: float,
    fit: float,
    alternatives: List[Dict[str, Any]],
    user_effort: Optional[str],
) -> AutoRouteDecision:
    effort = recommend_reasoning_effort(
        intent_result.intent,
        intent_result.complexity,
        user_effort,
        chosen.get("reasoning_control"),
        chosen.get("reasoning_levels"),
    )
    return AutoRouteDecision(
        chosen_model_id=chosen["id"],
        chosen_model_name=clean_model_display_name(chosen["display_name"], chosen["provider_id"]),
        provider_id=chosen["provider_id"],
        intent=intent_result.intent,
        reason_pt=reason_pt,
        confidence=intent_result.confidence,
        policy=policy_str,
        temperature=intent_result.recommended_temperature,
        decision_latency_ms=latency_ms,
        matched_signals=signals,
        complexity=int(intent_result.complexity),
        fit_score=fit,
        reasoning_effort=effort,
        model_tags=list(chosen.get("tags") or []),
        alternatives=alternatives,
    )


def rank_candidates(
    models_data: List[Dict[str, Any]],
    intent_result: IntentClassificationResult,
    policy_str: str,
) -> List[Dict[str, Any]]:
    """
    Aplica os filtros estruturais (sanidade, cota, janela de contexto, visão) e
    pontua cada candidato por adequação. Retorna a lista ordenada (melhor primeiro)
    de dicts com `model`, `profile`, `fit`, `breakdown`. Função sem I/O.
    """
    # 2. Filtro de Sanidade e Cooldown (Descarta esgotados)
    available_models = [m for m in models_data if m["quota_status"] not in ("exhausted", "cooldown")]
    if not available_models:
        available_models = list(models_data)  # fallback se todos estiverem esgotados

    # 3. Context Window Guard (Descarta modelos com janela insuficiente para evitar HTTP 400)
    context_guarded = [
        m for m in available_models
        if int(m["context_length"] or 0) >= intent_result.min_context_length_required
    ]
    if context_guarded:
        working_pool = context_guarded
    else:
        working_pool = sorted(available_models, key=lambda m: int(m["context_length"] or 0), reverse=True)[:5]

    profiles = {m["id"]: _row_profile(m) for m in working_pool}

    # 4. Filtro de Multimodalidade Retrospectiva
    if intent_result.intent == IntentKey.MULTIMODAL_VISION:
        vision_candidates = [m for m in working_pool if profiles[m["id"]].is_vision]
        if vision_candidates:
            working_pool = vision_candidates

    # 5. Pontuação de adequação por intenção × complexidade × política
    ranked: List[Dict[str, Any]] = []
    for m in working_pool:
        prof = profiles[m["id"]]
        fit, breakdown = score_candidate(m, prof, intent_result.intent, intent_result.complexity, policy_str)
        ranked.append({"model": m, "profile": prof, "fit": fit, "breakdown": breakdown})

    ranked.sort(
        key=lambda c: (
            -c["fit"],
            -float(c["model"].get("quality_score") or 0.0),
            -float(c["model"].get("nexuslocal_score") or 0.0),
            str(c["model"]["id"]),
        )
    )
    return ranked


def _alternatives_payload(ranked: List[Dict[str, Any]], exclude_id: str, limit: int = 4) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    for c in ranked:
        m = c["model"]
        if m["id"] == exclude_id:
            continue
        out.append({
            "model_id": m["id"],
            "model_name": clean_model_display_name(m["display_name"], m["provider_id"]),
            "provider_id": m["provider_id"],
            "fit_score": c["fit"],
            "tags": list(m.get("tags") or c["profile"].tags()),
        })
        if len(out) >= limit:
            break
    return out


# ── Seleção de Modelo com Blindagem de 2ª Escala ─────────────────────────────

async def select_best_model(
    intent_result: IntentClassificationResult,
    policy: str | RoutingPolicy,
    db: aiosqlite.Connection,
    previous_model_id: Optional[str] = None,
    user_reasoning_effort: Optional[str] = None,
) -> AutoRouteDecision:
    """
    Executa a seleção do modelo candidato combinando:
    - JEV Fast Model Cache em RAM (TTL 30s) para evitar queries repetidas
    - Verificação de sanidade (enabled == 1, quota != exhausted/cooldown)
    - Context Window Guard (context_length >= min_context_required)
    - Multimodalidade (perfil de visão)
    - Pontuação de adequação (fit) por intenção × complexidade × perfil × política
    - Afinidade de modelo (Sticky Routing) apenas quando o modelo anterior continua adequado
    - Rotação ponderada contra Thundering Herd entre candidatos equivalentes gratuitos
    - Esforço de raciocínio adaptativo para modelos com dial
    """
    global _SLOT_ROTATION_COUNTER
    t_start = time.perf_counter()

    if isinstance(policy, RoutingPolicy):
        policy_str = policy.value
    else:
        policy_str = str(policy or "balanced_smart").lower().strip()
    if policy_str not in _COST_PENALTY:
        policy_str = RoutingPolicy.BALANCED_SMART.value

    # 1. Catálogo roteável (cache + estados voláteis)
    models_data = await load_routing_catalog(db)
    if not models_data:
        raise ValueError("Nenhum modelo habilitado encontrado no sistema.")

    ranked = rank_candidates(models_data, intent_result, policy_str)
    if not ranked:
        raise ValueError("Nenhum modelo elegível para roteamento.")

    best = ranked[0]
    intent = intent_result.intent

    def _latency() -> float:
        return round((time.perf_counter() - t_start) * 1000 + intent_result.processing_time_ms, 3)

    # 6. Afinidade de Modelo (Sticky Routing / KV Cache Protector)
    # Mantém o modelo do turno anterior SOMENTE se ele continua adequado à nova intenção:
    # follow-ups do mesmo tema toleram mais; mudanças de intenção/complexidade trocam de modelo.
    if previous_model_id:
        prev = next((c for c in ranked if c["model"]["id"] == previous_model_id), None)
        if prev is not None:
            gap = best["fit"] - prev["fit"]
            if intent_result.inherited_from_history:
                tolerance = 8.0
            elif intent in (IntentKey.CODE_ENGINEERING, IntentKey.DEEP_REASONING, IntentKey.MULTIMODAL_VISION):
                tolerance = 2.5
            else:
                tolerance = 4.0
            if gap <= tolerance:
                return _decision(
                    prev["model"], intent_result, policy_str,
                    reason_pt=f"{intent_result.reason_label_pt} (KV-Cache)",
                    signals=intent_result.matched_signals + ["sticky_routing_cache"],
                    latency_ms=_latency(),
                    fit=prev["fit"],
                    alternatives=_alternatives_payload(ranked, prev["model"]["id"]),
                    user_effort=user_reasoning_effort,
                )

    # 7. Balanceamento Anti-Thundering Herd (Weighted Slot Rotation)
    # Em tarefas leves gratuitas, rotaciona entre candidatos praticamente equivalentes
    # (mesmo porte, fit a <= 2 pontos do melhor) para diluir rate limit 429.
    if intent in (IntentKey.TRIVIAL_QUICK, IntentKey.GENERAL_CHAT) and intent_result.complexity != ComplexityTier.HEAVY:
        close = [
            c for c in ranked
            if (best["fit"] - c["fit"]) <= 2.0
            and c["model"]["is_free"] == 1
            and c["profile"].size_tier == best["profile"].size_tier
        ]
        if len(close) >= 2 and best["model"]["is_free"] == 1:
            idx = _SLOT_ROTATION_COUNTER % len(close)
            _SLOT_ROTATION_COUNTER += 1
            chosen = close[idx]
            return _decision(
                chosen["model"], intent_result, policy_str,
                reason_pt=f"{intent_result.reason_label_pt} (Slot Rotativo)",
                signals=intent_result.matched_signals + ["slot_rotation_free"],
                latency_ms=_latency(),
                fit=chosen["fit"],
                alternatives=_alternatives_payload(ranked, chosen["model"]["id"]),
                user_effort=user_reasoning_effort,
            )

    # 8. Escolha pelo maior fit
    signals = list(intent_result.matched_signals)
    if previous_model_id and previous_model_id != best["model"]["id"]:
        signals.append("model_switch")
    return _decision(
        best["model"], intent_result, policy_str,
        reason_pt=intent_result.reason_label_pt,
        signals=signals,
        latency_ms=_latency(),
        fit=best["fit"],
        alternatives=_alternatives_payload(ranked, best["model"]["id"]),
        user_effort=user_reasoning_effort,
    )


def decision_to_dict(decision: AutoRouteDecision) -> Dict[str, Any]:
    """Serializa a decisão para o evento WebSocket / API (retrocompatível)."""
    return {
        "chosen_model_id": decision.chosen_model_id,
        "chosen_model_name": decision.chosen_model_name,
        "provider_id": decision.provider_id,
        "intent": decision.intent.value,
        "reason_pt": decision.reason_pt,
        "confidence": decision.confidence,
        "policy": decision.policy,
        "temperature": decision.temperature,
        "decision_latency_ms": decision.decision_latency_ms,
        "matched_signals": decision.matched_signals,
        "complexity": decision.complexity,
        "fit_score": decision.fit_score,
        "reasoning_effort": decision.reasoning_effort,
        "model_tags": decision.model_tags,
        "alternatives": decision.alternatives,
    }
