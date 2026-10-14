"""Síntese do Assistente Proativo — Fase 2 (F2.4).

Transforma ``InterestSignal`` + fontes em um texto curto no idioma da mensagem
original, com linha de motivo, perguntas de continuação e URLs usadas. O
parser é tolerante (fences, prosa em volta, ``<think>``) como no detector;
falha ⇒ ``Synthesis.error`` (``synth_parse`` | ``synth_timeout`` |
``synth_provider`` | ``no_synth_model``) — nunca levanta exceção.
"""
from __future__ import annotations

import asyncio
import json
import re
import time
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any, Optional, Sequence

from backend.logging_config import get_logger
from backend.proactive.config import SYNTH_META_KEYS, ProactiveConfig
from backend.proactive.detector import InterestSignal, _slice_first_json_object, normalize
from backend.proactive.researcher import Source, canonical_url

logger = get_logger(__name__)

MAX_TEXT_CHARS = 600
MAX_REASON_CHARS = 200
MAX_FOLLOW_UPS = 3
MAX_FOLLOW_UP_CHARS = 160
SYNTH_MAX_TOKENS = 700
DEFAULT_TIMEOUT_S = 20.0
MAX_MESSAGE_CHARS = 600
SOURCE_EXCERPT_CHARS = 1200

EXPIRY_BY_CATEGORY = {
    "news": timedelta(hours=48),
    "event": timedelta(days=7),
    "product": timedelta(days=7),
    "place": timedelta(days=7),
}
DEFAULT_EXPIRY = timedelta(days=7)

_URL_RE = re.compile(r"https?://\S+|www\.\S+", re.IGNORECASE)
_MD_LINK_RE = re.compile(r"\[([^\]]+)\]\((?:https?://|www\.)[^)]+\)")
_WS_RE = re.compile(r"\s+")


@dataclass
class Synthesis:
    text: str = ""
    reason_line: str = ""
    follow_ups: list[str] = field(default_factory=list)
    used_source_urls: list[str] = field(default_factory=list)
    event_date: Optional[str] = None
    model_label: str = ""
    model_source: str = ""
    latency_ms: float = 0.0
    raw: str = ""
    error: str = ""
    # telemetria para custo estimado (F5.2.4): chars do prompt e da resposta
    prompt_chars: int = 0
    response_chars: int = 0

    @property
    def ok(self) -> bool:
        return not self.error and bool(self.text)


# ─────────────────────────────────────────────────────────────────────────────
# Parser e pós-processamento (F2.4.2 / F2.4.4)
# ─────────────────────────────────────────────────────────────────────────────

def strip_links(text: str) -> str:
    """Remove links markdown (mantém o rótulo) e URLs soltas."""
    text = _MD_LINK_RE.sub(r"\1", text or "")
    text = _URL_RE.sub("", text)
    text = re.sub(r"\(\s*\)", "", text)          # parênteses vazios deixados por URLs
    text = re.sub(r"[ \t]{2,}", " ", text)
    return text.strip()


def clip_text(text: str, limit: int = MAX_TEXT_CHARS) -> str:
    text = _WS_RE.sub(" ", (text or "")).strip()
    if len(text) <= limit:
        return text
    cut = text[:limit]
    # Preferir terminar numa fronteira de frase
    for sep in (". ", "! ", "? "):
        idx = cut.rfind(sep)
        if idx >= limit * 0.5:
            return cut[: idx + 1].strip()
    return text[: limit - 1].rstrip() + "…"


def _as_str_list(value: Any, *, limit: int, max_items: int) -> list[str]:
    if isinstance(value, str):
        value = [value]
    if not isinstance(value, (list, tuple)):
        return []
    out: list[str] = []
    for item in value:
        if not isinstance(item, str):
            continue
        text = _WS_RE.sub(" ", item).strip()
        if not text:
            continue
        if len(text) > limit:
            text = text[: limit - 1].rstrip() + "…"  # ≤ limit, contando a reticência
        if text not in out:
            out.append(text)
        if len(out) >= max_items:
            break
    return out


