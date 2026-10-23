import re
from urllib.parse import urlparse


FILLER_WORDS = [
    # Ordens conversacionais à IA (R2)
    r"\bpode\s+(?:ir\s+)?(?:at[eé]\s+)?(?:a\s+|na\s+|no\s+)?(?:web|internet|google|site)\s+(?:e\s+)?(?:pegar|buscar|ver|olhar|achar|trazer|obter)\b",
    r"\b(?:acesse|acessar|consulte|consultar|veja|olhe|busque|pesquise|v[aá]\s+at[eé]|entre\s+no)\s+(?:a\s+|na\s+|no\s+|o\s+)?(?:web|internet|google|online|site)(?:\s+(?:e\s+)?(?:pegue|veja|busque|ache|procure|traga|consulte))?\b",
    r"\b(?:procure|busque|pesquise)\s+(?:na\s+internet|no\s+google|no\s+site|online)\b",
    r"\bentre\s+no\s+google\s+e\s+busque\b",
    r"\bpode\s+(?:ir\s+at[eé]|ir\s+na|acessar|buscar|pegar|olhar|ver)\b",
    r"\b(?:pegue|pegar|obtenha|obter|traga|trazer|consulte|consultar)\s+(?:o|a|os|as)?\b",
    r"\bme\s+(?:passe|envie|traga|d[eê]|forne[cç]a)\s+(?:o|a|os|as)?\b",
    r"\b(?:deles|dela|dele|delas|dessa\s+empresa|desse\s+local|deste\s+local|da\s+empresa|do\s+site|dessa\s+marca|desse\s+lugar)\b",
    r"\bvoc[eê]\s+pode(?:\s+me\s+dizer)?\b",
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
    r"\bcomo faço para\b",
    r"\bcomo faço pra\b",
    r"\bcomo eu faço para\b",
    r"\bcomo eu faço pra\b",
    r"\bcomo faço\b",
    r"\bcomo criar\b",
    r"\bcomo montar\b",
    r"\bcomo ter\b",
    r"\bcomo abrir\b",
    r"\bcomo começar\b",
    r"\bcomo conseguir\b",
    r"\bcomo posso\b",
    r"\bde sucesso\b",
    r"\bme ajude a\b",
    r"\bme ajude com\b",
    r"\bvocê sabe\b",
    r"\bsabe me dizer\b",
    r"\bqual o\b",
    r"\bqual é o\b",
    r"\bqual a\b",
    r"\bqual é a\b",
    r"\bquem é o\b",
    r"\bquem é a\b",
    r"\bquem foi o\b",
    r"\bo que é\b",
    r"\bo que foi\b",
    r"\búltimas notícias sobre\b",
    r"\bnotícias sobre\b",
]

DOMAIN_REGEX = re.compile(
    r"(?:https?://)?(?:www\.)?([a-zA-Z0-9-]+\.[a-zA-Z]{2,}(?:\.[a-zA-Z]{2,})?)(?:/[^\s,]*)?",
    re.IGNORECASE,
)

