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

    return f"""Resultados de pesquisa na web para "{query}":

{formatted_results}

---
Instruções: Os resultados da pesquisa web acima já foram consultados pelo sistema e estão disponíveis para você. Utilize essas informações diretamente como fatos e dados atualizados para responder à pergunta do usuário, citando as fontes quando relevante. Não afirme que não possui acesso à internet ou que não pode acessar a web, pois a pesquisa já foi realizada com sucesso."""
