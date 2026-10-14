"""Pesquisa do Assistente Proativo — Fase 2 (F2.3).

Fluxo: cache por ``topic_hash`` (24 h) → até 2 consultas no provedor de busca
global (``resolve_and_execute_search`` respeita provider/chave/habilitado) →
dedupe por URL canônica + ranking por domínio → deep read das 2 melhores
páginas (``fetch_page_content``: anti-SSRF, 2 MB, 6 s) → ≤ 3 fontes finais.

Nunca levanta exceção para o chamador: falhas viram ``ResearchResult.error``
(``web_search_disabled`` | ``no_results`` | ``timeout`` | ``search_error``).
"""
from __future__ import annotations

import asyncio
import ipaddress
import json
import re
import time
from dataclasses import asdict, dataclass, field
from datetime import datetime
from typing import Any, Awaitable, Callable, Optional, Sequence
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from backend.logging_config import get_logger
from backend.proactive.detector import InterestSignal, build_fallback_query, normalize

logger = get_logger(__name__)

MAX_QUERIES = 2
MAX_RESULTS_PER_QUERY = 6
DEEP_READ_PAGES = 2
DEEP_READ_TIMEOUT_S = 6.0
MAX_FINAL_SOURCES = 3
EXCERPT_CHARS = 1200
SNIPPET_CHARS = 300
CACHE_HOURS = 24
DEFAULT_TIMEOUT_S = 30.0

SearchFn = Callable[[str, Any], Awaitable[list[dict]]]
FetchFn = Callable[..., Awaitable[Optional[dict]]]


@dataclass
class Source:
    title: str
    url: str
    domain: str
    snippet: str = ""
    content_excerpt: str = ""
    published_at: Optional[str] = None
    score: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data.pop("score", None)
        return data

    def to_public(self) -> dict[str, str]:
        """Shape enviado ao cliente (contrato §3.2): ``{title, url, domain}``."""
        return {"title": self.title or self.domain, "url": self.url, "domain": self.domain}

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Source":
        url = str(data.get("url") or "")
        return cls(
            title=str(data.get("title") or ""),
            url=url,
            domain=str(data.get("domain") or domain_of(url)),
            snippet=str(data.get("snippet") or ""),
            content_excerpt=str(data.get("content_excerpt") or ""),
            published_at=data.get("published_at") or None,
        )


@dataclass
class ResearchResult:
    query: str
    sources: list[Source] = field(default_factory=list)
    cache_hit: bool = False
    elapsed_ms: float = 0.0
    error: str = ""
    queries: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.error and bool(self.sources)

    def sources_json(self) -> str:
        return json.dumps([s.to_dict() for s in self.sources], ensure_ascii=False)


# ─────────────────────────────────────────────────────────────────────────────
# URLs e ranking
# ─────────────────────────────────────────────────────────────────────────────

_TRACKING_PREFIXES = ("utm_", "fbclid", "gclid", "mc_cid", "mc_eid", "ref", "igshid", "si")


def canonical_url(url: str) -> str:
    """Remove fragmento, parâmetros de rastreio e normaliza host/esquema."""
    try:
        parts = urlsplit((url or "").strip())
    except ValueError:
        return (url or "").strip()
    if not parts.scheme or not parts.netloc:
        return (url or "").strip()
    host = parts.netloc.lower()
    if host.startswith("www."):
        host = host[4:]
    query = [
        (k, v) for k, v in parse_qsl(parts.query, keep_blank_values=True)
        if not k.lower().startswith(_TRACKING_PREFIXES)
    ]
    path = parts.path or "/"
    if len(path) > 1 and path.endswith("/"):
        path = path[:-1]
    return urlunsplit(("https" if parts.scheme in ("http", "https") else parts.scheme,
                       host, path, urlencode(query, doseq=True), ""))


_PRIVATE_HOST_SUFFIXES = (".local", ".internal", ".localhost", ".lan", ".home", ".arpa")


