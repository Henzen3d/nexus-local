import asyncio
import ipaddress
import os
import re
import socket
from urllib.parse import urljoin, urlparse
import httpx
from loguru import logger

try:
    from lxml import html
    HAS_LXML = True
except ImportError:
    HAS_LXML = False


DESKTOP_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "pt-BR,pt;q=0.9,en-US;q=0.8,en;q=0.7",
    "Sec-Ch-Ua": '"Not-A.Brand";v="99", "Chromium";v="124"',
    "Sec-Ch-Ua-Mobile": "?0",
    "Sec-Ch-Ua-Platform": '"Windows"',
}

DATE_REGEX = re.compile(
    r"(\d{1,2}\s+de\s+[a-zçA-ZÇ]+\s+de\s+\d{4}|\d{4}-\d{2}-\d{2}|\d{2}/\d{2}/\d{4})",
    re.IGNORECASE,
)


def _clean_text(text: str) -> str:
    return re.sub(r"\s+", " ", text or "").strip()


def extract_articles_and_content(html_text: str, base_url: str) -> dict:
    """Extrai títulos, links, datas e resumo de artigos de um documento HTML."""
    if not HAS_LXML:
        return {"title": "", "articles": [], "text_sample": ""}

    try:
        tree = html.fromstring(html_text)
    except Exception as e:
        logger.debug(f"[reader] Falha ao fazer parse lxml: {e}")
        return {"title": "", "articles": [], "text_sample": ""}

    # Remove elementos de ruído
    for tag in tree.xpath("//script | //style | //nav | //footer | //svg | //noscript"):
        tag.drop_tree()

    page_title = _clean_text("".join(tree.xpath("//title/text()")))

    articles_data: list[dict] = []
    seen_urls = set()

    # 1. Procura por elementos <article> ou containers de post
    article_elements = tree.xpath("//article | //div[contains(@class, 'post') or contains(@class, 'blog-card') or contains(@class, 'entry')]")

    for el in article_elements[:15]:
        # Título
        title_candidates = el.xpath(".//h1//text() | .//h2//text() | .//h3//text() | .//h4//text()")
        title = _clean_text(" ".join(title_candidates))
        if not title or len(title) < 5:
            continue

        # Link
        links = el.xpath(".//a/@href")
        article_url = ""
        for href in links:
            if href and not href.startswith(("#", "javascript:", "mailto:")):
                article_url = urljoin(base_url, href)
                break

        if not article_url or article_url in seen_urls:
            continue
        seen_urls.add(article_url)

        # Data
        date_candidates = el.xpath(".//time/text() | .//time/@datetime | .//*[contains(@class, 'date') or contains(@class, 'time')]/text()")
        date_str = _clean_text(" ".join(date_candidates))
        if not date_str:
            # Tenta via regex no texto do elemento
            match = DATE_REGEX.search(_clean_text("".join(el.xpath(".//text()"))))
            if match:
                date_str = match.group(1)

        # Resumo / Excerpt
        paragraphs = el.xpath(".//p//text()")
        excerpt = _clean_text(" ".join(paragraphs))[:250]

        articles_data.append({
            "title": title,
            "url": article_url,
            "date": date_str or None,
            "excerpt": excerpt or None,
        })

    # 2. Captura data de publicação no nível da página (se for uma página de artigo individual)
    page_date_candidates = tree.xpath(
        "//time/text() | //time/@datetime | //meta[@property='article:published_time']/@content | //meta[contains(@name, 'date')]/@content"
    )
    published_date = ""
    for candidate in page_date_candidates:
        candidate_clean = _clean_text(candidate)
        match = DATE_REGEX.search(candidate_clean)
        if match:
            published_date = match.group(1)
            break
        elif candidate_clean and len(candidate_clean) <= 30:
            published_date = candidate_clean
            break

    # 3. Amostra de texto limpo da página para contexto adicional
    body_texts = tree.xpath("//main//text() | //div[@id='content']//text() | //body//text()")
    raw_text = _clean_text(" ".join(body_texts))
    text_sample = raw_text[:2500] if raw_text else ""

    return {
        "title": page_title,
        "published_date": published_date or None,
        "articles": articles_data,
        "text_sample": text_sample,
    }


_MAX_REDIRECTS = 4
_MAX_BODY_BYTES = 2 * 1024 * 1024  # 2 MB — só precisamos de texto, não de downloads


def _is_private_ip(ip_str: str) -> bool:
    try:
        ip = ipaddress.ip_address(ip_str)
    except ValueError:
        return True
    return (
        ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_multicast
        or ip.is_reserved or ip.is_unspecified
        or (ip.version == 6 and ip.ipv4_mapped is not None and _is_private_ip(str(ip.ipv4_mapped)))
    )


