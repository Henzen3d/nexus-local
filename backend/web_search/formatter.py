def format_search_results(
    results: list[dict],
    query: str,
    template: str = None,
    scraped_pages: list[dict] = None,
) -> str:
    if not results and not scraped_pages:
        return ""
    
    sections = []

    # 1. Artigos e páginas extraídas via Deep Reader
    if scraped_pages:
        reader_blocks = []
        for page in scraped_pages:
            url = page.get("url", "")
            title = page.get("title", "")
            articles = page.get("articles", [])
            text_sample = page.get("text_sample", "")

            block = [f"Página: {url} ({title})"]
            if articles:
                block.append("Artigos / Publicações Identificados no Site:")
                for idx, a in enumerate(articles[:10], start=1):
                    date_info = f" [Publicado em: {a['date']}]" if a.get("date") else ""
                    excerpt_info = f"\n   Resumo: {a['excerpt']}" if a.get("excerpt") else ""
                    block.append(f"{idx}. \"{a['title']}\"{date_info}\n   Link: {a['url']}{excerpt_info}")
            elif text_sample:
                block.append(f"Conteúdo textual extraído da página:\n{text_sample[:1500]}")

            reader_blocks.append("\n".join(block))

        if reader_blocks:
            sections.append(
                "### CONTEÚDO EXTRAÍDO DIRETAMENTE DAS PÁGINAS WEB (DEEP READER):\n"
                + "\n\n".join(reader_blocks)
            )

    # 2. Resultados gerais de busca
    if results:
        search_blocks = []
        for i, r in enumerate(results):
            title = r.get("title", "")
            snippet = r.get("snippet", "")
            url = r.get("url", "")
            search_blocks.append(f"[{i+1}] {title}\n{snippet}\nFonte: {url}")

        sections.append(
            f"### RESULTADOS DE BUSCA NA WEB PARA \"{query}\":\n"
            + "\n\n".join(search_blocks)
        )

    full_content = "\n\n---\n\n".join(sections)

    if template and "{query}" in template and "{results}" in template:
        try:
            return template.format(query=query, results=full_content)
        except Exception:
            pass

    return f"""{full_content}

---
Instruções: Os dados acima foram consultados diretamente na web e em páginas reais pelo sistema. Utilize essas informações atualizadas (artigos específicos, datas de publicação e tendências) como base factual para responder com autoridade à pergunta do usuário abaixo, citando as fontes quando relevante. Não afirme que não possui acesso à internet ou que não pode acessar a web."""
