"""Telemetria mínima do Intelligent UI (plano 06, "medir antes de ligar").

Quatro perguntas por turno, em contadores de processo e uma linha de log:

- ``offered``: o catálogo entrou no prompt?
- ``produced``: o modelo escreveu um fence fechado?
- ``valid``: o envelope passou no validador (pelo menos um bloco)?
- ``discarded``: por que não (``no_fence``, ``invalid_json``, ``rejected_envelope``,
  ``empty_after_validation``) e quantos blocos caíram no caminho (``blocks_dropped``).

Sem dependência externa e sem tabela: os números zeram no restart e servem
para a pergunta operacional "está valendo a pena ligar?". ``GET
/api/intelligent-ui/stats`` (admin) expõe o snapshot.
"""
from __future__ import annotations

import json
import threading
import time
from collections import Counter
from typing import Any

from loguru import logger

from backend.ui_blocks.extract import FENCE_CHART_CLOSED_REGEX, FENCE_CLOSED_REGEX

DISCARD_REASONS = ("no_fence", "invalid_json", "rejected_envelope", "empty_after_validation")


def inspect_fence(text: str) -> dict[str, Any]:
    """Olha o último fence fechado do texto sem validar: há fence? JSON parseia? quantos blocos?"""
    matches = list(FENCE_CLOSED_REGEX.finditer(text or ""))
    alt = False
    if not matches:
        matches = list(FENCE_CHART_CLOSED_REGEX.finditer(text or ""))
        alt = bool(matches)
    if not matches:
        return {"found": False, "alt_fence": False, "json_ok": False, "raw_blocks": 0, "raw_len": 0}
    raw = matches[-1].group(1).strip()
    try:
        data = json.loads(raw)
        json_ok = True
    except (ValueError, TypeError):
        data = None
        json_ok = False
    raw_blocks = 0
    if isinstance(data, dict):
        blocks = data.get("blocks")
        if isinstance(blocks, list):
            raw_blocks = len(blocks)
        elif isinstance(blocks, dict) or "type" in data or any(k in data for k in ("kind", "steps", "fields", "html", "facts", "body", "items")):
            raw_blocks = 1
    return {"found": True, "alt_fence": alt, "json_ok": json_ok, "raw_blocks": raw_blocks, "raw_len": len(raw)}


