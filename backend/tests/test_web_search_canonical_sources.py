"""Testes de numeração canônica de fontes e deduplicação (T4.2)."""

import pytest
from backend.web_search.formatter import (
    build_canonical_sources,
    citation_cache_scope,
    format_search_results,
    normalize_source_url,
)


def test_normalize_source_url():
    assert normalize_source_url("https://WWW.Example.com/path/") == "https://www.example.com/path/"
    assert normalize_source_url("http://example.com:8080/foo") == "http://example.com:8080/foo"
    assert normalize_source_url("https://example.com/?q=1") == "https://example.com/?q=1"
    assert normalize_source_url("") == ""
    assert normalize_source_url("https://EXAMPLE.com:443/Relatorio?a=1#tabela") == (
        "https://example.com/Relatorio?a=1#tabela"
    )
    assert normalize_source_url("http://127.0.0.1/") == ""


def test_build_canonical_sources_deduplication_and_ordering():
    scraped = [
        {
            "url": "https://g1.globo.com/politica/noticia/1.ghtml",
            "title": "G1 Notícia Principal",
            "text_sample": "Texto da notícia apurada.",
            "articles": [
                {
                    "title": "Sub-artigo relacionado",
                    "url": "https://g1.globo.com/politica/noticia/sub.ghtml",
                    "excerpt": "Resumo do sub-artigo",
                }
            ],
        }
    ]
    results = [
        # Mesmo link do scraped (deve ser deduplicado, mantendo status was_read=True)
        {
            "title": "G1 Notícia Principal no Google",
            "url": "https://G1.Globo.com/politica/noticia/1.ghtml",
            "snippet": "Snippet de busca",
        },
        # Novo resultado de busca
        {
            "title": "Folha de S.Paulo",
            "url": "https://folha.uol.com.br/poder/artigo.shtml",
            "snippet": "Análise eleitoral",
        },
    ]

    canonical = build_canonical_sources(results, scraped)
    assert len(canonical) == 3

    assert canonical[0]["index"] == 1
    assert canonical[0]["url"] == "https://g1.globo.com/politica/noticia/1.ghtml"
    assert canonical[0]["was_read"] is True

    assert canonical[1]["index"] == 2
    assert canonical[1]["url"] == "https://g1.globo.com/politica/noticia/sub.ghtml"
    assert canonical[1]["was_read"] is False

    assert canonical[2]["index"] == 3
    assert canonical[2]["url"] == "https://folha.uol.com.br/poder/artigo.shtml"
    assert canonical[2]["was_read"] is False


def test_format_search_results_uses_canonical_indices():
    scraped = [
        {
            "url": "https://exemplo.com/lido",
            "title": "Página Lida",
            "text_sample": "Conteúdo extraído",
        }
    ]
    results = [
        {
            "title": "Outro Resultado",
            "url": "https://outro.com/busca",
            "snippet": "Trecho da busca",
        }
    ]

    output = format_search_results(results, query="consulta teste", scraped_pages=scraped)

    # Verifica que [1] está associado à página lida e [2] ao resultado de busca
    assert "Página: [1] https://exemplo.com/lido" in output
    assert "[2] Outro Resultado" in output
    assert "Fonte: https://outro.com/busca" in output

    # Verifica instrução de não repetir lista final de links
    assert "Não repita uma seção final de links ao término da resposta" in output
    assert "<dados_web>" in output
    assert "</dados_web>" in output


def test_numbered_source_cache_is_bound_to_order_and_exact_address():
    rows = [
        {"title": "2025", "url": "https://example.com/Relatorio?ano=2025"},
        {"title": "2026", "url": "https://example.com/Relatorio?ano=2026"},
    ]
    sources = build_canonical_sources(rows)
    assert [s["index"] for s in sources] == [1, 2]
    assert citation_cache_scope(sources) != citation_cache_scope(build_canonical_sources(rows[::-1]))
    assert citation_cache_scope(sources) != citation_cache_scope(sources[:1])

    formatted = format_search_results(rows, "relatório", "{query}: {results}", canonical_sources=sources)
    assert formatted.index("</dados_web>") < formatted.index("Não repita")
    plain = format_search_results(rows, "relatório", canonical_sources=[])
    assert "mantenha-os no texto" in plain
