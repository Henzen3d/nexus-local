"""Taxonomia e mapeamento de famílias para controles de esforço de raciocínio.

Multi+ / NexusLocal — Fase 1 (Reasoning Controls & Thinking Controls)
Referência: melhorias/esforco-reasoning/01-taxonomia-de-controles.md
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional, List


class ReasoningControl(str, Enum):
    NONE = "none"
    OPENAI_EFFORT = "openai_effort"
    GEMINI_THINKING = "gemini_thinking"
    ANTHROPIC_EFFORT = "anthropic_effort"
    OPENROUTER_REASONING = "openrouter_reasoning"
    XAI_EFFORT = "xai_effort"
    ALWAYS_ON = "always_on"
    BINARY_THINK = "binary_think"


# Escala interna ordenada de intensidade (do mais leve ao mais pesado)
VALID_REASONING_LEVELS: tuple[str, ...] = (
    "off",
    "minimal",
    "low",
    "medium",
    "high",
    "xhigh",
    "max",
)


@dataclass(frozen=True)
class ControlSpec:
    control: str
    levels: List[str] = field(default_factory=list)
    default: Optional[str] = None


def resolve_family(provider_id: str | None, model_name: str | None) -> ControlSpec:
    """Classifica um modelo em um contrato de reasoning via provider_id e model_name.

    Função estritamente pura, sem banco de dados e sem chamadas de rede.
    Retorna ControlSpec("none", [], None) caso não haja correspondência.
    """
    if not model_name or not str(model_name).strip():
        return ControlSpec(control=ReasoningControl.NONE.value, levels=[], default=None)

    pid = (provider_id or "").strip().lower()
    name = model_name.strip().lower()

    # 1. DeepSeek R1 / reasoner sem dial (pensa sempre)
    # Fonte: DeepSeek API Docs (https://api-docs.deepseek.com) — R1 não aceita reasoning_effort dial.
    if "deepseek-r1" in name or "deepseek-reasoner" in name or name.endswith("/deepseek-r1"):
        return ControlSpec(control=ReasoningControl.ALWAYS_ON.value, levels=[], default=None)

    # 2. Gemini thinking models nativos
    # Fonte: Google Gemini API (https://ai.google.dev/gemini-api/docs/thinking) — thinkingConfig com budget/level.
    # gemini-2.0-flash-thinking, gemini-2.5, gemini-3 thinking
    if (
        ("gemini" in pid or "google" in pid or "gemini" in name)
        and any(k in name for k in ("flash-thinking", "thinking", "gemini-2.5", "gemini-3"))
    ):
        return ControlSpec(
            control=ReasoningControl.GEMINI_THINKING.value,
            levels=["off", "low", "medium", "high"],
            default="medium",
        )

    # 3. Claude recente com dial de reasoning (ex: 3.7 Sonnet)
    # Fonte: Anthropic Docs (https://docs.anthropic.com/en/docs/build-with-claude/extended-thinking)
    # OpenRouter API (https://openrouter.ai/docs#reasoning) aceita objeto reasoning com effort.
    if "claude" in name and any(k in name for k in ("3-7", "3.7", "sonnet-3.7", "sonnet-3-7", "thinking", "thought")):
        levels = ["low", "medium", "high", "xhigh", "max"]
        if "openrouter" in pid:
            return ControlSpec(
                control=ReasoningControl.OPENROUTER_REASONING.value,
                levels=levels,
                default="medium",
            )
        return ControlSpec(
            control=ReasoningControl.ANTHROPIC_EFFORT.value,
            levels=levels,
            default="medium",
        )

    # 4. Família OpenAI reasoning (o1, o3, o4, gpt-5 variantes)
    # Fonte: OpenAI Platform Docs (https://platform.openai.com/docs/guides/reasoning) — reasoning_effort: low, medium, high.
    # Regex para capturar o1, o1-mini, o1-preview, o3, o3-mini, o4, etc.
    o_series_pattern = r"(^|[\/\-_])(o1|o3|o4)([\-_]|$)"
    if re.search(o_series_pattern, name) or "gpt-5-reasoning" in name or "gpt-5-thinking" in name:
        levels = ["low", "medium", "high"]
        if "openrouter" in pid:
            return ControlSpec(
                control=ReasoningControl.OPENROUTER_REASONING.value,
                levels=levels,
                default="medium",
            )
        return ControlSpec(
            control=ReasoningControl.OPENAI_EFFORT.value,
            levels=levels,
            default="medium",
        )

    # 5. Grok com reasoning
    # Fonte: xAI API Docs (https://docs.x.ai) — reasoning_effort documentado nos modelos reasoning.
    if "grok" in name and ("reasoning" in name or "think" in name):
        levels = ["low", "medium", "high"]
        if "openrouter" in pid:
            return ControlSpec(
                control=ReasoningControl.OPENROUTER_REASONING.value,
                levels=levels,
                default="medium",
            )
        return ControlSpec(
            control=ReasoningControl.XAI_EFFORT.value,
            levels=levels,
            default="medium",
        )

    # 6. Qwen com tag thinking sem dial
    # Fonte: Qwen Docs / vLLM — Qwen3-VL-Thinking / Qwen-Thinking sem parâmetro de esforço.
    if "qwen" in name and any(k in name for k in ("thinking", "reasoning")):
        return ControlSpec(control=ReasoningControl.ALWAYS_ON.value, levels=[], default=None)

    # 7. Modelos convencionais (Llama, Mistral, Groq, Cerebras, Cloudflare, etc.) -> none
    return ControlSpec(control=ReasoningControl.NONE.value, levels=[], default=None)
