"""
Sanitizador de segredos e informações altamente sensíveis (PII / Secrets Redactor).
Módulo isolado para prevenir importações circulares entre database e memory.
"""

import re
from backend.logging_config import get_logger

logger = get_logger(__name__)

_SECRET_PATTERNS = [
    # Chaves de provedores de IA (OpenAI, Anthropic, Google Gemini)
    re.compile(r"\b(?:sk-proj-[a-zA-Z0-9_\-]{20,}|sk-[a-zA-Z0-9_\-]{20,}|sk-ant-[a-zA-Z0-9_\-]{20,}|AIza[a-zA-Z0-9_\-]{35})\b"),
    # Chaves de infraestrutura (GitHub, AWS)
    re.compile(r"\b(?:ghp_[a-zA-Z0-9]{36}|github_pat_[a-zA-Z0-9_]{80,}|AKIA[0-9A-Z]{16})\b"),
    # Connection strings com senha embutida
    re.compile(r"(?:postgres(?:ql)?|mongodb(?:\+srv)?|mysql|redis)://[^:]+:([^@]+)@[^\s/]+", re.IGNORECASE),
    # JWT tokens
    re.compile(r"\beyJ[a-zA-Z0-9_\-]{20,}\.[a-zA-Z0-9_\-]{20,}\.[a-zA-Z0-9_\-]{20,}\b"),
    # Declarações explícitas de senha ou secret
    re.compile(r"(?:senha|password|passwd|api_key|token_secreto)\s*[:=]\s*([^\s,;]+)", re.IGNORECASE),
]


def sanitize_memory_text(text: str) -> tuple[str, bool]:
    """
    Sanitiza tokens de API, chaves secretas, senhas e credenciais.
    Retorna: (texto_sanitizado, deve_descartar)
    - Se o fato consistir puramente em uma credencial exposta, retorna ("", True).
    - Se for fato misto, substitui pela máscara '[REDACTED_CREDENTIAL]'.
    """
    if not text:
        return text, False

    clean = text
    found_secret = False

    for pat in _SECRET_PATTERNS:
        matches = list(pat.finditer(clean))
        if matches:
            found_secret = True
            for m in reversed(matches):
                if pat.groups > 0 and m.groups():
                    start, end = m.span(1)
                    clean = clean[:start] + "[REDACTED_CREDENTIAL]" + clean[end:]
                else:
                    clean = clean[:m.start()] + "[REDACTED_CREDENTIAL]" + clean[m.end():]

    if found_secret:
        logger.warning("[Security] Credencial sensível detectada no texto da memória.")
        # Se após remoção sobrar quase nada além de máscara ou pontuação, descarta
        stripped = re.sub(r"\[REDACTED_CREDENTIAL\]", "", clean).strip(" \t\n\r:=-,.")
        if len(stripped) < 4:
            logger.info("[Security] Fato composto exclusivamente por segredo foi descartado.")
            return "", True

    return clean, False
