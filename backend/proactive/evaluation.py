"""Avaliação offline do detector (F1.4) — núcleo reutilizado por
``scripts/proactive_eval.py`` e por ``backend/tests/test_proactive_detector.py``.

* :func:`load_gold` — lê ``backend/tests/fixtures/proactive_gold.jsonl``.
* :func:`evaluate_gate` — métricas do estágio 1 (sem LLM, sem I/O).
* :func:`evaluate_llm` — roda porteiro + classificador item a item e guarda o
  sinal bruto; :func:`compute_metrics` e :func:`threshold_sweep` recalculam
  precisão/recall/FP para qualquer threshold **sem** novas chamadas ao modelo.
* :func:`render_markdown` — tabelas prontas para colar em
  ``melhorias/assistente-proativo/resultados-spike-f1.md``.

Metas da fase (``melhorias/assistente-proativo/02-fase-1-spike-detector.md``):
porteiro rejeita ≥ 70 % das negativas e perde ≤ 10 % das positivas;
classificador com precisão ≥ 0,85 e taxa de falsos positivos ≤ 5 %.
"""
from __future__ import annotations

import asyncio
import json
import statistics
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable, Optional, Sequence

from backend.proactive.detector import (
    DEFAULT_SENSITIVITY,
    ClassifyMeta,
    Decision,
    GateResult,
    InterestSignal,
    classify_with_meta,
    evaluate,
    gate,
    threshold_for,
)

DEFAULT_GOLD_PATH = Path(__file__).resolve().parents[1] / "tests" / "fixtures" / "proactive_gold.jsonl"

GATE_MAX_LOST_POSITIVES = 0.10
GATE_MIN_REJECTED_NEGATIVES = 0.70
LLM_MIN_PRECISION = 0.85
LLM_MAX_FP_RATE = 0.05
LLM_MAX_P95_LATENCY_MS = 4000.0
SWEEP_THRESHOLDS = (0.5, 0.55, 0.6, 0.65, 0.7, 0.75, 0.8, 0.85, 0.9)


# ─────────────────────────────────────────────────────────────────────────────
# Gold
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class GoldItem:
    id: str
    text: str
    label: int
    category: str = "other"
    entity_type: str = "other"
    lang: str = "unknown"
    note: str = ""
    web_search_used: bool = False
    gate_expect: str = ""   # pass (positiva) | reject (regra do porteiro) | llm (classificador decide)


def load_gold(path: Optional[Path | str] = None) -> list[GoldItem]:
    """Lê o JSONL (uma mensagem rotulada por linha). Linhas vazias/comentários são ignorados."""
    gold_path = Path(path) if path else DEFAULT_GOLD_PATH
    items: list[GoldItem] = []
    with gold_path.open(encoding="utf-8") as fh:
        for line_no, line in enumerate(fh, start=1):
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            try:
                data = json.loads(line)
            except json.JSONDecodeError as exc:
                raise ValueError(f"{gold_path.name}:{line_no}: JSON inválido ({exc})") from exc
            items.append(
                GoldItem(
                    id=str(data.get("id") or f"line{line_no}"),
                    text=str(data["text"]),
                    label=int(data["label"]),
                    category=str(data.get("category") or "other"),
                    entity_type=str(data.get("entity_type") or "other"),
                    lang=str(data.get("lang") or "unknown"),
                    note=str(data.get("note") or ""),
                    web_search_used=bool(data.get("web_search_used", False)),
                    gate_expect=str(data.get("gate_expect") or ""),
                )
            )
    return items


# ─────────────────────────────────────────────────────────────────────────────
# Estágio 1 — porteiro
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class GateEvaluation:
    total: int
    positives: int
    negatives: int
    negatives_rejected: int
    positives_rejected: int
    reject_reasons_negatives: Counter = field(default_factory=Counter)
    lost_positives: list[tuple[str, str]] = field(default_factory=list)       # (id, reason)
    passed_negatives: list[str] = field(default_factory=list)                  # ids que vão ao LLM
    by_language: dict[str, dict[str, int]] = field(default_factory=dict)       # lang → {pos, pos_lost, neg, neg_rejected}
    results: dict[str, GateResult] = field(default_factory=dict)

    @property
    def rejected_negatives_rate(self) -> float:
        return self.negatives_rejected / self.negatives if self.negatives else 0.0

    @property
    def lost_positives_rate(self) -> float:
        return self.positives_rejected / self.positives if self.positives else 0.0

    @property
    def targets_met(self) -> bool:
        return (
            self.rejected_negatives_rate >= GATE_MIN_REJECTED_NEGATIVES
            and self.lost_positives_rate <= GATE_MAX_LOST_POSITIVES
        )


