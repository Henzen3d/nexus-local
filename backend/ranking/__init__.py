# j:\Arquivos Osmar\Multi+\backend\ranking\__init__.py
# Modulo de Ranking do NexusLocal
from .quota import (
    get_quota_status,
    mark_model_exhausted,
    mark_model_success,
    release_expired_quotas
)
from .failover import (
    resolve_model_with_failover,
    NoAvailableModelError,
    ResolvedModel,
)
