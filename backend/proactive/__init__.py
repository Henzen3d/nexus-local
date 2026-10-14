"""Assistente Proativo — pacote backend.

Fase 1 (spike): detector de interesse genuíno em dois estágios.

* :func:`backend.proactive.detector.gate` — porteiro léxico, puro e síncrono.
* :func:`backend.proactive.detector.classify` — classificador com modelo
  utilitário (JSON estrito, fail-closed).

Nada aqui toca o fluxo do chat ainda; a integração acontece na Fase 2
(ver ``melhorias/assistente-proativo/03-fase-2-nucleo-pipeline.md``).
"""
from backend.proactive.detector import (  # noqa: F401
    Decision,
    GateResult,
    InterestSignal,
    classify,
    evaluate,
    gate,
    parse_interest_signal,
    threshold_for,
)

__all__ = [
    "Decision",
    "GateResult",
    "InterestSignal",
    "classify",
    "evaluate",
    "gate",
    "parse_interest_signal",
    "threshold_for",
]
