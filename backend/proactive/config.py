"""Configuração do Assistente Proativo — Fase 2 (F2.2.1/F2.2.2).

Duas camadas:

* **Global (admin)** — :class:`ProactiveConfig`, lida de ``meta`` (chaves
  ``proactive_*``), com fallback para variáveis de ambiente ``PROACTIVE_*`` e,
  por fim, para os defaults do plano (3/h/conversa, 10/dia/usuário, cooldown
  24 h, 3 pendentes, concorrência 2, timeout total 45 s). Cache de 60 s no
  processo, no mesmo espírito do cache de role em ``backend/auth.py``.
* **Por usuário** — :class:`UserSettings`, lida de ``proactive_user_settings``.
  **Opt-in**: sem linha ⇒ ``enabled=False``.
"""
from __future__ import annotations

import asyncio
import json
import os
import re
import time
from dataclasses import dataclass, field, replace
from typing import Any, Optional

from backend.logging_config import get_logger

logger = get_logger(__name__)

ALLOWED_CATEGORIES: tuple[str, ...] = ("event", "news", "product", "place")
ALLOWED_SENSITIVITIES: tuple[str, ...] = ("low", "medium", "high")
DEFAULT_SENSITIVITY = "medium"

CONFIG_TTL_SECONDS = 60.0

DETECTOR_META_KEYS = ("proactive_detector_provider_id", "proactive_detector_model_id")
SYNTH_META_KEYS = ("proactive_synth_provider_id", "proactive_synth_model_id")


@dataclass(frozen=True)
class ProactiveConfig:
    """Parâmetros globais (admin). Imutável — use ``dataclasses.replace`` em testes."""

    enabled_global: bool = True
    detector_provider_id: Optional[str] = None
    detector_model_id: Optional[str] = None
    synth_provider_id: Optional[str] = None
    synth_model_id: Optional[str] = None
    max_per_hour_conv: int = 3
    max_per_day_user: int = 10
    topic_cooldown_hours: int = 24
    max_pending: int = 3
    concurrency: int = 2
    total_timeout_s: float = 45.0
    research_timeout_s: float = 30.0
    synth_timeout_s: float = 20.0
    allow_chat_model_fallback: bool = False
    # F4.4.1 — validade dos insights (news +48 h; demais categorias +7 d; event usa a data do evento)
    expiry_news_hours: int = 48
    expiry_default_days: int = 7
    # F5.4.3 — rollout gradual: o modal de onboarding só aparece quando o admin libera.
    # Enquanto estiver desligado, cada pessoa ainda pode ativar em Configurações.
    onboarding_enabled: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "enabled_global": self.enabled_global,
            "detector_provider_id": self.detector_provider_id,
            "detector_model_id": self.detector_model_id,
            "synth_provider_id": self.synth_provider_id,
            "synth_model_id": self.synth_model_id,
            "max_per_hour_conv": self.max_per_hour_conv,
            "max_per_day_user": self.max_per_day_user,
            "topic_cooldown_hours": self.topic_cooldown_hours,
            "max_pending": self.max_pending,
            "concurrency": self.concurrency,
            "total_timeout_s": self.total_timeout_s,
            "research_timeout_s": self.research_timeout_s,
            "synth_timeout_s": self.synth_timeout_s,
            "allow_chat_model_fallback": self.allow_chat_model_fallback,
            "expiry_news_hours": self.expiry_news_hours,
            "expiry_default_days": self.expiry_default_days,
            "onboarding_enabled": self.onboarding_enabled,
        }


