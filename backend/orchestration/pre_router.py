"""
backend/orchestration/pre_router.py
Pré-Router & Triage Agent do Nexus Local (Arquitetura de Triagem em Dois Estágios).

Objetivos:
1. Interceptação ultra-rápida (< 200ms com LLM rápido, < 1ms por regras).
2. Classificação em 3 tiers operacionais:
   - 'trivial': conversas casuais, saudações, frases curtas sem demanda técnica.
   - 'specific_lookup': dúvidas pontuais estilo Google, fatos diretos, cotações, definições rápidas.
   - 'deep_technical': código, arquitetura, depuração, matemática, análise complexa.
3. Extração semântica e léxica de 'strict_constraints' (ex: 'apenas código', 'máximo 3 linhas').
4. Eliminação de round-trips lentos de busca web gerando queries pré-planejadas.
5. Modulação dinâmica do System Prompt para eliminar diluição de instruções.
"""

from __future__ import annotations

import asyncio
import json
import re
import time
from typing import Any, List, Literal, Optional, Tuple
from pydantic import BaseModel, Field

from backend.logging_config import get_logger
from backend.ranking.smart_router import (
    _RE_CODE_BLOCKS,
    _RE_CODE_SYNTAX,
    _RE_CODE_KEYWORDS,
    _RE_DEEP_THOUGHT,
    _RE_TRIVIAL_SHORT,
    _RE_WEB_FACTUAL,
    is_trivial_greeting,
)
from backend.web_search.planner import clean_query_text

logger = get_logger(__name__)

PRE_ROUTER_META_KEYS: tuple[str, str] = (
    "pre_router_provider_id",
    "pre_router_model_id",
)

TRIAGE_TIMEOUT_SECONDS = 1.0

_RE_TEMPORAL = re.compile(
    r"\b(hoje|agora|ontem|amanhã|recentes?|atual|202[4-9]|neste\s+ano|neste\s+mês|notícias?|debate|eleições?)\b",
    re.IGNORECASE,
)


# ── Contrato de Dados (Pydantic) ─────────────────────────────────────────────

class IntentRouting(BaseModel):
    intent_tier: Literal["trivial", "specific_lookup", "deep_technical"] = Field(
        default="specific_lookup",
        description="trivial: conversa casual ou fato óbvio; "
                    "specific_lookup: dúvida pontual estilo Google que exige resposta direta + síntese curta; "
                    "deep_technical: código, arquitetura, matemática, análise complexa ou escrita longa."
    )
    reasoning_effort: Literal["low", "medium", "high"] = Field(
        default="medium",
        description="Nível de raciocínio necessário para o modelo principal."
    )
    needs_web_search: bool = Field(
        default=False,
        description="True se envolver eventos recentes, preços, versões atuais, fatos específicos ou risco de alucinação."
    )
    search_queries: List[str] = Field(
        default_factory=list,
        description="Até 2 queries curtas e otimizadas para motor de busca caso needs_web_search seja True."
    )
    strict_constraints: List[str] = Field(
        default_factory=list,
        description="Restrições explícitas pedidas pelo usuário (ex: 'apenas código', 'máximo 3 linhas', 'sem libs externas')."
    )
    mode_status_pt: str = Field(
        default="",
        description="Rótulo visual descritivo para exibição na interface do usuário."
    )
    triage_source: Literal["short_circuit", "fast_llm", "heuristic_rules"] = Field(
        default="heuristic_rules",
        description="Origem da decisão de triagem."
    )
    latency_ms: float = Field(
        default=0.0,
        description="Latência em ms para computar a triagem."
    )


# ── Regexes de Extração de Restrições Estritas (Strict Constraints) ──────────

_RE_ONLY_CONSTRAINT = re.compile(
    r"\b(?:apenas|somente|only)\s+([^.,;!\n]{2,30}?)(?:[.,;!\n]|$)",
    re.IGNORECASE,
)
_RE_WITHOUT_CONSTRAINT = re.compile(
    r"\b(?:sem\s+(?:usar\s+)?|sem\s+|não\s+use\s+|without\s+)([^.,;!\n]{2,35}?)(?:[.,;!\n]|$)",
    re.IGNORECASE,
)
_RE_LIMIT_LINES = re.compile(
    r"\b(?:máximo|no\s+máximo|max|em\s+até)\s+(?:de\s+)?(\d+)\s*(linhas|frases|palavras|parágrafos|tópicos|itens)\b",
    re.IGNORECASE,
)
_RE_FORMAT_TABLE = re.compile(
    r"\b(?:em\s+(?:formato\s+de\s+|uma\s+)?tabela|em\s+tabela|in\s+(?:a\s+)?table)\b",
    re.IGNORECASE,
)
_RE_FORMAT_JSON = re.compile(
    r"\b(?:em\s+(?:formato\s+)?json|somente\s+json|retorne\s+(?:em\s+)?json|only\s+json)\b",
    re.IGNORECASE,
)


