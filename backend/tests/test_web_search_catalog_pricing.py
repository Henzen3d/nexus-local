"""test_web_search_catalog_pricing.py — Testes da Tarefa T4 (Incidente de Busca Web e Preços).

Valida:
1. T4.1: Planejamento de sub-consultas focadas para catálogo oficial e preços (distinção Gemini API vs Vertex AI).
2. T4.1: Suporte a múltiplos fabricantes (Google, OpenAI, Anthropic) comprovando que o fluxo não é restrito a um provedor.
3. T4.1: Deduplicação e normalização de consultas equivalentes antes da execução.
4. T4.2: Extração de tabelas estruturadas pelo leitor (cabeçalhos, linhas, unidades, tokens de input/output).
5. T4.2: Preferência de ranqueamento para documentação oficial sobre comparadores genéricos.
6. T4.3: Classificação de cobertura (sufficient, partial, absent) e presença de distinção entre ofertas.
7. T4.3: Invalidação de cache semântico quando o conteúdo/preço da mesma URL muda.
8. T4.3: Estabilidade de citações canônicas [1], [2] para entrega consistente ao modelo de reserva no failover.
"""

from __future__ import annotations

import json
from pathlib import Path
import pytest

from backend.web_search.agent import (
    is_catalog_pricing_query,
    plan_catalog_pricing_queries,
    deduplicate_queries,
    normalize_query_key,
    score_search_result,
)
from backend.web_search.reader import (
    extract_tables,
    extract_articles_and_content,
    format_table_markdown,
)
from backend.web_search.formatter import (
    build_canonical_sources,
    citation_cache_scope,
    classify_search_coverage,
    format_search_results,
    normalize_source_url,
)


@pytest.fixture
def catalog_fixture() -> dict:
    fixture_path = Path(__file__).parent / "fixtures" / "incident_web_search_catalog_pricing.json"
    with open(fixture_path, encoding="utf-8") as f:
        return json.load(f)


# ── T4.1: Planejamento de sub-consultas e normalização ──────────────────────


def test_t4_1_detect_catalog_pricing_intent():
    assert is_catalog_pricing_query("Quais são os últimos modelos LLM do Google e seus preços")
    assert is_catalog_pricing_query("modelos e preços da OpenAI")
    assert is_catalog_pricing_query("Claude models and pricing table Anthropic")
    assert is_catalog_pricing_query("qual o catálogo de modelos e custos de tokens da Mistral")
    # Não deve classificar falsamente buscas pontuais
    assert not is_catalog_pricing_query("qual a cotação do dólar hoje")
    assert not is_catalog_pricing_query("qual a capital do Brasil")


def test_t4_1_plan_queries_google_distinction():
    q = "Quais são os últimos modelos LLM do Google e seus preços"
    planned = plan_catalog_pricing_queries(q)

    assert len(planned) >= 3
    # Catálogo oficial
    assert any("catalog" in p.lower() or "model" in p.lower() for p in planned)
    # Preços oficiais Gemini API / AI Studio
    assert any("gemini api" in p.lower() or "ai studio" in p.lower() for p in planned)
    # Distinção Google Cloud Vertex AI
    assert any("vertex" in p.lower() for p in planned)


def test_t4_1_plan_queries_multi_vendor():
    # OpenAI
    q_openai = "Quais são os últimos modelos e preços da OpenAI?"
    planned_openai = plan_catalog_pricing_queries(q_openai)
    assert any("openai" in p.lower() and "catalog" in p.lower() for p in planned_openai)
    assert any("openai" in p.lower() and "pricing" in p.lower() for p in planned_openai)

    # Anthropic
    q_anthropic = "Modelos Claude e preços Anthropic"
    planned_anthropic = plan_catalog_pricing_queries(q_anthropic)
    assert any("anthropic" in p.lower() and "catalog" in p.lower() for p in planned_anthropic)
    assert any("anthropic" in p.lower() and "pricing" in p.lower() for p in planned_anthropic)

    # Fornecedor genérico
    q_generic = "Quais são os modelos e preços da Cohere?"
    planned_generic = plan_catalog_pricing_queries(q_generic)
    assert any("cohere" in p.lower() and "catalog" in p.lower() for p in planned_generic)
    assert any("cohere" in p.lower() and "pricing" in p.lower() for p in planned_generic)


def test_t4_1_query_deduplication_and_normalization():
    raw_queries = [
        "Google Gemini official models catalog",
        "google gemini official models catalog ",  # Duplicata com whitespace e case
        "Google Gemini, official models catalog!",  # Duplicata com pontuação
        "Google AI Studio Gemini API pricing token cost official",
        "Google Cloud Vertex AI pricing Gemini token official",
    ]
    deduped = deduplicate_queries(raw_queries)
    assert len(deduped) == 3
    assert deduped[0] == "Google Gemini official models catalog"
    assert deduped[1] == "Google AI Studio Gemini API pricing token cost official"
    assert deduped[2] == "Google Cloud Vertex AI pricing Gemini token official"


