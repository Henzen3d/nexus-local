import asyncio
import re
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


async def fetch_page_content(url: str, timeout: float = 6.0) -> dict | None:
    """Faz requisição HTTP assíncrona com timeout estrito e extrai o conteúdo."""
    try:
        async with httpx.AsyncClient(
            headers=DESKTOP_HEADERS,
            follow_redirects=True,
            timeout=timeout,
            verify=False,
        ) as client:
            res = await client.get(url)
            if res.status_code != 200:
                logger.debug(f"[reader] {url} respondeu {res.status_code}")
                return None

            html_text = res.text
            extracted = extract_articles_and_content(html_text, str(res.url))
            extracted["url"] = str(res.url)
            return extracted
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
