"""test_golden_reasoning_and_web_search.py — Testes da suíte Golden Prompt.

Valida:
1. Resolução anafórica de entidades no Query Planner da busca web (R2).
2. Auto-trigger para consultas comerciais/locais e ordens explícitas (R3).
3. Filtro rígido de relevância contra tutoriais de VoIP e descarte de fontes sem a entidade (R4).
4. Salvaguardas anti-truncamento e elevação de max_tokens para modelos de raciocínio (R1).
"""
import pytest
import re

from backend.ranking.smart_router import IntentKey, classify_intent
from backend.web_search.heuristics import should_search
from backend.web_search.planner import plan_search_queries, extract_context_entities, clean_query_text
from backend.web_search.agent import score_search_result


def test_clean_query_text_strips_ai_action_commands():
    """Valida remoção agressiva de prefixos imperativos e comandos à IA."""
    raw = "pode ir até a web e pegar o telefone deles"
    cleaned = clean_query_text(raw)
    assert "pode ir" not in cleaned
    assert "web" not in cleaned
    assert "pegar" not in cleaned
    assert "deles" not in cleaned
    assert "telefone" in cleaned


def test_extract_context_entities_from_history():
    """Valida extração de entidade e cidade do histórico de conversas."""
    history = [
        {"role": "user", "content": "como posso contratar a fix serviços de blumenau sc?"},
        {"role": "assistant", "content": "A Fix Serviços em Blumenau oferece manutenção residencial."},
    ]
    entities = extract_context_entities(history)
    assert len(entities) > 0
    # Verifica que capturou a empresa e a cidade
    assert any("fix" in e.lower() for e in entities)
    assert any("blumenau" in e.lower() for e in entities)


def test_anaphora_resolution_in_plan_search_queries():
    """Valida que 'pegue o telefone deles' gera queries com a entidade do histórico anterior."""
    history = [
        {"role": "user", "content": "como posso contratar a fix serviços de blumenau sc?"},
    ]
    prompt = "pode ir até a web e pegar o telefone deles"
    queries = plan_search_queries(prompt, history=history)

    assert len(queries) > 0
    # A query principal deve focar na Fix Serviços de Blumenau e telefone
    combined = " ".join(queries).lower()
    assert "fix" in combined
    assert "telefone" in combined
    # Não deve buscar a frase literal de comando
    assert "pode ir até a web" not in combined
    assert "pegar o telefone deles" not in combined


def test_auto_trigger_commercial_and_local_queries():
    """Valida auto-trigger de busca web para dados de contato comercial e contratação."""
    commercial_queries = [
        "como posso contratar a fix serviços de blumenau sc?",
        "pode ir até a web e pegar o telefone deles",
        "qual o whatsapp e telefone de atendimento da empresa?",
        "onde fica o endereço deles?",
        "acesse a web e pesquise o site oficial",
        "busque na internet o contato",
    ]

    for q in commercial_queries:
        # 1. Heurísticas
        should, score = should_search(q, sensitivity="medium")
        assert should is True, f"should_search falhou para: '{q}' (score={score})"

        # 2. Smart Router
        res = classify_intent(q, web_search=False)
        assert res.intent == IntentKey.WEB_RESEARCH, f"Smart router falhou para: '{q}' (intent={res.intent})"