# (campo do dataclass, chave em meta, variável de ambiente, conversor)
_FIELD_SPECS: tuple[tuple[str, str, str, str], ...] = (
    ("enabled_global", "proactive_enabled_global", "PROACTIVE_ENABLED_GLOBAL", "bool"),
    ("detector_provider_id", "proactive_detector_provider_id", "PROACTIVE_DETECTOR_PROVIDER_ID", "str"),
    ("detector_model_id", "proactive_detector_model_id", "PROACTIVE_DETECTOR_MODEL_ID", "str"),
    ("synth_provider_id", "proactive_synth_provider_id", "PROACTIVE_SYNTH_PROVIDER_ID", "str"),
    ("synth_model_id", "proactive_synth_model_id", "PROACTIVE_SYNTH_MODEL_ID", "str"),
    ("max_per_hour_conv", "proactive_max_per_hour_conv", "PROACTIVE_MAX_PER_HOUR_CONV", "int"),
    ("max_per_day_user", "proactive_max_per_day_user", "PROACTIVE_MAX_PER_DAY_USER", "int"),
    ("topic_cooldown_hours", "proactive_topic_cooldown_hours", "PROACTIVE_TOPIC_COOLDOWN_HOURS", "int"),
    ("max_pending", "proactive_max_pending", "PROACTIVE_MAX_PENDING", "int"),
    ("concurrency", "proactive_concurrency", "PROACTIVE_CONCURRENCY", "int"),
    ("total_timeout_s", "proactive_total_timeout_s", "PROACTIVE_TOTAL_TIMEOUT_S", "float"),
    ("research_timeout_s", "proactive_research_timeout_s", "PROACTIVE_RESEARCH_TIMEOUT_S", "float"),
    ("synth_timeout_s", "proactive_synth_timeout_s", "PROACTIVE_SYNTH_TIMEOUT_S", "float"),
    ("allow_chat_model_fallback", "proactive_allow_chat_model_fallback", "PROACTIVE_ALLOW_CHAT_MODEL_FALLBACK", "bool"),
    ("expiry_news_hours", "proactive_expiry_news_hours", "PROACTIVE_EXPIRY_NEWS_HOURS", "int"),
    ("expiry_default_days", "proactive_expiry_default_days", "PROACTIVE_EXPIRY_DEFAULT_DAYS", "int"),
    ("onboarding_enabled", "proactive_onboarding_enabled", "PROACTIVE_ONBOARDING_ENABLED", "bool"),
)

META_KEY_BY_FIELD: dict[str, str] = {spec[0]: spec[1] for spec in _FIELD_SPECS}
FIELD_KIND: dict[str, str] = {spec[0]: spec[3] for spec in _FIELD_SPECS}

#: F4.4.1 — limites aceitos pelo ``PUT /admin-config`` (mín., máx.). Fora disso ⇒ 422.
ADMIN_FIELD_LIMITS: dict[str, tuple[float, float]] = {
    "max_per_hour_conv": (0, 20),
    "max_per_day_user": (0, 100),
    "topic_cooldown_hours": (0, 720),
    "max_pending": (1, 10),
    "concurrency": (1, 8),
    "total_timeout_s": (10, 300),
    "research_timeout_s": (5, 300),
    "synth_timeout_s": (5, 120),
    "expiry_news_hours": (1, 720),
    "expiry_default_days": (1, 90),
}

_TRUE_WORDS = {"1", "true", "yes", "on", "sim"}
_FALSE_WORDS = {"0", "false", "no", "off", "nao", "não"}


def _coerce(raw: Any, kind: str, default: Any) -> Any:
    """Converte texto de ``meta``/env no tipo do campo; valor inválido ⇒ default."""
    if raw is None:
        return default
    text = str(raw).strip()
    if text == "":
        return default
    try:
        if kind == "bool":
            low = text.lower()
            if low in _TRUE_WORDS:
                return True
            if low in _FALSE_WORDS:
                return False
            return default
        if kind == "int":
            value = int(float(text))
            return value if value >= 0 else default
        if kind == "float":
            value = float(text)
            return value if value > 0 else default
        return text
    except (TypeError, ValueError):
        return default


_cache: Optional[tuple[float, ProactiveConfig]] = None
_cache_lock = asyncio.Lock()


def invalidate_config_cache() -> None:
    """Força releitura de ``meta`` na próxima chamada (PUT do admin, testes)."""
    global _cache
    _cache = None