def extract_heuristic_constraints(prompt: str) -> list[str]:
    """Extrai restrições explícitas e rígidas do prompt do usuário."""
    constraints: list[str] = []
    text = prompt.strip()

    # Formatos estruturados (tabela / JSON)
    if _RE_FORMAT_TABLE.search(text):
        constraints.append("Responder em formato de tabela")
    if _RE_FORMAT_JSON.search(text):
        constraints.append("Responder estritamente em formato JSON válido")

    # Limites numéricos (linhas, tópicos, parágrafos)
    m_limit = _RE_LIMIT_LINES.search(text)
    if m_limit:
        num, unit = m_limit.group(1), m_limit.group(2).lower()
        constraints.append(f"No máximo {num} {unit}")

    # Restrições de exclusão ("sem usar bibliotecas externas", "sem introdução")
    for m in _RE_WITHOUT_CONSTRAINT.finditer(text):
        target = m.group(1).strip()
        if len(target) > 2 and not target.lower().startswith("dúvida"):
            constraints.append(f"Sem {target}")

    # Restrições de foco ("apenas o código", "somente a resposta")
    for m in _RE_ONLY_CONSTRAINT.finditer(text):
        target = m.group(1).strip()
        t_clean = re.sub(r"^(?:o|a|os|as|the)\s+", "", target, flags=re.I).strip().lower()
        if t_clean in ("código", "codigo", "code", "json", "tabela", "table", "resposta", "resultado"):
            constraints.append(f"Apenas {target}")

    # Deduplica preservando ordem
    seen = set()
    deduped = []
    for c in constraints:
        c_clean = c.strip().capitalize()
        if c_clean.lower() not in seen:
            seen.add(c_clean.lower())
            deduped.append(c_clean)
    return deduped[:4]


def format_triage_mode_status(routing: IntentRouting) -> str:
    """Gera o texto de status dinâmico para a UX do Nexus Local."""
    if routing.intent_tier == "trivial":
        return "⚡ Modo Conversa Casual"
    elif routing.intent_tier == "specific_lookup":
        if routing.needs_web_search and routing.search_queries:
            q = routing.search_queries[0]
            if len(q) > 42:
                q = q[:39] + "…"
            return f"⚡ Modo Direto • Web: {q}"
        return "⚡ Modo Direto (Síntese Rápida)"
    else:  # deep_technical
        effort_label = "Raciocínio Alto" if routing.reasoning_effort == "high" else "Análise Técnica"
        return f"🧠 Modo Engenharia Profunda • {effort_label}"


# ── Classificador Heurístico (Fallback / < 1ms) ──────────────────────────────

def classify_heuristic_triage(
    prompt: str,
    history: list[dict] | None = None,
) -> IntentRouting:
    """Classificação léxica e determinística instantânea (< 0.5ms)."""
    t0 = time.perf_counter()
    text = (prompt or "").strip()
    constraints = extract_heuristic_constraints(text)

    # 1. Saudação trivial / conversa leve
    if is_trivial_greeting(text) or (len(text) < 20 and _RE_TRIVIAL_SHORT.match(text)):
        routing = IntentRouting(
            intent_tier="trivial",
            reasoning_effort="low",
            needs_web_search=False,
            search_queries=[],
            strict_constraints=constraints,
            triage_source="heuristic_rules",
            latency_ms=round((time.perf_counter() - t0) * 1000, 2),
        )
        routing.mode_status_pt = format_triage_mode_status(routing)
        return routing

    # 2. Sinais de Engenharia / Código / Análise Profunda
    has_code = bool(
        _RE_CODE_BLOCKS.search(text)
        or _RE_CODE_SYNTAX.search(text)
        or _RE_CODE_KEYWORDS.search(text)
    )
    has_deep_thought = bool(_RE_DEEP_THOUGHT.search(text))

    if has_code or has_deep_thought:
        routing = IntentRouting(
            intent_tier="deep_technical",
            reasoning_effort="high" if (has_deep_thought or len(text) > 200) else "medium",
            needs_web_search=bool(_RE_TEMPORAL.search(text)),
            search_queries=[clean_query_text(text)] if _RE_TEMPORAL.search(text) else [],
            strict_constraints=constraints,
            triage_source="heuristic_rules",
            latency_ms=round((time.perf_counter() - t0) * 1000, 2),
        )
        routing.mode_status_pt = format_triage_mode_status(routing)
        return routing

    # 3. Dúvida Pontual / Busca Factual / Lookup estilo Google
    is_temporal = bool(_RE_TEMPORAL.search(text))
    is_factual = bool(_RE_WEB_FACTUAL.search(text) or "?" in text or is_temporal)

    cleaned_q = clean_query_text(text)
    routing = IntentRouting(
        intent_tier="specific_lookup",
        reasoning_effort="low" if is_factual else "medium",
        needs_web_search=is_temporal or bool(re.search(r"\b(quem|quando|onde|quanto|preço|cotação|debate|notícias|hoje|202[4-9])\b", text, re.I)),
        search_queries=[cleaned_q] if (is_temporal or is_factual) and len(cleaned_q) > 4 else [],
        strict_constraints=constraints,
        triage_source="heuristic_rules",
        latency_ms=round((time.perf_counter() - t0) * 1000, 2),
    )
    routing.mode_status_pt = format_triage_mode_status(routing)
    return routing