_ISO_DATE_RE = re.compile(r"(\d{4})-(\d{2})-(\d{2})")


def parse_event_date(value: Any) -> Optional[str]:
    """Aceita ``YYYY-MM-DD`` (ou texto contendo-o); devolve ISO ou ``None``."""
    if not isinstance(value, str):
        return None
    m = _ISO_DATE_RE.search(value)
    if not m:
        return None
    try:
        return datetime(int(m.group(1)), int(m.group(2)), int(m.group(3))).strftime("%Y-%m-%d")
    except ValueError:
        return None


def parse_synthesis(raw: str, sources: Sequence[Source]) -> Synthesis:
    """Parser tolerante + pós-processamento. ``error='synth_parse'`` se não houver texto."""
    synthesis = Synthesis(raw=raw or "")
    blob = _slice_first_json_object(raw or "")
    data: Any = None
    if blob:
        try:
            data = json.loads(blob)
        except (TypeError, ValueError):
            data = None
    if not isinstance(data, dict):
        synthesis.error = "synth_parse"
        return synthesis

    text = clip_text(strip_links(str(data.get("text") or "")))
    if not text:
        synthesis.error = "synth_parse"
        return synthesis
    synthesis.text = text
    synthesis.reason_line = clip_text(strip_links(str(data.get("reason_line") or "")), MAX_REASON_CHARS)
    synthesis.follow_ups = _as_str_list(data.get("follow_ups"), limit=MAX_FOLLOW_UP_CHARS, max_items=MAX_FOLLOW_UPS)
    synthesis.event_date = parse_event_date(data.get("event_date"))

    # used_source_urls ⊆ sources (comparação por URL canônica)
    allowed = {canonical_url(s.url): s.url for s in sources}
    used: list[str] = []
    for url in _as_str_list(data.get("used_source_urls"), limit=2048, max_items=10):
        original = allowed.get(canonical_url(url))
        if original and original not in used:
            used.append(original)
    synthesis.used_source_urls = used
    return synthesis


def compute_expires_at(
    category: str,
    *,
    event_date: Optional[str] = None,
    now: Optional[datetime] = None,
    news_hours: Optional[int] = None,
    default_days: Optional[int] = None,
) -> str:
    """F2.4.5: ``event`` → data do evento (fim do dia) ou +7 d; ``news`` +48 h; demais +7 d.

    F4.4.1: ``news_hours``/``default_days`` vêm da configuração do admin
    (``expiry_news_hours`` / ``expiry_default_days``); ``None`` ⇒ defaults do plano.
    """
    now = now or datetime.now(timezone.utc)
    if category == "event" and event_date:
        try:
            day = datetime.strptime(event_date, "%Y-%m-%d")
        except ValueError:
            day = None
        if day is not None:
            end_of_day = day.replace(hour=23, minute=59, second=59)
            if end_of_day.replace(tzinfo=now.tzinfo) > now:
                return end_of_day.strftime("%Y-%m-%d %H:%M:%S")
    if category == "news":
        delta = timedelta(hours=news_hours) if news_hours else EXPIRY_BY_CATEGORY["news"]
    else:
        delta = timedelta(days=default_days) if default_days else EXPIRY_BY_CATEGORY.get(category, DEFAULT_EXPIRY)
    return (now + delta).strftime("%Y-%m-%d %H:%M:%S")


# ─────────────────────────────────────────────────────────────────────────────
# Prompt
# ─────────────────────────────────────────────────────────────────────────────