async def _read_meta_map(db: Any) -> dict[str, str]:
    try:
        async with db.execute("SELECT key, value FROM meta WHERE key LIKE 'proactive_%'") as cur:
            rows = await cur.fetchall()
    except Exception as exc:  # tabela ausente em DBs muito antigos ⇒ defaults
        logger.debug("[Proactive] meta indisponível, usando defaults: %s", exc)
        return {}
    return {str(k): ("" if v is None else str(v)) for k, v in rows}


def build_config(meta: dict[str, str], env: Optional[dict[str, str]] = None) -> ProactiveConfig:
    """Resolve ``meta → env → defaults`` (puro; usado por :func:`load_config` e testes)."""
    env = os.environ if env is None else env
    defaults = ProactiveConfig()
    values: dict[str, Any] = {}
    for field_name, meta_key, env_key, kind in _FIELD_SPECS:
        default = getattr(defaults, field_name)
        resolved = _coerce(env.get(env_key), kind, default)
        if meta_key in meta and meta[meta_key].strip() != "":
            resolved = _coerce(meta[meta_key], kind, resolved)
        values[field_name] = resolved
    cfg = replace(defaults, **values)
    # Sanidade: concorrência ≥ 1, timeouts coerentes, validades ≥ 1
    if cfg.concurrency < 1:
        cfg = replace(cfg, concurrency=1)
    if cfg.research_timeout_s > cfg.total_timeout_s:
        cfg = replace(cfg, research_timeout_s=cfg.total_timeout_s)
    if cfg.expiry_news_hours < 1:
        cfg = replace(cfg, expiry_news_hours=defaults.expiry_news_hours)
    if cfg.expiry_default_days < 1:
        cfg = replace(cfg, expiry_default_days=defaults.expiry_default_days)
    return cfg


async def load_config(db: Any, *, force: bool = False) -> ProactiveConfig:
    """Carrega a configuração global com cache de 60 s por processo."""
    global _cache
    now = time.monotonic()
    if not force and _cache and _cache[0] > now:
        return _cache[1]
    async with _cache_lock:
        if not force and _cache and _cache[0] > now:
            return _cache[1]
        cfg = build_config(await _read_meta_map(db))
        _cache = (now + CONFIG_TTL_SECONDS, cfg)
        return cfg


def validate_admin_updates(updates: dict[str, Any]) -> dict[str, Any]:
    """Valida/normaliza o corpo do ``PUT /admin-config``. Levanta ``ValueError``
    com mensagem legível quando um campo está fora dos limites ou do tipo."""
    clean: dict[str, Any] = {}
    for field_name, value in updates.items():
        if field_name not in META_KEY_BY_FIELD:
            raise ValueError(f"campo desconhecido: {field_name}")
        if value is None:
            continue
        kind = FIELD_KIND[field_name]
        if kind == "bool":
            if isinstance(value, bool):
                clean[field_name] = value
            else:
                coerced = _coerce(value, "bool", None)
                if coerced is None:
                    raise ValueError(f"{field_name} deve ser booleano")
                clean[field_name] = coerced
            continue
        if kind == "str":
            text = str(value).strip()
            clean[field_name] = text  # "" ⇒ limpa a chave (volta ao env/default)
            continue
        try:
            number = float(value)
        except (TypeError, ValueError):
            raise ValueError(f"{field_name} deve ser numérico")
        low, high = ADMIN_FIELD_LIMITS.get(field_name, (0, float("inf")))
        if not (low <= number <= high):
            raise ValueError(f"{field_name} fora do intervalo [{low:g}, {high:g}]")
        clean[field_name] = int(number) if kind == "int" else number
    return clean


async def save_admin_config(db: Any, updates: dict[str, Any]) -> ProactiveConfig:
    """Persiste os campos informados em ``meta`` (padrão ``INSERT OR REPLACE``),
    invalida o cache e devolve a configuração efetiva (F4.4.1)."""
    for field_name, value in updates.items():
        key = META_KEY_BY_FIELD[field_name]
        if isinstance(value, bool):
            text = "true" if value else "false"
        elif isinstance(value, float):
            text = f"{value:g}"
        else:
            text = "" if value is None else str(value)
        if text == "":
            await db.execute("DELETE FROM meta WHERE key = ?", (key,))
        else:
            await db.execute("INSERT OR REPLACE INTO meta (key, value) VALUES (?, ?)", (key, text))
    await db.commit()
    invalidate_config_cache()
    return await load_config(db, force=True)