# ── Triagem com Modelo Utilitário Rápido (Stage 1 / < 200ms) ────────────────

TRIAGE_SYSTEM_PROMPT = """Você é o Pré-Router e Classificador de Triagem em tempo real do Nexus Local.
Analise a mensagem do usuário e responda ESTRITAMENTE com um JSON válido (sem texto adicional, sem formatação markdown além de JSON).

SCHEMA DO JSON:
{
  "intent_tier": "trivial" | "specific_lookup" | "deep_technical",
  "reasoning_effort": "low" | "medium" | "high",
  "needs_web_search": true | false,
  "search_queries": ["query 1", "query 2"],
  "strict_constraints": ["restrição 1", "restrição 2"]
}

DIRETRIZES:
1. intent_tier:
   - "trivial": saudação ("olá", "tudo bem?"), conversa casual, agradecimento ou frase sem solicitação técnica/factual.
   - "specific_lookup": dúvida pontual estilo Google, definição rápida, preço, cotação, comando único ou fato específico que exige resposta direta e síntese curta.
   - "deep_technical": código, depuração, arquitetura, matemática, engenharia, análise crítica complexa ou escrita longa.
2. reasoning_effort: "low" para trivial ou lookup direto; "medium" para explicações normais; "high" para problemas difíceis ou código complexo.
3. needs_web_search: true se envolver notícias, eventos de 2024-2026, eleições, pessoas públicas no presente, preços ou fatos mutáveis. Se true, forneça até 2 search_queries curtas e objetivas.
4. strict_constraints: extraia apenas restrições explícitas feitas pelo usuário (ex: "apenas código", "máximo 3 linhas", "sem bibliotecas externas"). Se não houver, deixe [].
"""


def _slice_first_json_object(raw: str) -> Optional[str]:
    """Extrai a primeira substring de JSON válido do texto, tolerando fences e thinking."""
    cleaned = re.sub(r"<think>[\s\S]*?</think>", "", raw, flags=re.IGNORECASE)
    cleaned = re.sub(r"```(?:json)?", "", cleaned).replace("```", "").strip()

    start = cleaned.find("{")
    end = cleaned.rfind("}")
    if start != -1 and end != -1 and end > start:
        return cleaned[start : end + 1]
    return None