def format_sources_block(sources: Sequence[Source]) -> str:
    lines: list[str] = []
    for idx, src in enumerate(sources, start=1):
        head = f"[{idx}] {src.title or src.domain} — {src.domain} — {src.url}"
        if src.published_at:
            head += f" — published: {src.published_at}"
        lines.append(head)
        if src.snippet:
            lines.append(f"    snippet: {src.snippet}")
        if src.content_excerpt:
            excerpt = src.content_excerpt[:SOURCE_EXCERPT_CHARS]
            lines.append(f"    excerpt: {excerpt}")
    return "\n".join(lines) if lines else "(no sources)"


def build_synth_messages(
    signal: InterestSignal,
    sources: Sequence[Source],
    *,
    user_message: str = "",
    now: Optional[datetime] = None,
) -> list[dict[str, str]]:
    from backend.proactive.prompts import render_synth_system_prompt, render_synth_user_prompt

    language = signal.language if signal.language in ("pt-BR", "en-US", "es-ES") else "pt-BR"
    message = _WS_RE.sub(" ", user_message or "").strip()
    if len(message) > MAX_MESSAGE_CHARS:
        message = message[:MAX_MESSAGE_CHARS].rstrip() + "…"
    return [
        {
            "role": "system",
            "content": render_synth_system_prompt(topic=signal.topic or "", emotion=signal.emotion or "curious"),
        },
        {
            "role": "user",
            "content": render_synth_user_prompt(
                today=(now or datetime.now()).strftime("%Y-%m-%d"),
                language=language,
                topic=signal.topic or "",
                entities=", ".join(signal.entities or []) or "(none)",
                category=signal.category or "other",
                emotion=signal.emotion or "curious",
                message=message or "(not available)",
                sources_block=format_sources_block(sources),
            ),
        },
    ]


# ─────────────────────────────────────────────────────────────────────────────
# Modelo (F2.4.3)
# ─────────────────────────────────────────────────────────────────────────────

class NoSynthModel(RuntimeError):
    """Nenhum modelo utilitário configurado e fallback para o modelo do chat desligado."""


async def resolve_synth_model(
    db: Any,
    user_id: Optional[str],
    conv_provider_id: Optional[str],
    conv_model_id: Optional[str],
    config: ProactiveConfig,
) -> tuple[Any, str, str]:
    """``meta.proactive_synth_*`` → cascata utilitária → modelo da conversa (se permitido)."""
    from backend.providers.utility_model import SOURCE_CHAT_FALLBACK, resolve_utility_model

    provider, model_name, source = await resolve_utility_model(
        db, user_id, conv_provider_id or "", conv_model_id or "", override_meta_keys=SYNTH_META_KEYS
    )
    if source == SOURCE_CHAT_FALLBACK and not config.allow_chat_model_fallback:
        raise NoSynthModel("proactive_allow_chat_model_fallback=false")
    return provider, model_name, source


# ─────────────────────────────────────────────────────────────────────────────
# Síntese
# ─────────────────────────────────────────────────────────────────────────────

async def synthesize(
    signal: InterestSignal,
    sources: Sequence[Source],
    *,
    provider: Any,
    model_name: str,
    user_message: str = "",
    timeout: float = DEFAULT_TIMEOUT_S,
    max_tokens: int = SYNTH_MAX_TOKENS,
    now: Optional[datetime] = None,
    model_source: str = "",
) -> Synthesis:
    """Chama o modelo (``stream_chat``, temperatura baixa) e devolve :class:`Synthesis`."""
    messages = build_synth_messages(signal, sources, user_message=user_message, now=now)
    prompt_chars = sum(len(str(m.get("content") or "")) for m in messages)
    chunks: list[str] = []

    async def _collect() -> None:
        async for token in provider.stream_chat(
            model=model_name, messages=messages, temperature=0.3, max_tokens=max_tokens
        ):
            chunks.append(str(token))

    started = time.perf_counter()
    try:
        await asyncio.wait_for(_collect(), timeout=timeout)
    except asyncio.TimeoutError:
        raw = "".join(chunks)
        return Synthesis(raw=raw, error="synth_timeout", model_label=model_name,
                         model_source=model_source, latency_ms=(time.perf_counter() - started) * 1000,
                         prompt_chars=prompt_chars, response_chars=len(raw))
    except Exception as exc:
        logger.debug("[Proactive] erro do provedor na síntese: %s", exc)
        raw = "".join(chunks)
        return Synthesis(raw=raw, error=f"synth_provider:{type(exc).__name__}",
                         model_label=model_name, model_source=model_source,
                         latency_ms=(time.perf_counter() - started) * 1000,
                         prompt_chars=prompt_chars, response_chars=len(raw))

    synthesis = parse_synthesis("".join(chunks), sources)
    synthesis.latency_ms = (time.perf_counter() - started) * 1000
    synthesis.model_label = model_name
    synthesis.model_source = model_source
    synthesis.prompt_chars = prompt_chars
    synthesis.response_chars = len(synthesis.raw or "")
    if synthesis.ok and not synthesis.reason_line:
        synthesis.reason_line = default_reason_line(signal)
    return synthesis


