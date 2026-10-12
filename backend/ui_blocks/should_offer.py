"""Heurístico de oferta do catálogo de UI Blocks no prompt.

Regra da Seção 8 de 00-visao-e-spec.md:
- regex: gráfico|grafico|compar|versus|\\bvs\\b|etapa|progresso|escolh|selecion|cartão|cartao|imagem|foto|indicador|barra|calcul|simul
- ou 3+ números e uma destas palavras: custo, tempo, modelo, %, taxa, valor
"""

from __future__ import annotations

import re

TRIGGER_REGEX = re.compile(
    r"gr[aá]fico|compar|versus|\bvs\b|etapa|progresso|escolh|selecion|cart[aã]o|imagem|foto|indicador|barra|calcul|simul",
    re.IGNORECASE,
)

NUMBER_REGEX = re.compile(r"\b\d+(?:[.,]\d+)?\b")

WORDS_WITH_NUMBERS = {"custo", "tempo", "modelo", "%", "taxa", "valor"}


def should_offer_ui(user_text: str) -> bool:
    """Verifica se a última mensagem do usuário justifica a injeção do catálogo visual."""
    if not isinstance(user_text, str) or not user_text.strip():
        return False

    text_lower = user_text.lower()

    if TRIGGER_REGEX.search(text_lower):
        return True

    # Verifica se há 3 ou mais números e uma das palavras-chave
    numbers = NUMBER_REGEX.findall(user_text)
    if len(numbers) >= 3:
        for w in WORDS_WITH_NUMBERS:
            if w in text_lower:
                return True

    return False