# ── T4.2: Extração de tabelas e ranqueamento oficial vs comparadores ──────────


def test_t4_2_reader_extracts_structured_tables():
    sample_html = """
    <html>
      <head><title>Google AI Pricing</title></head>
      <body>
        <h1>Gemini Models Pricing</h1>
        <p>Official pricing per million tokens.</p>
        <table id="pricing-table">
          <thead>
            <tr>
              <th>Model</th>
              <th>Input Price (1M tokens)</th>
              <th>Output Price (1M tokens)</th>
              <th>Context Window</th>
            </tr>
          </thead>
          <tbody>
            <tr>
              <td>Gemini 1.5 Flash</td>
              <td>$0.075</td>
              <td>$0.30</td>
              <td>1M tokens</td>
            </tr>
            <tr>
              <td>Gemini 1.5 Pro</td>
              <td>$3.50</td>
              <td>$10.50</td>
              <td>2M tokens</td>
            </tr>
          </tbody>
        </table>
      </body>
    </html>
    """
    extracted = extract_articles_and_content(sample_html, base_url="https://ai.google.dev/pricing")
    assert "tables" in extracted
    tables = extracted["tables"]
    assert len(tables) >= 1

    tbl = tables[0]
    assert tbl["headers"] == ["Model", "Input Price (1M tokens)", "Output Price (1M tokens)", "Context Window"]
    assert len(tbl["rows"]) == 2
    assert tbl["rows"][0] == ["Gemini 1.5 Flash", "$0.075", "$0.30", "1M tokens"]
    assert tbl["rows"][1] == ["Gemini 1.5 Pro", "$3.50", "$10.50", "2M tokens"]

    # Formatação markdown
    md = format_table_markdown(tbl)
    assert "| Model | Input Price (1M tokens) | Output Price (1M tokens) | Context Window |" in md
    assert "| Gemini 1.5 Flash | $0.075 | $0.30 | 1M tokens |" in md
    assert "| Gemini 1.5 Pro | $3.50 | $10.50 | 2M tokens |" in md


def test_t4_2_score_search_result_prefers_official_over_comparator():
    user_msg = "Quais são os últimos modelos LLM do Google e seus preços"

    official_res = {
        "title": "Gemini API Pricing | Google AI for Developers",
        "url": "https://ai.google.dev/gemini-api/docs/pricing",
        "snippet": "Preços oficiais do Gemini 1.5 Pro e 1.5 Flash por 1M de tokens input e output.",
    }
    vertex_res = {
        "title": "Vertex AI Pricing | Google Cloud",
        "url": "https://cloud.google.com/vertex-ai/pricing",
        "snippet": "Preços do Vertex AI no Google Cloud para Gemini e modelos fundacionais.",
    }
    comparator_res = {
        "title": "Gemini 1.5 Pro Pricing & Benchmark Comparison",
        "url": "https://artificialanalysis.ai/models/gemini-1-5-pro",
        "snippet": "Comparador de preço de LLMs entre Google, OpenAI e Anthropic.",
    }
    generic_blog_res = {
        "title": "Os novos modelos de inteligência artificial",
        "url": "https://tecnoblog.net/artigo/novos-modelos-ia",
        "snippet": "Artigo comentando os lançamentos de tecnologia do ano.",
    }

    score_official = score_search_result(user_msg, official_res)
    score_vertex = score_search_result(user_msg, vertex_res)
    score_comparator = score_search_result(user_msg, comparator_res)
    score_blog = score_search_result(user_msg, generic_blog_res)

    # Documentação oficial deve ter pontuação muito superior à de comparadores
    assert score_official > score_comparator, f"Oficial ({score_official}) deveria ser > Comparador ({score_comparator})"
    assert score_vertex > score_comparator, f"Vertex ({score_vertex}) deveria ser > Comparador ({score_comparator})"
    assert score_comparator > score_blog


# ── T4.3: Classificação de cobertura e estabilidade de citações ──────────────


def test_t4_3_classify_search_coverage_sufficient(catalog_fixture):
    query = catalog_fixture["original_query"]
    results = catalog_fixture["search_results"]
    scraped = catalog_fixture["scraped_pages"]

    cov = classify_search_coverage(query, results=results, scraped_pages=scraped)
    assert cov["catalog_coverage"] == "sufficient"
    assert cov["pricing_coverage"] == "sufficient"
    assert cov["overall"] == "sufficient"
    assert cov["has_gemini_api"] is True
    assert cov["has_vertex_ai"] is True