async def is_safe_public_url(url: str) -> bool:
    """Bloqueia SSRF: só http(s) e só hosts que resolvem para IPs públicos.

    O domínio lido pelo Deep Reader vem do prompt do usuário (``extract_domains_and_urls``);
    sem esta checagem era possível apontar um DNS para 127.0.0.1 / 172.x (rede
    Docker: backend, Portainer no host, metadata endpoints) e receber o conteúdo
    de volta dentro do contexto do modelo.
    """
    try:
        parsed = urlparse(url)
    except Exception:
        return False
    if parsed.scheme not in ("http", "https") or not parsed.hostname:
        return False
    host = parsed.hostname.strip("[]").lower()
    if host in ("localhost",) or host.endswith((".local", ".internal", ".localhost")):
        return False
    if os.getenv("WEB_SEARCH_ALLOW_PRIVATE_HTTP", "false").lower() in ("1", "true", "yes"):
        return True
    try:
        loop = asyncio.get_running_loop()
        infos = await asyncio.wait_for(
            loop.run_in_executor(None, lambda: socket.getaddrinfo(host, parsed.port or 80, proto=socket.IPPROTO_TCP)),
            timeout=3.0,
        )
    except Exception:
        return False
    addrs = {info[4][0] for info in infos}
    if not addrs:
        return False
    return not any(_is_private_ip(a) for a in addrs)


async def fetch_page_content(url: str, timeout: float = 6.0) -> dict | None:
    """Faz requisição HTTP assíncrona com timeout estrito e extrai o conteúdo.

    Redirects são seguidos manualmente para revalidar cada destino contra a
    lista de IPs privados (um 302 para http://169.254.169.254 não passa).
    """
    try:
        current = url
        async with httpx.AsyncClient(
            headers=DESKTOP_HEADERS,
            follow_redirects=False,
            timeout=timeout,
            verify=False,
        ) as client:
            for _hop in range(_MAX_REDIRECTS + 1):
                if not await is_safe_public_url(current):
                    logger.debug(f"[reader] URL bloqueada por política anti-SSRF: {current}")
                    return None
                async with client.stream("GET", current) as res:
                    if res.status_code in (301, 302, 303, 307, 308):
                        location = res.headers.get("location")
                        if not location:
                            return None
                        current = urljoin(current, location)
                        continue
                    if res.status_code != 200:
                        logger.debug(f"[reader] {current} respondeu {res.status_code}")
                        return None
                    ctype = (res.headers.get("content-type") or "").lower()
                    if ctype and not any(t in ctype for t in ("html", "xml", "text/plain")):
                        return None
                    chunks: list[bytes] = []
                    total = 0
                    async for chunk in res.aiter_bytes():
                        total += len(chunk)
                        if total > _MAX_BODY_BYTES:
                            break
                        chunks.append(chunk)
                    raw = b"".join(chunks)
                    try:
                        html_text = raw.decode(res.encoding or "utf-8", errors="replace")
                    except (LookupError, TypeError):
                        html_text = raw.decode("utf-8", errors="replace")
                    extracted = extract_articles_and_content(html_text, current)
                    extracted["url"] = current
                    return extracted
            logger.debug(f"[reader] Excesso de redirects a partir de {url}")
            return None
    except Exception as e:
        logger.debug(f"[reader] Erro ao acessar {url}: {e}")
        return None


async def deep_read_target(url: str, max_sub_articles: int = 3, timeout: float = 6.0) -> dict | None:
    """
    Lê a página principal e, se encontrar artigos sem data definida,
    faz um fetch rápido nos 2-3 primeiros links para capturar as datas e títulos exatos.
    Idêntico ao comportamento do Grok ao inspecionar artigos específicos.
    """
    main_page = await fetch_page_content(url, timeout=timeout)
    if not main_page:
        return None

    articles = main_page.get("articles", [])
    if articles:
        tasks = []
        for a in articles[:max_sub_articles]:
            if not a.get("date") and a.get("url"):
                tasks.append(fetch_page_content(a["url"], timeout=4.0))

        if tasks:
            results = await asyncio.gather(*tasks, return_exceptions=True)
            for i, r in enumerate(results):
                if isinstance(r, dict):
                    date_val = r.get("published_date")
                    if not date_val and r.get("text_sample"):
                        date_match = DATE_REGEX.search(r["text_sample"])
                        if date_match:
                            date_val = date_match.group(1)
                    if date_val and i < len(articles):
                        articles[i]["date"] = date_val

    return main_page
