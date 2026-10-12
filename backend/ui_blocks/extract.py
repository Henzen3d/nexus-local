"""Extrator de fence nexus-ui da resposta do assistente."""

from __future__ import annotations

import re
from typing import Any

from backend.ui_blocks.validate import validate_envelope

# Regex para fences nexus-ui fechados
FENCE_CLOSED_REGEX = re.compile(
    r"```nexus-ui\s*([\s\S]*?)\s*```",
    re.MULTILINE,
)

# Regex para fence nexus-ui aberto (stream incompleto ou fence não fechado)
FENCE_OPEN_REGEX = re.compile(
    r"```nexus-ui[\s\S]*$",
    re.MULTILINE,
)


def extract_ui(text: str) -> tuple[str, dict[str, Any] | None]:
    """Extrai o último fence nexus-ui da prosa.

    Retorna (prosa_limpa, envelope_validado). Se nenhum envelope for válido,
    retorna (prosa_limpa, None).
    """
    if not isinstance(text, str) or not text:
        return text or "", None

    # Verifica se há fences fechados
    closed_matches = list(FENCE_CLOSED_REGEX.finditer(text))

    if closed_matches:
        # Se houver mais de um, usar apenas o último (spec seção 4)
        last_match = closed_matches[-1]
        raw_json = last_match.group(1).strip()
        envelope = validate_envelope(raw_json)

        # Remove todos os fences fechados da prosa
        cleaned_text = FENCE_CLOSED_REGEX.sub("", text)
        # Remove também qualquer fence aberto remanescente após os fechados
        cleaned_text = FENCE_OPEN_REGEX.sub("", cleaned_text).rstrip()

        return cleaned_text, envelope

    # Se não há fechado, verifica se há fence aberto
    if "```nexus-ui" in text:
        cleaned_text = FENCE_OPEN_REGEX.sub("", text).rstrip()
        return cleaned_text, None

    return text, None
