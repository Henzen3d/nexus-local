import asyncio
import inspect
import re
import time
from dataclasses import dataclass
from typing import Any, Callable, Awaitable, Optional
from loguru import logger

from backend.web_search.planner import plan_search_queries, extract_domains_and_urls, extract_context_entities
from backend.web_search.providers import resolve_and_execute_search
from backend.web_search.reader import deep_read_target, is_public_url_candidate


@dataclass(frozen=True)
class SearchBudget:
    """Orçamento de execução da busca web (T2.1)."""
    mode: str = "standard"          # "fast_factual" | "standard"
    max_queries: int = 3
    max_results: int = 10
    max_main_reads: int = 2
    max_sub_articles: int = 3
    deadline_s: float = 12.0

    @classmethod
    def fast_factual(cls) -> "SearchBudget":
        return cls(
            mode="fast_factual",
            max_queries=1,
            max_results=3,
            max_main_reads=1,
            max_sub_articles=0,
            deadline_s=4.0,
        )

    @classmethod
    def standard(cls) -> "SearchBudget":
        return cls()


_RE_BROAD_OR_COMPARISON = re.compile(
    r"\b("
    r"compare|comparar|compara[çc][ãa]o|comparaci[óo]n|versus|vs\.?|"
    r"diferen[çc]as?\s+entre|differences?\s+between|diferencias?\s+entre|"
    r"pesquisa\s+(?:completa|profunda|aprofundada|detalhada)|"
    r"pesquise\s+(?:profundamente|a\s+fundo|todas?)|"
    r"deep\s+research|comprehensive|in[\-\s]depth|detailed\s+analysis|"
    r"an[áa]lise\s+detalhada|an[áa]lisis\s+detallado|investigaci[óo]n\s+profunda|"
    r"investigue|todas?\s+as\s+fontes|all\s+sources|m[úu]ltiplas?\s+fontes|"
    r"vantagens?\s+e\s+desvantagens?|pros?\s+and\s+cons?|pr[óo]s?\s+e\s+contras?"
    r")\b",
    re.IGNORECASE,
)

_RE_WEATHER_INTENT = re.compile(
    r"\b(clima|tempo|temperatura|previs[ãa]o(?:\s+do\s+tempo)?|chuva|chover|"
    r"weather|forecast|temperature|rain|"
    r"pron[óo]stico|lluvia|llover)\b",
    re.IGNORECASE,
)

_RE_PUNCTUAL_INTENT = re.compile(
    r"\b(clima|tempo|temperatura|previs[ãa]o|weather|forecast|pron[óo]stico|"
    r"cota[çc][ãa]o|pre[çc]o|precio|price|exchange\s+rate|valor\s+do|valor\s+da|"
    r"placar|score|resultado|marcador|"
    r"capital|popula[çc][ãa]o|population|poblaci[óo]n|"
    r"presidente|president|ceo|prefeito|mayor|alcalde|primeiro[\-\s]ministro|prime\s+minister|"
    r"hor[áa]rio|hora\s+atual|current\s+time|qu[ée]\s+hora|que\s+horas|"
    r"vers[ãa]o\s+atual|latest\s+version|[úu]ltima\s+versi[óo]n|release\s+date|"
    r"quem\s+[ée]|who\s+is|qui[ée]n\s+es|qual\s+[ée]|what\s+is|cu[áa]l\s+es|"
    r"quando\s+[ée]|when\s+is|cu[áa]ndo\s+es|quanto\s+custa|how\s+much|cu[áa]nto\s+cuesta)\b",
    re.IGNORECASE,
)

_WEATHER_NON_LOCALITY_TOKENS = {
    "qual", "como", "esta", "está", "vai", "estar", "clima", "tempo", "temperatura",
    "previsao", "previsão", "hoje", "amanha", "amanhã", "agora", "semana", "celsius",
    "fahrenheit", "graus", "degrees", "weather", "forecast", "temperature", "today",
    "tomorrow", "now", "what", "whats", "what's", "the", "for", "in", "like", "here",
    "aqui", "pronostico", "pronóstico", "hoy", "manana", "mañana", "cual", "cuál",
    "como", "cómo", "del", "para", "por", "favor", "em", "na", "no", "de", "do", "da",
    "chover", "chuva", "rain", "lluvia", "llover", "vai", "will", "it", "is", "en",
}


