import re
from urllib.parse import urlparse


FILLER_WORDS = [
    r"\bpor favor\b",
    r"\bverifique\b",
    r"\bverificar\b",
    r"\bquais foram\b",
    r"\bquais são\b",
    r"\bfaça uma\b",
    r"\bfaça\b",
    r"\bpesquisa online\b",
    r"\bpesquise\b",
    r"\bbusque\b",
    r"\bprocure\b",
    r"\bme diga\b",
    r"\bme informe\b",
    r"\bse achar relevante\b",
    r"\bpode fazer perguntas adicionais\b",
    r"\bperguntas adicionais\b",
    r"\bcomo fazer\b",
]

DOMAIN_REGEX = re.compile(
    r"(?:https?://)?(?:www\.)?([a-zA-Z0-9-]+\.[a-zA-Z]{2,}(?:\.[a-zA-Z]{2,})?)(?:/[^\s,]*)?",
    re.IGNORECASE,
)


def extract_domains_and_urls(message: str) -> list[dict]:
    """Identifica domínios e URLs completos mencionados no prompt."""
    found = []
    for match in DOMAIN_REGEX.finditer(message):
        full_match = match.group(0).strip("(),.")
        domain = match.group(1).lower()
        # Ignora extensões de arquivos comuns que possam parecer domínios
        if domain.endswith((".png", ".jpg", ".pdf", ".txt", ".json", ".py", ".ts")):
            continue
        
        full_url = full_match if full_match.startswith("http") else f"https://{full_match}"
        found.append({
            "raw": full_match,
            "domain": domain,
            "url": full_url,
        })
    return found


def clean_query_text(text: str) -> str:
    """Remove palavras de preenchimento conversacional e pontuação excessiva."""
    cleaned = text
    for pattern in FILLER_WORDS:
        cleaned = re.sub(pattern, " ", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"[\"'\(\)\[\]\?!,;]", " ", cleaned)
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    return cleaned


def plan_search_queries(user_message: str) -> list[str]:
    """
    Decompõe o prompt do usuário em 1 a 3 sub-consultas otimizadas com operadores de busca.
    Inspirado no Query Planner do Grok e Perplexity Pro.
    """
    queries: list[str] = []
    domains_info = extract_domains_and_urls(user_message)
    msg_lower = user_message.lower()

    # 1. Se houver domínio/site mencionado (ex: fixblu.com.br)
    if domains_info:
        main_domain = domains_info[0]["domain"]
        
        # Sub-query 1: Focada no site/blog do domínio alvo
        if any(w in msg_lower for w in ["blog", "post", "artigo", "notícia", "dica"]):
            queries.append(f"site:{main_domain} (blog OR postagens OR artigos OR noticias)")
        else:
            queries.append(f"site:{main_domain}")

        # Se houver menção de marca/nome associado (ex: "fix serviços", "blumenau")
        brand_parts = []
        if "fix serviços" in msg_lower or "fix servicos" in msg_lower:
            brand_parts.append('"fix serviços"')
        elif "fix" in msg_lower:
            brand_parts.append('"fix"')
        if "blumenau" in msg_lower:
            brand_parts.append("Blumenau")
        
        if brand_parts:
            queries.append(f"{' '.join(brand_parts)} blog OR notícias")

    # 2. Sub-query para tendências / temas secundários (ex: "tendências de postagens similares")
    if any(w in msg_lower for w in ["tendência", "tendencias", "similar", "similares", "próximos meses", "2026", "2025"]):
        # Tenta identificar o nicho no texto
        niche_terms = []
        if any(w in msg_lower for w in ["eletricista", "eletrica", "elétrica"]):
            niche_terms.append("eletricista")
        if any(w in msg_lower for w in ["encanador", "hidraulica", "hidráulica"]):
            niche_terms.append("encanador")
        if any(w in msg_lower for w in ["manutenção", "manutencao", "serviços residenciais", "reparos"]):
            niche_terms.append('"serviços residenciais"')
        if any(w in msg_lower for w in ["marido de aluguel"]):
            niche_terms.append('"marido de aluguel"')

        niche_str = " OR ".join(niche_terms) if niche_terms else "serviços residenciais manutenção"
        queries.append(f'tendências conteúdo blog ({niche_str}) 2026')

    # 3. Fallback ou se não gerou queries: limpa o texto geral do usuário
    if not queries:
        cleaned = clean_query_text(user_message)
        if cleaned:
            queries.append(cleaned[:120])
        else:
            queries.append(user_message[:100])

    # Deduplica preservando ordem e limita a 3 queries para manter velocidade máxima
    seen = set()
    final_queries = []
    for q in queries:
        q_norm = q.strip()
        if q_norm and q_norm not in seen:
            seen.add(q_norm)
            final_queries.append(q_norm)

    return final_queries[:3]