async def run_pre_router_triage(
    db: Any,
    user_message: str,
    user_id: Optional[str] = None,
    history: Optional[list[dict]] = None,
    fallback_provider_id: Optional[str] = None,
    fallback_model_id: Optional[str] = None,
) -> IntentRouting:
    """Executa o pipeline de triagem em dois estágios com fallback resiliente."""
    t0 = time.perf_counter()
    msg = (user_message or "").strip()

    # Estágio 0: Short-circuit para saudações e frases ultra-curtas (< 0.1ms)
    if is_trivial_greeting(msg) or (len(msg) < 18 and _RE_TRIVIAL_SHORT.match(msg)):
        res = classify_heuristic_triage(msg, history)
        res.triage_source = "short_circuit"
        res.latency_ms = round((time.perf_counter() - t0) * 1000, 2)
        return res

    # Estágio 1: Tentativa com modelo utilitário rápido (< 200ms)
    try:
        from backend.providers.utility_model import resolve_utility_model

        provider, model_name, _source = await resolve_utility_model(
            db,
            user_id,
            fallback_provider_id or "groq",
            fallback_model_id or "groq/llama-3.1-8b-instant",
            override_meta_keys=PRE_ROUTER_META_KEYS,
        )

        messages = [
            {"role": "system", "content": TRIAGE_SYSTEM_PROMPT},
            {"role": "user", "content": f"Mensagem do usuário:\n{msg[:800]}"},
        ]

        async def _call_llm() -> str:
            chunks: list[str] = []
            async for token in provider.stream_chat(
                model=model_name,
                messages=messages,
                temperature=0.1,
                max_tokens=150,
            ):
                chunks.append(token)
            return "".join(chunks).strip()

        raw_output = await asyncio.wait_for(_call_llm(), timeout=TRIAGE_TIMEOUT_SECONDS)
        json_slice = _slice_first_json_object(raw_output)

        if json_slice:
            data = json.loads(json_slice)
            tier = data.get("intent_tier")
            if tier not in ("trivial", "specific_lookup", "deep_technical"):
                tier = "specific_lookup"

            effort = data.get("reasoning_effort")
            if effort not in ("low", "medium", "high"):
                effort = "low" if tier == "trivial" else ("high" if tier == "deep_technical" else "medium")

            needs_web = bool(data.get("needs_web_search", False))
            queries = [str(q).strip() for q in data.get("search_queries", []) if str(q).strip()][:2]
            constraints = [str(c).strip() for c in data.get("strict_constraints", []) if str(c).strip()][:4]

            # Mescla restrições léxicas encontradas no prompt
            lexical_constraints = extract_heuristic_constraints(msg)
            for lc in lexical_constraints:
                if lc.lower() not in [c.lower() for c in constraints]:
                    constraints.append(lc)

            routing = IntentRouting(
                intent_tier=tier,
                reasoning_effort=effort,
                needs_web_search=needs_web,
                search_queries=queries,
                strict_constraints=constraints[:4],
                triage_source="fast_llm",
                latency_ms=round((time.perf_counter() - t0) * 1000, 2),
            )
            routing.mode_status_pt = format_triage_mode_status(routing)
            return routing

    except Exception as e:
        logger.debug(f"[pre_router] Falha ou timeout no fast LLM ({e}), usando regras heurísticas")

    # Estágio 2: Fallback resiliente para regras heurísticas
    routing = classify_heuristic_triage(msg, history)
    routing.latency_ms = round((time.perf_counter() - t0) * 1000, 2)
    return routing


# ── Modulação Dinâmica do System Prompt ──────────────────────────────────────

def build_modular_system_prompt_addition(routing: IntentRouting) -> str:
    """Gera blocos de prompt sob medida baseados no tier e restrições identificadas."""
    blocks: list[str] = []

    if routing.intent_tier == "trivial":
        blocks.append(
            "[MODO CONVERSA CASUAL / TRIVIAL]\n"
            "- Responda em no máximo 1 a 2 frases diretas, naturais e sem rodeios.\n"
            "- Não adicione explicações extras, listas ou introduções formais."
        )
    elif routing.intent_tier == "specific_lookup":
        blocks.append(
            "[MODO RESPOSTA RÁPIDA & EMBASAMENTO]\n"
            "- Entregue a resposta exata, o fato ou o comando já na primeira frase em **negrito** (sem saudações longas).\n"
            "- Logo abaixo, adicione de 2 a 4 bullet points curtos com o embasamento essencial ou contexto das fontes.\n"
            "- Evite parágrafos prolixos. Pare imediatamente após responder o solicitado."
        )
    elif routing.intent_tier == "deep_technical":
        blocks.append(
            "[MODO ENGENHARIA PROFUNDA & RIGOR TÉCNICO]\n"
            "- Inicie com um veredito técnico direto ou visão arquitetural na primeira linha.\n"
            "- Em seguida, desenvolva a solução completa, cobrindo casos de borda, código pronto para produção, boas práticas e tabelas comparativas quando útil.\n"
            "- Priorize precisão técnica absoluta e profundidade resolutiva."
        )

    if routing.strict_constraints:
        items = "\n".join(f"- {c}" for c in routing.strict_constraints)
        blocks.append(
            f"[RESTRIÇÕES OBRIGATÓRIAS DESTA RESPOSTA]:\n"
            f"{items}\n"
            "Cumpra estas regras estritamente acima de qualquer formatação padrão."
        )

    return ("\n\n" + "\n\n".join(blocks)) if blocks else ""