ANAPHORIC_PRONOUNS_REGEX = re.compile(
    r"\b(deles|dela|dele|delas|dessa\s+empresa|desse\s+local|deste\s+local|da\s+empresa|do\s+site|dessa\s+marca|desse\s+lugar|dali)\b",
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


def extract_context_entities(history: list[dict] | None) -> list[str]:
    """Extrai entidades (empresas, marcas, serviços, cidades) de mensagens recentes do histórico."""
    if not history:
        return []

    entities: list[str] = []
    for msg in reversed(history[-4:]):
        content = msg.get("content") or ""
        if not isinstance(content, str) or not content.strip():
            continue
        c_lower = content.lower()

        # 1. Padrões específicos de alta relevância (ex: Fix Serviços Blumenau)
        if "fix serviços" in c_lower or "fix servicos" in c_lower:
            if "blumenau" in c_lower:
                entities.append("Fix Serviços Blumenau")
            else:
                entities.append("Fix Serviços")
        elif "blumenau" in c_lower and "fix" in c_lower:
            entities.append("Fix Serviços Blumenau")

        # 2. Padrões de contratação e empresas no histórico
        for match in re.finditer(
            r"\b(?:contratar|comprar\s+de|falar\s+com|empresa|loja|agência|clínica|marca|serviços?\s+de)\s+([A-Za-zÀ-ÿ0-9\s\-]+?)(?:\?|\.|\,|!|para|em\s+[A-Z]{2}|$|\n)",
            content,
            re.IGNORECASE,
        ):
            cand = match.group(1).strip()
            cand = re.sub(r"^(?:a|o|as|os|um|uma)\s+", "", cand, flags=re.IGNORECASE).strip()
            if len(cand) >= 3 and cand.lower() not in ("você", "ia", "google", "site", "web"):
                city_match = re.search(r"\b(blumenau|florian[oó]polis|joinville|curitiba|s[aã]o\s+paulo|itajai|itajaí)\b", c_lower)
                if city_match and city_match.group(1) not in cand.lower():
                    cand = f"{cand} {city_match.group(1).capitalize()}"
                entities.append(cand)

        # 3. Nomes próprios compostos com iniciais maiúsculas
        for match in re.finditer(
            r"\b([A-ZÀ-ÿ][a-zà-ÿ0-9]+(?:\s+(?:de|da|do|dos|das|e|em)?\s+[A-ZÀ-ÿ][a-zà-ÿ0-9]+)+)\b",
            content,
        ):
            cand = match.group(1).strip()
            if len(cand) >= 4 and not any(cand.lower().startswith(p) for p in ("como posso", "você pode", "olá", "bom dia", "boa tarde")):
                entities.append(cand)

        if entities:
            break

    seen = set()
    cleaned_entities = []
    for ent in entities:
        norm = re.sub(r"\s+", " ", ent).strip()
        if norm.lower() not in seen:
            seen.add(norm.lower())
            cleaned_entities.append(norm)
    return cleaned_entities


def clean_query_text(text: str) -> str:
    """Remove palavras de preenchimento conversacional e pontuação excessiva."""
    cleaned = text
    for pattern in FILLER_WORDS:
        cleaned = re.sub(pattern, " ", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"[\"'\(\)\[\]\?!,;]", " ", cleaned)
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    return cleaned


def plan_search_queries(user_message: str, history: list[dict] | None = None) -> list[str]:
    """
    Decompõe o prompt do usuário em 1 a 3 sub-consultas otimizadas com operadores de busca.
    Resolve contexto conversacional e anáfora a partir das mensagens recentes.
    """
    queries: list[str] = []
    domains_info = extract_domains_and_urls(user_message)
    msg_lower = user_message.lower()

    # 0. Resolução anafórica de contexto do histórico (R2)
    has_anaphora = bool(ANAPHORIC_PRONOUNS_REGEX.search(user_message))
    has_missing_entity = (
        any(w in msg_lower for w in ["telefone", "whatsapp", "contato", "endereço", "endereco", "site oficial", "horário", "horario"])
        and not any(w in msg_lower for w in ["fix", "blumenau", "google", "empresa", "loja"])
    )

    context_entities = []
    if (has_anaphora or has_missing_entity) and history:
        context_entities = extract_context_entities(history)

    if context_entities:
        primary_entity = context_entities[0]
        cleaned_order = clean_query_text(user_message)
        contact_terms = [
            kw for kw in ["telefone", "whatsapp", "contato", "endereço", "endereco", "site oficial", "horário", "horario"]
            if kw in msg_lower
        ]
        contact_str = " ".join(contact_terms) if contact_terms else cleaned_order
        if any(w in msg_lower for w in ["telefone", "whatsapp", "contato"]):
            queries.append(f'"{primary_entity}" telefone')
            queries.append(f'"{primary_entity}" WhatsApp contato')
            queries.append(f'"{primary_entity}"')
        else:
            queries.append(f'"{primary_entity}" {contact_str}'.strip())
            queries.append(f'"{primary_entity}"')

    # 1. Se houver domínio/site mencionado (ex: fixblu.com.br)
    if domains_info:
        main_domain = domains_info[0]["domain"]
        if any(w in msg_lower for w in ["blog", "post", "artigo", "notícia", "dica"]):
            queries.append(f"site:{main_domain} (blog OR postagens OR artigos OR noticias)")
        else:
            queries.append(f"site:{main_domain}")

    # 2. Identificação global de marcas, entidades e cidades no próprio prompt
    brand_parts = []
    if "fix serviços" in msg_lower or "fix servicos" in msg_lower:
        brand_parts.append('"fix serviços"')
    elif re.search(r"\bfix\b", msg_lower):
        brand_parts.append('"fix"')
    if "blumenau" in msg_lower:
        brand_parts.append("Blumenau")

    if brand_parts:
        if domains_info:
            queries.append(f"{' '.join(brand_parts)} blog OR notícias")
        else:
            queries.append(f"{' '.join(brand_parts)}")
            if any(w in msg_lower for w in ["empresa", "negócio", "loja", "serviço", "serviços"]):
                queries.append(f"{' '.join(brand_parts)} empresa")

    # 3. Sub-query para tendências / temas secundários (ex: "tendências de postagens similares")
    if any(w in msg_lower for w in ["tendência", "tendencias", "similar", "similares", "próximos meses", "2026", "2025"]):
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

    # 4. Query limpa do texto geral do usuário
    cleaned = clean_query_text(user_message)
    if cleaned and cleaned not in queries:
        queries.append(cleaned[:120])

    if not queries:
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