# ─────────────────────────────────────────────────────────────────────────────
# Preferências por usuário
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class UserSettings:
    user_id: str
    enabled: bool = False                       # opt-in
    sensitivity: str = DEFAULT_SENSITIVITY
    categories: list[str] = field(default_factory=lambda: list(ALLOWED_CATEGORIES))
    quiet_hours: Optional[dict[str, Any]] = None
    push_enabled: bool = False
    persona_style: str = "lumi"
    onboarding_seen_at: Optional[str] = None
    updated_at: Optional[str] = None
    exists: bool = False                        # havia linha no banco?

    def to_dict(self) -> dict[str, Any]:
        return {
            "enabled": self.enabled,
            "sensitivity": self.sensitivity,
            "categories": list(self.categories),
            "quiet_hours": self.quiet_hours,
            "push_enabled": self.push_enabled,
            "persona_style": self.persona_style,
            "onboarding_seen_at": self.onboarding_seen_at,
            "updated_at": self.updated_at,
        }


def _parse_json(raw: Any, default: Any) -> Any:
    if raw is None or raw == "":
        return default
    if isinstance(raw, (list, dict)):
        return raw
    try:
        return json.loads(raw)
    except (TypeError, ValueError):
        return default


def normalize_categories(value: Any) -> list[str]:
    """Mantém apenas categorias conhecidas, na ordem canônica, sem repetição."""
    if not isinstance(value, (list, tuple, set)):
        return list(ALLOWED_CATEGORIES)
    wanted = {str(v).strip().lower() for v in value}
    return [c for c in ALLOWED_CATEGORIES if c in wanted]


def normalize_sensitivity(value: Any) -> str:
    text = str(value or "").strip().lower()
    return text if text in ALLOWED_SENSITIVITIES else DEFAULT_SENSITIVITY


_HHMM = re.compile(r"^([01]\d|2[0-3]):[0-5]\d$")


def validate_quiet_hours(value: Any) -> Optional[dict[str, str]]:
    """``{start:"22:00", end:"08:00"}`` ou ``None``; qualquer outra forma ⇒ ``ValueError`` (F4.1.2)."""
    if value is None:
        return None
    if not isinstance(value, dict):
        raise ValueError("quiet_hours deve ser um objeto {start, end} ou null")
    start, end = value.get("start"), value.get("end")
    if not isinstance(start, str) or not isinstance(end, str) or not _HHMM.match(start) or not _HHMM.match(end):
        raise ValueError("quiet_hours.start/end devem estar no formato HH:MM")
    if start == end:
        raise ValueError("quiet_hours.start e end não podem ser iguais")
    return {"start": start, "end": end}


async def get_user_settings(db: Any, user_id: str) -> UserSettings:
    """Preferências do usuário; sem linha ⇒ defaults com ``enabled=False``."""
    try:
        async with db.execute(
            """SELECT enabled, sensitivity, categories_json, quiet_hours_json,
                      onboarding_seen_at, updated_at, push_enabled, persona_style
               FROM proactive_user_settings WHERE user_id = ?""",
            (user_id,),
        ) as cur:
            row = await cur.fetchone()
    except Exception:
        # Fallback para schemas antigos sem as colunas novas
        try:
            async with db.execute(
                """SELECT enabled, sensitivity, categories_json, quiet_hours_json,
                          onboarding_seen_at, updated_at
                   FROM proactive_user_settings WHERE user_id = ?""",
                (user_id,),
            ) as cur:
                row = await cur.fetchone()
        except Exception as exc:
            logger.debug("[Proactive] proactive_user_settings indisponível: %s", exc)
            row = None
    if not row:
        return UserSettings(user_id=user_id)
    push_val = bool(row[6]) if len(row) > 6 and row[6] is not None else False
    persona_val = str(row[7]) if len(row) > 7 and row[7] is not None else "lumi"
    return UserSettings(
        user_id=user_id,
        enabled=bool(row[0]),
        sensitivity=normalize_sensitivity(row[1]),
        categories=normalize_categories(_parse_json(row[2], list(ALLOWED_CATEGORIES))),
        quiet_hours=_parse_json(row[3], None) if row[3] else None,
        push_enabled=push_val,
        persona_style=persona_val,
        onboarding_seen_at=row[4],
        updated_at=row[5],
        exists=True,
    )


