# j:\Arquivos Osmar\Multi+\backend\ranking\__init__.py
# Modulo de Ranking do NexusLocal
from .quota import (
    get_quota_status,
    mark_model_exhausted,
    mark_model_success,
    release_expired_quotas,
    is_quota_exhausted_error,
)
from .failover import (
    resolve_model_with_failover,
    NoAvailableModelError,
    ResolvedModel,
)
from .smart_router import (
    IntentKey,
    ComplexityTier,
    RoutingPolicy,
    IntentClassificationResult,
    AutoRouteDecision,
    classify_intent,
    select_best_model,
    is_adaptive_routing_enabled,
    set_adaptive_routing_enabled,
)
from .classifier import (
    classify_failure,
    extract_suggested_model,
    FailureClassification,
)
from .canonical import (
    canonical_model_id,
    extract_family_from_canonical,
    apply_zero_token_cooldown,
)
from .eligibility import (
    check_candidate_eligibility,
    is_candidate_eligible_in_memory,
    EligibilityResult,
)
from .admission import admission_controller
from .health_registry import (
    health_registry,
    InMemoryHealthRegistry,
    HealthConfig,
)

