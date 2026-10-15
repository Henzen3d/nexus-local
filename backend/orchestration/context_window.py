"""Política de janela de contexto e fallback de poda — item 04."""


REGISTRY_TRUST_FROM = "2026-10"
TRIM_FAIL_KEEP = 12


def resolve_context_length(
    api_context: int | None,
    registry_ctx: int | None = None,
    verified_at: str | None = None,
) -> int:
    """Decide o context_length a gravar com base na API e no registry.

    - Se a API devolveu um valor positivo, usa ele como base.
    - Se o registry tiver valor maior E verified_at >= 2026-10, sobe para max(base, registry).
    - Heurística por nome de modelo não entra aqui.
    """
    base = api_context if api_context and api_context > 0 else 8192
    if not registry_ctx or registry_ctx <= 0:
        return base
    if not verified_at or verified_at < REGISTRY_TRUST_FROM:
        return base
    return max(base, registry_ctx)


def history_after_trim_failure(history: list, keep: int = TRIM_FAIL_KEEP) -> list:
    """Quando a poda lança exceção, entrega as últimas N mensagens."""
    if not history:
        return []
    return history[-keep:]
