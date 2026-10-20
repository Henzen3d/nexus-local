"""
backend/ranking/admission.py
Controle de Admissão e Semáforos de Concorrência (por modelo e por provedor).
Previne sobrecarga e thundering herd durante picos de tráfego e failovers em cascata.
"""

from __future__ import annotations
import threading
from typing import Dict


class AdmissionController:
    """Controlador de admissão em memória com contagem de requisições em voo (in-flight)."""

    def __init__(self, default_max_per_model: int = 10, default_max_per_provider: int = 30):
        self._lock = threading.Lock()
        self._inflight_by_model: Dict[str, int] = {}
        self._inflight_by_provider: Dict[str, int] = {}
        self._active_canary_probes: set[str] = set()
        self.max_per_model = default_max_per_model
        self.max_per_provider = default_max_per_provider

    def try_acquire_canary_probe(self, scope_key: str) -> bool:
        """
        Adquire um probe canary single-flight por escopo (model_id ou provider_id).
        Garante que apenas UM probe concorra para recuperar o modelo/provedor após cooldown.
        """
        with self._lock:
            if scope_key in self._active_canary_probes:
                return False
            self._active_canary_probes.add(scope_key)
            return True

    def release_canary_probe(self, scope_key: str) -> None:
        """Libera o lock do probe canary após a conclusão da requisição."""
        with self._lock:
            self._active_canary_probes.discard(scope_key)

    def is_canary_in_flight(self, scope_key: str) -> bool:
        with self._lock:
            return scope_key in self._active_canary_probes

    def is_admission_available(self, model_id: str, provider_id: str) -> bool:
        """Verifica se há capacidade de admissão disponível para o modelo e provedor."""
        with self._lock:
            if self._inflight_by_model.get(model_id, 0) >= self.max_per_model:
                return False
            if self._inflight_by_provider.get(provider_id, 0) >= self.max_per_provider:
                return False
            return True

    def acquire(self, model_id: str, provider_id: str) -> bool:
        """Tenta adquirir um slot de admissão. Retorna True se concedido, False se cheio."""
        with self._lock:
            if self._inflight_by_model.get(model_id, 0) >= self.max_per_model:
                return False
            if self._inflight_by_provider.get(provider_id, 0) >= self.max_per_provider:
                return False

            self._inflight_by_model[model_id] = self._inflight_by_model.get(model_id, 0) + 1
            self._inflight_by_provider[provider_id] = self._inflight_by_provider.get(provider_id, 0) + 1
            return True

    def release(self, model_id: str, provider_id: str) -> None:
        """Libera o slot de admissão ao concluir o processamento ou stream."""
        with self._lock:
            if model_id in self._inflight_by_model:
                self._inflight_by_model[model_id] = max(0, self._inflight_by_model[model_id] - 1)
            if provider_id in self._inflight_by_provider:
                self._inflight_by_provider[provider_id] = max(0, self._inflight_by_provider[provider_id] - 1)

    def get_in_flight_counts(self, model_id: str, provider_id: str) -> tuple[int, int]:
        with self._lock:
            return (
                self._inflight_by_model.get(model_id, 0),
                self._inflight_by_provider.get(provider_id, 0),
            )

    def reset(self) -> None:
        """Limpa todo o estado para testes."""
        with self._lock:
            self._inflight_by_model.clear()
            self._inflight_by_provider.clear()
            self._active_canary_probes.clear()
            self.max_per_model = 10
            self.max_per_provider = 30


admission_controller = AdmissionController()
