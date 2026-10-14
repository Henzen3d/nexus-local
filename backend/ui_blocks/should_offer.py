"""Gatilhos do catálogo modular (plano 12 §3).

Radicais ancorados e exclusões preservam os casos negativos de compartilhar,
comparecer, simultâneo, barraco e cartaz. Só contratos já implementados entram.
"""

from __future__ import annotations

import re

NUMBER_REGEX = re.compile(r"\b\d+(?:[.,]\d+)?\b")

WORDS_WITH_NUMBERS = ("custo", "tempo", "modelo", "%", "taxa", "valor")
_WORDS_WITH_NUMBERS_REGEX = re.compile(
    r"%|\b(?:custos?|tempos?|modelos?|taxas?|valor(?:es)?)\b",
    re.IGNORECASE,
)


# Prioridade estável, independente da ordem das palavras. Reserva uma vaga para
# follow_up: no máximo dois módulos de conteúdo e um de continuação por turno.
MODULE_TRIGGERS = (
    ("chart", r"\bgr[aá]fic[oa]s?\b|\bcompar(?!tilh|ec)|\bversus\b|\bvs\b|\bevolu|\btend[eê]n|\bdistribui|\bparticipa|\bbarras?\b"),
    ("metric", r"\bindicador|\bkpis?\b|\bm[eé]trica|\bresumo\b|\btotal\b|\btaxas?\b|%"),
    ("progress", r"\betapas?\b|\bprogress|\bchecklist\b|\bpasso a passo\b|\broteiro\b"),
    ("controls", r"\bcalcul|\bc[aá]lculos?\b|\bsimul(?!t)|\bestim|\bparcel|\bdivid|\bescolh|\bselecion|\bprefer|\bqual (?:dos|das)\b"),
    ("callout", r"\baten[çc][aã]o\b|\bcuidado\b|\bimportante\b|\baviso\b|\brisco\b"),
    ("card", r"\bimage(?:m|ns)\b|\bfotos?\b|\bfotografia|\bcart(?:[aã]o|[oõ]es)\b|\bproduto|\bficha\b"),
    ("sandbox", r"\bsimul(?!t)|\banima|\b3d\b|\bvisualiz(?:e|ar) o algoritmo\b|\binterativ"),
)
_MODULE_REGEXES = tuple((name, re.compile(pattern, re.IGNORECASE)) for name, pattern in MODULE_TRIGGERS)


def select_modules(user_text: str) -> tuple[str, ...]:
    if not isinstance(user_text, str) or not user_text.strip():
        return ()
    matches = [name for name, pattern in _MODULE_REGEXES if pattern.search(user_text)]
    if len(NUMBER_REGEX.findall(user_text)) >= 3 and _WORDS_WITH_NUMBERS_REGEX.search(user_text):
        if "chart" not in matches:
            matches.insert(0, "chart")
    return tuple(matches[:2] + (["follow_up"] if matches else []))


def should_offer_ui(user_text: str) -> bool:
    """Verifica se a última mensagem do usuário justifica a injeção do catálogo visual."""
    if not isinstance(user_text, str) or not user_text.strip():
        return False

    if select_modules(user_text):
        return True

    # Três ou mais números junto de uma palavra de medida: provável comparação/série
    numbers = NUMBER_REGEX.findall(user_text)
    if len(numbers) >= 3 and _WORDS_WITH_NUMBERS_REGEX.search(user_text):
        return True

    return False
