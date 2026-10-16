"""backend/tools — Sistema de integração de ferramentas e APIs públicas do NexusLocal.
"""
from backend.tools.base import DEFAULT_TTL, ToolProvider, ToolResult
from backend.tools.cache import evict_expired, get_cached, invalidate_family, set_cached
from backend.tools.dispatcher import dispatch_tool
from backend.tools.failover import (
    get_tool_provider_quota_status,
    mark_tool_provider_exhausted,
    mark_tool_provider_success,
    release_expired_tool_quotas,
    resolve_tool,
)
from backend.tools.registry import (
    ToolRegistry,
    auto_register_default_providers,
    get_all_families,
    get_provider,
    get_providers,
    register_provider,
)
from backend.tools.security import is_safe_url, sanitize_data, sanitize_svg, wrap_tool_result
from backend.tools.intent import detect_intents, ToolIntent
from backend.tools.context_injector import format_single_tool_result, build_tools_context_block
from backend.tools.tool_definitions import TOOL_DEFINITIONS, handle_tool_call

__all__ = [
    "ToolResult",
    "ToolProvider",
    "DEFAULT_TTL",
    "ToolRegistry",
    "auto_register_default_providers",
    "register_provider",
    "get_providers",
    "get_provider",
    "get_all_families",
    "dispatch_tool",
    "resolve_tool",
    "get_tool_provider_quota_status",
    "mark_tool_provider_exhausted",
    "mark_tool_provider_success",
    "release_expired_tool_quotas",
    "get_cached",
    "set_cached",
    "evict_expired",
    "invalidate_family",
    "sanitize_data",
    "sanitize_svg",
    "is_safe_url",
    "wrap_tool_result",
    "detect_intents",
    "ToolIntent",
    "format_single_tool_result",
    "build_tools_context_block",
    "TOOL_DEFINITIONS",
    "handle_tool_call",
]