def test_t4_3_classify_search_coverage_partial_when_no_tables():
    query = "Quais são os últimos modelos LLM do Google e seus preços"
    # Apenas resultados gerais sem tabela e sem preços por token
    results = [
        {
            "title": "Google anuncia nova família Gemini",
            "url": "https://blog.google/technology/ai/gemini-models",
            "snippet": "Apresentamos o Gemini 1.5 Pro e Gemini 1.5 Flash com melhorias de raciocínio.",
        }
    ]
    scraped = [
        {
            "url": "https://blog.google/technology/ai/gemini-models",
            "title": "Google anuncia nova família Gemini",
            "text_sample": "O Gemini 1.5 Pro e Gemini 1.5 Flash são os mais novos modelos.",
            "tables": [],
        }
    ]
    cov = classify_search_coverage(query, results=results, scraped_pages=scraped)
    assert cov["catalog_coverage"] in ("sufficient", "partial")
    assert cov["pricing_coverage"] == "absent"
    assert cov["overall"] == "partial"


def test_t4_3_format_search_results_includes_tables_and_guidelines(catalog_fixture):
    query = catalog_fixture["original_query"]
    results = catalog_fixture["search_results"]
    scraped = catalog_fixture["scraped_pages"]

    formatted = format_search_results(results, query=query, scraped_pages=scraped)

    # Verifica inclusão de tabelas estruturadas
    assert "Tabelas estruturadas / Dados de preços extraídos:" in formatted
    assert "Gemini 1.5 Flash" in formatted
    assert "$0.075" in formatted
    assert "$0.30" in formatted
    assert "$3.50" in formatted

    # Verifica inclusão da avaliação de cobertura
    assert "AVALIAÇÃO DE COBERTURA DA BUSCA" in formatted
    assert "Distinção de ofertas" in formatted

    # Verifica diretriz de proibição de preenchimento por memória e de precisão de tokens
    assert "TRANSPARÊNCIA E PRECISÃO EM CATÁLOGO E PREÇOS" in formatted
    assert "sem inventar valores" in formatted
    assert "Diferencie tokens de entrada (input) e tokens de saída (output)" in formatted


def test_t4_3_citation_cache_invalidates_on_content_change():
    """Garante que se o preço/conteúdo na mesma URL mudar, o cache_scope é alterado."""
    sources_v1 = [
        {
            "index": 1,
            "url": "https://ai.google.dev/pricing",
            "title": "Pricing",
            "snippet": "Gemini 1.5 Pro: $3.50 input, $10.50 output per 1M tokens",
            "was_read": True,
        }
    ]
    sources_v2 = [
        {
            "index": 1,
            "url": "https://ai.google.dev/pricing",
            "title": "Pricing",
            "snippet": "Gemini 1.5 Pro: $2.50 input, $7.50 output per 1M tokens",  # Preço alterado
            "was_read": True,
        }
    ]

    hash_v1 = citation_cache_scope(sources_v1)
    hash_v2 = citation_cache_scope(sources_v2)

    assert hash_v1 != hash_v2, "O cache_scope DEVE invalidar quando o conteúdo/preço da mesma URL muda!"


def test_t4_3_failover_stable_citation_delivery(catalog_fixture):
    """
    Simula failover entre candidatos de modelo garantindo que:
    1. A lista canônica de fontes mantém numeração idêntica [1], [2].
    2. A ordem e índices inline não mudam na substituição do modelo.
    """
    results = catalog_fixture["search_results"]
    scraped = catalog_fixture["scraped_pages"]

    # Constrói fontes canônicas
    canonical_sources = build_canonical_sources(results, scraped)

    assert len(canonical_sources) >= 3
    assert canonical_sources[0]["index"] == 1
    assert canonical_sources[0]["url"] == "https://ai.google.dev/gemini-api/docs/pricing"
    assert canonical_sources[0]["was_read"] is True

    assert canonical_sources[1]["index"] == 2
    assert canonical_sources[1]["url"] == "https://cloud.google.com/vertex-ai/pricing"
    assert canonical_sources[1]["was_read"] is True

    # Modelo 1 (ex: OrcaRouter/DeepSeek) receberia formatted_payload
    payload_model_1 = format_search_results(
        results, query=catalog_fixture["original_query"],
        scraped_pages=scraped, canonical_sources=canonical_sources
    )

    # Modelo 2 (ex: OpenRouter/Nemotron fallback) recebe o mesmo conjunto sem re-executar busca
    payload_fallback_model = format_search_results(
        results, query=catalog_fixture["original_query"],
        scraped_pages=scraped, canonical_sources=canonical_sources
    )

    assert payload_model_1 == payload_fallback_model
    assert "Página: [1] https://ai.google.dev/gemini-api/docs/pricing" in payload_fallback_model
    assert "Página: [2] https://cloud.google.com/vertex-ai/pricing" in payload_fallback_model