def has_explicit_weather_locality(text: str) -> bool:
    """Retorna True se uma pergunta de clima mencionar explicitamente uma localidade."""
    tokens = re.findall(r"[A-Za-zÀ-ÿ0-9\-]{2,}", text or "")
    meaningful = [
        tok for tok in tokens
        if tok.lower() not in _WEATHER_NON_LOCALITY_TOKENS
        and not re.fullmatch(r"\d+(?:[cf°])?", tok.lower())
    ]
    return len(meaningful) >= 1


def select_search_budget(
    user_message: str,
    *,
    intent_routing: Any = None,
    web_search_requested: bool = False,
) -> SearchBudget:
    """
    Seleciona SearchBudget.fast_factual apenas para lookups curtos com entidade e
    intenção pontuais identificadas; mantém SearchBudget.standard para pesquisa ampla,
    comparação, domínio/URL alvo ou consultas complexas/ambíguas.
    """
    text = (user_message or "").strip()
    if not text:
        return SearchBudget.standard()

    # Domínio/URL explícito, pedido amplo/comparação ou texto longo -> política completa
    if extract_domains_and_urls(text):
        return SearchBudget.standard()
    if _RE_BROAD_OR_COMPARISON.search(text):
        return SearchBudget.standard()
    if len(text) > 160 or text.count("?") >= 2 or "\n" in text:
        return SearchBudget.standard()

    intent_tier = getattr(intent_routing, "intent_tier", None) if intent_routing is not None else None
    if intent_tier == "deep_technical":
        return SearchBudget.standard()

    # Clima sem localidade explícita: não inferir cidade e não forçar fast_factual ambíguo
    if _RE_WEATHER_INTENT.search(text):
        if not has_explicit_weather_locality(text):
            return SearchBudget.standard()
        return SearchBudget.fast_factual()

    # Outras consultas factuais pontuais curtas com entidade identificável
    has_punctual = bool(_RE_PUNCTUAL_INTENT.search(text))
    if not has_punctual and intent_tier != "specific_lookup":
        return SearchBudget.standard()

    # Garante que existe ao menos uma entidade/termo substantivo além de stopwords
    words = [w.lower() for w in re.findall(r"[A-Za-zÀ-ÿ0-9]{2,}", text)]
    entity_words = [
        w for w in words
        if w not in COMMON_STOPWORDS
        and w not in {
            "what", "who", "when", "where", "how", "much", "the", "is", "are", "for",
            "today", "now", "current", "latest", "price", "rate", "score", "version",
            "quien", "quién", "cual", "cuál", "cuando", "cuándo", "cuanto", "cuánto",
            "hoy", "ahora", "actual", "precio", "valor", "hoje", "agora", "atual",
            "preço", "cotação", "cotacao", "placar", "resultado", "versão", "versao",
            "custa", "cuesta", "horas", "hora", "time", "capital", "presidente", "president",
        }
    ]
    if has_punctual and entity_words:
        return SearchBudget.fast_factual()
    if intent_tier == "specific_lookup" and len(entity_words) >= 1 and len(text) <= 120:
        return SearchBudget.fast_factual()

    return SearchBudget.standard()

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
    pre_planned_queries: list[str] | None = None,
    budget: Optional[SearchBudget] = None,
    clock: Callable[[], float] = time.monotonic,
) -> dict:
    """
    Executa busca agêntica respeitando ``SearchBudget`` e deadline compartilhado:
    1. Query Planner: decompõe ou usa queries pré-planejadas, limitadas por ``budget.max_queries``.
    2. Multi-Search: executa buscas dentro do saldo de deadline e preserva resultados parciais.
    3. Reader: lê até ``budget.max_main_reads`` páginas públicas (com ``budget.max_sub_articles``)
       dentro do saldo restante, reutilizando snippets se a leitura opcional expirar.
    """
    eff_budget = budget or SearchBudget.standard()
    t0 = clock()
    deadline = t0 + max(0.2, float(eff_budget.deadline_s))

    # 1. Planejamento de consultas (usa queries do Pré-Router se disponíveis)
    if pre_planned_queries and len(pre_planned_queries) > 0:
        planned_queries = [q.strip() for q in pre_planned_queries if q and q.strip()]
    else:
        planned_queries = plan_search_queries(user_message, history=history)
    planned_queries = planned_queries[: max(1, int(eff_budget.max_queries))]
    logger.info(
        "[agentic_search] mode={} planned_queries={} max_results={} max_reads={} max_sub={} deadline={:.1f}s",
        eff_budget.mode,
        len(planned_queries),
        eff_budget.max_results,
        eff_budget.max_main_reads,
        eff_budget.max_sub_articles,
        eff_budget.deadline_s,
    )

    all_results: list[dict] = []
    seen_urls: set[str] = set()
    search_timed_out = False
    read_timed_out = False

    async def _emit(evt: dict):
        if on_event:
            try:
                await on_event(evt)
            except Exception:
                pass

    async def _call_search(query: str, timeout_s: float) -> list[dict]:
        # Compatível com mocks/testes que substituem resolve_and_execute_search sem kwargs extras
        try:
            sig = inspect.signature(resolve_and_execute_search)
            params = sig.parameters
            kwargs: dict[str, Any] = {}
            if "max_results_override" in params:
                kwargs["max_results_override"] = eff_budget.max_results
            if "timeout" in params:
                kwargs["timeout"] = timeout_s
            return await resolve_and_execute_search(query, db, search_config, **kwargs)
        except (TypeError, ValueError):
            return await resolve_and_execute_search(query, db, search_config)

    # 2. Executa as buscas planejadas em paralelo dentro do saldo do deadline
    async def _run_single_search(idx: int, query: str) -> list[dict]:
        if idx > 0:
            await asyncio.sleep(0.25 * idx)

        step_id = f"search-step-{idx}"
        await _emit({
            "type": "process_step_start",
            "id": step_id,
            "step_type": "search",
            "title": f"Pesquisado na web por: {query}",
            "detail": query,
        })

        results: list[dict] = []
        end_status = "completed"
        try:
            rem = max(0.1, deadline - clock())
            results = await _call_search(query, rem)
        except asyncio.CancelledError:
            end_status = "timeout"
            raise
        except Exception as e:
            end_status = "failed"
            logger.debug("[agentic_search] Erro na busca #{}: {}", idx, type(e).__name__)
        finally:
            await _emit({
                "type": "process_step_end",
                "id": step_id,
                "status": end_status,
            })
        return results

    search_tasks = [asyncio.create_task(_run_single_search(i, q)) for i, q in enumerate(planned_queries)]
    rem_search = deadline - clock()
    if search_tasks:
        if rem_search <= 0:
            search_timed_out = True
            for t in search_tasks:
                t.cancel()
            search_outputs = await asyncio.gather(*search_tasks, return_exceptions=True)
        else:
            done, pending = await asyncio.wait(search_tasks, timeout=rem_search)
            if pending:
                search_timed_out = True
                for t in pending:
                    t.cancel()
                await asyncio.gather(*pending, return_exceptions=True)
            search_outputs = []
            for t in search_tasks:
                if t in done and not t.cancelled():
                    try:
                        search_outputs.append(t.result())
                    except Exception:
                        pass
    else:
        search_outputs = []

    for output in search_outputs:
        if isinstance(output, list):
            for r in output:
                url = r.get("url")
                if not url or url in seen_urls:
                    continue
                if not is_public_url_candidate(url):
                    continue
                seen_urls.add(url)
                all_results.append(r)

    returned_results = all_results[: max(1, int(eff_budget.max_results))]

    # 3. Identifica páginas de alta relevância para leitura profunda (respeitando max_main_reads)
    domains_info = extract_domains_and_urls(user_message)
    target_urls_to_read: list[str] = []
    max_reads = max(0, int(eff_budget.max_main_reads))

    if max_reads > 0:
        if domains_info:
            main_domain = domains_info[0]["domain"]
            domain_matches = [
                r["url"] for r in returned_results
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
                candidate_fallback = f"https://{main_domain}/blog/"
                if is_public_url_candidate(candidate_fallback):
                    target_urls_to_read.append(candidate_fallback)

        main_domain_str = domains_info[0]["domain"] if domains_info else None
        scored_candidates = []
        for r in returned_results:
            url = r.get("url", "")
            if url and url not in target_urls_to_read and not url.endswith((".pdf", ".zip", ".jpg", ".png")):
                rel_score = score_search_result(user_message, r, target_domain=main_domain_str, history=history)
                if rel_score > 5.0:
                    scored_candidates.append((rel_score, url))

        scored_candidates.sort(key=lambda x: x[0], reverse=True)
        for _, best_url in scored_candidates:
            if len(target_urls_to_read) >= max_reads:
                break
            target_urls_to_read.append(best_url)

        target_urls_to_read = target_urls_to_read[:max_reads]

    # 4. Leitura das páginas selecionadas dentro do saldo restante do deadline
    scraped_pages: list[dict] = []
    reads_started = 0
    reads_completed = 0
    rem_read = deadline - clock()

    if target_urls_to_read and rem_read > 0.1:
        async def _run_single_read(idx: int, url: str) -> dict | None:
            nonlocal reads_started
            reads_started += 1
            step_id = f"reader-step-{idx}"
            await _emit({
                "type": "process_step_start",
                "id": step_id,
                "step_type": "navigate",
                "title": f"Lendo conteúdo de {url}",
                "detail": url,
            })

            page_data = None
            end_status = "completed"
            try:
                per_read_timeout = min(5.0, max(0.1, deadline - clock()))
                page_data = await deep_read_target(
                    url,
                    max_sub_articles=eff_budget.max_sub_articles,
                    timeout=per_read_timeout,
                )
            except asyncio.CancelledError:
                end_status = "timeout"
                raise
            except Exception as e:
                end_status = "failed"
                logger.debug("[agentic_search] Erro ao ler alvo #{}: {}", idx, type(e).__name__)
            finally:
                await _emit({
                    "type": "process_step_end",
                    "id": step_id,
                    "status": end_status,
                })
            return page_data

        read_tasks = [asyncio.create_task(_run_single_read(i, u)) for i, u in enumerate(target_urls_to_read)]
        done_r, pending_r = await asyncio.wait(read_tasks, timeout=max(0.05, rem_read))
        if pending_r:
            read_timed_out = True
            for t in pending_r:
                t.cancel()
            await asyncio.gather(*pending_r, return_exceptions=True)

        for t in read_tasks:
            if t in done_r and not t.cancelled():
                try:
                    out = t.result()
                except Exception:
                    out = None
                if isinstance(out, dict) and (out.get("articles") or out.get("text_sample")):
                    scraped_pages.append(out)
                    reads_completed += 1
    elif target_urls_to_read and rem_read <= 0.1:
        read_timed_out = True

    elapsed_ms = round(max(0.0, (clock() - t0) * 1000.0), 1)
    metrics = {
        "mode": eff_budget.mode,
        "queries_executed": len(planned_queries),
        "results_returned": len(returned_results),
        "reads_started": reads_started,
        "reads_completed": reads_completed,
        "elapsed_ms": elapsed_ms,
        "timed_out": bool(search_timed_out or read_timed_out),
        "search_timed_out": search_timed_out,
        "read_timed_out": read_timed_out,
    }
    logger.info(
        "[agentic_search] done mode={} queries={} results={} reads={}/{} elapsed_ms={:.1f} timed_out={}",
        metrics["mode"],
        metrics["queries_executed"],
        metrics["results_returned"],
        metrics["reads_completed"],
        metrics["reads_started"],
        metrics["elapsed_ms"],
        metrics["timed_out"],
    )

    return {
        "search_results": returned_results,
        "scraped_pages": scraped_pages,
        "executed_queries": planned_queries,
        "metrics": metrics,
    }