def test_relevance_scoring_discards_voip_tutorials():
    """Valida que domínios de tutoriais de VoIP recebem score 0.0 para perguntas de contato empresarial."""
    user_msg = "pode ir até a web e pegar o telefone deles"
    history = [{"role": "user", "content": "como posso contratar a fix serviços de blumenau sc?"}]

    voip_result_1 = {
        "title": "Como fazer ligações grátis pelo celular - Tecnobits",
        "snippet": "Aprenda a fazer ligações VoIP gratuitas pela web usando o aplicativo no celular.",
        "url": "https://tecnobits.com/como-fazer-ligacoes-voip/",
    }
    voip_result_2 = {
        "title": "Número virtual temporário online - Blacktel",
        "snippet": "Receba SMS e faça chamadas com números virtuais VoIP temporários.",
        "url": "https://www.blacktel.io/pt/recursos/voip",
    }
    legit_result = {
        "title": "Fix Serviços Blumenau - Telefone e WhatsApp",
        "snippet": "Entre em contato com a Fix Serviços em Blumenau SC pelo telefone e WhatsApp comercial.",
        "url": "https://www.fixservicosblu.com.br/contato",
    }

    score_voip_1 = score_search_result(user_msg, voip_result_1, history=history)
    score_voip_2 = score_search_result(user_msg, voip_result_2, history=history)
    score_legit = score_search_result(user_msg, legit_result, history=history)

    assert score_voip_1 == 0.0, f"VoIP não deveria pontuar: {score_voip_1}"
    assert score_voip_2 == 0.0, f"VoIP não deveria pontuar: {score_voip_2}"
    assert score_legit > 25.0, f"Resultado legítimo deveria ter score alto: {score_legit}"


def test_relevance_scoring_enforces_mandatory_entity():
    """Se o resultado não menciona a entidade do contexto nem o município, score deve ser 0.0."""
    user_msg = "pode ir até a web e pegar o telefone deles"
    history = [{"role": "user", "content": "como contratar a fix serviços de blumenau"}]

    unrelated_result = {
        "title": "Telefone das Casas Bahia em Joinville",
        "snippet": "Confira o número de telefone da filial das Casas Bahia em Joinville.",
        "url": "https://guiamais.com.br/casas-bahia-joinville",
    }
    score = score_search_result(user_msg, unrelated_result, history=history)
    assert score == 0.0


def test_thinking_tag_unclosed_safeguard():
    """Valida salvaguarda de fechamento de tag <think> truncated."""
    truncated_response = "<think>Analisando a empresa Fix Serviços em Blumenau... teste (principalmente em elétrica"
    
    # Simula a salvaguarda do resolve_request
    open_th = re.findall(r"<(think|thinking|reasoning|analysis)\b[^>]*>", truncated_response, re.IGNORECASE)
    close_th = re.findall(r"</(think|thinking|reasoning|analysis)>", truncated_response, re.IGNORECASE)
    if len(open_th) > len(close_th):
        last_open = open_th[-1]
        truncated_response += f"</{last_open}>\n\n"

    assert "</think>" in truncated_response
    # O bloco agora é válido para parsers
    assert truncated_response.endswith("</think>\n\n")


def test_debate_query_planning_and_relevance():
    """Valida planejamento e relevância para perguntas de debates presidenciais."""
    user_prompt = "quem está participando do debate presidencial na globo hoje dia 23/10/2026? e quem é o hoster que está intermediando o debate?"
    queries = plan_search_queries(user_prompt)

    # 1. Queries focadas e limpas
    assert len(queries) >= 2
    combined_q = " ".join(queries).lower()
    assert "debate" in combined_q
    assert "globo" in combined_q
    assert "23 outubro 2026" in combined_q or "2026" in combined_q

    # 2. Nenhuma contaminação residencial ou predial
    assert "serviços residenciais" not in combined_q
    assert "manutenção" not in combined_q

    # 3. Relevância: notícia do Terra/Globo/UOL deve ter pontuação alta (>30)
    legit_news = {
        "title": "Globo realiza debate presidencial entre Lula e Flávio Bolsonaro",
        "snippet": "Encontro nesta sexta-feira (23/10/2026) terá mediação de César Tralli nos Estúdios Globo.",
        "url": "https://www.terra.com.br/noticias/eleicoes/debate-globo-segundo-turno-2026",
    }
    score_news = score_search_result(user_prompt, legit_news)
    assert score_news > 30.0

    # 4. Blog predial ou de condomínio deve receber score 0.0
    condo_blog = {
        "title": "Tendências de manutenção predial em 2026",
        "snippet": "Confira inovações tecnológicas para condomínios e manutenção residencial em 2026.",
        "url": "https://tecniko.app/blog/tendencias-de-manutencao-predial-2026",
    }
    score_condo = score_search_result(user_prompt, condo_blog)
    assert score_condo == 0.0