async def upsert_user_settings(
    db: Any,
    user_id: str,
    *,
    enabled: Optional[bool] = None,
    sensitivity: Optional[str] = None,
    categories: Optional[list[str]] = None,
    quiet_hours: Optional[dict[str, Any]] = None,
    clear_quiet_hours: bool = False,
    push_enabled: Optional[bool] = None,
    persona_style: Optional[str] = None,
    onboarding_seen: Optional[bool] = None,
) -> UserSettings:
    """Atualiza apenas os campos informados e devolve o estado final."""
    current = await get_user_settings(db, user_id)
    new_enabled = current.enabled if enabled is None else bool(enabled)
    new_sensitivity = current.sensitivity if sensitivity is None else normalize_sensitivity(sensitivity)
    new_categories = current.categories if categories is None else normalize_categories(categories)
    new_push = current.push_enabled if push_enabled is None else bool(push_enabled)
    new_persona = current.persona_style if persona_style is None else str(persona_style).strip().lower()
    if clear_quiet_hours:
        new_quiet: Optional[dict[str, Any]] = None
    else:
        new_quiet = current.quiet_hours if quiet_hours is None else quiet_hours
    new_onboarding = current.onboarding_seen_at
    if onboarding_seen is True and not new_onboarding:
        from datetime import datetime, timezone

        new_onboarding = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
    elif onboarding_seen is False:
        new_onboarding = None

    try:
        await db.execute(
            """INSERT INTO proactive_user_settings
                   (user_id, enabled, sensitivity, categories_json, quiet_hours_json, push_enabled, persona_style, onboarding_seen_at, updated_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, datetime('now'))
               ON CONFLICT(user_id) DO UPDATE SET
                   enabled = excluded.enabled,
                   sensitivity = excluded.sensitivity,
                   categories_json = excluded.categories_json,
                   quiet_hours_json = excluded.quiet_hours_json,
                   push_enabled = excluded.push_enabled,
                   persona_style = excluded.persona_style,
                   onboarding_seen_at = excluded.onboarding_seen_at,
                   updated_at = datetime('now')""",
            (
                user_id,
                1 if new_enabled else 0,
                new_sensitivity,
                json.dumps(new_categories, ensure_ascii=False),
                json.dumps(new_quiet, ensure_ascii=False) if new_quiet is not None else None,
                1 if new_push else 0,
                new_persona,
                new_onboarding,
            ),
        )
    except Exception:
        # Fallback se colunas ainda não existirem no DB
        await db.execute(
            """INSERT INTO proactive_user_settings
                   (user_id, enabled, sensitivity, categories_json, quiet_hours_json, onboarding_seen_at, updated_at)
               VALUES (?, ?, ?, ?, ?, ?, datetime('now'))
               ON CONFLICT(user_id) DO UPDATE SET
                   enabled = excluded.enabled,
                   sensitivity = excluded.sensitivity,
                   categories_json = excluded.categories_json,
                   quiet_hours_json = excluded.quiet_hours_json,
                   onboarding_seen_at = excluded.onboarding_seen_at,
                   updated_at = datetime('now')""",
            (
                user_id,
                1 if new_enabled else 0,
                new_sensitivity,
                json.dumps(new_categories, ensure_ascii=False),
                json.dumps(new_quiet, ensure_ascii=False) if new_quiet is not None else None,
                new_onboarding,
            ),
        )
    await db.commit()
    return await get_user_settings(db, user_id)
