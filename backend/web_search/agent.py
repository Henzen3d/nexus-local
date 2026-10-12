import asyncio
from typing import Any, Callable, Awaitable
from loguru import logger

from backend.web_search.planner import plan_search_queries, extract_domains_and_urls
from backend.web_search.providers import resolve_and_execute_search
from backend.web_search.reader import deep_read_target


async def execute_agentic_search(
    user_message: str,
    db: Any,
    search_config: dict,
    on_event: Callable[[dict], Awaitable[None]] | None = None,
) -> dict:
    """
    Executa busca agêntica multi-passo:
    1. Query Planner: decompõe em sub-consultas especializadas.
    2. Multi-Search: executa cada busca e emite eventos em tempo real.
    3. Deep Reader: faz scraping e extração de artigos/datas reais nos sites-alvo.
    """
    # 1. Planejamento de consultas
    planned_queries = plan_search_queries(user_message)
    logger.info(f"[agentic_search] Consultas planejadas ({len(planned_queries)}): {planned_queries}")

    all_results: list[dict] = []
    seen_urls = set()

    # 2. Executa as buscas planejadas em paralelo para máxima velocidade
    async def _run_single_search(idx: int, query: str) -> list[dict]:
        if idx > 0:
            await asyncio.sleep(0.25 * idx)

        step_id = f"search-step-{idx}"
        if on_event:
            await on_event({
                "type": "process_step_start",
                "id": step_id,
                "step_type": "search",
                "title": f"Pesquisado na web por: {query}",
                "detail": query,
            })

        results = []
        try:
            results = await resolve_and_execute_search(query, db, search_config)
        except Exception as e:
            logger.debug(f"[agentic_search] Erro na busca '{query}': {e}")
        finally:
            if on_event:
                await on_event({
                    "type": "process_step_end",
                    "id": step_id,
                    "status": "completed",
                })
        return results

    search_tasks = [_run_single_search(i, q) for i, q in enumerate(planned_queries)]
    search_outputs = await asyncio.gather(*search_tasks, return_exceptions=True)

    for output in search_outputs:
        if isinstance(output, list):
            for r in output:
                url = r.get("url")
                if url and url not in seen_urls:
                    seen_urls.add(url)
                    all_results.append(r)

    # 3. Identifica páginas de alta relevância para leitura profunda (Deep Reader)
    domains_info = extract_domains_and_urls(user_message)
    target_urls_to_read: list[str] = []

    if domains_info:
        main_domain = domains_info[0]["domain"]
        domain_matches = [
            r["url"] for r in all_results
            if main_domain in r.get("url", "").lower()
        ]
        blog_matches = [
            u for u in domain_matches
            if any(w in u.lower() for w in ["/blog", "/artigo", "/post", "/noticia"])
        ]
        if blog_matches:
            target_urls_to_read.append(blog_matches[0])
        elif domain_matches:
            target_urls_to_read.append(domain_matches[0])
        else:
            target_urls_to_read.append(f"https://{main_domain}/blog/")

    for r in all_results[:4]:
        url = r.get("url", "")
        if url and url not in target_urls_to_read and not url.endswith((".pdf", ".zip", ".jpg", ".png")):
            target_urls_to_read.append(url)
            break

    target_urls_to_read = target_urls_to_read[:2]

    # 4. Leitura profunda das páginas em paralelo
    async def _run_single_read(idx: int, url: str) -> dict | None:
        step_id = f"reader-step-{idx}"
        if on_event:
            await on_event({
                "type": "process_step_start",
                "id": step_id,
                "step_type": "navigate",
                "title": f"Lendo conteúdo de {url}",
                "detail": url,
            })

        page_data = None
        try:
            page_data = await deep_read_target(url, max_sub_articles=3, timeout=5.0)
        except Exception as e:
            logger.debug(f"[agentic_search] Erro ao ler {url}: {e}")
        finally:
            if on_event:
                await on_event({
                    "type": "process_step_end",
                    "id": step_id,
                    "status": "completed",
                })
        return page_data

    read_tasks = [_run_single_read(i, u) for i, u in enumerate(target_urls_to_read)]
    read_outputs = await asyncio.gather(*read_tasks, return_exceptions=True)

    scraped_pages: list[dict] = []
    for out in read_outputs:
        if isinstance(out, dict) and (out.get("articles") or out.get("text_sample")):
            scraped_pages.append(out)

    return {
        "search_results": all_results[:10],
        "scraped_pages": scraped_pages,
        "executed_queries": planned_queries,
    }
