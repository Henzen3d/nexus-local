import re

TEMPORAL_KEYWORDS = [
    "hoje", "agora", "atual", "atualmente", "recente", "recentemente",
    "última", "últimas", "últimos", "esse ano", "este ano", "2025", "2026",
    "notícia", "notícias", "acontecendo", "novidade", "news", "today", "now"
]

FACTUAL_QUERY_PATTERNS = [
    r"\bquem (é|foi|ganhou|venceu)\b",
    r"\bquando (foi|será|ocorre)\b",
    r"\bqual (é|foi) o (preço|valor|cotação)\b",
    r"\bpreço (do|da|de)\b",
    r"\bcotação\b",
    r"\bresultado (do|da|de)\b",
    r"\bwho (is|was|won)\b",
    r"\bwhen (is|was|will)\b",
    r"\bprice of\b"
]

DOMAIN_SIGNALS = [
    "eleição", "eleições", "presidente", "prefeito",
    "bolsa de valores", "dólar", "criptomoeda", "bitcoin",
    "jogo", "placar", "campeonato", "futebol", "weather", "clima", "tempo"
]

def should_search(message: str, sensitivity: str = "medium") -> tuple[bool, float]:
    """
    Retorna (deve_buscar, confiança).
    Sensibilidade ajusta o threshold de confiança necessário.
    - low: Exige sinal muito forte (threshold 0.6)
    - medium: Equilíbrio padrão (threshold 0.4)
    - high: Muito sensível, arrisca falsos positivos (threshold 0.25)
    """
    score = 0.0
    msg_lower = message.lower()

    if any(kw in msg_lower for kw in TEMPORAL_KEYWORDS):
        score += 0.4
    if any(re.search(p, msg_lower) for p in FACTUAL_QUERY_PATTERNS):
        score += 0.35
    if any(d in msg_lower for d in DOMAIN_SIGNALS):
        score += 0.25

    thresholds = {"low": 0.6, "medium": 0.4, "high": 0.25}
    threshold = thresholds.get(sensitivity, 0.4)

    return score >= threshold, score