_EMOTION_WORDS = {
    "pt-BR": {"excited": "animado(a)", "curious": "curioso(a)", "happy": "feliz", "surprised": "surpreso(a)",
              "worried": "preocupado(a)", "nostalgic": "nostálgico(a)", "sad": "triste", "neutral": "interessado(a)"},
    "en-US": {"excited": "excited", "curious": "curious", "happy": "happy", "surprised": "surprised",
              "worried": "worried", "nostalgic": "nostalgic", "sad": "sad", "neutral": "interested"},
    "es-ES": {"excited": "entusiasmado(a)", "curious": "curioso(a)", "happy": "feliz", "surprised": "sorprendido(a)",
              "worried": "preocupado(a)", "nostalgic": "nostálgico(a)", "sad": "triste", "neutral": "interesado(a)"},
}
_REASON_TEMPLATES = {
    "pt-BR": "Pesquisei porque você pareceu {emotion} com {topic}.",
    "en-US": "I looked it up because you seemed {emotion} about {topic}.",
    "es-ES": "Lo busqué porque parecías {emotion} con {topic}.",
}


def default_reason_line(signal: InterestSignal) -> str:
    """Linha de motivo determinística (§3.4) quando o modelo não a fornece."""
    language = signal.language if signal.language in _REASON_TEMPLATES else "pt-BR"
    emotion = _EMOTION_WORDS[language].get(signal.emotion or "neutral", _EMOTION_WORDS[language]["neutral"])
    return _REASON_TEMPLATES[language].format(emotion=emotion, topic=signal.topic or normalize(signal.suggested_query))


async def model_label(db: Any, source: str, model_name: str, conv_model_id: Optional[str]) -> str:
    """Id global do modelo (``provider/model``) para gravar em ``synth_model``/``messages.model_id``.

    ``resolve_utility_model`` devolve só o nome específico do provedor; aqui
    recuperamos o id global conforme o degrau da cascata que foi usado.
    """
    from backend.providers.utility_model import (
        SOURCE_CHAT_FALLBACK,
        SOURCE_ENHANCER,
        SOURCE_MEMORY_EXTRACTOR,
        SOURCE_OVERRIDE,
        read_meta,
    )

    try:
        if source == SOURCE_OVERRIDE:
            label = await read_meta(db, SYNTH_META_KEYS[1])
        elif source == SOURCE_MEMORY_EXTRACTOR:
            label = await read_meta(db, "memory_extractor_model_id")
        elif source == SOURCE_ENHANCER:
            async with db.execute("SELECT enhancer_model_id FROM enhancer_config WHERE id = 1") as cur:
                row = await cur.fetchone()
            label = row[0] if row else None
        elif source == SOURCE_CHAT_FALLBACK:
            label = conv_model_id
        else:
            label = None
    except Exception:
        label = None
    return str(label or model_name or "")
