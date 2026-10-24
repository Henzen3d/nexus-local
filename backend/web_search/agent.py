import asyncio
import re
from typing import Any, Callable, Awaitable
from loguru import logger

from backend.web_search.planner import plan_search_queries, extract_domains_and_urls, extract_context_entities
from backend.web_search.providers import resolve_and_execute_search
from backend.web_search.reader import deep_read_target

COMMON_STOPWORDS = {
    "como", "para", "uma", "com", "por", "que", "dos", "das", "aos", "nas",
    "nos", "mais", "sobre", "qual", "quem", "esse", "essa", "isso", "esta",
    "este", "está", "estao", "estão", "onde", "quando", "seus", "suas", "você",
    "voce", "pode", "fazer", "faco", "faço", "criar", "ter", "ser", "tem",
    "sucesso", "bom", "boa", "tudo", "aqui", "diga", "informe", "favor",
    "qual", "quais", "dele", "dela", "deles", "delas", "pelo", "pela",
    "pelos", "pelas", "entre", "contra", "sem", "sob", "atrás", "pegar", "buscar"
}

GENERIC_TUTORIAL_DOMAINS = {
    "tecnobits.com", "melhorplano.net", "falemaisvoip.com.br", "blacktel.io",
    "telefones.net.br", "ligarnumeros.com", "guiamais.com.br", "tudocelular.com",
    "techtudo.com.br", "tecmundo.com.br", "canaltech.com.br", "wikihow.com",
    "voip.com.br", "voipdobrasil.com.br"
}


