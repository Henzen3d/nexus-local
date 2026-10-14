"""Extrator de fence nexus-ui da resposta do assistente."""

from __future__ import annotations

import re
from typing import Any

from backend.ui_blocks.validate import validate_envelope

# Regex para fences nexus-ui fechados (aceita ```nexus-ui, ```nexus-ui/1, ```nexus e ```chart com JSON)
FENCE_CLOSED_REGEX = re.compile(
    r"```(?:nexus-ui(?:/1)?|nexus)\s*([\s\S]*?)\s*```",
    re.MULTILINE,
)

FENCE_CHART_CLOSED_REGEX = re.compile(
    r"```(?:chart|ui)\s*(\{[\s\S]*?\})\s*```",
    re.MULTILINE,
)

# Regex para fence aberto (stream incompleto ou fence não fechado)
FENCE_OPEN_REGEX = re.compile(
    r"```(?:nexus-ui(?:/1)?|nexus)[\s\S]*$",
    re.MULTILINE,
)


def extract_ui(
    text: str,
    *,
    image_hosts: list[str] | None = None,
    allow_private_http: bool | None = None,
) -> tuple[str, dict[str, Any] | None]:
    """Extrai o último fence de UI da prosa.

    Retorna (prosa_limpa, envelope_validado). Se nenhum envelope for válido,
    retorna (prosa_limpa, None). ``image_hosts``/``allow_private_http`` são a
    configuração efetiva do turno; ``None`` cai no ambiente.
    """
    if not isinstance(text, str) or not text:
        return text or "", None

    def _validate(raw_json: str) -> dict[str, Any] | None:
        return validate_envelope(raw_json, image_hosts=image_hosts, allow_private_http=allow_private_http)

    # 1. Tenta padrão primário nexus-ui
    closed_matches = list(FENCE_CLOSED_REGEX.finditer(text))
    if closed_matches:
        last_match = closed_matches[-1]
        raw_json = last_match.group(1).strip()
        envelope = _validate(raw_json)

        # Remove todos os fences fechados da prosa
        cleaned_text = FENCE_CLOSED_REGEX.sub("", text)
        cleaned_text = FENCE_OPEN_REGEX.sub("", cleaned_text).rstrip()

        return cleaned_text, envelope

    # 2. Tenta padrão alternativo ```chart { ... }``` (caso o modelo gere fence de gráfico direto)
    chart_matches = list(FENCE_CHART_CLOSED_REGEX.finditer(text))
    if chart_matches:
        last_match = chart_matches[-1]
        raw_json = last_match.group(1).strip()
        envelope = _validate(raw_json)
        if envelope:
            cleaned_text = FENCE_CHART_CLOSED_REGEX.sub("", text).rstrip()
            return cleaned_text, envelope

    # 3. Se não há fechado, verifica se há fence aberto em streaming
    if "```nexus-ui" in text or "```nexus" in text:
        cleaned_text = FENCE_OPEN_REGEX.sub("", text).rstrip()
        return cleaned_text, None

    return text, None
