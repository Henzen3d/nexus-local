"""
backend/ranking/smart_router.py
Motor de Classificação de Intenções e Auto-Roteamento Inteligente (NexusLocal Smart Router).

Implementa:
- Taxonomia canônica de 6 intenções primárias + general_chat
- Níveis de complexidade (LIGHT, MEDIUM, HEAVY)
- Classificação ultrarrápida (< 2ms) com pré-compilação de regex
- Histerese de tópico (Topic Momentum) e blindagem contra amnésia
- Detecção retrospectiva de multimodalidade
- Context Window Guard (< model.context_length)
- Afinidade de modelo (Sticky Routing / KV Cache Protector)
- Rotação ponderada de slots contra Thundering Herd
- Políticas: economical_free, balanced_smart, max_performance
"""

from __future__ import annotations

import re
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import List, Optional, Dict, Any

import aiosqlite
from backend.logging_config import get_logger

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


# ── Expressões Regulares Pré-Compiladas (< 0.2ms) ───────────────────────────

# Sinais de Código
_RE_CODE_BLOCKS = re.compile(r"```[a-zA-Z0-9_\-\+\#]*\n[\s\S]*?```", re.MULTILINE)
_RE_CODE_SYNTAX = re.compile(
    r"\b(def|class|import|return|function|const|let|var|public|private|protected|"
    r"struct|impl|fn|async\s+def|SELECT\s+[\s\S]*?FROM|WHERE\s+|INSERT\s+INTO|UPDATE\s+[\s\S]*?SET|"
    r"DELETE\s+FROM|console\.log|print\(|Traceback|NullPointerException|TypeError|ValueError|"
    r"IndexError|KeyError|AttributeError|Exception|dockerfile|kubernetes|terraform|regex|"
    r"fastapi|express|react|vue|angular|svelte|django|flask|spring|sql|graphql|typescript|"
    r"javascript|python|golang|rust|c\+\+|csharp|swift|kotlin|php|html|css|json|yaml)\b",
    re.IGNORECASE,
)
_RE_CODE_KEYWORDS = re.compile(
    r"\b(código|função|script|bug|debug|erro|stacktrace|refatore|refatorar|compilar|"
    r"api|endpoint|backend|frontend|query|banco\s+de\s+dados|repositório|git\s+commit|"
    r"pull\s+request|npm\s+run|pip\s+install|classe|variável|parâmetro)\b",
    re.IGNORECASE,
)

# Sinais de Raciocínio Profundo & Dedução
_RE_DEEP_THOUGHT = re.compile(
    r"\b(calcule|resolva\s+o\s+problema|prove\s+que|demonstre|enigma|teorema|"
    r"probabilidade|an[aá]lise\s+cr[ií]tica|vantagens\s+e\s+desvantagens|deduza|"
    r"fa[cç]a\s+uma\s+an[aá]lise\s+l[oó]gica|passo\s+a\s+passo\s+detalhado|derive|"
    r"equa[cç][aã]o|hip[oó]tese|premissa|contradi[cç][aã]o|racioc[ií]nio|"
    r"otimiza[cç][aã]o\s+matem[aá]tica|jogos\s+de\s+l[oó]gica|paradoxo)\b",
    re.IGNORECASE,
)

# Sinais Triviais / Rápidos
_RE_TRIVIAL_SHORT = re.compile(
    r"^(oi|ol[aá]|bom\s+dia|boa\s+tarde|boa\s+noite|valeu|obrigad[oa]|tchau|"
    r"ok|beleza|sim|n[aã]o|como\s+vai|tudo\s+bem|e\s+a[ií]|obrigado\s+pela\s+ajuda|"
    r"perfeito|entendi|combinado|"
    r"ol[aá][,\s]+(bom\s+dia|boa\s+tarde|boa\s+noite|tudo\s+bem|como\s+vai)|"
    r"oi[,\s]+(bom\s+dia|boa\s+tarde|boa\s+noite|tudo\s+bem|como\s+vai))[!\?\.\s]*$",
    re.IGNORECASE,
)

# Sinais de Redação & Criatividade Longform
_RE_CREATIVE = re.compile(
    r"\b(escreva\s+uma?\s+redação|artigo|e-?mail\s+formal|redija|roteiro|poema|conto|"
    r"reescreva\s+com\s+tom|crônica|storytelling|discurso|copywriting|narrativa|"
    r"carta\s+de\s+apresentação|proposta\s+comercial|ensaio|biografia)\b",
    re.IGNORECASE,
)

