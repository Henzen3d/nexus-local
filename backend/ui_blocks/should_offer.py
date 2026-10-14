"""Heurístico de oferta do catálogo de UI Blocks no prompt.

Regra da Seção 8 de 00-visao-e-spec.md:
- regex: gráfico|grafico|compar|versus|\\bvs\\b|etapa|progresso|escolh|selecion|cartão|cartao|imagem|foto|indicador|barra|calcul|simul
- ou 3+ números e uma destas palavras: custo, tempo, modelo, %, taxa, valor

Os radicais da spec são ancorados no início de palavra (``\\b``) e alguns
levam exclusões para não disparar em palavras comuns sem relação com visual:
``compartilhar``/``comparecer`` (não é "comparar"), ``simultâneo`` (não é
"simular"), ``embarrar``/``barraco`` (não é "barra"), ``cartaz``/``cartucho``
(não é "cartão"). Disparar à toa custa ~280 tokens de catálogo por turno e
convida o modelo a inventar um widget onde só cabia prosa.
"""

from __future__ import annotations

import re

TRIGGER_REGEX = re.compile(
    r"\bgr[aá]fic[oa]s?\b"
    r"|\bcompar(?!tilh|ec)"  # comparar/comparação/comparativo; não compartilhar/comparecer
    r"|\bversus\b|\bvs\.?\b"
    r"|\betapas?\b"
    r"|\bprogress"  # progresso/progressão
    r"|\bescolh"  # escolher/escolha
    r"|\bselecion"  # selecionar/seleção (selecionar)
    r"|\bcart(?:[aã]o|[oõ]es)\b"
    r"|\bimage(?:m|ns)\b"
    r"|\bfotos?\b|\bfotografia"
    r"|\bindicador"
    r"|\bbarras?\b"
    r"|\bcalcul"  # calcular/calculadora/cálculo (sem acento)
    r"|\bc[aá]lculos?\b"
    r"|\bsimul(?!t)",  # simular/simulação/simulador; não simultâneo
    re.IGNORECASE,
)

NUMBER_REGEX = re.compile(r"\b\d+(?:[.,]\d+)?\b")

WORDS_WITH_NUMBERS = ("custo", "tempo", "modelo", "%", "taxa", "valor")
_WORDS_WITH_NUMBERS_REGEX = re.compile(
    r"%|\b(?:custos?|tempos?|modelos?|taxas?|valor(?:es)?)\b",
    re.IGNORECASE,
)


def should_offer_ui(user_text: str) -> bool:
    """Verifica se a última mensagem do usuário justifica a injeção do catálogo visual."""
    if not isinstance(user_text, str) or not user_text.strip():
        return False

    if TRIGGER_REGEX.search(user_text):
        return True

    # Três ou mais números junto de uma palavra de medida: provável comparação/série
    numbers = NUMBER_REGEX.findall(user_text)
    if len(numbers) >= 3 and _WORDS_WITH_NUMBERS_REGEX.search(user_text):
        return True

    return False
