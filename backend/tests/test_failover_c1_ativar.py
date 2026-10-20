"""
backend/tests/test_failover_c1_ativar.py
Testes unitários da Etapa C1 do Golden Prompt v3.0:
- Ativação do score adaptativo por saúde (H) sob feature flag.
- Prevenção do efeito de rebanho (thundering herd): rajada de requisições
  distribui carga usando admission control load-aware em vez de migrar tudo
  para um único secundário.
- Canary probe single-flight por escopo: apenas uma requisição concorre para
  testar a recuperação de modelo/provedor após cooldown.
"""

import pytest
import aiosqlite
from unittest.mock import patch, MagicMock

from backend.ranking.smart_router import (
    rank_candidates,
    is_adaptive_routing_enabled,
    set_adaptive_routing_enabled,
    IntentClassificationResult,
    IntentKey,
    ComplexityTier,
)
from backend.ranking.health_registry import InMemoryHealthRegistry, HealthConfig
from backend.ranking.admission import admission_controller, AdmissionController
from backend.ranking.token_bucket import token_bucket_manager


@pytest.fixture(autouse=True)
def clean_admission_and_flag():
    admission_controller.reset()
    token_bucket_manager.reset()
    set_adaptive_routing_enabled(True)
    yield
    admission_controller.reset()
    token_bucket_manager.reset()
    set_adaptive_routing_enabled(None)


def make_dummy_intent():
    return IntentClassificationResult(
        intent=IntentKey.GENERAL_CHAT,
        complexity=ComplexityTier.LIGHT,
        confidence=0.9,
        reason_label_pt="Chat Geral",
        suggested_family=None,
        processing_time_ms=1.0,
        min_context_length_required=4096,
        recommended_temperature=0.7,
        matched_signals=[],
    )


def make_candidate(mid: str, pid: str, quality: float, is_free: int = 1):
    return {
        "id": mid,
        "provider_id": pid,
        "name": mid.split("/")[-1],
        "display_name": mid,
        "context_length": 16384,
        "confirmed_free": is_free,
        "prov_is_free": is_free,
        "is_free": is_free,
        "nexuslocal_score": quality,
        "quality_score": quality,
        "has_ranking": True,
        "quota_status": "available",
        "supports_vision": 0,
        "reasoning_control": "none",
        "reasoning_levels": [],
        "is_local": 0,
        "tags": ["chat"],
    }


def test_feature_flag_toggles_adaptive_scoring():
    """
    C1: Garante que a feature flag liga/desliga o cálculo do score adaptativo.
    Quando desligado, usa o fit/quality baseline. Quando ligado, aplica H e carga.
    """
    intent = make_dummy_intent()
    cand_a = make_candidate("prov1/mod_a", "prov1", quality=85.0)
    cand_b = make_candidate("prov2/mod_b", "prov2", quality=80.0)

    # 1. Com flag DESLIGADA: Mod A (qualidade 85) vence Mod B (qualidade 80)
    set_adaptive_routing_enabled(False)
    ranked_off = rank_candidates([cand_a, cand_b], intent, "balanced_smart")
    assert ranked_off[0]["model"]["id"] == "prov1/mod_a"

    # 2. Com flag LIGADA: Mod A degradado (H baixo) e Mod B saudável (H alto)
    set_adaptive_routing_enabled(True)
    custom_registry = InMemoryHealthRegistry(HealthConfig())
    # Mod A falhou várias vezes
    for _ in range(5):
        custom_registry.record_failure("prov1/mod_a", "prov1", "PRE_STREAM_ERR")
    # Mod B teve múltiplos sucessos rápidos
    for _ in range(5):
        custom_registry.record_success("prov2/mod_b", "prov2", ttft_ms=120.0)

    with patch("backend.ranking.smart_router.health_registry", custom_registry):
        ranked_on = rank_candidates([cand_a, cand_b], intent, "balanced_smart")
        # Mod B agora vence devido ao fator de saúde H muito superior
        assert ranked_on[0]["model"]["id"] == "prov2/mod_b"
        assert ranked_on[0]["H"] > ranked_on[1]["H"]


def test_burst_requests_distribute_load_preventing_thundering_herd():
    """
    Risco #3 / C1: Rajada de requisições concorrentes não migra toda para um único secundário.
    A contagem in-flight do admission control atua na ordenação efetiva.
    """
    intent = make_dummy_intent()
    cand_a = make_candidate("prov1/mod_sec1", "prov1", quality=82.0)
    cand_b = make_candidate("prov2/mod_sec2", "prov2", quality=80.0)

    # Inicialmente, mod_sec1 é melhor que mod_sec2
    ranked_init = rank_candidates([cand_a, cand_b], intent, "balanced_smart")
    assert ranked_init[0]["model"]["id"] == "prov1/mod_sec1"

    # Simula 2 requisições em voo (in-flight) já adquiridas no mod_sec1
    admission_controller.acquire("prov1/mod_sec1", "prov1")
    admission_controller.acquire("prov1/mod_sec1", "prov1")

    # A 3ª requisição concorrente avalia: a penalidade de carga em mod_sec1
    # faz com que mod_sec2 (sem carga) passe a ser selecionado como o melhor candidato!
    ranked_burst = rank_candidates([cand_a, cand_b], intent, "balanced_smart")
    assert ranked_burst[0]["model"]["id"] == "prov2/mod_sec2"
    assert ranked_burst[1]["model"]["id"] == "prov1/mod_sec1"


def test_canary_probe_single_flight():
    """
    C1: Canary probe HALF_OPEN é estritamente single-flight por escopo.
    Apenas UMA requisição concorre para testar a recuperação após cooldown.
    """
    adm = AdmissionController()
    scope = "prov1/recovering_model"

    # 1. Primeiro probe adquire com sucesso
    assert adm.try_acquire_canary_probe(scope) is True
    assert adm.is_canary_in_flight(scope) is True

    # 2. Segundo probe concorrente tenta ao mesmo tempo e é barrado (single-flight)
    assert adm.try_acquire_canary_probe(scope) is False

    # 3. Primeiro probe encerra e libera
    adm.release_canary_probe(scope)
    assert adm.is_canary_in_flight(scope) is False

    # 4. Novo probe agora pode adquirir
    assert adm.try_acquire_canary_probe(scope) is True
    adm.release_canary_probe(scope)
