def format_search_results(results: list[dict], query: str, template: str = None) -> str:
    if not results:
        return ""
    
    blocks = []
    for i, r in enumerate(results):
        title = r.get("title", "")
        snippet = r.get("snippet", "")
        url = r.get("url", "")
        blocks.append(f"[{i+1}] {title}\n{snippet}\nFonte: {url}")
    
    formatted_results = "\n\n".join(blocks)

    if template and "{query}" in template and "{results}" in template:
        try:
            return template.format(query=query, results=formatted_results)
        except Exception:
            pass

    return f"""Resultados de busca para "{query}":

{formatted_results}

---
Use essas informações para responder a pergunta do usuário abaixo, citando as fontes quando relevante."""