def score_search_result(
    user_message: str,
    result: dict,
    target_domain: str | None = None,
    history: list[dict] | None = None,
) -> float:
    """Calcula a relevância de um resultado da busca para o prompt do usuário e histórico."""
    url = result.get("url", "").lower()
    title = result.get("title", "").lower()
    snippet = result.get("snippet", "").lower()
    combined_text = f"{title} {snippet} {url}"

    # 1. Filtro rígido contra sites de tutoriais genéricos e VoIP quando o assunto é comercial/contato
    is_contact_or_business = any(
        w in user_message.lower() for w in ["telefone", "whatsapp", "contato", "endereço", "endereco", "contratar", "falar com"]
    ) or (history and any(
        w in str(m.get("content", "")).lower() for m in history[-2:] for w in ["fix", "blumenau", "contratar", "empresa", "telefone"]
    ))
    if is_contact_or_business and any(d in url for d in GENERIC_TUTORIAL_DOMAINS):
        return 0.0

    score = 0.0

    # 2. Bônus por domínio alvo
    if target_domain and target_domain in url:
        score += 50.0

    # 3. Identifica entidades de destaque no prompt corrente OU no histórico (se anafórico)
    specific_entities = []
    msg_lower = user_message.lower()
    if "fix serviços" in msg_lower or "fix servicos" in msg_lower:
        specific_entities.append("fix serviços")
    elif re.search(r"\bfix\b", msg_lower):
        specific_entities.append("fix")
    if "blumenau" in msg_lower:
        specific_entities.append("blumenau")

    from backend.web_search.planner import ANAPHORIC_PRONOUNS_REGEX
    has_anaphora = bool(ANAPHORIC_PRONOUNS_REGEX.search(user_message))
    has_missing_entity = (
        any(w in msg_lower for w in ["telefone", "whatsapp", "contato", "endereço", "endereco", "site oficial", "horário", "horario"])
        and not any(w in msg_lower for w in ["globo", "debate", "google", "empresa", "loja"])
    )

    # Injeta entidades resolvidas do histórico SOMENTE se o prompt for anafórico ou dependente de contexto
    if (has_anaphora or has_missing_entity) and history:
        for ent in extract_context_entities(history):
            e_lower = ent.lower()
            if "fix" in e_lower and "fix" not in specific_entities:
                specific_entities.append("fix")
            if "blumenau" in e_lower and "blumenau" not in specific_entities:
                specific_entities.append("blumenau")
            for token in re.findall(r"\b[a-zA-ZÀ-ÿ0-9_-]{3,}\b", e_lower):
                if token not in COMMON_STOPWORDS and token not in specific_entities:
                    specific_entities.append(token)

    # Validação obrigatória de entidade: se busca uma empresa/local específico,
    # resultados que não mencionam a entidade nem o município são descartados com 0.0
    if specific_entities:
        has_entity_match = any(ent in combined_text for ent in specific_entities)
        if not has_entity_match:
            return 0.0
        score += 25.0

    # Bônus para veículos de imprensa e portais de jornalismo para perguntas noticiosas / políticas
    NEWS_DOMAINS = {
        "globo.com", "g1.globo.com", "oglobo.globo.com", "uol.com.br", "noticias.uol.com.br",
        "folha.uol.com.br", "estadao.com.br", "cnnbrasil.com.br", "terra.com.br",
        "metropoles.com", "poder360.com.br", "infomoney.com.br", "cartacapital.com.br",
        "bbc.com", "reuters.com", "agenciabrasil.ebc.com.br", "tse.jus.br", "diariolocal.com.br"
    }
    is_news_or_politics = any(
        w in msg_lower for w in ["debate", "eleição", "eleições", "presidente", "presidencial", "política", "politica", "notícia", "noticia", "jornal"]
    )
    if is_news_or_politics:
        if any(nd in url for nd in NEWS_DOMAINS):
            score += 35.0
        # Penaliza e descarta blogs de nicho residencial/predial irrelevantes para política/eleições
        UNRELATED_TOPIC_DOMAINS = {
            "tecniko.app", "cantinhofamiliar.com.br", "porter.com.br", "seicondf.org.br"
        }
        if any(bd in url for bd in UNRELATED_TOPIC_DOMAINS):
            return 0.0

    # 4. Extrai termos de conteúdo do prompt do usuário
    msg_words = re.findall(r"\b[a-zA-ZÀ-ÿ0-9_-]{3,}\b", msg_lower)
    content_terms = [w for w in msg_words if w not in COMMON_STOPWORDS]

    if content_terms:
        matched_terms = [t for t in content_terms if t in combined_text]
        match_ratio = len(matched_terms) / len(content_terms)
        score += match_ratio * 30.0

    # Penalidade severa para PDFs ou formatos não textuais
    if url.endswith((".pdf", ".zip", ".jpg", ".png")):
        score -= 100.0

    return score


async def execute_agentic_search(
    user_message: str,
    db: Any,
    search_config: dict,
    on_event: Callable[[dict], Awaitable[None]] | None = None,
    history: list[dict] | None = None,
) -> dict:
    """
    Executa busca agêntica multi-passo:
    1. Query Planner: decompõe em sub-consultas especializadas com histórico.
    2. Multi-Search: executa cada busca e emite eventos em tempo real.
    3. Deep Reader: faz scraping e extração de artigos/datas reais nos sites-alvo.
    """
    # 1. Planejamento de consultas com resolução de contexto conversacional (R2)
    planned_queries = plan_search_queries(user_message, history=history)
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

    # Avalia relevância dos demais resultados antes de despachar o Deep Reader
    main_domain_str = domains_info[0]["domain"] if domains_info else None
    scored_candidates = []
    for r in all_results:
        url = r.get("url", "")
        if url and url not in target_urls_to_read and not url.endswith((".pdf", ".zip", ".jpg", ".png")):
            rel_score = score_search_result(user_message, r, target_domain=main_domain_str, history=history)
            if rel_score > 5.0:  # limiar mínimo de relevância
                scored_candidates.append((rel_score, url))

    # Ordena pelo maior score e pega os melhores
    scored_candidates.sort(key=lambda x: x[0], reverse=True)
    for _, best_url in scored_candidates:
        if len(target_urls_to_read) >= 2:
            break
        target_urls_to_read.append(best_url)

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