def is_public_looking_url(url: str) -> bool:
    """Pré-filtro anti-SSRF **sem DNS** (F5.1.3): só ``http(s)`` e nunca hosts
    locais nem IPs literais privados/loopback/link-local/reservados.

    O Deep Reader (``fetch_page_content``) ainda resolve o DNS e revalida cada
    redirect; aqui a fonte nem entra na lista de resultados (nem como snippet),
    então um resultado de busca apontando para ``http://10.0.0.5`` ou
    ``http://169.254.169.254`` jamais chega ao modelo nem à UI.
    """
    try:
        parts = urlsplit((url or "").strip())
    except ValueError:
        return False
    if parts.scheme not in ("http", "https"):
        return False
    host = (parts.hostname or "").strip().lower()
    if not host:
        return False
    if host == "localhost" or host.endswith(_PRIVATE_HOST_SUFFIXES):
        return False
    try:
        ip = ipaddress.ip_address(host)
    except ValueError:
        return True  # nome de domínio: a checagem com DNS fica para o reader
    if ip.version == 6 and ip.ipv4_mapped is not None:
        ip = ip.ipv4_mapped
    return not (
        ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_multicast
        or ip.is_reserved or ip.is_unspecified
    )


def domain_of(url: str) -> str:
    try:
        host = urlsplit(url).netloc.lower()
    except ValueError:
        return ""
    if host.startswith("www."):
        host = host[4:]
    return host.split(":")[0]


_SOCIAL_DOMAINS = (
    "facebook.com", "instagram.com", "twitter.com", "x.com", "tiktok.com", "pinterest.com",
    "reddit.com", "threads.net", "linkedin.com", "youtube.com", "youtu.be", "t.me", "whatsapp.com",
)
_TICKET_HINTS = ("ingresso", "ticket", "sympla", "eventim", "eventbrite", "blueticket", "uhuu",
                 "ticketmaster", "bilheteria", "entrada", "boletos", "tickets")
_NEWS_HINTS = ("g1.globo.com", "globo.com", "uol.com.br", "folha.uol", "estadao", "cnnbrasil",
               "cnn.com", "bbc.", "reuters", "nsctotal", "ndmais", "gazeta", "correio", "terra.com.br",
               "r7.com", "metropoles", "veja.abril", "exame.com", "valor.globo", "elpais", "nytimes",
               "theguardian", "apnews", "oglobo", "band.uol", "noticias", "news", "jornal", "diario")
_AGGREGATOR_HINTS = ("pinterest", "quora", "answers", "forum", "scribd", "slideshare", "aliexpress",
                     "shopee", "mercadolivre.com.br/lista", "amazon.", "ebay.", "temu.")


def score_source(url: str, entity_tokens: Sequence[str]) -> float:
    """Heurística do plano: oficial/ingressos/notícias > agregadores/redes sociais."""
    domain = domain_of(url)
    if not domain:
        return -10.0
    score = 0.0
    compact = domain.replace("-", "").replace(".", "")
    for tok in entity_tokens:
        if len(tok) >= 4 and tok in compact:
            score += 3.0  # domínio "oficial" (contém o nome da entidade)
            break
    if any(h in domain for h in _TICKET_HINTS):
        score += 2.0
    if any(h in domain for h in _NEWS_HINTS):
        score += 2.0
    if any(domain == d or domain.endswith("." + d) for d in _SOCIAL_DOMAINS):
        score -= 3.0
    if any(h in domain for h in _AGGREGATOR_HINTS):
        score -= 1.0
    if domain.endswith(".gov.br") or domain.endswith(".gov") or domain.endswith(".edu"):
        score += 1.5
    return score


def _entity_tokens(signal: InterestSignal) -> list[str]:
    tokens: list[str] = []
    for ent in list(signal.entities or []) + [signal.topic or ""]:
        for tok in re.split(r"[^a-z0-9]+", normalize(ent)):
            if len(tok) >= 4 and tok not in tokens:
                tokens.append(tok)
    return tokens


