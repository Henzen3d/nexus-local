"""Construtor puro de payload para parâmetros de esforço de raciocínio.

Multi+ / NexusLocal — Fase 3 (Tradução de payload por provedor)
Referência: melhorias/esforco-reasoning/02-backend-catalogo-e-payload.md
"""
from __future__ import annotations

import copy
from typing import Optional, List, Dict, Any
from .families import ReasoningControl, VALID_REASONING_LEVELS


def build_gemini_thinking_config(level: Optional[str]) -> Optional[Dict[str, Any]]:
    """Monta a seção thinkingConfig nativa para o generationConfig da API Gemini.

    Retorna None se o nível for vazio ou não reconhecido.
    Retorna {"thinkingBudget": 0} se level == "off".
    """
    if not level or level not in VALID_REASONING_LEVELS:
        return None

    norm_level = level.strip().lower()
    if norm_level == "off":
        return {"thinkingBudget": 0}

    # Orçamentos proporcionais suportados pelas APIs Gemini 2.0 / 2.5
    budget_map: dict[str, int] = {
        "minimal": 512,
        "low": 1024,
        "medium": 4096,
        "high": 16384,
        "xhigh": 24576,
        "max": 32768,
    }
    budget = budget_map.get(norm_level, 4096)
    return {"thinkingBudget": budget}


def build_effort_payload(
    control: Optional[str],
    level: Optional[str],
    base_payload: Dict[str, Any],
    allowed_levels: Optional[List[str]] = None,
) -> Dict[str, Any]:
    """Injeta os parâmetros de raciocínio de acordo com o contrato do provedor.

    Função estritamente pura e determinística. Devolve uma cópia do payload base.
    Se o controle for 'none', 'always_on', ou se o nível não for suportado,
    devolve o payload inalterado.
    """
    payload = copy.deepcopy(base_payload)

    if not control or control in (ReasoningControl.NONE.value, ReasoningControl.ALWAYS_ON.value):
        return payload

    if not level or not str(level).strip():
        return payload

    norm_level = str(level).strip().lower()
    if norm_level not in VALID_REASONING_LEVELS:
        return payload

    # Se uma lista de níveis permitidos foi fornecida, valida se o nível pertence a ela
    if allowed_levels is not None and norm_level not in allowed_levels:
        return payload

    # 1. OpenAI-compat e xAI
    if control in (ReasoningControl.OPENAI_EFFORT.value, ReasoningControl.XAI_EFFORT.value):
        payload["reasoning_effort"] = norm_level
        return payload

    # 2. OpenRouter (objeto estruturado {"reasoning": {"effort": ...}})
    if control == ReasoningControl.OPENROUTER_REASONING.value:
        existing_reasoning = payload.get("reasoning")
        if isinstance(existing_reasoning, dict):
            new_reasoning = dict(existing_reasoning)
        else:
            new_reasoning = {}
        new_reasoning["effort"] = norm_level
        payload["reasoning"] = new_reasoning
        return payload

    # 3. Gemini nativo (se base_payload contiver generationConfig)
    if control == ReasoningControl.GEMINI_THINKING.value:
        thinking_cfg = build_gemini_thinking_config(norm_level)
        if thinking_cfg is not None:
            if "generationConfig" in payload and isinstance(payload["generationConfig"], dict):
                payload["generationConfig"]["thinkingConfig"] = thinking_cfg
            else:
                # Se for chamado via endpoint OpenAI-compat de Gemini
                payload["reasoning_effort"] = norm_level
        return payload

    # 4. Anthropic nativo (campo 'effort')
    if control == ReasoningControl.ANTHROPIC_EFFORT.value:
        payload["effort"] = norm_level
        return payload

    # 5. Binário (on/off)
    if control == ReasoningControl.BINARY_THINK.value:
        payload["think"] = (norm_level != "off")
        return payload

    # 6. Agnes oficial. A API rejeita "off"; o desligado é o literal "none".
    if control == ReasoningControl.AGNES_EFFORT.value:
        payload["reasoning_effort"] = "none" if norm_level == "off" else norm_level
        return payload

    return payload
