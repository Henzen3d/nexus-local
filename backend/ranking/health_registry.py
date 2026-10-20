"""
backend/ranking/health_registry.py
Health Registry em Memória + Persistência em Lote + Modo SOMBRA.

Implementa as seções 6.2, 6.4 e Fase B2 do Golden Prompt v3.0:
- Registro operacional em RAM baseado em EWMA (TTFT e velocidade) e janelas temporais de confiabilidade.
- Shrinkage estatístico para pequenas amostras (K ≈ 10).
- Circuit breaker adaptativo (omega) com decaimento exponencial por meia-vida.
- Curva de pressão de quota contínua (phi_quota).
- Clamps rígidos garantindo fatores estritamente finitos sem ln(0).
- Modo SOMBRA: score calculado e logado sem alterar o roteamento em produção.
- Flush assíncrono em lote a cada 60s (write-behind) e no shutdown, sem travar o event loop nem chamadas de LLM.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from datetime import datetime, timezone
import math
import threading
import time
from typing import Dict, List, Optional, Tuple, Any
import aiosqlite

from backend.logging_config import get_logger
from backend.ranking.canonical import canonical_model_id

logger = get_logger(__name__)


# ── Parâmetros de Configuração do Score e Registry ───────────────────────────

@dataclass
class HealthConfig:
    # Pesos do score multiplicativo (soma 1.0)
    w_rel: float = 0.45
    w_lat: float = 0.15
    w_quota: float = 0.20
    w_brk: float = 0.20

    # Limites do multiplicador de saúde H
    H_MIN: float = 0.05
    H_MAX: float = 1.10

    # Clamps dos fatores individuais antes do logaritmo
    phi_rel_min: float = 0.05
    phi_rel_max: float = 1.00

    phi_lat_min: float = 0.30
    phi_lat_max: float = 1.15

    phi_quota_min: float = 0.05
    phi_quota_max: float = 1.00

    omega_min: float = 0.02
    omega_max: float = 1.00

    # Shrinkage de confiabilidade
    k_shrinkage: float = 10.0

    # Coeficientes EWMA
    alpha_ttft: float = 0.30
    alpha_speed: float = 0.25
    baseline_ttft_ms: float = 1500.0

    # Circuit breaker penalty e meia-vida
    half_life_seconds: float = 300.0
    p_max: float = 0.98

    # Severidades de falha
    severity_timeout: float = 0.35
    severity_429: float = 0.60
    severity_zero_token: float = 0.50
    severity_402: float = 0.98
    severity_unknown: float = 0.40

    # Peso de mid-stream vs pré-stream
    mid_stream_weight: float = 2.0
    pre_stream_weight: float = 1.0

    # Modo SOMBRA (ativação do roteador adaptativo apenas em C1)
    shadow_mode: bool = True

    # Intervalo de flush em lote para o SQLite
    flush_interval_seconds: float = 60.0


# ── Registro Operacional em Memória por Modelo ───────────────────────────────

@dataclass
class ModelHealthRecord:
    model_id: str
    provider_id: str
    canonical_id: str

    # EWMA de latência
    ewma_ttft_ms: Optional[float] = None
    ewma_tps: Optional[float] = None

    # Circuit breaker
    penalty_p: float = 0.0
    last_failure_time: float = 0.0
    half_life_sec: float = 300.0

    # Amostras de eventos (timestamp monotônico, peso, outcome)
    # outcomes: 'SUCCESS', 'ZERO_TOKEN', 'MID_STREAM_DROP', 'RATE_LIMIT_429', 'TIMEOUT', etc.
    recent_events: List[Tuple[float, float, str]] = field(default_factory=list)

    # Pressão de cota [0.0, 1.0]
    quota_pressure: float = 0.0

    # Controle de estado sujo para write-behind
    dirty: bool = False
    last_flush_time: float = 0.0


# ── Gerenciador do Health Registry ───────────────────────────────────────────

class InMemoryHealthRegistry:
    """Registro de saúde em RAM com cálculo probabilístico, modo sombra e flush em lote."""

    def __init__(self, config: Optional[HealthConfig] = None):
        self.config = config or HealthConfig()
        self._lock = threading.Lock()
        self._records: Dict[str, ModelHealthRecord] = {}
        self._flush_task: Optional[asyncio.Task] = None
        self._running = False

    def _get_or_create(self, model_id: str, provider_id: str) -> ModelHealthRecord:
        with self._lock:
            if model_id not in self._records:
                cid = canonical_model_id(model_id)
                self._records[model_id] = ModelHealthRecord(
                    model_id=model_id,
                    provider_id=provider_id,
                    canonical_id=cid,
                    half_life_sec=self.config.half_life_seconds,
                )
            return self._records[model_id]

    def get_record(self, model_id: str) -> Optional[ModelHealthRecord]:
        with self._lock:
            return self._records.get(model_id)

    def record_success(
        self,
        model_id: str,
        provider_id: str,
        ttft_ms: Optional[float] = None,
        chars_per_sec: Optional[float] = None,
    ) -> None:
        """Registra sucesso na resposta do modelo e atualiza EWMAs."""
        rec = self._get_or_create(model_id, provider_id)
        now_mono = time.monotonic()
        with self._lock:
            rec.recent_events.append((now_mono, 1.0, "SUCCESS"))
            # Poda eventos mais velhos que 24h (86400s)
            rec.recent_events = [e for e in rec.recent_events if (now_mono - e[0]) <= 86400.0]

            # Atualiza TTFT EWMA
            if ttft_ms is not None and ttft_ms > 0:
                if rec.ewma_ttft_ms is None:
                    rec.ewma_ttft_ms = float(ttft_ms)
                else:
                    rec.ewma_ttft_ms = (
                        self.config.alpha_ttft * float(ttft_ms)
                        + (1.0 - self.config.alpha_ttft) * rec.ewma_ttft_ms
                    )

            # Atualiza Velocidade EWMA
            if chars_per_sec is not None and chars_per_sec > 0:
                # 4 caracteres por token aproximado para tps
                tps = chars_per_sec / 4.0
                if rec.ewma_tps is None:
                    rec.ewma_tps = float(tps)
                else:
                    rec.ewma_tps = (
                        self.config.alpha_speed * float(tps)
                        + (1.0 - self.config.alpha_speed) * rec.ewma_tps
                    )

            rec.dirty = True

    def record_failure(
        self,
        model_id: str,
        provider_id: str,
        outcome: str,
        stage: str = "pre_stream",
    ) -> None:
        """Registra falha categorizada, atualiza penalidade acumulada P e relógio de meia-vida."""
        rec = self._get_or_create(model_id, provider_id)
        now_mono = time.monotonic()

        weight = self.config.mid_stream_weight if stage == "mid_stream" else self.config.pre_stream_weight

        # Determina severidade conforme taxonomia unificada
        outcome_upper = outcome.upper()
        if "402" in outcome_upper or "QUOTA" in outcome_upper:
            sev = self.config.severity_402
        elif "429" in outcome_upper or "RATE_LIMIT" in outcome_upper:
            sev = self.config.severity_429
        elif "ZERO_TOKEN" in outcome_upper:
            sev = self.config.severity_zero_token
        elif "TIMEOUT" in outcome_upper or "5" in outcome_upper:
            sev = self.config.severity_timeout
        else:
            sev = self.config.severity_unknown

        with self._lock:
            rec.recent_events.append((now_mono, weight, outcome_upper))
            rec.recent_events = [e for e in rec.recent_events if (now_mono - e[0]) <= 86400.0]

            # Atualiza penalidade com decaimento prévio caso houvesse
            if rec.last_failure_time > 0 and rec.penalty_p > 0:
                dt = max(0.0, now_mono - rec.last_failure_time)
                rec.penalty_p = rec.penalty_p * (2.0 ** (-dt / rec.half_life_sec))

            # P_new = min(P_MAX, 1 - (1 - P_old) * (1 - severity))
            rec.penalty_p = min(self.config.p_max, 1.0 - (1.0 - rec.penalty_p) * (1.0 - sev))
            rec.last_failure_time = now_mono
            rec.dirty = True

    def calculate_health(
        self,
        model_id: str,
        provider_id: str,
        now_mono: Optional[float] = None,
        quota_pressure: Optional[float] = None,
    ) -> Tuple[float, Dict[str, float]]:
        """
        Calcula o multiplicador de saúde H e retorna os fatores individuais clampados.
        Garante valores 100% finitos sem ln(0), NaN ou inf.
        """
        rec = self._get_or_create(model_id, provider_id)
        now = now_mono or time.monotonic()
        cfg = self.config

        with self._lock:
            # ── 1. phi_rel (Confiabilidade com Shrinkage e Janelas) ──────────
            # Janelas sobrepostas: 10m (600s), 1h (3600s), 24h (86400s)
            w_10m, w_1h, w_24h = 0.60, 0.25, 0.15
            attempts_10m = sum(e[1] for e in rec.recent_events if (now - e[0]) <= 600.0)
            success_10m = sum(e[1] for e in rec.recent_events if (now - e[0]) <= 600.0 and e[2] == "SUCCESS")

            attempts_1h = sum(e[1] for e in rec.recent_events if (now - e[0]) <= 3600.0)
            success_1h = sum(e[1] for e in rec.recent_events if (now - e[0]) <= 3600.0 and e[2] == "SUCCESS")

            attempts_24h = sum(e[1] for e in rec.recent_events if (now - e[0]) <= 86400.0)
            success_24h = sum(e[1] for e in rec.recent_events if (now - e[0]) <= 86400.0 and e[2] == "SUCCESS")

            eff_attempts = (w_10m * attempts_10m) + (w_1h * attempts_1h) + (w_24h * attempts_24h)
            eff_success = (w_10m * success_10m) + (w_1h * success_1h) + (w_24h * success_24h)

            if eff_attempts > 0:
                raw_rel = eff_success / max(eff_attempts, 1e-6)
                confidence = eff_attempts / (eff_attempts + cfg.k_shrinkage)
                phi_rel = 1.0 + confidence * (raw_rel - 1.0)
            else:
                phi_rel = 1.0  # Sem dados = neutro

            # ── 2. phi_latency (EWMA de TTFT) ────────────────────────────────
            if rec.ewma_ttft_ms is not None and rec.ewma_ttft_ms > 0:
                # Relação contra baseline TTFT (1500ms)
                # Mais rápido que baseline -> até 1.15; muito lento -> até 0.30
                phi_lat = cfg.baseline_ttft_ms / max(rec.ewma_ttft_ms, 200.0)
            else:
                phi_lat = 1.0  # Neutro

            # ── 3. phi_quota (Curva Contínua de Pressão de Quota) ───────────
            s = quota_pressure if quota_pressure is not None else rec.quota_pressure
            s = max(0.0, min(1.0, float(s)))
            if s <= 0.70:
                phi_quota = 1.0
            elif s < 0.95:
                phi_quota = 1.0 - 0.95 * ((s - 0.70) / 0.25)
            else:
                phi_quota = 0.05

            # ── 4. omega (Circuit Breaker com Decaimento) ────────────────────
            if rec.last_failure_time > 0 and rec.penalty_p > 0:
                dt = max(0.0, now - rec.last_failure_time)
                cur_p = rec.penalty_p * (2.0 ** (-dt / rec.half_life_sec))
            else:
                cur_p = 0.0
            omega = 1.0 - cur_p

        # Clamps estritos para evitar ln(0) e outliers
        c_phi_rel = max(cfg.phi_rel_min, min(cfg.phi_rel_max, phi_rel))
        c_phi_lat = max(cfg.phi_lat_min, min(cfg.phi_lat_max, phi_lat))
        c_phi_quota = max(cfg.phi_quota_min, min(cfg.phi_quota_max, phi_quota))
        c_omega = max(cfg.omega_min, min(cfg.omega_max, omega))

        # Log-ponderação e exponencial
        log_h = (
            cfg.w_rel * math.log(c_phi_rel)
            + cfg.w_lat * math.log(c_phi_lat)
            + cfg.w_quota * math.log(c_phi_quota)
            + cfg.w_brk * math.log(c_omega)
        )
        h_val = math.exp(log_h)
        h_clamped = max(cfg.H_MIN, min(cfg.H_MAX, h_val))

        factors = {
            "phi_rel": round(c_phi_rel, 4),
            "phi_lat": round(c_phi_lat, 4),
            "phi_quota": round(c_phi_quota, 4),
            "omega": round(c_omega, 4),
            "H": round(h_clamped, 4),
        }
        return h_clamped, factors

    def calculate_shadow_score(
        self,
        model_id: str,
        provider_id: str,
        base_score: float,
        fit_score: float = 1.0,
        quota_pressure: Optional[float] = None,
    ) -> Tuple[float, float, Dict[str, float]]:
        """
        Calcula o score de saúde em modo sombra:
        shadow_effective_score = base_score * fit_score * H
        Retorna (shadow_effective_score, H, factors).
        """
        h_val, factors = self.calculate_health(
            model_id=model_id,
            provider_id=provider_id,
            quota_pressure=quota_pressure,
        )
        shadow_score = float(base_score) * float(fit_score) * h_val
        return shadow_score, h_val, factors

    async def flush_dirty_records(self, db: aiosqlite.Connection) -> int:
        """
        Persistência write-behind em lote. Grava registros com alterações em RAM
        na tabela model_quota_status. Não bloqueia conexões do usuário.
        """
        dirty_records: List[ModelHealthRecord] = []
        with self._lock:
            for rec in self._records.values():
                if rec.dirty:
                    dirty_records.append(rec)

        if not dirty_records:
            return 0

        now_mono = time.monotonic()
        flushed_count = 0
        try:
            for r in dirty_records:
                h_val, factors = self.calculate_health(r.model_id, r.provider_id, now_mono=now_mono)
                # Atualiza as colunas de health metrics preservando compatibilidade
                await db.execute("""
                    UPDATE model_quota_status
                    SET penalty_score = ?,
                        last_failure_ts = ?,
                        half_life_sec = ?,
                        ewma_ttft_ms = ?,
                        ewma_tps = ?,
                        sr_10m = ?,
                        canonical_id = ?
                    WHERE model_id = ?
                """, (
                    r.penalty_p,
                    r.last_failure_time,
                    r.half_life_sec,
                    r.ewma_ttft_ms or 1500.0,
                    r.ewma_tps or 30.0,
                    factors["phi_rel"],
                    r.canonical_id,
                    r.model_id,
                ))
                flushed_count += 1

            await db.commit()
            with self._lock:
                for r in dirty_records:
                    r.dirty = False
                    r.last_flush_time = now_mono

            logger.debug("HealthRegistry: flush de %d registros em lote persistido com sucesso.", flushed_count)
        except Exception as e:
            # Preserva estado dirty em RAM caso o banco esteja travado para tentar na próxima rodada
            logger.warning("HealthRegistry: falha no flush em lote (tentará na próxima rodada): %s", e)
        return flushed_count

    async def start_background_flush_loop(self, db_getter):
        """Inicia tarefa de background assíncrona para flush periódico a cada 60s."""
        self._running = True
        logger.info(
            "HealthRegistry: loop de flush em lote iniciado (intervalo: %.0fs).",
            self.config.flush_interval_seconds,
        )
        while self._running:
            try:
                await asyncio.sleep(self.config.flush_interval_seconds)
                db = await db_getter()
                try:
                    await self.flush_dirty_records(db)
                finally:
                    await db.close()
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error("Erro no loop de flush do HealthRegistry: %s", e)

    def stop_background_flush(self):
        self._running = False
        if self._flush_task and not self._flush_task.done():
            self._flush_task.cancel()


health_registry = InMemoryHealthRegistry()