def build_queries(signal: InterestSignal, *, now: Optional[datetime] = None) -> list[str]:
    """``suggested_query`` (+ ano quando ``time_sensitive``) e, opcionalmente, 1 extra."""
    now = now or datetime.now()
    primary = (signal.suggested_query or "").strip() or build_fallback_query(signal.topic, signal.entities)
    if not primary:
        return []
    if signal.time_sensitive and not re.search(r"\b20\d{2}\b", primary):
        primary = f"{primary} {now.year}"
    queries = [primary]
    extra = build_fallback_query(signal.topic, signal.entities)
    if extra and normalize(extra) != normalize(primary) and len(queries) < MAX_QUERIES:
        # Só vale a pena se trouxer palavras novas (evita duas buscas quase iguais)
        new_words = set(normalize(extra).split()) - set(normalize(primary).split())
        if new_words:
            queries.append(extra)
    return queries[:MAX_QUERIES]


# ─────────────────────────────────────────────────────────────────────────────
# Cache por topic_hash
# ─────────────────────────────────────────────────────────────────────────────

async def lookup_cached_sources(db: Any, topic_hash: str, *, hours: int = CACHE_HOURS) -> Optional[list[Source]]:
    """Reaproveita ``sources_json`` de um insight recente (qualquer usuário — a
    pesquisa é pública; a síntese é refeita por usuário)."""
    if not topic_hash:
        return None
    try:
        async with db.execute(
            """SELECT sources_json FROM proactive_insights
               WHERE topic_hash = ?
                 AND status IN ('ready','delivered','seen')
                 AND sources_json IS NOT NULL AND sources_json <> ''
                 AND created_at > datetime('now', ?)
               ORDER BY created_at DESC LIMIT 1""",
            (topic_hash, f"-{int(hours)} hours"),
        ) as cur:
            row = await cur.fetchone()
    except Exception as exc:
        logger.debug("[Proactive] cache de pesquisa indisponível: %s", exc)
        return None
    if not row or not row[0]:
        return None
    try:
        data = json.loads(row[0])
    except (TypeError, ValueError):
        return None
    sources = [Source.from_dict(d) for d in data if isinstance(d, dict) and d.get("url")]
    return sources or None


# ─────────────────────────────────────────────────────────────────────────────
# Pesquisa
# ─────────────────────────────────────────────────────────────────────────────

async def _default_search(query: str, db: Any) -> list[dict]:
    from backend.web_search.providers import resolve_and_execute_search

    return await resolve_and_execute_search(query, db)


async def _default_fetch(url: str, timeout: float = DEEP_READ_TIMEOUT_S) -> Optional[dict]:
    from backend.web_search.reader import fetch_page_content

    return await fetch_page_content(url, timeout=timeout)


async def _web_search_enabled(db: Any) -> bool:
    try:
        from backend.web_search.providers import get_web_search_config

        cfg = await get_web_search_config(db)
    except Exception as exc:
        logger.debug("[Proactive] web_search_config indisponível: %s", exc)
        return False
    return bool(cfg and cfg.get("enabled"))


def _clip(text: Any, limit: int) -> str:
    text = re.sub(r"\s+", " ", str(text or "")).strip()
    if len(text) > limit:
        text = text[:limit].rstrip() + "…"
    return text


def merge_results(raw_results: Sequence[Sequence[dict]], entity_tokens: Sequence[str]) -> list[Source]:
    """Dedupe por URL canônica e ordena por score (desempate: ordem de chegada)."""
    seen: dict[str, Source] = {}
    order: list[str] = []
    for results in raw_results:
        for item in results or []:
            url = str((item or {}).get("url") or "").strip()
            if not is_public_looking_url(url):
                continue
            key = canonical_url(url)
            if key in seen:
                existing = seen[key]
                if not existing.snippet and item.get("snippet"):
                    existing.snippet = _clip(item.get("snippet"), SNIPPET_CHARS)
                continue
            src = Source(
                title=_clip(item.get("title"), 160),
                url=url,
                domain=domain_of(url),
                snippet=_clip(item.get("snippet"), SNIPPET_CHARS),
                score=score_source(url, entity_tokens),
            )
            seen[key] = src
            order.append(key)
    ranked = sorted(order, key=lambda k: -seen[k].score)  # sort é estável
    return [seen[k] for k in ranked]


_DATE_RE = re.compile(r"\b(\d{4}-\d{2}-\d{2}|\d{1,2}/\d{1,2}/\d{4}|\d{1,2} de [a-zç]+(?: de \d{4})?)\b", re.IGNORECASE)


