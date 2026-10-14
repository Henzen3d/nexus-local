"""Extrator de fence nexus-ui da resposta do assistente."""

from __future__ import annotations

import re
from typing import Any

from backend.ui_blocks.diagnostics import validate_with_diagnostics, ui_error

# Fences só contam quando a abertura está no início de uma linha (até 3 espaços,
# como no CommonMark) e seguida de quebra de linha. Uma menção inline na prosa
# ("use o fence ```nexus-ui no final") não é fence e não pode engolir o texto.
# Aceita ```nexus-ui, ```nexus-ui/1 e ```nexus; o fechamento é ``` sozinho na linha.
FENCE_CLOSED_REGEX = re.compile(
    r"^[ \t]{0,3}```(?:nexus-ui(?:/1)?|nexus)[ \t]*\r?\n([\s\S]*?)\r?\n[ \t]{0,3}```[ \t]*$",
    re.MULTILINE,
)

# Tolerância para modelo que escreve ```chart { ... } ``` ou ```ui { ... } ``` direto
FENCE_CHART_CLOSED_REGEX = re.compile(
    r"^[ \t]{0,3}```(?:chart|ui)[ \t]*\r?\n\s*(\{[\s\S]*?\})\s*\r?\n[ \t]{0,3}```[ \t]*$",
    re.MULTILINE,
)

# Fence aberto (stream incompleto ou fence não fechado): do início da linha até o fim
FENCE_OPEN_REGEX = re.compile(
    r"^[ \t]{0,3}```(?:nexus-ui(?:/1)?|nexus)[ \t]*(?:\r?\n[\s\S]*)?$",
    re.MULTILINE,
)


def extract_ui(
    text: str,
    *,
    image_hosts: list[str] | None = None,
    allow_private_http: bool | None = None,
    diagnostics: dict | None = None,
) -> tuple[str, dict[str, Any] | None]:
    """Extrai o último fence de UI da prosa.

    Retorna (prosa_limpa, envelope_validado). Se nenhum envelope for válido,
    retorna (prosa_limpa, None). ``image_hosts``/``allow_private_http`` são a
    configuração efetiva do turno; ``None`` cai no ambiente.
    """
    if diagnostics is not None:
        diagnostics.update(errors=[], dropped=0)
    if not isinstance(text, str) or not text:
        return text or "", None

    def _validate(raw_json: str) -> dict[str, Any] | None:
        report = validate_with_diagnostics(raw_json, image_hosts=image_hosts, allow_private_http=allow_private_http)
        if diagnostics is not None:
            diagnostics.update(errors=report['errors'], dropped=report['dropped'])
        return report['envelope']

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
    if FENCE_OPEN_REGEX.search(text):
        if diagnostics is not None:
            diagnostics.update(errors=[ui_error('fence_unclosed')], dropped=1)
        cleaned_text = FENCE_OPEN_REGEX.sub("", text).rstrip()
        return cleaned_text, None

    return text, None