def evaluate_gate(items: Sequence[GoldItem]) -> GateEvaluation:
    positives = [i for i in items if i.label == 1]
    negatives = [i for i in items if i.label == 0]
    ev = GateEvaluation(
        total=len(items), positives=len(positives), negatives=len(negatives),
        negatives_rejected=0, positives_rejected=0,
    )
    by_lang: dict[str, dict[str, int]] = defaultdict(lambda: {"pos": 0, "pos_lost": 0, "neg": 0, "neg_rejected": 0})
    for item in items:
        result = gate(item.text, web_search_used=item.web_search_used)
        ev.results[item.id] = result
        stats = by_lang[item.lang]
        if item.label == 1:
            stats["pos"] += 1
            if not result.passed:
                ev.positives_rejected += 1
                stats["pos_lost"] += 1
                ev.lost_positives.append((item.id, result.reason))
        else:
            stats["neg"] += 1
            if result.passed:
                ev.passed_negatives.append(item.id)
            else:
                ev.negatives_rejected += 1
                stats["neg_rejected"] += 1
                ev.reject_reasons_negatives[result.reason] += 1
    ev.by_language = dict(by_lang)
    return ev


# ─────────────────────────────────────────────────────────────────────────────
# Estágio 2 — classificador
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class LLMRecord:
    """Um item do gold depois de passar pelo pipeline porteiro → classificador."""

    id: str
    label: int
    lang: str
    category: str
    gate_passed: bool
    gate_reason: str
    signal: Optional[InterestSignal] = None
    meta: Optional[ClassifyMeta] = None

    def decision(self, sensitivity: str = DEFAULT_SENSITIVITY, threshold: Optional[float] = None) -> Decision:
        """Decisão para um threshold arbitrário (sem nova chamada ao modelo)."""
        thr = threshold if threshold is not None else threshold_for(sensitivity)
        if self.signal is None:
            empty = InterestSignal(interest=0.0, reason=f"gate:{self.gate_reason}")
            return Decision(False, f"gate:{self.gate_reason}", thr, empty)
        sig = InterestSignal(**self.signal.to_dict())   # cópia: evaluate() pode preencher a query
        return evaluate(sig, sensitivity, threshold=thr)

    def predicted(self, sensitivity: str = DEFAULT_SENSITIVITY, threshold: Optional[float] = None) -> int:
        return 1 if (self.gate_passed and self.decision(sensitivity, threshold).accepted) else 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "label": self.label,
            "lang": self.lang,
            "category": self.category,
            "gate_passed": self.gate_passed,
            "gate_reason": self.gate_reason,
            "signal": self.signal.to_dict() if self.signal else None,
            "latency_ms": round(self.meta.latency_ms, 1) if self.meta else None,
            "est_tokens": self.meta.est_tokens if self.meta else None,
            "error": self.meta.error if self.meta else "",
            "raw": self.meta.raw if self.meta else "",
        }


async def evaluate_llm(
    items: Sequence[GoldItem],
    *,
    provider: Any,
    model_name: str,
    sensitivity: str = DEFAULT_SENSITIVITY,
    concurrency: int = 2,
    timeout: float = 8.0,
    include_gate_rejected: bool = False,
    progress: Optional[Any] = None,
) -> list[LLMRecord]:
    """Roda porteiro + classificador no gold. Só chama o modelo para itens que passaram
    no porteiro (ou para todos, com ``include_gate_rejected`` — útil para medir
    quanto o porteiro "esconde" do classificador)."""
    semaphore = asyncio.Semaphore(max(1, concurrency))
    records: list[Optional[LLMRecord]] = [None] * len(items)

    async def _one(idx: int, item: GoldItem) -> None:
        g = gate(item.text, web_search_used=item.web_search_used)
        record = LLMRecord(
            id=item.id, label=item.label, lang=item.lang, category=item.category,
            gate_passed=g.passed, gate_reason=g.reason,
        )
        if g.passed or include_gate_rejected:
            async with semaphore:
                signal, meta = await classify_with_meta(
                    item.text, [], provider=provider, model_name=model_name,
                    timeout=timeout, language_hint=g.language if g.language != "unknown" else None,
                )
            record.signal, record.meta = signal, meta
        records[idx] = record
        if progress:
            progress(record)

    await asyncio.gather(*(_one(i, item) for i, item in enumerate(items)))
    return [r for r in records if r is not None]