class IntelligentUiTelemetry:
    """Contadores de processo, thread-safe, com snapshot serializável."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self.reset()

    def reset(self) -> None:
        with self._lock:
            self.since = time.time()
            self.turns = 0
            self.offered = 0
            self.produced = 0
            self.produced_when_offered = 0
            self.produced_without_offer = 0
            self.valid = 0
            self.blocks_in = 0
            self.blocks_out = 0
            self.discarded: Counter[str] = Counter()
            self.block_types: Counter[str] = Counter()
            self.modules_offered: Counter[str] = Counter()
            self.modules_produced: Counter[str] = Counter()
            self.error_codes: Counter[str] = Counter()
            self.diagnostic_dropped = 0
            self.corrections: dict[str, Counter] = {}
            self._correction_messages: dict[tuple[str, str], tuple[str, bool]] = {}

    def record_turn(
        self,
        *,
        offered: bool,
        modules: tuple[str, ...] = (),
        text: str,
        envelope: dict[str, Any] | None,
        voice_mode: bool = False,
        request_id: str | None = None,
        ui_errors: list[dict] | None = None,
        ui_dropped: int = 0,
    ) -> dict[str, Any]:
        """Registra um turno com a flag ligada. Devolve o resumo (também vai para o log)."""
        info = inspect_fence(text)
        produced = bool(info["found"])
        out_blocks = len(envelope.get("blocks", [])) if isinstance(envelope, dict) else 0
        valid = out_blocks > 0

        reason: str | None = None
        if not produced:
            reason = "no_fence"
        elif not info["json_ok"]:
            reason = "invalid_json"
        elif not valid:
            # JSON parseou mas nada sobrou: envelope rejeitado (v≠1, sem blocks…) ou blocos todos inválidos
            reason = "empty_after_validation" if info["raw_blocks"] > 0 else "rejected_envelope"

        dropped = max(0, int(info["raw_blocks"]) - out_blocks) if produced and info["json_ok"] else 0

        with self._lock:
            self.error_codes.update(e["code"] for e in (ui_errors or []))
            self.diagnostic_dropped += ui_dropped
            self.turns += 1
            if offered:
                self.offered += 1
                self.modules_offered.update(set(modules))
            if produced:
                self.produced += 1
                if offered:
                    self.produced_when_offered += 1
                else:
                    self.produced_without_offer += 1
            if valid:
                self.valid += 1
                self.modules_produced.update({str(b.get("type")) for b in envelope.get("blocks", [])})
                for b in envelope.get("blocks", []):  # type: ignore[union-attr]
                    self.block_types[str(b.get("type", "?"))] += 1
            if produced and info["json_ok"]:
                self.blocks_in += int(info["raw_blocks"])
                self.blocks_out += out_blocks
            # Só conta descarte quando houve tentativa (offered ou fence): "no_fence" sem
            # oferta é o caminho normal de um turno de prosa, não um descarte.
            if reason and (offered or produced):
                self.discarded[reason] += 1

        summary = {
            "offered": offered,
            "modules": list(modules) if offered else [],
            "produced": produced,
            "valid": valid,
            "alt_fence": info["alt_fence"],
            "blocks_in": int(info["raw_blocks"]) if produced else 0,
            "blocks_out": out_blocks,
            "blocks_dropped": dropped,
            "reason": reason,
            "voice_mode": voice_mode,
        }
        logger.bind(request_id=request_id).info(
            "intelligent_ui turn offered={offered} produced={produced} valid={valid} "
            "blocks={blocks_in}/{blocks_out} dropped={blocks_dropped} reason={reason} modules={modules}",
            **summary,
        )
        return summary

    def offer_correction(self, user_id: str, message_id: str, model_id: str) -> None:
        with self._lock:
            key = (user_id, message_id)
            if key in self._correction_messages:
                return
            # Bounded process-only state, no error payload or conversation text.
            if len(self._correction_messages) >= 2048:
                self._correction_messages.pop(next(iter(self._correction_messages)))
            self._correction_messages[key] = (model_id, False)
            counts = self.corrections.setdefault(model_id, Counter(
                correction_offered=0, correction_requested=0, correction_valid=0))
            counts['correction_offered'] += 1

    def request_correction(self, user_id: str, message_id: str) -> str | None:
        with self._lock:
            key = (user_id, message_id)
            offer = self._correction_messages.get(key)
            if not offer or offer[1]:
                return None
            model_id = offer[0]
            self._correction_messages[key] = (model_id, True)
            self.corrections[model_id]['correction_requested'] += 1
            return model_id

    def correction_result(self, model_id: str, valid: bool) -> None:
        if valid:
            with self._lock:
                counts = self.corrections.get(model_id)
                if counts is not None:
                    counts['correction_valid'] += 1

    def snapshot(self) -> dict[str, Any]:
        with self._lock:
            return {
                "since": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(self.since)),
                "turns": self.turns,
                "offered": self.offered,
                "produced": self.produced,
                "produced_when_offered": self.produced_when_offered,
                "produced_without_offer": self.produced_without_offer,
                "valid": self.valid,
                "blocks_in": self.blocks_in,
                "blocks_out": self.blocks_out,
                "blocks_dropped": max(0, self.blocks_in - self.blocks_out),
                "discarded": {k: self.discarded.get(k, 0) for k in DISCARD_REASONS},
                "block_types": dict(self.block_types),
                "modules_offered": dict(self.modules_offered),
                "modules_produced": dict(self.modules_produced),
                "ui_error_codes": dict(self.error_codes),
                "ui_dropped": self.diagnostic_dropped,
                "corrections": {model: {**dict(counts), "valid_rate": _ratio(counts["correction_valid"], counts["correction_requested"])} for model, counts in self.corrections.items()},
                "rates": {
                    "produced_given_offered": _ratio(self.produced_when_offered, self.offered),
                    "valid_given_produced": _ratio(self.valid, self.produced),
                    "blocks_kept": _ratio(self.blocks_out, self.blocks_in),
                },
            }


def _ratio(num: int, den: int) -> float | None:
    return round(num / den, 3) if den else None


intelligent_ui_telemetry = IntelligentUiTelemetry()
