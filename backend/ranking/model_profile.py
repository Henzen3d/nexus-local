"""
backend/ranking/model_profile.py
Perfil heurístico de capacidades de um modelo a partir do catálogo (função pura).

O Smart Router precisa saber, sem chamadas externas e em microssegundos, se um
modelo é pequeno/rápido, grande/fronteira, se "pensa" (reasoning), se é
especialista em código ou se enxerga imagens. Essa informação é derivada
deterministicamente do id/nome do modelo, do provedor e das colunas já
existentes em `models` (reasoning_control, supports_vision, context_length).

Nada aqui consulta banco ou rede. O resultado é cacheado por chave
(id, nome, provedor, controle, visão) via functools.lru_cache.

Referência: melhorias/smart-router/06-diagnostico-e-calibracao-2026.md
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from functools import lru_cache
from typing import Optional, Tuple

from backend.reasoning.families import resolve_family

# ── Tiers de tamanho ─────────────────────────────────────────────────────────
SIZE_NANO = 0      # ≤ 4B  (llama-3.2-1b/3b, gemma3:4b, ministral-3b, phi-2)
SIZE_SMALL = 1     # 5–16B (llama-3.1-8b, qwen3-8b/14b, gemma-3-12b, mini/lite)
SIZE_MEDIUM = 2    # 17–45B (gpt-oss-20b, qwen3-32b, qwq-32b, gemma-3-27b, mistral-small)
SIZE_LARGE = 3     # 46–200B (llama-3.3-70b, gpt-oss-120b, qwen3.5-122b, gemini flash)
SIZE_FRONTIER = 4  # > 200B ou fronteira (kimi-k2, deepseek-v3/v4, glm-5, gemini pro)

SIZE_LABELS = {
    SIZE_NANO: "nano",
    SIZE_SMALL: "small",
    SIZE_MEDIUM: "medium",
    SIZE_LARGE: "large",
    SIZE_FRONTIER: "frontier",
}

# Modos de raciocínio (do mais "barato" ao mais "caro" para perguntas triviais)
REASONING_NONE = "none"          # não pensa
REASONING_HYBRID = "hybrid"      # pensa se solicitado (qwen3, deepseek-v3.1+, glm-4.5+, kimi-k2.5+)
REASONING_DIAL = "dial"          # dial de esforço (gemini 2.5/3, gpt-5, gpt-oss, claude 3.7+)
REASONING_ALWAYS_ON = "always_on"  # pensa sempre (r1, qwq, *-thinking, magistral, o-series)

# Provedores com inferência de latência muito baixa (LPU / wafer-scale)
FAST_PROVIDERS = frozenset({"groq", "cerebras", "sambanova"})

# ── Regex pré-compiladas ─────────────────────────────────────────────────────
_RE_MOE = re.compile(r"(\d+)\s*x\s*(\d+(?:\.\d+)?)b(?![a-z0-9])")
_RE_PARAMS = re.compile(r"(?<![a-z])(\d+(?:\.\d+)?)\s*b(?![a-z0-9])")
_RE_ACTIVE = re.compile(r"(?<![a-z])a\d+(?:\.\d+)?b(?![a-z0-9])")

_RE_NON_CHAT = re.compile(
    r"(embed|embedding|moderation|rerank|-ocr|ocr-|whisper|transcribe|/tts|-tts|"
    r"realtime|voxtral|guard|safety|-fim|image|video|audio|sdxl|stable-diffusion|flux)",
    re.IGNORECASE,
)
_RE_CODER = re.compile(
    r"(coder|codestral|devstral|sqlcoder|starcoder|-code\b|-code-|code-agent|z-coder|"
    r"vibe-cli|codex|deepseek-coder)",
    re.IGNORECASE,
)
_RE_VISION_HINT = re.compile(
    r"(vision|-vl-|-vl\b|/vl|pixtral|gemini|gpt-4o|gpt-4\.1|gpt-5|claude|llama-4|"
    r"gemma-3-(?:4|12|27)b|gemma3:(?:4|12|27)b|gemma-4|gemma4|kimi-k2\.[5-9]|glm-4\.\dv|"
    r"qwen3-vl|qwen3\.5|qwen3\.6|llava|phi-4-multimodal|minicpm-v|mistral-small-3\.[1-9]|"
    r"mistral-medium-3|agnes)",
    re.IGNORECASE,
)
_RE_SPEED_HINT = re.compile(
    r"(instant|-fast|flash-lite|lite\b|turbo|lightning|mini\b|nano\b|tiny|micro)",
    re.IGNORECASE,
)
_RE_ALWAYS_ON = re.compile(
    r"(deepseek-r1|r1-distill|deepseek-reasoner|qwq|-thinking|_thinking|thinking\b|magistral|"
    r"(^|[/\-_])o[134](?:-mini|-pro)?([\-_]|$)|minimax-m[2-9]|reasoner)",
    re.IGNORECASE,
)
_RE_DIAL = re.compile(
    r"(gemini-2\.5|gemini-3|gpt-5|gpt-oss|claude-(?:3\.7|3-7|4|opus-4|sonnet-4|haiku-4)|"
    r"grok-[3-9]|agnes-)",
    re.IGNORECASE,
)
_RE_HYBRID = re.compile(
    r"(qwen3(?![\-.]?vl)|qwen3\.5|qwen3\.6|deepseek-v3\.[1-9]|deepseek-v4|deepseek-chat|"
    r"glm-4\.[5-9]|glm-5|kimi-k2\.[5-9]|kimi-k2-thinking|nemotron-3|mistral-medium-3\.5|"
    r"gemma-4|gemma4|hy[3-9]|longcat|minimax)",
    re.IGNORECASE,
)
_RE_INSTRUCT_ONLY = re.compile(r"(-instruct|instruct$|-it\b|coder)", re.IGNORECASE)

# Famílias explícitas de tier (avaliadas ANTES do parse de parâmetros)
_TIER_OVERRIDES: Tuple[Tuple[re.Pattern[str], int], ...] = tuple(
    (re.compile(p, re.IGNORECASE), t)
    for p, t in (
        # Fronteira
        (r"kimi-k2", SIZE_FRONTIER),
        (r"deepseek-v3", SIZE_FRONTIER),
        (r"deepseek-v4-pro", SIZE_FRONTIER),
        (r"deepseek-v4(?!-flash)", SIZE_FRONTIER),
        (r"deepseek-r1(?!-distill)", SIZE_FRONTIER),
        (r"deepseek-(chat|reasoner)", SIZE_FRONTIER),
        (r"glm-5\.\d-flash", SIZE_LARGE),
        (r"glm-5", SIZE_FRONTIER),
        (r"glm-4\.[67](?!-flash|-air)", SIZE_FRONTIER),
        (r"qwen3-235b|qwen3\.5-397b|qwen3-coder-480b|qwen3-coder(?!-30b|-flash)|qwen-max", SIZE_FRONTIER),
        (r"llama-4-maverick|llama-3\.1-405b", SIZE_FRONTIER),
        (r"gemini-[0-9.]+-pro|gemini-3(?!-flash)", SIZE_FRONTIER),
        (r"gpt-5(?!-mini|-nano)|gpt-4\.1(?!-mini|-nano)|gpt-4o(?!-mini)|chatgpt-4o", SIZE_FRONTIER),
        (r"(^|[/\-_])o[13](-pro)?([\-_]|$)", SIZE_FRONTIER),
        (r"claude-(3-5-sonnet|3\.5-sonnet|3-7|3\.7|sonnet-4|opus-4|opus|sonnet)", SIZE_FRONTIER),
        (r"grok-[34](?!-mini)", SIZE_FRONTIER),
        (r"nemotron-3-ultra|nemotron-3\.5-ultra", SIZE_FRONTIER),
        (r"minimax-m[2-9]", SIZE_FRONTIER),
        (r"mistral-large-3|mistral-large-2512", SIZE_FRONTIER),
        (r"command-a", SIZE_FRONTIER),
        (r"hy4|longcat-2", SIZE_FRONTIER),
        (r"z-chat|z-coder", SIZE_FRONTIER),
        # Grandes
        (r"deepseek-v4-flash", SIZE_LARGE),
        (r"r1-distill-llama-70b", SIZE_LARGE),
        (r"llama-4-scout", SIZE_LARGE),
        (r"gpt-oss[:\-]120b", SIZE_LARGE),
        (r"nemotron-3-super|nemotron-3-120b|nemotron-70b", SIZE_LARGE),
        (r"qwen3\.5-122b|qwen2\.5-72b|qwen-2\.5-72b|qwen-plus", SIZE_LARGE),
        (r"mistral-large|mistral-medium|magistral-medium|devstral-medium|devstral-2(?!-small)|devstral-2512",
         SIZE_LARGE),
        (r"gemini-[0-9.]+-flash(?!-lite)|gemini-3-flash", SIZE_LARGE),
        (r"glm-4\.5-air", SIZE_LARGE),
        (r"pixtral-large|command-r-plus|mixtral-8x22b", SIZE_LARGE),
        (r"agnes-[0-9.]+-flash|gpt-5-mini|gpt-4\.1-mini|o4-mini|o3-mini|grok-3-mini", SIZE_LARGE),
        (r"hy3|nemotron-3\.5-lightning|laguna|jev\b|orcarouter", SIZE_LARGE),
        # Médios
        (r"gpt-oss[:\-]20b", SIZE_MEDIUM),
        (r"glm-4\.7-flash|glm-4\.6-flash", SIZE_MEDIUM),
        (r"mistral-small|magistral-small|devstral-small|codestral(?!-embed)|mistral-code|vibe-cli|leanstral",
         SIZE_MEDIUM),
        (r"gemma-sea-lion", SIZE_MEDIUM),
        (r"mixtral-8x7b", SIZE_MEDIUM),
        (r"command-r(?!-plus)", SIZE_MEDIUM),
        # Pequenos
        (r"gpt-4o-mini|gpt-4\.1-nano|gpt-5-nano", SIZE_SMALL),
        (r"gemini-[0-9.]+-flash-lite|gemini-1\.5-flash", SIZE_SMALL),
        (r"qwen-turbo|mistral-nemo|open-mistral-nemo|mistral-tiny|pixtral-12b|phi-4|phi-3", SIZE_SMALL),
        (r"llama3\.1-8b|llama3\b|llama2\b|mistral$|^mistral:|qwen2\.5$", SIZE_SMALL),
        # Nano
        (r"phi-2|granite-4\.0-h-micro|gemma-3n", SIZE_NANO),
    )
)

# Qualidade-base heurística (0–100) por família/geração. Avaliada em ordem; a
# primeira correspondência vence. Só é usada quando NÃO há ranking real
# (model_rankings.quality_score > 50) para o modelo.
_QUALITY_TABLE: Tuple[Tuple[re.Pattern[str], float], ...] = tuple(
    (re.compile(p, re.IGNORECASE), q)
    for p, q in (
        # DeepSeek
        (r"deepseek-v4-pro", 93), (r"deepseek-v4-flash", 88), (r"deepseek-v4", 91),
        (r"deepseek-v3\.2", 90), (r"deepseek-v3\.1", 88), (r"deepseek-v3", 86),
        (r"deepseek-reasoner|deepseek-r1(?!-distill)", 90), (r"deepseek-chat", 88),
        (r"r1-distill-llama-70b", 82), (r"r1-distill-qwen-32b", 78), (r"r1-distill", 72),
        # Moonshot Kimi
        (r"kimi-k2\.7", 92), (r"kimi-k2\.6", 91), (r"kimi-k2\.5", 90), (r"kimi-k2", 88),
        # Zhipu GLM
        (r"glm-5\.\d-flash", 85), (r"glm-5\.[1-9]", 91), (r"glm-5", 90),
        (r"glm-4\.7-flash", 80), (r"glm-4\.7", 87), (r"glm-4\.6", 86), (r"glm-4\.5-air", 82), (r"glm-4\.5", 85),
        (r"z-coder", 86), (r"z-chat", 84),
        # Qwen
        (r"qwen3(?:\.\d)?-max", 91), (r"qwen3(?:\.\d)?-plus", 88), (r"qwen3(?:\.\d)?-flash", 80),
        (r"qwen3\.6-27b", 82), (r"qwen3\.6", 81),
        (r"qwen3\.5-397b", 91), (r"qwen3\.5-122b", 87), (r"qwen3\.5-27b", 81), (r"qwen3\.5-35b", 80), (r"qwen3\.5-9b", 70),
        (r"qwen3-coder-480b|qwen3-coder(?!-30b|-flash)", 90), (r"qwen3-coder", 80), (r"qwen3-235b", 88), (r"qwen3-vl-32b", 80),
        (r"qwen3-vl-30b", 77), (r"qwen3-32b", 80), (r"qwen3-30b", 77), (r"qwen3-14b", 72), (r"qwen3-8b", 68),
        (r"qwen3-vl-8b", 68), (r"qwen3", 74),
        (r"qwq", 80), (r"qwen-?2\.5-coder-32b|qwen2\.5-coder-32b", 79), (r"qwen-?2\.5-72b|qwen2\.5-72b", 80),
        (r"qwen-?2\.5-coder", 70), (r"qwen-?2\.5-7b|qwen2\.5-7b", 65), (r"qwen2\.5", 68),
        (r"qwen-max", 88), (r"qwen-plus", 84), (r"qwen-turbo", 72),
        # OpenAI
        (r"gpt-oss[:\-]120b", 85), (r"gpt-oss[:\-]20b", 76), (r"gpt-5-nano", 76), (r"gpt-5-mini", 86), (r"gpt-5", 94),
        (r"gpt-4\.1-nano", 70), (r"gpt-4\.1-mini", 80), (r"gpt-4\.1", 88), (r"gpt-4o-mini", 76), (r"gpt-4o", 86),
        (r"(^|[/\-_])o3-mini", 84), (r"(^|[/\-_])o4-mini", 88), (r"(^|[/\-_])o3", 92), (r"(^|[/\-_])o1", 88),
        # Google
        (r"gemini-3(?:\.\d)?-pro", 95), (r"gemini-3(?:\.\d)?-flash-lite", 82), (r"gemini-3(?:\.\d)?-flash", 90),
        (r"gemini-2\.5-pro", 92), (r"gemini-2\.5-flash-lite", 78), (r"gemini-2\.5-flash", 87),
        (r"gemini-2\.0-flash-lite", 74), (r"gemini-2\.0-flash", 82), (r"gemini-1\.5-pro", 78), (r"gemini-1\.5-flash", 72),
        (r"gemma-4-31b|gemma4:31b", 80), (r"gemma-4|gemma4", 78), (r"gemma-sea-lion", 74),
        (r"gemma-?3-27b|gemma3:27b", 76), (r"gemma-?3-12b|gemma3:12b", 70), (r"gemma-?3-4b|gemma3:4b", 60),
        (r"gemma-?3-1b|gemma3:1b|gemma-3n", 50), (r"gemma-?2-9b|gemma2-9b", 64), (r"gemma-7b", 55),
        # Meta Llama
        (r"llama-4-maverick", 84), (r"llama-4-scout", 79), (r"llama-3\.1-405b", 83),
        (r"llama-3\.3-70b", 80), (r"llama-3\.1-70b|llama-3-70b|nemotron-70b", 78),
        (r"llama-3\.2-11b-vision", 66), (r"llama-3\.2-90b", 76), (r"llama-3\.1-8b|llama3\.1-8b", 66),
        (r"llama-3\.2-3b", 56), (r"llama-3\.2-1b", 48), (r"llama-3-8b|llama3-8b|llama3\b", 60), (r"llama-2", 45),
        # Mistral
        (r"mistral-large-3|mistral-large-2512", 86), (r"mistral-large", 80),
        (r"mistral-medium-3\.5|mistral-medium-3-5|mistral-medium-2604", 86), (r"mistral-medium-3|mistral-medium-25", 84),
        (r"mistral-medium", 78), (r"magistral-medium", 85), (r"magistral-small", 78),
        (r"devstral-2|devstral-2512|devstral-medium", 85), (r"devstral-small", 78), (r"devstral", 82),
        (r"codestral-mamba", 70), (r"codestral", 80), (r"mistral-code|vibe-cli", 80), (r"leanstral", 75),
        (r"mistral-small-3|mistral-small-25|mistral-small-26", 76), (r"mistral-small", 72),
        (r"ministral-14b|ministral-3:14b", 70), (r"ministral-8b|ministral-3:8b", 65), (r"ministral-3b|ministral-3:3b", 56),
        (r"mistral-nemo|open-mistral-nemo", 66), (r"mixtral-8x22b", 72), (r"mixtral-8x7b", 64),
        (r"mistral-tiny", 55), (r"mistral-7b|open-mistral-7b|^mistral$|^mistral:", 58),
        (r"pixtral-large", 80), (r"pixtral-12b", 68),
        # NVIDIA / MiniMax / Anthropic / xAI / outros
        (r"nemotron-3-ultra", 90), (r"nemotron-3-super|nemotron-3-120b", 85), (r"nemotron-3\.5-lightning", 78),
        (r"nemotron-3-nano", 76), (r"nemotron", 76),
        (r"minimax-m3", 91), (r"minimax-m2\.7", 89), (r"minimax-m2\.5", 88), (r"minimax-m2", 86), (r"minimax", 82),
        (r"claude.*opus", 95), (r"claude.*sonnet-4|claude-sonnet-4", 92), (r"claude.*3-7|claude.*3\.7", 90),
        (r"claude.*3-5-sonnet|claude.*3\.5-sonnet", 88), (r"claude.*haiku", 82), (r"claude", 88),
        (r"grok-4", 92), (r"grok-3-mini", 82), (r"grok-3", 88), (r"grok", 80),
        (r"command-a", 82), (r"command-r-plus", 74), (r"command-r", 68),
        (r"phi-4", 72), (r"phi-3", 62), (r"phi-2", 45), (r"granite-4", 62), (r"granite", 58),
        (r"hermes-2-pro", 58), (r"sqlcoder", 62), (r"hy4", 86), (r"hy3", 82), (r"longcat-2", 86), (r"longcat", 82),
        (r"agnes-3", 84), (r"agnes-2", 80), (r"laguna", 75), (r"jev\b", 75), (r"orcarouter", 75),
    )
)

# Qualidade-base por tier quando nenhuma família é reconhecida
_TIER_FALLBACK_QUALITY = {
    SIZE_NANO: 55.0,
    SIZE_SMALL: 66.0,
    SIZE_MEDIUM: 74.0,
    SIZE_LARGE: 80.0,
    SIZE_FRONTIER: 86.0,
}


@dataclass(frozen=True)
class ModelProfile:
    """Capacidades inferidas de um modelo (imutável, cacheável)."""
    model_id: str
    name: str
    provider_id: str
    size_tier: int
    params_b: Optional[float]
    reasoning_mode: str          # none | hybrid | dial | always_on
    is_coder: bool
    is_vision: bool
    is_chat_capable: bool
    fast_provider: bool
    speed_score: float           # 0.0 (lento) .. 1.0 (instantâneo)
    baseline_quality: float      # 0..100

    @property
    def size_label(self) -> str:
        return SIZE_LABELS.get(self.size_tier, "unknown")

    @property
    def is_reasoning(self) -> bool:
        return self.reasoning_mode != REASONING_NONE

    @property
    def always_on_reasoning(self) -> bool:
        return self.reasoning_mode == REASONING_ALWAYS_ON

    @property
    def is_small(self) -> bool:
        return self.size_tier <= SIZE_SMALL

    @property
    def is_big(self) -> bool:
        return self.size_tier >= SIZE_LARGE

    def tags(self) -> Tuple[str, ...]:
        out = [self.size_label]
        if self.reasoning_mode != REASONING_NONE:
            out.append(f"reasoning:{self.reasoning_mode}")
        if self.is_coder:
            out.append("coder")
        if self.is_vision:
            out.append("vision")
        if self.fast_provider:
            out.append("fast-provider")
        if not self.is_chat_capable:
            out.append("non-chat")
        return tuple(out)


def _parse_params_b(text: str) -> Optional[float]:
    """Extrai a contagem total de parâmetros (bilhões) do nome; ignora 'aNNb' (ativos)."""
    moe = _RE_MOE.search(text)
    if moe:
        try:
            return float(moe.group(1)) * float(moe.group(2))
        except ValueError:
            pass
    cleaned = _RE_ACTIVE.sub(" ", text)
    values = []
    for m in _RE_PARAMS.finditer(cleaned):
        try:
            values.append(float(m.group(1)))
        except ValueError:
            continue
    if not values:
        return None
    return max(values)


def _tier_from_params(params_b: float) -> int:
    if params_b <= 4.5:
        return SIZE_NANO
    if params_b <= 16:
        return SIZE_SMALL
    if params_b <= 45:
        return SIZE_MEDIUM
    if params_b <= 200:
        return SIZE_LARGE
    return SIZE_FRONTIER


def _detect_size_tier(text: str, params_b: Optional[float]) -> int:
    for pattern, tier in _TIER_OVERRIDES:
        if pattern.search(text):
            return tier
    if params_b is not None:
        return _tier_from_params(params_b)
    low = text
    if re.search(r"(nano|micro|tiny)\b", low):
        return SIZE_NANO
    if re.search(r"(mini|lite|instant|turbo|small)\b", low):
        return SIZE_SMALL
    if re.search(r"(ultra|max|pro|opus|large|plus)\b", low):
        return SIZE_FRONTIER
    if re.search(r"(medium|flash|super)\b", low):
        return SIZE_LARGE
    return SIZE_MEDIUM


def _detect_reasoning_mode(text: str, provider_id: str, name: str, reasoning_control: Optional[str]) -> str:
    ctrl = (reasoning_control or "").strip().lower()
    if ctrl == REASONING_ALWAYS_ON:
        return REASONING_ALWAYS_ON
    if _RE_ALWAYS_ON.search(text):
        return REASONING_ALWAYS_ON
    if ctrl and ctrl not in ("none", "unset"):
        # openai_effort, gemini_thinking, anthropic_effort, openrouter_reasoning,
        # xai_effort, agnes_effort, binary_think → o esforço é controlável
        return REASONING_DIAL
    # Fallback: taxonomia pura de famílias (mesma fonte do seed de reasoning_control)
    try:
        spec = resolve_family(provider_id, name)
        if spec.control == REASONING_ALWAYS_ON:
            return REASONING_ALWAYS_ON
        if spec.control not in ("none", ""):
            return REASONING_DIAL
    except Exception:  # pragma: no cover - defensivo
        pass
    if _RE_DIAL.search(text):
        return REASONING_DIAL
    if _RE_HYBRID.search(text) and not _RE_INSTRUCT_ONLY.search(name):
        return REASONING_HYBRID
    return REASONING_NONE


def _baseline_quality(text: str, size_tier: int) -> float:
    for pattern, q in _QUALITY_TABLE:
        if pattern.search(text):
            return float(q)
    return _TIER_FALLBACK_QUALITY.get(size_tier, 70.0)


@lru_cache(maxsize=4096)
def profile_model(
    model_id: str,
    name: str,
    provider_id: str,
    reasoning_control: Optional[str] = None,
    supports_vision: int = 0,
) -> ModelProfile:
    """Deriva o perfil de capacidades de um modelo. Pura e cacheada."""
    pid = (provider_id or "").strip().lower()
    nm = (name or "").strip()
    text = f"{model_id or ''} {nm}".lower()

    params_b = _parse_params_b(text)
    size_tier = _detect_size_tier(text, params_b)
    reasoning_mode = _detect_reasoning_mode(text, pid, nm, reasoning_control)
    is_coder = bool(_RE_CODER.search(text))
    is_vision = bool(int(supports_vision or 0) == 1 or _RE_VISION_HINT.search(text) or pid == "gemini")
    is_chat = not _RE_NON_CHAT.search(text)
    fast_provider = pid in FAST_PROVIDERS

    speed = {SIZE_NANO: 0.55, SIZE_SMALL: 0.45, SIZE_MEDIUM: 0.32, SIZE_LARGE: 0.18, SIZE_FRONTIER: 0.08}[size_tier]
    if fast_provider:
        speed += 0.35
    if _RE_SPEED_HINT.search(text):
        speed += 0.12
    if reasoning_mode == REASONING_ALWAYS_ON:
        speed -= 0.35
    speed = max(0.0, min(1.0, speed))

    quality = _baseline_quality(text, size_tier)

    return ModelProfile(
        model_id=model_id,
        name=nm,
        provider_id=pid,
        size_tier=size_tier,
        params_b=params_b,
        reasoning_mode=reasoning_mode,
        is_coder=is_coder,
        is_vision=is_vision,
        is_chat_capable=is_chat,
        fast_provider=fast_provider,
        speed_score=round(speed, 3),
        baseline_quality=quality,
    )


def clear_profile_cache() -> None:
    """Limpa o cache LRU (útil em testes)."""
    profile_model.cache_clear()