# Mapeamento canônico sugerido de famílias por intenção
INTENT_FAMILY_MAPPING: Dict[IntentKey, List[str]] = {
    IntentKey.TRIVIAL_QUICK: [
        "llama-3.1-8b",
        "llama-3.2-3b",
        "gemma-2-9b",
    ],
    IntentKey.CODE_ENGINEERING: [
        "qwen-2.5-coder-32b",
        "deepseek-coder",
        "llama-3.3-70b",
        "claude-3.5-sonnet",
        "qwen-2.5-coder",
    ],
    IntentKey.DEEP_REASONING: [
        "deepseek-r1",
        "gemini-2.0-flash-thinking",
        "qwq-32b",
    ],
    IntentKey.CREATIVE_LONGFORM: [
        "llama-3.3-70b",
        "gemini-2.5-flash",
        "gemini-2.0-flash",
        "mistral-large",
    ],
    IntentKey.MULTIMODAL_VISION: [
        "gemini-2.0-flash",
        "llama-3.2-11b-vision",
        "gemini-1.5-flash",
    ],
    IntentKey.WEB_RESEARCH: [
        "gemini-2.0-flash",
        "llama-3.3-70b",
    ],
    IntentKey.GENERAL_CHAT: [
        "llama-3.3-70b",
        "llama-3.1-8b",
        "gemini-2.0-flash",
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

    # ─────────────────────────────────────────────────────────────────────────
    # ESTÁGIO 0: Histerese de Tópico & Memória de Sessão (Anti-Amnésia)
    # ─────────────────────────────────────────────────────────────────────────

    # [0.A] Multimodalidade Retrospectiva
    has_current_attachment = bool(attachments)
    has_history_images = _history_has_images(history)

    if has_current_attachment or has_history_images:
        signal = "attachment_current" if has_current_attachment else "retrospective_vision_history"
        signals.append(signal)
        t_end = time.perf_counter()
        return IntentClassificationResult(
            intent=IntentKey.MULTIMODAL_VISION,
            complexity=ComplexityTier.MEDIUM,
            confidence=0.98,
            matched_signals=signals,
            reason_label_pt="Imagens & Visão Multimodal",
            suggested_family="gemini-2.0-flash",
            min_context_length_required=min_context_required,
            inherited_from_history=has_history_images and not has_current_attachment,
            recommended_temperature=0.4,
            processing_time_ms=round((t_end - t_start) * 1000, 3),
        )

    # [0.B] Topic Momentum (Inércia de Contexto Técnico)
    # Perguntas curtas (< 35 caracteres) em conversas técnicas retêm o modelo especialista
    if len(prompt_str) < 35 and len(prompt_str) > 0:
        prev_key: Optional[IntentKey] = None
        if previous_intent:
            try:
                prev_key = IntentKey(previous_intent)
            except ValueError:
                pass
        if not prev_key:
            prev_key = _history_has_technical_context(history)

        if prev_key in (IntentKey.CODE_ENGINEERING, IntentKey.DEEP_REASONING):
            signals.append(f"topic_momentum_{prev_key.value}")
            label = (
                "Código & Programação (Continuidade)"
                if prev_key == IntentKey.CODE_ENGINEERING
                else "Raciocínio Lógico (Continuidade)"
            )
            family = (
                "qwen-2.5-coder-32b"
                if prev_key == IntentKey.CODE_ENGINEERING
                else "deepseek-r1"
            )
            temp = 0.2 if prev_key == IntentKey.CODE_ENGINEERING else 0.6
            t_end = time.perf_counter()
            return IntentClassificationResult(
                intent=prev_key,
                complexity=ComplexityTier.LIGHT,
                confidence=0.92,
                matched_signals=signals,
                reason_label_pt=label,
                suggested_family=family,
                min_context_length_required=min_context_required,
                inherited_from_history=True,
                recommended_temperature=temp,
                processing_time_ms=round((t_end - t_start) * 1000, 3),
            )

    # ─────────────────────────────────────────────────────────────────────────
    # ESTÁGIO 1: Filtros Determinísticos Instantâneos (< 0.2ms)
    # ─────────────────────────────────────────────────────────────────────────

    # [1.A] Análise de Toggle Web
    if web_search:
        signals.append("web_search_active")
        t_end = time.perf_counter()
        return IntentClassificationResult(
            intent=IntentKey.WEB_RESEARCH,
            complexity=ComplexityTier.MEDIUM,
            confidence=0.96,
            matched_signals=signals,
            reason_label_pt="Síntese & Pesquisa Web",
            suggested_family="gemini-2.0-flash",
            min_context_length_required=min_context_required,
            recommended_temperature=0.5,
            processing_time_ms=round((t_end - t_start) * 1000, 3),
        )

    # [1.B] Heurística Trivial Pura
    if _RE_TRIVIAL_SHORT.match(prompt_str):
        signals.append("trivial_short_greeting")
        t_end = time.perf_counter()
        return IntentClassificationResult(
            intent=IntentKey.TRIVIAL_QUICK,
            complexity=ComplexityTier.LIGHT,
            confidence=1.0,
            matched_signals=signals,
            reason_label_pt="Saudação / Pergunta Rápida",
            suggested_family="llama-3.1-8b",
            min_context_length_required=min_context_required,
            recommended_temperature=0.5,
            processing_time_ms=round((t_end - t_start) * 1000, 3),
        )

    # ─────────────────────────────────────────────────────────────────────────
    # ESTÁGIO 2: Extrator de Sinais Léxicos e Restrições de Complexidade
    # ─────────────────────────────────────────────────────────────────────────

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
            if (len(prompt_str) > 400 or has_code_block)
            else ComplexityTier.MEDIUM
        )
        t_end = time.perf_counter()
        return IntentClassificationResult(
            intent=IntentKey.CODE_ENGINEERING,
            complexity=complexity,
            confidence=0.95,
            matched_signals=signals,
            reason_label_pt="Código & Engenharia",
            suggested_family="qwen-2.5-coder-32b",
            min_context_length_required=min_context_required,
            recommended_temperature=0.2,
            processing_time_ms=round((t_end - t_start) * 1000, 3),
        )

    # Raciocínio Profundo & Dedução Lógica
    thought_match = _RE_DEEP_THOUGHT.search(prompt_str)
    if thought_match:
        signals.append(f"deep_thought:{thought_match.group(0)}")
        complexity = (
            ComplexityTier.HEAVY if len(prompt_str) > 300 else ComplexityTier.MEDIUM
        )
        t_end = time.perf_counter()
        return IntentClassificationResult(
            intent=IntentKey.DEEP_REASONING,
            complexity=complexity,
            confidence=0.92,
            matched_signals=signals,
            reason_label_pt="Raciocínio & Dedução",
            suggested_family="deepseek-r1",
            min_context_length_required=min_context_required,
            recommended_temperature=0.6,
            processing_time_ms=round((t_end - t_start) * 1000, 3),
        )

    # Redação & Criatividade Longform
    creative_match = _RE_CREATIVE.search(prompt_str)
    if creative_match:
        signals.append(f"creative_intent:{creative_match.group(0)}")
        complexity = (
            ComplexityTier.HEAVY if len(prompt_str) > 300 else ComplexityTier.MEDIUM
        )
        t_end = time.perf_counter()
        return IntentClassificationResult(
            intent=IntentKey.CREATIVE_LONGFORM,
            complexity=complexity,
            confidence=0.89,
            matched_signals=signals,
            reason_label_pt="Redação & Conteúdo Criativo",
            suggested_family="llama-3.3-70b",
            min_context_length_required=min_context_required,
            recommended_temperature=0.7,
            processing_time_ms=round((t_end - t_start) * 1000, 3),
        )

    # Fallback rápido para conversas gerais ou perguntas curtas
    if len(prompt_str) < 60:
        signals.append("short_general_query")
        intent = IntentKey.TRIVIAL_QUICK
        label = "Pergunta Curta / Direta"
        family = "llama-3.1-8b"
        temp = 0.5
        complexity = ComplexityTier.LIGHT
    else:
        signals.append("general_conversation")
        intent = IntentKey.GENERAL_CHAT
        label = "Conversação Geral"
        family = "llama-3.3-70b"
        temp = 0.5
        complexity = ComplexityTier.MEDIUM

    t_end = time.perf_counter()
    return IntentClassificationResult(
        intent=intent,
        complexity=complexity,
        confidence=0.82,
        matched_signals=signals,
        reason_label_pt=label,
        suggested_family=family,
        min_context_length_required=min_context_required,
        recommended_temperature=temp,
        processing_time_ms=round((t_end - t_start) * 1000, 3),
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


# ── Seleção de Modelo com Blindagem de 2ª Escala ─────────────────────────────

async def select_best_model(
    intent_result: IntentClassificationResult,
    policy: str | RoutingPolicy,
    db: aiosqlite.Connection,
    previous_model_id: Optional[str] = None,
) -> AutoRouteDecision:
    """
    Executa a seleção do modelo candidato combinando:
    - JEV Fast Model Cache em RAM (TTL 30s) para evitar queries repetidas
    - Verificação de sanidade (enabled == 1, quota != exhausted/cooldown)
    - Context Window Guard (context_length >= min_context_required)
    - Multimodalidade (supports_vision == 1 ou provedor de visão)
    - Afinidade de modelo (Sticky Routing / KV Cache Protector)
    - Rotação ponderada contra Thundering Herd em provedores free
    - Ordenação final por NexusLocal Score / Quality Score
    """
    global _SLOT_ROTATION_COUNTER, _MODEL_CACHE, _MODEL_CACHE_TIME
    t_start = time.perf_counter()

    if isinstance(policy, RoutingPolicy):
        policy_str = policy.value
    else:
        policy_str = str(policy or "balanced_smart").lower().strip()

    # 1. Carrega todos os modelos habilitados (com JEV Model Cache em RAM)
    now = time.monotonic()
    if _MODEL_CACHE is not None and (now - _MODEL_CACHE_TIME) < _MODEL_CACHE_TTL:
        models_data = [dict(m) for m in _MODEL_CACHE]
    else:
        query = """
            SELECT m.id, m.provider_id, m.name, m.display_name, m.context_length,
                   COALESCE(m.confirmed_free, 0) as confirmed_free,
                   COALESCE(p.is_free, 0) as prov_is_free,
                   COALESCE(mr.nexuslocal_score, 50.0) as nexuslocal_score,
                   COALESCE(mr.quality_score, 50.0) as quality_score,
                   COALESCE(mqs.status, 'available') as quota_status,
                   COALESCE(m.supports_vision, 0) as supports_vision
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
            models_data.append({
                "id": r[0],
                "provider_id": r[1],
                "name": r[2],
                "display_name": r[3],
                "context_length": r[4] or 8192,
                "confirmed_free": r[5],
                "prov_is_free": r[6],
                "is_free": 1 if (r[5] == 1 or r[6] == 1) else 0,
                "nexuslocal_score": float(r[7]),
                "quality_score": float(r[8]),
                "quota_status": r[9],
                "supports_vision": r[10],
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

    # 2. Filtro de Sanidade e Cooldown (Descarta esgotados)
    available_models = [
        m for m in models_data
        if m["quota_status"] not in ("exhausted", "cooldown")
    ]
    if not available_models:
        available_models = models_data  # fallback se todos estiverem esgotados

    # 3. Context Window Guard (Descarta modelos com janela insuficiente para evitar HTTP 400)
    context_guarded = [
        m for m in available_models
        if m["context_length"] >= intent_result.min_context_length_required
    ]
    if context_guarded:
        working_pool = context_guarded
    else:
        # Se nenhum suportar a janela exigida, usa os maiores disponíveis
        working_pool = sorted(available_models, key=lambda m: m["context_length"], reverse=True)[:5]

    # 4. Filtro de Multimodalidade Retrospectiva
    if intent_result.intent == IntentKey.MULTIMODAL_VISION:
        vision_candidates = [
            m for m in working_pool
            if m["supports_vision"] == 1
            or m["provider_id"] == "gemini"
            or "vision" in m["name"].lower()
            or "vision" in m["id"].lower()
            or "flash" in m["name"].lower()
        ]
        if vision_candidates:
            working_pool = vision_candidates

    # 5. Mapeamento de Famílias / Especialistas por Intenção
    target_families = INTENT_FAMILY_MAPPING.get(intent_result.intent, [])
    specialist_candidates = []
    for m in working_pool:
        m_id_low = m["id"].lower()
        m_name_low = m["name"].lower()
        if any(f in m_id_low or f in m_name_low for f in target_families):
            specialist_candidates.append(m)

    candidate_pool = specialist_candidates if specialist_candidates else working_pool

    # 6. Aplicação da Política de Roteamento
    if policy_str == RoutingPolicy.ECONOMICAL_FREE.value:
        free_candidates = [m for m in candidate_pool if m["is_free"] == 1]
        if free_candidates:
            candidate_pool = free_candidates
        else:
            # Fallback para o modelo pago mais barato / disponível
            all_free = [m for m in working_pool if m["is_free"] == 1]
            if all_free:
                candidate_pool = all_free

    elif policy_str == RoutingPolicy.BALANCED_SMART.value:
        if intent_result.intent == IntentKey.TRIVIAL_QUICK:
            free_fast = [m for m in candidate_pool if m["is_free"] == 1]
            if free_fast:
                candidate_pool = free_fast
        elif intent_result.intent in (IntentKey.CODE_ENGINEERING, IntentKey.DEEP_REASONING):
            # Prioriza modelos especialistas com alto score
            high_quality = [m for m in candidate_pool if m["quality_score"] >= 80]
            if high_quality:
                candidate_pool = high_quality

    elif policy_str == RoutingPolicy.MAX_PERFORMANCE.value:
        # Busca o maior score absoluto independente de custo
        pass

    # 7. Afinidade de Modelo (Sticky Routing / KV Cache Protector)
    # Se o modelo do turno anterior estiver no pool com score competitivo (delta <= 15%), mantém!
    if previous_model_id and candidate_pool:
        prev_matches = [m for m in candidate_pool if m["id"] == previous_model_id]
        if prev_matches:
            prev_m = prev_matches[0]
            best_score = max(m["nexuslocal_score"] for m in candidate_pool)
            delta = best_score - prev_m["nexuslocal_score"]
            if delta <= (best_score * 0.15):
                t_end = time.perf_counter()
                latency_ms = round((t_end - t_start) * 1000 + intent_result.processing_time_ms, 3)
                return AutoRouteDecision(
                    chosen_model_id=prev_m["id"],
                    chosen_model_name=prev_m["display_name"],
                    provider_id=prev_m["provider_id"],
                    intent=intent_result.intent,
                    reason_pt=f"{intent_result.reason_label_pt} (KV-Cache)",
                    confidence=intent_result.confidence,
                    policy=policy_str,
                    temperature=intent_result.recommended_temperature,
                    decision_latency_ms=latency_ms,
                    matched_signals=intent_result.matched_signals + ["sticky_routing_cache"],
                )

    # 8. Balanceamento Anti-Thundering Herd (Weighted Slot Rotation)
    # Em tarefas triviais/gerais gratuitas, rotaciona entre provedores com scores muito próximos (<= 5% delta)
    if intent_result.intent in (IntentKey.TRIVIAL_QUICK, IntentKey.GENERAL_CHAT):
        top_candidates = sorted(candidate_pool, key=lambda m: m["nexuslocal_score"], reverse=True)
        if len(top_candidates) >= 2:
            best_s = top_candidates[0]["nexuslocal_score"]
            close_candidates = [
                m for m in top_candidates
                if (best_s - m["nexuslocal_score"]) <= (best_s * 0.05) and m["is_free"] == 1
            ]
            if len(close_candidates) >= 2:
                idx = _SLOT_ROTATION_COUNTER % len(close_candidates)
                _SLOT_ROTATION_COUNTER += 1
                chosen = close_candidates[idx]
                t_end = time.perf_counter()
                latency_ms = round((t_end - t_start) * 1000 + intent_result.processing_time_ms, 3)
                return AutoRouteDecision(
                    chosen_model_id=chosen["id"],
                    chosen_model_name=chosen["display_name"],
                    provider_id=chosen["provider_id"],
                    intent=intent_result.intent,
                    reason_pt=f"{intent_result.reason_label_pt} (Slot Rotativo)",
                    confidence=intent_result.confidence,
                    policy=policy_str,
                    temperature=intent_result.recommended_temperature,
                    decision_latency_ms=latency_ms,
                    matched_signals=intent_result.matched_signals + ["slot_rotation_free"],
                )

    # 9. Escolha pelo maior NexusLocal Score
    candidate_pool.sort(key=lambda m: m["nexuslocal_score"], reverse=True)
    chosen = candidate_pool[0]

    t_end = time.perf_counter()
    latency_ms = round((t_end - t_start) * 1000 + intent_result.processing_time_ms, 3)

    return AutoRouteDecision(
        chosen_model_id=chosen["id"],
        chosen_model_name=chosen["display_name"],
        provider_id=chosen["provider_id"],
        intent=intent_result.intent,
        reason_pt=intent_result.reason_label_pt,
        confidence=intent_result.confidence,
        policy=policy_str,
        temperature=intent_result.recommended_temperature,
        decision_latency_ms=latency_ms,
        matched_signals=intent_result.matched_signals,
    )