def _apply_page(source: Source, page: Optional[dict], *, want_dates: bool) -> None:
    if not isinstance(page, dict):
        return
    if not source.title and page.get("title"):
        source.title = _clip(page.get("title"), 160)
    excerpt = _clip(page.get("text_sample"), EXCERPT_CHARS)
    if excerpt:
        source.content_excerpt = excerpt
    published = page.get("published_date")
    if published:
        source.published_at = _clip(published, 40)
    if want_dates and not source.published_at:
        # Datas de artigos/eventos listados na página ajudam a estimar expires_at
        for art in page.get("articles") or []:
            if isinstance(art, dict) and art.get("date"):
                source.published_at = _clip(art.get("date"), 40)
                break
        if not source.published_at and excerpt:
            m = _DATE_RE.search(excerpt)
            if m:
                source.published_at = m.group(1)


async def _research_inner(
    signal: InterestSignal,
    db: Any,
    *,
    topic_hash: str,
    search_fn: SearchFn,
    fetch_fn: FetchFn,
    now: Optional[datetime],
    use_cache: bool,
) -> ResearchResult:
    queries = build_queries(signal, now=now)
    primary = queries[0] if queries else (signal.suggested_query or "")
    result = ResearchResult(query=primary, queries=list(queries))

    # Web search global desligada ⇒ pesquisa proativa desligada (mesmo com cache)
    if not await _web_search_enabled(db):
        result.error = "web_search_disabled"
        return result

    if use_cache:
        cached = await lookup_cached_sources(db, topic_hash)
        if cached:
            result.sources = cached[:MAX_FINAL_SOURCES]
            result.cache_hit = True
            return result

    if not queries:
        result.error = "no_results"
        return result

    try:
        raw = await asyncio.gather(*(search_fn(q, db) for q in queries), return_exceptions=True)
    except Exception as exc:  # defensivo — gather com return_exceptions não deve levantar
        logger.warning("[Proactive] busca falhou: %s", exc)
        result.error = "search_error"
        return result
    batches: list[Sequence[dict]] = []
    for item in raw:
        if isinstance(item, BaseException):
            logger.debug("[Proactive] consulta falhou: %s", item)
            continue
        batches.append(item or [])
    if not batches and raw:
        result.error = "search_error"
        return result

    ranked = merge_results(batches, _entity_tokens(signal))
    if not ranked:
        result.error = "no_results"
        return result

    # Deep read concorrente das 2 melhores (tolerante a falha)
    top = ranked[:DEEP_READ_PAGES]
    pages = await asyncio.gather(
        *(fetch_fn(src.url, timeout=DEEP_READ_TIMEOUT_S) for src in top), return_exceptions=True
    )
    want_dates = signal.category == "event"
    for src, page in zip(top, pages):
        if isinstance(page, BaseException):
            logger.debug("[Proactive] deep read falhou em %s: %s", src.url, page)
            continue
        _apply_page(src, page, want_dates=want_dates)

    result.sources = ranked[:MAX_FINAL_SOURCES]
    return result


async def research(
    signal: InterestSignal,
    db: Any,
    *,
    topic_hash: str = "",
    timeout: float = DEFAULT_TIMEOUT_S,
    search_fn: Optional[SearchFn] = None,
    fetch_fn: Optional[FetchFn] = None,
    now: Optional[datetime] = None,
    use_cache: bool = True,
) -> ResearchResult:
    """Etapa de pesquisa completa com timeout (padrão 30 s)."""
    started = time.perf_counter()
    try:
        result = await asyncio.wait_for(
            _research_inner(
                signal, db,
                topic_hash=topic_hash,
                search_fn=search_fn or _default_search,
                fetch_fn=fetch_fn or _default_fetch,
                now=now,
                use_cache=use_cache,
            ),
            timeout=timeout,
        )
    except asyncio.TimeoutError:
        result = ResearchResult(query=signal.suggested_query or "", error="timeout")
    except Exception as exc:
        logger.warning("[Proactive] pesquisa falhou: %s", exc)
        result = ResearchResult(query=signal.suggested_query or "", error="search_error")
    result.elapsed_ms = (time.perf_counter() - started) * 1000
    return result