@dataclass
class Metrics:
    threshold: float
    tp: int = 0
    fp: int = 0
    tn: int = 0
    fn: int = 0
    by_category: dict[str, dict[str, int]] = field(default_factory=dict)
    by_language: dict[str, dict[str, int]] = field(default_factory=dict)
    latency_p50_ms: float = 0.0
    latency_p95_ms: float = 0.0
    avg_est_tokens: float = 0.0
    llm_calls: int = 0
    errors: Counter = field(default_factory=Counter)
    false_positives: list[str] = field(default_factory=list)
    false_negatives: list[str] = field(default_factory=list)
    private_person_leaks: list[str] = field(default_factory=list)

    @property
    def precision(self) -> float:
        return self.tp / (self.tp + self.fp) if (self.tp + self.fp) else 0.0

    @property
    def recall(self) -> float:
        return self.tp / (self.tp + self.fn) if (self.tp + self.fn) else 0.0

    @property
    def f1(self) -> float:
        p, r = self.precision, self.recall
        return 2 * p * r / (p + r) if (p + r) else 0.0

    @property
    def fp_rate(self) -> float:
        return self.fp / (self.fp + self.tn) if (self.fp + self.tn) else 0.0

    @property
    def targets_met(self) -> bool:
        return self.precision >= LLM_MIN_PRECISION and self.fp_rate <= LLM_MAX_FP_RATE and not self.private_person_leaks


