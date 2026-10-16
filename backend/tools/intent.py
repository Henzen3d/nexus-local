"""backend/tools/intent.py — Detecção rápida de intenção baseada em regex (<2ms).
Identifica automaticamente quando a mensagem do usuário necessita de dados reais
de APIs gratuitas (clima, moedas, dados brasileiros, conhecimento, notícias, etc.).
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, List, Optional


@dataclass
class ToolIntent:
    family: str           # 'weather', 'currency', 'brasil', 'knowledge', 'news', 'translation', 'geo', 'fun'
    action: str           # 'current', 'forecast', 'convert', 'lookup', etc.
    params: dict[str, Any] = field(default_factory=dict)
    confidence: float = 0.0  # 0.0 a 1.0
    raw_match: str = ""   # trecho da mensagem que ativou a regra


# ── Padrões Regex Pré-compilados ────────────────────────────────────

# Weather
_RE_WEATHER_CITY = re.compile(
    r"(?:clima|tempo|temperatura|previs[ãa]o|forecast|weather)\s+(?:em|in|de|para)\s+([a-zA-ZÀ-ÿ0-9\s\-]+?)(?:\?|\.|$|\s+(?:hoje|amanh[ãa]|agora|nesta semana))",
    re.IGNORECASE,
)
_RE_RAIN = re.compile(
    r"(?:vai\s+chover|vai\s+ter\s+chuva|chove|chovendo)\s+(?:em|in)\s+([a-zA-ZÀ-ÿ0-9\s\-]+?)(?:\?|\.|$)",
    re.IGNORECASE,
)
_RE_DEGREES = re.compile(
    r"(?:quantos\s+graus|qual\s+(?:a\s+)?temperatura)\s+(?:faz|est[áa])\s+(?:em|in)\s+([a-zA-ZÀ-ÿ0-9\s\-]+?)(?:\?|\.|$)",
    re.IGNORECASE,
)

# Currency
_RE_CURRENCY_PAIR = re.compile(
    r"(?:cota[çc][ãa]o|c[âa]mbio|valor|pre[çc]o)\s+(?:do|da|de)\s+(d[óo]lar|euro|libra|bitcoin|btc|usd|eur|gbp|ars|cad|jpy)(?:\s+(?:hoje|agora|em\s+reais?|em\s+brl))?",
    re.IGNORECASE,
)
_RE_CURRENCY_CONVERT = re.compile(
    r"(?:quanto\s+(?:[eé]|est[aá]|vale)|converter?)\s+(\d+(?:[\.,]\d+)?)\s+(d[óo]lar(?:es)?|euro(?:s)?|libra(?:s)?|reais?|real|usd|eur|brl|gbp)\s+(?:em|para|to)\s+(d[óo]lar(?:es)?|euro(?:s)?|libra(?:s)?|reais?|real|usd|eur|brl|gbp)",
    re.IGNORECASE,
)
_RE_CURRENCY_SHORT = re.compile(
    r"\b(\d+(?:[\.,]\d+)?)\s*(usd|eur|brl|gbp)\s+(?:em|para|to|in)\s+(usd|eur|brl|gbp)\b",
    re.IGNORECASE,
)

# Brasil (CEP, CNPJ, DDD, Feriados)
_RE_CEP = re.compile(r"\b(?:cep|CEP)\s*:?\s*(\d{5}-?\d{3})\b")
_RE_CEP_SOLO = re.compile(r"\b(\d{5}-\d{3})\b")
_RE_CNPJ = re.compile(r"\b(?:cnpj|CNPJ)\s*:?\s*(\d{2}\.?\d{3}\.?\d{3}/?\d{4}-?\d{2})\b")
_RE_DDD = re.compile(r"\b(?:ddd|DDD)\s+(?:de\s+)?(\d{2})\b")
_RE_FERIADOS = re.compile(r"\b(?:feriados?)\s+(?:de|em|do\s+ano\s+de)\s+(\d{4})\b", re.IGNORECASE)

# Knowledge (Wikipedia / Open Library)
_RE_WHO_WHAT = re.compile(
    r"^(?:quem\s+(?:[eé]|foi|era)|o\s+que\s+(?:[eé]|s[aã]o|significa)|defina|defini[çc][ãa]o\s+de)\s+([a-zA-ZÀ-ÿ0-9\s\-'\"]+?)\??$",
    re.IGNORECASE,
)
_RE_TELL_ABOUT = re.compile(
    r"(?:me\s+(?:fale|conte|diga|explique)\s+sobre|informa[çc][õo]es\s+sobre|pesquise\s+sobre)\s+([a-zA-ZÀ-ÿ0-9\s\-'\"]+?)(?:\?|\.|$)",
    re.IGNORECASE,
)
_RE_WIKI = re.compile(r"\b(?:wikipedia|wiki)\s+([a-zA-ZÀ-ÿ0-9\s\-]+?)(?:\?|\.|$)", re.IGNORECASE)

# News
_RE_NEWS = re.compile(
    r"(?:not[íi]cias?|novidades?|news|[úu]ltimas)\s+(?:sobre|de|do|da|a\s+respeito\s+de)\s+([a-zA-ZÀ-ÿ0-9\s\-]+?)(?:\?|\.|$)",
    re.IGNORECASE,
)
_RE_WHATS_HAPPENING = re.compile(
    r"(?:o\s+que\s+(?:est[aá]|t[aá])\s+acontecendo)\s+(?:com|no|na|em)\s+([a-zA-ZÀ-ÿ0-9\s\-]+?)(?:\?|\.|$)",
    re.IGNORECASE,
)

# Translation
_RE_TRANSLATE = re.compile(
    r"(?:traduz(?:a|ir)?|tradu[çc][ãa]o\s+de)\s+[\"']?(.+?)[\"']?\s+para\s+(ingl[êe]s|portugu[êe]s|espanhol|franc[êe]s|alem[ãa]o|italiano|english|spanish|french)",
    re.IGNORECASE,
)

# Fun (piadas, curiosidades)
_RE_FUN_JOKE = re.compile(
    r"(?:conte-?me|me\s+conte|diga)\s+(?:uma\s+)?(?:piada|anedota)",
    re.IGNORECASE,
)
_RE_FUN_FACT = re.compile(
    r"(?:conte-?me|me\s+conte|diga|voc[êe]\s+sabe)\s+(?:uma\s+)?(?:curiosidade|fato\s+curioso|fato\s+aleat[óo]rio)",
    re.IGNORECASE,
)


def _normalize_currency_code(name: str) -> str:
    n = name.lower().strip()
    if "dólar" in n or "dolar" in n or n == "usd":
        return "USD"
    if "euro" in n or n == "eur":
        return "EUR"
    if "libra" in n or n == "gbp":
        return "GBP"
    if "real" in n or "reais" in n or n == "brl":
        return "BRL"
    if "bitcoin" in n or n == "btc":
        return "BTC"
    if "ars" in n or "peso" in n:
        return "ARS"
    if "cad" in n:
        return "CAD"
    if "jpy" in n or "iene" in n:
        return "JPY"
    return name.upper()


def _normalize_lang_code(name: str) -> str:
    n = name.lower().strip()
    if "ingl" in n or "eng" in n:
        return "en"
    if "port" in n:
        return "pt"
    if "espanh" in n or "span" in n:
        return "es"
    if "fran" in n:
        return "fr"
    if "alem" in n or "ger" in n:
        return "de"
    if "ital" in n:
        return "it"
    return "en"


def detect_intents(message: str, lang: str = "pt") -> list[ToolIntent]:
    """Analisa o texto do usuário e detecta intenções que casam com famílias de ferramentas.
    
    Executa puramente com regex compilados em <2ms, sem chamadas extras de LLM.
    Descarta mensagens muito curtas ou puramente conversacionais.
    """
    if not message or len(message.strip()) < 8:
        return []

    text = message.strip()
    intents: list[ToolIntent] = []

    # 1. Weather
    m_w = _RE_WEATHER_CITY.search(text) or _RE_RAIN.search(text) or _RE_DEGREES.search(text)
    if m_w:
        city = m_w.group(1).strip()
        # Filtra termos genéricos
        if len(city) >= 2 and city.lower() not in ("hoje", "amanhã", "agora", "aqui", "lá"):
            intents.append(ToolIntent(
                family="weather",
                action="current",
                params={"city": city, "days": 3},
                confidence=0.9,
                raw_match=m_w.group(0),
            ))

    # 2. Currency
    m_cp = _RE_CURRENCY_PAIR.search(text)
    if m_cp:
        curr = _normalize_currency_code(m_cp.group(1))
        from_code = curr if curr != "BRL" else "USD"
        to_code = "BRL" if from_code != "BRL" else "USD"
        intents.append(ToolIntent(
            family="currency",
            action="quote",
            params={"from": from_code, "to": to_code},
            confidence=0.95,
            raw_match=m_cp.group(0),
        ))
    else:
        m_cc = _RE_CURRENCY_CONVERT.search(text)
        if m_cc:
            amount_str = m_cc.group(1).replace(",", ".")
            try:
                amount = float(amount_str)
            except ValueError:
                amount = 1.0
            from_code = _normalize_currency_code(m_cc.group(2))
            to_code = _normalize_currency_code(m_cc.group(3))
            intents.append(ToolIntent(
                family="currency",
                action="convert",
                params={"from": from_code, "to": to_code, "amount": amount},
                confidence=0.95,
                raw_match=m_cc.group(0),
            ))
        else:
            m_cs = _RE_CURRENCY_SHORT.search(text)
            if m_cs:
                amount_str = m_cs.group(1).replace(",", ".")
                try:
                    amount = float(amount_str)
                except ValueError:
                    amount = 1.0
                from_code = m_cs.group(2).upper()
                to_code = m_cs.group(3).upper()
                intents.append(ToolIntent(
                    family="currency",
                    action="convert",
                    params={"from": from_code, "to": to_code, "amount": amount},
                    confidence=0.92,
                    raw_match=m_cs.group(0),
                ))

    # 3. Brasil (CEP, CNPJ, DDD, Feriados)
    m_cep = _RE_CEP.search(text) or _RE_CEP_SOLO.search(text)
    if m_cep:
        intents.append(ToolIntent(
            family="brasil",
            action="cep",
            params={"type": "cep", "value": m_cep.group(1)},
            confidence=0.95,
            raw_match=m_cep.group(0),
        ))

    m_cnpj = _RE_CNPJ.search(text)
    if m_cnpj:
        intents.append(ToolIntent(
            family="brasil",
            action="cnpj",
            params={"type": "cnpj", "value": m_cnpj.group(1)},
            confidence=0.95,
            raw_match=m_cnpj.group(0),
        ))

    m_ddd = _RE_DDD.search(text)
    if m_ddd:
        intents.append(ToolIntent(
            family="brasil",
            action="ddd",
            params={"type": "ddd", "value": m_ddd.group(1)},
            confidence=0.88,
            raw_match=m_ddd.group(0),
        ))

    m_fer = _RE_FERIADOS.search(text)
    if m_fer:
        intents.append(ToolIntent(
            family="brasil",
            action="holidays",
            params={"type": "feriados", "year": int(m_fer.group(1))},
            confidence=0.92,
            raw_match=m_fer.group(0),
        ))

    # 4. News
    m_news = _RE_NEWS.search(text) or _RE_WHATS_HAPPENING.search(text)
    if m_news:
        topic = m_news.group(1).strip()
        if len(topic) >= 2:
            intents.append(ToolIntent(
                family="news",
                action="search",
                params={"query": topic, "max_results": 3},
                confidence=0.85,
                raw_match=m_news.group(0),
            ))

    # 5. Translation
    m_tr = _RE_TRANSLATE.search(text)
    if m_tr:
        content_to_tr = m_tr.group(1).strip()
        target_lang = _normalize_lang_code(m_tr.group(2))
        if len(content_to_tr) >= 2:
            intents.append(ToolIntent(
                family="translation",
                action="translate",
                params={"text": content_to_tr, "target": target_lang},
                confidence=0.9,
                raw_match=m_tr.group(0),
            ))

    # 6. Fun
    if _RE_FUN_JOKE.search(text):
        intents.append(ToolIntent(
            family="fun",
            action="joke",
            params={"type": "joke"},
            confidence=0.85,
            raw_match="piada",
        ))
    elif _RE_FUN_FACT.search(text):
        intents.append(ToolIntent(
            family="fun",
            action="fact",
            params={"type": "fact"},
            confidence=0.85,
            raw_match="curiosidade",
        ))

    # 7. Knowledge (Wikipedia) — se não pegou clima, câmbio, brasil, notícias
    if not intents:
        m_wiki = _RE_WIKI.search(text)
        if m_wiki:
            query = m_wiki.group(1).strip()
            if len(query) >= 2:
                intents.append(ToolIntent(
                    family="knowledge",
                    action="search",
                    params={"query": query},
                    confidence=0.9,
                    raw_match=m_wiki.group(0),
                ))
        else:
            m_know = _RE_WHO_WHAT.search(text) or _RE_TELL_ABOUT.search(text)
            if m_know:
                query = m_know.group(1).strip().strip("'\"?")
                # Ignora pronomes ou saudações comuns
                if len(query) >= 3 and query.lower() not in ("você", "voce", "ele", "ela", "isso", "aquilo"):
                    intents.append(ToolIntent(
                        family="knowledge",
                        action="search",
                        params={"query": query},
                        confidence=0.82,
                        raw_match=m_know.group(0),
                    ))

    # Ordena por confiança decrescente
    intents.sort(key=lambda i: i.confidence, reverse=True)
    return intents
