import re

TEMPORAL_KEYWORDS = [
    "hoje", "agora", "atual", "atualmente", "recente", "recentemente",
    "última", "últimas", "últimos", "esse ano", "este ano", "deste ano", "desse ano",
    "neste ano", "nesse ano", "ano atual", "ano corrente", "2025", "2026",
    "notícia", "notícias", "acontecendo", "novidade", "news", "today", "now",
    "atualidade", "hoje em dia", "latest", "recent",
]

FACTUAL_QUERY_PATTERNS = [
    r"\bquem\s+(é|são|foi|foram|ganhou|ganharam|venceu|venceram|lidera|lideram)\b",
    r"\bquais\s+(são|foram|serão)\b",
    r"\bqual\s+(é|foi|será)\s+o\s+(preço|valor|cotação|resultado)\b",
    r"\bcomo\s+(está|estão|ficou|ficaram)\b",
    r"\bquando\s+(foi|será|ocorre|acontece)\b",
    r"\bpreço\s+(do|da|de|dos|das)\b",
    r"\bcotação\b",
    r"\bresultado\s+(do|da|de|das|dos)\b",
    r"\belei[cç][õo]es\s+(deste|desse|neste|nesse)\s+ano\b",
    r"\bcandidatos?\s+(do|de|ao)?\s*(segundo|1º|2º|primeiro)?\s*turno\b",
    r"\bwho\s+(is|are|was|were|won)\b",
    r"\bwhich\s+(is|are|were)\b",
    r"\bwhen\s+(is|was|will)\b",
    r"\bprice\s+of\b",
    r"\bhow\s+(is|are)\b",
]

DOMAIN_SIGNALS = [
    "eleição", "eleições", "presidente", "prefeito", "governador", "senador",
    "deputado", "candidato", "candidatos", "segundo turno", "primeiro turno",
    "tse", "pesquisa eleitoral", "bolsa de valores", "dólar", "criptomoeda", "bitcoin",
    "jogo", "placar", "campeonato", "futebol", "weather", "clima", "tempo",
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
        score += 0.3
    if any(re.search(p, msg_lower) for p in FACTUAL_QUERY_PATTERNS):
        score += 0.35
    if any(d in msg_lower for d in DOMAIN_SIGNALS):
        score += 0.25

    thresholds = {"low": 0.6, "medium": 0.4, "high": 0.25}
    threshold = thresholds.get(sensitivity, 0.4)

    return score >= threshold, score