def _percentile(values: Sequence[float], pct: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    k = (len(ordered) - 1) * pct
    lo, hi = int(k), min(int(k) + 1, len(ordered) - 1)
    return ordered[lo] + (ordered[hi] - ordered[lo]) * (k - lo)


def compute_metrics(
    records: Sequence[LLMRecord],
    *,
    sensitivity: str = DEFAULT_SENSITIVITY,
    threshold: Optional[float] = None,
) -> Metrics:
    thr = threshold if threshold is not None else threshold_for(sensitivity)
    m = Metrics(threshold=thr)
    cat: dict[str, dict[str, int]] = defaultdict(lambda: {"tp": 0, "fp": 0, "tn": 0, "fn": 0})
    lang: dict[str, dict[str, int]] = defaultdict(lambda: {"tp": 0, "fp": 0, "tn": 0, "fn": 0})
    latencies: list[float] = []
    tokens: list[int] = []
    for rec in records:
        pred = rec.predicted(sensitivity, thr)
        cell = ("tp" if rec.label == 1 else "fp") if pred == 1 else ("fn" if rec.label == 1 else "tn")
        setattr(m, cell, getattr(m, cell) + 1)
        cat[rec.category][cell] += 1
        lang[rec.lang][cell] += 1
        if cell == "fp":
            m.false_positives.append(rec.id)
        elif cell == "fn":
            m.false_negatives.append(rec.id)
        if rec.meta is not None:
            m.llm_calls += 1
            latencies.append(rec.meta.latency_ms)
            tokens.append(rec.meta.est_tokens)
            if rec.meta.error:
                m.errors[rec.meta.error.split(":")[0]] += 1
        # Vazamento crítico: classificador marcou pessoa privada e MESMO ASSIM foi aceito
        if pred == 1 and rec.signal is not None and rec.signal.entity_type == "private_person":
            m.private_person_leaks.append(rec.id)
    m.by_category = dict(cat)
    m.by_language = dict(lang)
    m.latency_p50_ms = _percentile(latencies, 0.50)
    m.latency_p95_ms = _percentile(latencies, 0.95)
    m.avg_est_tokens = statistics.fmean(tokens) if tokens else 0.0
    return m


def threshold_sweep(
    records: Sequence[LLMRecord],
    thresholds: Iterable[float] = SWEEP_THRESHOLDS,
    *,
    sensitivity: str = DEFAULT_SENSITIVITY,
) -> list[Metrics]:
    return [compute_metrics(records, sensitivity=sensitivity, threshold=t) for t in thresholds]


def best_threshold(sweep: Sequence[Metrics]) -> Optional[Metrics]:
    """Menor threshold que cumpre as metas (maximiza recall dentro da meta); ``None`` se nenhum."""
    ok = [m for m in sweep if m.precision >= LLM_MIN_PRECISION and m.fp_rate <= LLM_MAX_FP_RATE]
    if not ok:
        return None
    return max(ok, key=lambda m: (m.recall, -m.threshold))


# ─────────────────────────────────────────────────────────────────────────────
# Relatório
# ─────────────────────────────────────────────────────────────────────────────

def _pct(value: float) -> str:
    return f"{value * 100:.1f} %"


def render_gate_markdown(ev: GateEvaluation) -> str:
    lines = [
        "### Estágio 1 — porteiro léxico (sem LLM)",
        "",
        "| Métrica | Valor | Meta |",
        "|---|---|---|",
        f"| Negativas rejeitadas sem LLM | {ev.negatives_rejected}/{ev.negatives} ({_pct(ev.rejected_negatives_rate)}) | ≥ 70 % |",
        f"| Positivas perdidas | {ev.positives_rejected}/{ev.positives} ({_pct(ev.lost_positives_rate)}) | ≤ 10 % |",
        f"| Resultado | {'✅ metas cumpridas' if ev.targets_met else '❌ abaixo da meta'} | |",
        "",
        "Motivos de rejeição (negativas):",
        "",
        "| Motivo | Qtd |",
        "|---|---|",
    ]
    for reason, count in ev.reject_reasons_negatives.most_common():
        lines.append(f"| `{reason}` | {count} |")
    lines += ["", "Por idioma:", "", "| Idioma | Positivas (perdidas) | Negativas (rejeitadas) |", "|---|---|---|"]
    for lang_code, st in sorted(ev.by_language.items()):
        lines.append(f"| {lang_code} | {st['pos']} ({st['pos_lost']}) | {st['neg']} ({st['neg_rejected']}) |")
    lines += ["", f"Negativas que passam ao classificador: {', '.join(ev.passed_negatives) or '—'}"]
    if ev.lost_positives:
        lines += ["", "Positivas perdidas: " + ", ".join(f"{i} (`{r}`)" for i, r in ev.lost_positives)]
    return "\n".join(lines)


def render_llm_markdown(metrics: Metrics, sweep: Optional[Sequence[Metrics]] = None,
                        model_label: str = "") -> str:
    lines = [
        f"### Estágio 2 — classificador{(' — ' + model_label) if model_label else ''}",
        "",
        "| Métrica | Valor | Meta |",
        "|---|---|---|",
        f"| Threshold avaliado | {metrics.threshold:.2f} | medium = 0,70 |",
        f"| Precisão | {metrics.precision:.3f} | ≥ 0,85 |",
        f"| Recall | {metrics.recall:.3f} | — |",
        f"| F1 | {metrics.f1:.3f} | — |",
        f"| Taxa de falsos positivos | {_pct(metrics.fp_rate)} | ≤ 5 % |",
        f"| Matriz (TP/FP/TN/FN) | {metrics.tp}/{metrics.fp}/{metrics.tn}/{metrics.fn} | |",
        f"| Latência p50 / p95 | {metrics.latency_p50_ms:.0f} ms / {metrics.latency_p95_ms:.0f} ms | p95 ≤ 4 000 ms |",
        f"| Tokens médios (estimados) | {metrics.avg_est_tokens:.0f} | |",
        f"| Chamadas ao modelo | {metrics.llm_calls} | |",
        f"| Erros | {dict(metrics.errors) or '—'} | |",
        f"| Vazamentos `private_person` | {', '.join(metrics.private_person_leaks) or 'nenhum'} | 0 |",
        f"| Resultado | {'✅ metas cumpridas' if metrics.targets_met else '❌ abaixo da meta'} | |",
        "",
        "Por categoria (TP/FP/TN/FN):",
        "",
        "| Categoria | TP | FP | TN | FN |",
        "|---|---|---|---|---|",
    ]
    for name, c in sorted(metrics.by_category.items()):
        lines.append(f"| {name} | {c['tp']} | {c['fp']} | {c['tn']} | {c['fn']} |")
    lines += ["", "Por idioma (TP/FP/TN/FN):", "", "| Idioma | TP | FP | TN | FN |", "|---|---|---|---|---|"]
    for name, c in sorted(metrics.by_language.items()):
        lines.append(f"| {name} | {c['tp']} | {c['fp']} | {c['tn']} | {c['fn']} |")
    if metrics.false_positives:
        lines += ["", "Falsos positivos: " + ", ".join(metrics.false_positives)]
    if metrics.false_negatives:
        lines += ["", "Falsos negativos: " + ", ".join(metrics.false_negatives)]
    if sweep:
        lines += ["", "Varredura de threshold:", "", "| Threshold | Precisão | Recall | F1 | FP rate |", "|---|---|---|---|---|"]
        for m in sweep:
            lines.append(f"| {m.threshold:.2f} | {m.precision:.3f} | {m.recall:.3f} | {m.f1:.3f} | {_pct(m.fp_rate)} |")
        best = best_threshold(sweep)
        lines += ["", f"Melhor threshold dentro das metas: {best.threshold:.2f}" if best else "Nenhum threshold cumpre as metas."]
    return "\n".join(lines)


def render_markdown(gate_eval: GateEvaluation, llm_metrics: Optional[Metrics] = None,
                    sweep: Optional[Sequence[Metrics]] = None, model_label: str = "") -> str:
    parts = [render_gate_markdown(gate_eval)]
    if llm_metrics is not None:
        parts.append(render_llm_markdown(llm_metrics, sweep, model_label))
    return "\n\n".join(parts) + "\n"
