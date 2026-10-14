"""Detector de interesse genuíno — Fase 1 do Assistente Proativo.

Dois estágios, do mais barato para o mais caro:

1. :func:`gate` — **porteiro léxico** (estágio 1). Função pura, síncrona,
   sem I/O, < 1 ms. Reprova rapidamente a maioria das mensagens que nunca
   deveriam gerar pesquisa proativa (curtas, código, perguntas diretas,
   pedidos explícitos de busca, só emoção sem assunto, assunto sem emoção,
   desabafos sensíveis, turnos que já usaram web search).
2. :func:`classify` — **classificador com modelo utilitário** (estágio 2).
   Pede JSON estrito a um modelo pequeno e devolve :class:`InterestSignal`.
   Qualquer falha (timeout, erro do provedor, JSON inválido) resulta em
   ``interest = 0`` — *fail-closed*: na dúvida, não incomoda o usuário.
3. :func:`evaluate` — regras pós-classificação (pessoa privada nunca,
   threshold por sensibilidade, categoria pesquisável, query de fallback).

Este módulo não conhece banco, WebSocket nem conversa: recebe texto e um
provedor já resolvido. A integração com ``_process_turn`` é da Fase 2.
"""
from __future__ import annotations

import asyncio
import json
import re
import time
import unicodedata
from dataclasses import asdict, dataclass, field
from datetime import datetime
from typing import Any, Iterable, Literal, Optional, Sequence

from backend.logging_config import get_logger

logger = get_logger(__name__)

# ─────────────────────────────────────────────────────────────────────────────
# Tipos e constantes públicas
# ─────────────────────────────────────────────────────────────────────────────

EntityType = Literal[
    "public_figure", "event", "product", "place", "organization", "private_person", "other"
]
Category = Literal["event", "news", "product", "place", "other"]

ENTITY_TYPES: tuple[str, ...] = (
    "public_figure", "event", "product", "place", "organization", "private_person", "other",
)
CATEGORIES: tuple[str, ...] = ("event", "news", "product", "place", "other")
RESEARCHABLE_CATEGORIES: frozenset[str] = frozenset({"event", "news", "product", "place"})
LANGUAGES: tuple[str, ...] = ("pt-BR", "en-US", "es-ES")

#: Threshold de ``interest`` por sensibilidade do usuário (F1.2.7).
SENSITIVITY_THRESHOLDS: dict[str, float] = {"low": 0.8, "medium": 0.7, "high": 0.6}
DEFAULT_SENSITIVITY = "medium"

#: Chaves em ``meta`` que permitem ao admin fixar um modelo dedicado (F4).
DETECTOR_META_KEYS: tuple[str, str] = (
    "proactive_detector_provider_id",
    "proactive_detector_model_id",
)

MIN_MESSAGE_CHARS = 25
MAX_ANALYSIS_CHARS = 2000          # o porteiro só olha o começo de colagens enormes
MAX_CONTEXT_MESSAGES = 3           # F1.2.2: nunca o histórico inteiro
MAX_CONTEXT_CHARS = 600
MAX_QUERY_CHARS = 120
CLASSIFIER_MAX_TOKENS = 300

# Motivos de reprovação do porteiro (strings estáveis — usadas em métricas/logs)
REASON_PASSED = "passed"
REASON_WEB_SEARCH_USED = "web_search_used"
REASON_TOO_SHORT = "too_short"
REASON_CODE = "code_or_paste"
REASON_SEARCH_REQUEST = "explicit_search_request"
REASON_DIRECT_QUESTION = "direct_question"
REASON_SENSITIVE = "sensitive_topic"
REASON_NO_EMOTION = "no_emotion"
REASON_NO_ENTITY = "no_entity"


@dataclass
class GateResult:
    """Saída do porteiro léxico (F1.1.1)."""

    passed: bool
    reason: str
    emotion_hits: list[str] = field(default_factory=list)
    entity_candidates: list[str] = field(default_factory=list)
    language: str = "unknown"   # pt-BR | en-US | es-ES | unknown (heurística)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class InterestSignal:
    """Saída do classificador (F1.2.1). ``interest == 0`` significa "não"."""

    interest: float = 0.0
    topic: str = ""
    entities: list[str] = field(default_factory=list)
    entity_type: str = "other"
    category: str = "other"
    suggested_query: str = ""
    time_sensitive: bool = False
    emotion: str = "neutral"
    language: str = "unknown"
    reason: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class ClassifyMeta:
    """Telemetria de uma chamada ao classificador (usada pela avaliação F1.4)."""

    latency_ms: float = 0.0
    prompt_chars: int = 0
    response_chars: int = 0
    raw: str = ""
    error: str = ""

    @property
    def est_tokens(self) -> int:
        # Estimativa grosseira (≈ 4 chars/token); providers em streaming não devolvem usage.
        return (self.prompt_chars + self.response_chars) // 4


@dataclass
class Decision:
    """Resultado das regras pós-classificação (F1.2.6)."""

    accepted: bool
    reason: str
    threshold: float
    signal: InterestSignal

    def to_dict(self) -> dict[str, Any]:
        return {
            "accepted": self.accepted,
            "reason": self.reason,
            "threshold": self.threshold,
            "signal": self.signal.to_dict(),
        }


# ─────────────────────────────────────────────────────────────────────────────
# Normalização
# ─────────────────────────────────────────────────────────────────────────────

_COMBINING_MARKS = re.compile(r"[\u0300-\u036f]")
_WS = re.compile(r"\s+")


def normalize(text: str) -> str:
    """Minúsculas, sem acentos, espaços colapsados (``"Tô ANIMADO"`` → ``"to animado"``)."""
    text = unicodedata.normalize("NFKD", text or "")
    text = _COMBINING_MARKS.sub("", text)
    return _WS.sub(" ", text).strip().lower()


# ─────────────────────────────────────────────────────────────────────────────
# Léxicos (acentos removidos — sempre casados contra ``normalize(text)``)
# ─────────────────────────────────────────────────────────────────────────────

_EMOTION_PT = [
    r"animad[oa]s?", r"animadissim[oa]s?", r"empolgad[oa]s?", r"empolgadissim[oa]s?",
    r"ansios[oa]s?", r"nao vejo a hora", r"mal posso esperar", r"mal consigo esperar",
    r"nao aguento (mais )?esperar", r"contando (as|os) (horas|dias)",
    r"louc[oa]s? (pra|para|por)", r"doid[oa]s? (pra|para|por)",
    r"quero (muito|demais|tanto)", r"queria (muito|demais|tanto)", r"quero ir", r"queria ir",
    r"preciso ir", r"tenho que ir", r"vou com certeza", r"nao posso perder", r"imperdivel",
    r"(to|tou|estou) pensando em ir", r"pensando em ir", r"bora\b", r"partiu\b",
    r"adorei", r"ador[oa]\b", r"amei", r"\bam[oa]\b", r"amando", r"apaixonad[oa]s?",
    r"curios[oa]s?", r"curiosidade", r"interessad[oa]s?", r"interessante demais",
    r"incrive(l|is)", r"\bdemais\b", r"muito louc[oa]", r"que louc(o|ura)", r"sensacional",
    r"fantastic[oa]", r"maravilh\w*", r"perfeit[oa]", r"que top", r"top demais", r"muito top",
    r"\bmassa\b", r"show de bola", r"\bdahora\b", r"\bda hora\b", r"irad[oa]", r"brab[oa]\b",
    r"insan[oa]", r"absurd[oa]", r"\bfoda\b", r"legal demais", r"m[oó] legal", r"muito legal",
    r"\bnossa\b", r"caramba", r"caraca", r"\buau\b", r"\bwow\b", r"\bserio\b", r"mentira\b",
    r"nao acredito", r"nao to acreditando", r"finalmente", r"ate que enfim",
    r"preocupad[oa]s?", r"assustad[oa]s?", r"chocad[oa]s?", r"chatead[oa]s?", r"\btriste\b",
    r"fiquei sabendo", r"soube que", r"\bvi que\b", r"ouvi (dizer|falar)", r"descobri (que|um|uma)",
    r"\bli que\b", r"\bsonho\b", r"sonhando", r"vontade\b", r"tentad[oa]s?",
    r"\bhype\b", r"hypad[oa]", r"surtand[oa]", r"surtei", r"gritei", r"chorand[oa]", r"chorei",
    r"orgulho", r"\bfeliz\b", r"felicidade", r"emocionad[oa]s?", r"emocionante", r"pirar\b",
    r"saudade", r"ai meu deus", r"meu deus", r"\bufa\b", r"que maravilha", r"que lindo",
]

_EMOTION_EN = [
    r"excited", r"exciting", r"can'?t wait", r"cannot wait", r"stoked", r"pumped", r"hyped",
    r"\bhype\b", r"psyched", r"thrilled", r"\blove(d)?\b", r"awesome", r"amazing", r"incredible",
    r"unbelievable", r"\bomg\b", r"oh my (god|gosh)", r"\bwow\b", r"no way", r"seriously",
    r"for real", r"curious", r"interested", r"wonder(ing)? (if|when|where)", r"dying to",
    r"so cool", r"insane", r"crazy", r"finally", r"worried", r"shocked", r"heard (that|about|the)",
    r"saw that", r"found out", r"just learned", r"learned that", r"read that", r"can'?t believe",
    r"\bdream\b", r"gotta go", r"need to (go|be there|see)", r"wanna go", r"want to go",
    r"thinking (of|about) (going|getting|buying|visiting)", r"count me in", r"let'?s go",
    r"obsessed", r"blown away", r"mind blown", r"hooked", r"in love", r"so happy", r"\bproud\b",
    r"bummed", r"gutted", r"\bwoah\b", r"\bwhoa\b", r"\byay\b", r"woohoo", r"i need (this|that|it)",
]

_EMOTION_ES = [
    r"emocionad[oa]s?", r"emocionadisim[oa]s?", r"ilusionad[oa]s?", r"entusiasmad[oa]s?",
    r"no veo la hora", r"no puedo esperar", r"me muero (por|de ganas)", r"muero de ganas",
    r"me encant[ao]", r"me flipa", r"flipando", r"\bflipo\b", r"increible", r"\bgenial\b",
    r"\bbrutal\b", r"una pasada", r"que guay", r"chevere", r"\bchido\b", r"padrisim[oa]",
    r"\bbacan[oa]?\b", r"madre mia", r"en serio", r"no me lo creo", r"no lo puedo creer",
    r"curios[oa]s?", r"curiosidad", r"interesad[oa]s?", r"\bojala\b", r"quiero ir", r"quisiera ir",
    r"tengo que ir", r"hay que ir", r"me entere", r"supe que", r"escuche que", r"lei que",
    r"por fin", r"preocupad[oa]s?", r"impresionante", r"espectacular", r"que ilusion",
    r"que emocion", r"que ganas", r"tengo (muchas )?ganas", r"alucinante", r"me vuelve loc[oa]",
    r"locura", r"que fuerte", r"\bguau\b", r"dios mio", r"sorprendid[oa]s?", r"orgullos[oa]s?",
    r"enamor[ea]\w*", r"me gusta muchisimo", r"\bvamos\b",
]

# Sinais universais (pontuação enfática, risadas, emojis)
_EMOTION_UNIVERSAL = [
    (re.compile(r"!{2,}"), "!!"),
    (re.compile(r"\?!|!\?"), "?!"),
    (re.compile(r"\b(k{3,}|haha\w*|jaja\w*|rsrs\w*|lol|lmao)\b"), "laugh"),
]
_EMOJI_HITS = "🤩😍🔥🎉😱🥳😭❤️🙌👏😳🤯😲🥹💜💖✨🎶🎸🎤🙏😁😆🤗👀💥🚀😊🥰😢💃🕺🍻"
_EMOJI_RE = re.compile("[" + re.escape(_EMOJI_HITS.replace("❤️", "❤")) + "]")


def _compile_lexicon(patterns: Iterable[str]) -> re.Pattern[str]:
    # Cada entrada já cuida das próprias bordas quando necessário; para as
    # demais, exigimos início de palavra (evita "animado" dentro de "reanimado").
    parts = []
    for p in patterns:
        if p.startswith(r"\b") or p.startswith("("):
            parts.append(p)
        else:
            parts.append(r"\b" + p)
    return re.compile("|".join(f"(?:{p})" for p in parts))


_LEXICONS: dict[str, re.Pattern[str]] = {
    "pt-BR": _compile_lexicon(_EMOTION_PT),
    "en-US": _compile_lexicon(_EMOTION_EN),
    "es-ES": _compile_lexicon(_EMOTION_ES),
}

# ── Detecção de idioma (stopwords distintivas) ───────────────────────────────
_STOP_PT = frozenset("""
nao voce vc pra pro to tou estou muito com vai vou isso tambem ja ele ela do da dos das um uma
em eu mas que meu minha fiquei sabendo demais hoje amanha ontem aqui gente mano cara tô
""".split())
_STOP_EN = frozenset("""
the and is to it that of in for so this my be are was on with at go going just we you i'm im
can't cant i've ive there here today tomorrow about from they them he she
""".split())
_STOP_ES = frozenset("""
y el los las muy voy es esta pero ya lo se del al yo mi con para que este esta hoy manana ayer
aqui tengo quiero estoy tambien porque pero una un ella ellos
""".split())
_SHARED_PT_ES = frozenset({"que", "de", "no", "en", "para", "con", "una", "un", "aqui"})


def detect_language(text: str) -> str:
    """Heurística barata por stopwords: ``pt-BR`` | ``en-US`` | ``es-ES`` | ``unknown``."""
    tokens = re.findall(r"[a-z']+", normalize(text))
    if not tokens:
        return "unknown"
    scores = {"pt-BR": 0.0, "en-US": 0.0, "es-ES": 0.0}
    for tok in tokens:
        if tok in _SHARED_PT_ES:
            scores["pt-BR"] += 0.5
            scores["es-ES"] += 0.5
            continue
        if tok in _STOP_PT:
            scores["pt-BR"] += 1
        if tok in _STOP_EN:
            scores["en-US"] += 1
        if tok in _STOP_ES:
            scores["es-ES"] += 1
    # Marcas ortográficas fortes no texto original
    raw = text or ""
    if re.search(r"[ãõ]|ção|ções|lh[aeiou]", raw.lower()):
        scores["pt-BR"] += 2
    if re.search(r"[¿¡]|ñ", raw):
        scores["es-ES"] += 2
    best = max(scores, key=scores.get)
    if scores[best] <= 0:
        return "unknown"
    # Empate → prefere pt-BR (idioma principal do produto)
    tied = [lang for lang, s in scores.items() if s == scores[best]]
    if len(tied) > 1:
        return "pt-BR" if "pt-BR" in tied else tied[0]
    return best


# ── Pergunta direta / pedido de pesquisa / código / sensível ─────────────────
_INTERROGATIVE_START = re.compile(
    r"(^[¿¡\s]*|[.!?¿]\s*)(qual|quais|como|quando|onde|aonde|quem|quanto|quantos|quantas|por que|porque|"
    r"o que|oq|que horas|cade|what|when|where|who|how|which|why|cual|cuales|cuando|donde|quien|"
    r"cuanto|cuantos|cuantas)\b"
)
_IMPLICIT_ASK = re.compile(
    r"\b(me (diz|diga|fala|fale|conta|conte|explica|explique|mostra|mostre|lembra|lembre)|"
    r"(voce|vc|tu) sabe|sabe (se|quando|onde|qual|quem|como|quanto|me dizer)|"
    r"tell me|do you know|can you tell|dime|me dices|sabes (si|cuando|donde|cual|quien|como))\b"
)
_SEARCH_IMPERATIVE = re.compile(
    r"(^|[.!?;,]\s*)(pesquis[ae]|procur[ae]|busc[ae]|googl[ae]|search|find|look up|lookup|"
    r"investig[ae]|verifi(ca|que)|che(ca|que)|confere|confira|averigua|revisa)\b"
)
_SEARCH_DIRECTIVE = re.compile(
    r"\b(pesquis\w* (pra|para|sobre|isso|ai|aqui|na (internet|web)|no google)|"
    r"procur\w* (pra mim|ai|sobre|na (internet|web))|"
    r"busc\w* (pra mim|ai|sobre|na (internet|web)|no google|en (internet|la web|google)|informacion)|"
    r"d[ae] uma (pesquisada|procurada|buscada|olhada na (internet|web)|googlada)|"
    r"pode (pesquisar|procurar|buscar|verificar|checar|conferir|dar uma olhada)|"
    r"poderia (pesquisar|procurar|buscar|verificar|checar)|"
    r"consegue (pesquisar|procurar|buscar|achar|encontrar|verificar)|"
    r"me ajuda a (achar|encontrar|procurar|buscar)|faz uma (pesquisa|busca)|"
    r"search (for|the web|online|it|that|this|up)|look (it|that|this) up|"
    r"can you (search|find|look|check|google)|could you (search|find|look|check)|"
    r"google (it|that|this|for)|find out (if|when|where|what|whether)|check (if|when|whether|online)|"
    r"puedes (buscar|investigar|buscarme|averiguar|revisar)|podrias (buscar|investigar|averiguar)|"
    r"busca(me)? (en|sobre|por|informacion)|investiga (sobre|si|cuando))\b"
)
_CODE_TOKENS = re.compile(
    r"(```|\b(def|class|import|from|return|const|let|var|function|async|await|public|static|void|"
    r"select|insert|update|delete|where|order by|npm|pip|sudo|docker|traceback|exception|"
    r"typeerror|valueerror|nullpointerexception|undefined|console\.log|print\()\b|->|=>|==|!=|\w+\(\)|"
    r"\{|\}|;\s*$)"
)
_SYMBOLS = set("{}[]()<>=|\\/_$#@%^*~`+")
_SENSITIVE_ALT = (
    r"cancer|tumor|quimio\w*|diagnostic\w*|depress\w*|ansiedade|panico|suicid\w*|terapia|"
    r"terapeuta|psiquiatr\w*|psicolog\w*|remedio|medicamento|antidepressiv\w*|hospital|internad[oa]|"
    r"cirurgia|biopsia|gravid\w*|aborto|hiv|doenca|doente|demitid[oa]|desempregad[oa]|"
    r"divida|dividas|endividad[oa]|falencia|falid[oa]|despejo|divorcio|separacao|traicao|traiu|"
    r"morreu|faleceu|falecimento|velorio|enterro|luto|processo judicial|advogad[oa]|prisao|"
    r"pres[oa]|overdose|vicio|anxiety|panic attack\w*|therap\w*|chemo|surgery|pregnan\w*|"
    r"miscarriage|laid off|fired|unemployed|debts?|bankrupt\w*|eviction|divorce|cheated|"
    r"passed away|funeral|lawsuit|lawyer|arrested|rehab|depresion|ansiedad|cirugia|embaraz\w*|"
    r"despedid[oa]|desemplead[oa]|deuda\w*|quiebra|desahucio|engan[oa]\w*|fallecio|murio|"
    r"demanda judicial|abogad[oa]|detenid[oa]"
)
_SENSITIVE_TERMS = re.compile(rf"\b(?:{_SENSITIVE_ALT})\b")
_FIRST_PERSON_ALT = (
    r"eu|meu|minha|meus|minhas|me|mim|comigo|to|tou|estou|fui|fiquei|tenho|tive|sou|perdi|"
    r"i|i'm|im|my|mine|we|our|i've|ive|yo|mi|mis|estoy|tuve|soy|conmigo|nuestr[oa]"
)
# Termo sensível até 4 palavras DEPOIS de um marcador de primeira pessoa, na mesma frase:
# "minha mãe foi diagnosticada com câncer" ✓ · "fui demitido" ✓ · "o Ozzy morreu, era meu ídolo" ✗
_SENSITIVE_WINDOW = re.compile(
    rf"\b(?:{_FIRST_PERSON_ALT})\b(?:\s+[^\s.!?]+){{0,4}}?\s+(?:{_SENSITIVE_ALT})\b"
)

# ── Entidades ────────────────────────────────────────────────────────────────
_SENTENCE_SPLIT = re.compile(r"(?<=[.!?…])\s+|\n+")
_EDGE_PUNCT = ".,!?;:()[]{}\"'“”‘’«»…—–-"
_CONNECTORS = frozenset({"e", "&", "de", "da", "do", "das", "dos", "di", "del", "della", "y",
                         "and", "of", "the", "la", "le", "el", "los", "las", "van", "von", "em", "no", "na"})
_QUOTED = re.compile(r"[\"“«]([^\"”»]{2,60})[\"”»]")
_HASHTAG = re.compile(r"(?<!\w)#([A-Za-z0-9_À-ÿ]{2,40})")
_ALNUM_MIX = re.compile(r"^(?=.*[A-Za-z])(?=.*\d)[A-Za-z0-9][\w.+-]*$")   # GTA6, S26, RTX5090
_CAMEL = re.compile(r"^[a-z]+[A-Z]\w*$|^[A-Z][a-z]+[A-Z]\w*$")           # iPhone, PlayStation
_INTERJECTION_CAPS = frozenset({"KKK", "KKKK", "OMG", "LOL", "LMAO", "WTF", "AAA", "AAAA", "URGENTE",
                                "SIM", "NAO", "NÃO", "EU", "VC", "PQ", "TMJ", "SOS", "YES", "NO"})
_EVENT_VERBS = (
    "vem", "vai", "vao", "vão", "anunciou", "anuncia", "anunciaram", "lanca", "lança", "lancou", "lançou",
    "estreia", "estreou", "toca", "tocar", "tocam", "chega", "chegou", "abre", "abriu", "inaugura",
    "inaugurou", "sai", "saiu", "volta", "voltou", "ganhou", "venceu", "perdeu", "contratou", "renovou",
    "acontece", "rola", "rolar", "ter", "tem", "comes", "coming", "announced", "announces", "releases",
    "released", "drops", "dropped", "premieres", "opens", "opened", "won", "lost", "signed", "launches",
    "launched", "starts", "llega", "anuncio", "anunció", "lanza", "lanzo", "lanzó", "estrena", "estreno",
    "estrenó", "abrio", "abrió", "viene", "vuelve", "gano", "ganó", "perdio", "perdió", "ficho", "fichó",
    "sale", "empieza",
)
_EVENT_VERB_RE = re.compile(r"\b(" + "|".join(map(re.escape, _EVENT_VERBS)) + r")\b")
_EVENT_NOUNS = re.compile(
    r"\b(show|shows|festival|feira|exposicao|exposição|lancamento|lançamento|estreia|turne|turnê|"
    r"jogo|final|concerto|peca|peça|palestra|congresso|workshop|corrida|maratona|oktoberfest|"
    r"concert|gig|fair|premiere|match|game|conference|expo|tour|concierto|feria|estreno|partido|"
    r"festa|party|fiesta|balada|evento|event)\b"
)
_TEMPORAL = re.compile(
    r"\b(hoje|amanha|amanhã|ontem|fim de semana|fds|finde|sabado|sábado|domingo|segunda|terca|terça|"
    r"quarta|quinta|sexta|semana que vem|mes que vem|mês que vem|proxim[oa]|próxim[oa]|"
    r"janeiro|fevereiro|marco|março|abril|maio|junho|julho|agosto|setembro|outubro|novembro|dezembro|"
    r"tonight|today|tomorrow|this weekend|next (week|month|weekend)|monday|tuesday|wednesday|thursday|"
    r"friday|saturday|sunday|january|february|march|april|may|june|july|august|september|october|"
    r"november|december|hoy|manana|mañana|fin de semana|esta semana|la proxima|la próxima|enero|"
    r"febrero|marzo|mayo|junio|julio|septiembre|octubre|noviembre|diciembre|"
    r"\d{1,2}/\d{1,2}(/\d{2,4})?|dia \d{1,2}|\b20\d{2}\b)\b"
)
_SENTENCE_START_STOPLIST = frozenset(normalize(w) for w in """
eu nossa hoje ontem amanha amanhã serio sério caramba caraca vi ouvi fiquei soube descobri li que nao não
to tô tou estou acho meu minha meus minhas gente mano cara oi ola olá bom boa dia noite tarde ok obrigado
obrigada valeu beleza sim claro entao então mas porque pq tipo olha veja alias aliás enfim finalmente
mentira gostei adorei amei queria quero preciso tenho vou vamos bora partiu parece saiu vai ta tá sera será
i the just omg wow so my yo hoy ayer madre que qué no me ya vi estoy tengo quiero genial increible increíble
oh great awesome heard saw can't cant we our it this that there here when what why how where who
mañana manana ojala ojalá por fin dios uau top show mi mis nos nosso nossa dizem falaram alguem alguém
i'm im i've ive i'll i'd you're we're it's that's there's he's she's they're don't can't won't didn't isn't
monday tuesday wednesday thursday friday saturday sunday january february march april may june july august
september october november december o a os as um uma the an el la los las un una
""".split())
#: Tokens que nunca iniciam uma entidade (artigos/pronomes capitalizados no começo da frase)
_LEADING_STRIP = frozenset(normalize(w) for w in """
o a os as um uma the an el la los las un una i i'm eu nossa heard saw vi ouvi li soube descobri
omg lol lmao wtf kkk kkkk
""".split()) | _CONNECTORS
#: Tokens que nunca entram numa entidade, em posição alguma ("São Paulo I need" → "São Paulo")
_NEVER_ENTITY = frozenset(normalize(w) for w in """
i i'm i've i'll i'd omg lol lmao wtf kkk kkkk kkkkk haha hahaha
""".split())


def _clean_token(tok: str) -> str:
    return tok.strip(_EDGE_PUNCT)


def _is_capitalized(tok: str) -> bool:
    return bool(tok) and tok[0].isalpha() and tok[0].isupper()


def _is_acronym(tok: str) -> bool:
    letters = [c for c in tok if c.isalpha()]
    return len(letters) >= 2 and all(c.isupper() for c in letters) and tok.upper() not in _INTERJECTION_CAPS


def _is_strong_token(tok: str) -> bool:
    """Token que é entidade mesmo no início da frase (sigla, camelCase, letras+dígitos)."""
    return _is_acronym(tok) or bool(_CAMEL.match(tok)) or bool(_ALNUM_MIX.match(tok))


def extract_entity_candidates(text: str) -> list[str]:
    """Candidatos a entidade sem NLP pesado (F1.1.3). Ordem de aparição, sem repetição."""
    found: list[str] = []
    seen: set[str] = set()

    def add(candidate: str) -> None:
        candidate = candidate.strip(_EDGE_PUNCT + " ")
        if len(candidate) < 2:
            return
        key = normalize(candidate)
        if key and key not in seen:
            seen.add(key)
            found.append(candidate)

    text = (text or "")[:MAX_ANALYSIS_CHARS]

    for m in _QUOTED.finditer(text):
        add(m.group(1))
    for m in _HASHTAG.finditer(text):
        add("#" + m.group(1))

    for sentence in _SENTENCE_SPLIT.split(text):
        tokens = [t for t in sentence.split() if t]
        n = len(tokens)
        i = 0
        while i < n:
            tok = _clean_token(tokens[i])
            if not tok:
                i += 1
                continue
            at_start = i == 0
            if (_is_capitalized(tok) or _is_strong_token(tok)) and normalize(tok) not in _NEVER_ENTITY:
                run = [tok]
                j = i + 1
                while j < n:
                    nxt = _clean_token(tokens[j])
                    if not nxt or normalize(nxt) in _NEVER_ENTITY:
                        break
                    if _is_capitalized(nxt) or _is_strong_token(nxt):
                        run.append(nxt)
                    elif normalize(nxt) in _CONNECTORS and j + 1 < n and (
                        _is_capitalized(_clean_token(tokens[j + 1])) or _is_strong_token(_clean_token(tokens[j + 1]))
                    ):
                        run.append(nxt)
                    elif nxt.isdigit() and len(nxt) <= 4 and len(run) >= 1:
                        run.append(nxt)   # "iPhone 17", "Switch 2", "Copa 2026"
                        j += 1
                        break
                    else:
                        break
                    j += 1
                # Fecha a sequência sem conector pendurado ("Coldplay e" → "Coldplay")
                while run and normalize(run[-1]) in _CONNECTORS:
                    run.pop()
                # Remove artigos/pronomes capitalizados na frente ("O iPhone 17" → "iPhone 17",
                # "Heard the Bluesfest" → "Bluesfest"); o que sobra deixa de contar como início.
                stripped_leading = False
                while run and len(run) > 1 and normalize(run[0]) in _LEADING_STRIP and not _is_strong_token(run[0]):
                    run.pop(0)
                    stripped_leading = True
                if stripped_leading:
                    at_start = False
                accept = False
                if len(run) >= 2:
                    accept = True
                elif run:
                    single = run[0]
                    if not at_start:
                        accept = normalize(single) not in _SENTENCE_START_STOPLIST or _is_strong_token(single)
                    elif _is_strong_token(single):
                        accept = True
                    elif normalize(single) not in _SENTENCE_START_STOPLIST:
                        # Início de frase: aceita se um verbo de evento vier logo depois
                        # ("Coldplay anunciou…") ou se a frase for só esse nome ("Coldplay!!!").
                        tail = " ".join(normalize(_clean_token(t)) for t in tokens[i + 1:i + 4])
                        accept = bool(_EVENT_VERB_RE.search(tail)) or (n == 1 and len(single) >= 4)
                if accept and run:
                    add(" ".join(run))
                i = max(j, i + 1)
            else:
                i += 1

        # Evento genérico/data perto de verbo de evento (sem maiúsculas: "vai ter festival ... mês que vem")
        norm_sentence = normalize(sentence)
        temporal = _TEMPORAL.search(norm_sentence) or _TEMPORAL.search(sentence.lower())
        if temporal:
            verb = _EVENT_VERB_RE.search(norm_sentence)
            noun = _EVENT_NOUNS.search(norm_sentence)
            if noun and (verb or temporal):
                add(f"{noun.group(1)} · {temporal.group(0).strip()}")
            elif verb:
                add(f"{verb.group(1)} … {temporal.group(0).strip()}")

    return found[:12]


def find_emotion_hits(text: str) -> list[str]:
    """Marcadores de emoção/interesse encontrados (nos três léxicos + universais)."""
    norm = normalize(text[:MAX_ANALYSIS_CHARS])
    hits: list[str] = []
    seen: set[str] = set()
    for lexicon in _LEXICONS.values():
        for m in lexicon.finditer(norm):
            hit = m.group(0).strip()
            if hit and hit not in seen:
                seen.add(hit)
                hits.append(hit)
    for pattern, label in _EMOTION_UNIVERSAL:
        if pattern.search(norm) and label not in seen:
            seen.add(label)
            hits.append(label)
    emojis = _EMOJI_RE.findall(text[:MAX_ANALYSIS_CHARS])
    if emojis:
        hits.append("emoji:" + "".join(dict.fromkeys(emojis))[:6])
    return hits


def _looks_like_code(text: str, norm: str) -> bool:
    if "```" in text:
        return True
    compact = [c for c in text if not c.isspace()]
    if compact:
        symbol_ratio = sum(1 for c in compact if c in _SYMBOLS) / len(compact)
        if symbol_ratio >= 0.4:
            return True
    code_hits = len(_CODE_TOKENS.findall(norm))
    if code_hits >= 2:
        return True
    # Mensagem que é só URL(s)
    stripped = re.sub(r"https?://\S+", "", text).strip()
    if text.strip() and len(stripped) < 10 and "http" in text:
        return True
    return False


def _is_direct_question(norm: str) -> bool:
    if "?" in norm and _INTERROGATIVE_START.search(norm):
        return True
    return bool(_IMPLICIT_ASK.search(norm))


def _is_search_request(norm: str) -> bool:
    return bool(_SEARCH_DIRECTIVE.search(norm) or _SEARCH_IMPERATIVE.search(norm))


def _is_sensitive_personal(norm: str) -> bool:
    """Termo sensível na MESMA frase de um marcador de primeira pessoa.

    "Minha mãe foi diagnosticada com câncer" → sensível (não pesquisar).
    "O Flamengo demitiu o técnico!!" → não (é notícia, sem primeira pessoa).
    """
    for sentence in re.split(r"(?<=[.!?…])\s+|\n+", norm):
        if _SENSITIVE_TERMS.search(sentence) and _SENSITIVE_WINDOW.search(sentence):
            return True
    return False


# ─────────────────────────────────────────────────────────────────────────────
# Estágio 1 — porteiro
# ─────────────────────────────────────────────────────────────────────────────

def gate(message: str, *, web_search_used: bool = False) -> GateResult:
    """Porteiro léxico (F1.1.5): puro, síncrono, sem I/O, < 1 ms.

    Regras, na ordem (a primeira que reprovar define ``reason``):

    1. ``web_search_used`` — o turno já pesquisou; proatividade seria redundante.
    2. ``too_short`` — menos de 25 caracteres.
    3. ``code_or_paste`` — blocos de código, ≥ 40 % de símbolos, tokens de código, só URL.
    4. ``explicit_search_request`` — "pesquisa pra mim…" é busca web normal.
    5. ``sensitive_topic`` — saúde/finanças/luto em primeira pessoa (nunca pesquisar).
    6. ``direct_question`` — pergunta à IA sem emoção (será respondida normalmente).
    7. ``no_emotion`` — nenhum marcador de emoção/interesse.
    8. ``no_entity`` — emoção sem nenhum assunto identificável.
    """
    text = (message or "")
    if web_search_used:
        return GateResult(False, REASON_WEB_SEARCH_USED)

    stripped = text.strip()
    if len(stripped) < MIN_MESSAGE_CHARS:
        return GateResult(False, REASON_TOO_SHORT)

    text = stripped[:MAX_ANALYSIS_CHARS]
    norm = normalize(text)
    language = detect_language(text)

    if _looks_like_code(text, norm):
        return GateResult(False, REASON_CODE, language=language)
    if _is_search_request(norm):
        return GateResult(False, REASON_SEARCH_REQUEST, language=language)
    if _is_sensitive_personal(norm):
        return GateResult(False, REASON_SENSITIVE, language=language)

    emotion_hits = find_emotion_hits(text)
    if not emotion_hits and _is_direct_question(norm):
        return GateResult(False, REASON_DIRECT_QUESTION, language=language)
    if not emotion_hits:
        return GateResult(False, REASON_NO_EMOTION, language=language)

    entities = extract_entity_candidates(text)
    if not entities:
        return GateResult(False, REASON_NO_ENTITY, emotion_hits=emotion_hits, language=language)

    return GateResult(True, REASON_PASSED, emotion_hits=emotion_hits,
                      entity_candidates=entities, language=language)


# ─────────────────────────────────────────────────────────────────────────────
# Estágio 2 — classificador
# ─────────────────────────────────────────────────────────────────────────────

_THINK_BLOCK = re.compile(r"<think>.*?</think>", re.S)
_FENCE = re.compile(r"```(?:json)?\s*(.*?)```", re.S)
_LANG_ALIASES = {
    "pt": "pt-BR", "pt-br": "pt-BR", "pt_br": "pt-BR", "ptbr": "pt-BR", "portuguese": "pt-BR",
    "portugues": "pt-BR", "português": "pt-BR", "brazilian portuguese": "pt-BR",
    "en": "en-US", "en-us": "en-US", "en_us": "en-US", "en-gb": "en-US", "english": "en-US",
    "es": "es-ES", "es-es": "es-ES", "es_es": "es-ES", "es-mx": "es-ES", "es-ar": "es-ES",
    "spanish": "es-ES", "espanol": "es-ES", "español": "es-ES", "castellano": "es-ES",
}


def normalize_language(value: Any, default: str = "unknown") -> str:
    if not isinstance(value, str) or not value.strip():
        return default
    key = value.strip().lower()
    if key in _LANG_ALIASES:
        return _LANG_ALIASES[key]
    for lang in LANGUAGES:
        if key == lang.lower():
            return lang
    return _LANG_ALIASES.get(key.split("-")[0], default)


def _slice_first_json_object(text: str) -> Optional[str]:
    """Primeiro ``{...}`` balanceado (ignora chaves dentro de strings)."""
    start = text.find("{")
    while start != -1:
        depth = 0
        in_str = False
        escape = False
        for idx in range(start, len(text)):
            ch = text[idx]
            if in_str:
                if escape:
                    escape = False
                elif ch == "\\":
                    escape = True
                elif ch == '"':
                    in_str = False
                continue
            if ch == '"':
                in_str = True
            elif ch == "{":
                depth += 1
            elif ch == "}":
                depth -= 1
                if depth == 0:
                    return text[start:idx + 1]
        start = text.find("{", start + 1)
    return None


def _as_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return value != 0
    if isinstance(value, str):
        return value.strip().lower() in {"true", "yes", "sim", "si", "sí", "1", "y"}
    return False


def _as_str(value: Any, limit: int) -> str:
    if value is None:
        return ""
    if not isinstance(value, str):
        value = str(value)
    return _WS.sub(" ", value).strip()[:limit]


def _as_entities(value: Any) -> list[str]:
    if isinstance(value, str):
        value = [part for part in re.split(r"[,;|]", value)]
    if not isinstance(value, (list, tuple)):
        return []
    out: list[str] = []
    for item in value:
        text = _as_str(item if not isinstance(item, dict) else item.get("name", ""), 80)
        if text and text.lower() not in {x.lower() for x in out}:
            out.append(text)
        if len(out) >= 10:
            break
    return out


def parse_interest_signal(raw: str) -> InterestSignal:
    """Parser tolerante (F1.2.3): primeiro ``{...}`` da resposta, validado campo a campo.

    Qualquer falha ⇒ ``interest = 0`` e ``reason = "parse_error:<motivo>"`` (fail-closed).
    """
    text = raw or ""
    text = _THINK_BLOCK.sub("", text)
    fence = _FENCE.search(text)
    if fence and "{" in fence.group(1):
        text = fence.group(1)
    blob = _slice_first_json_object(text)
    if not blob:
        logger.debug("[Proactive] classificador sem JSON: %r", raw[:200] if raw else raw)
        return InterestSignal(interest=0.0, reason="parse_error:no_json")
    try:
        data = json.loads(blob)
    except Exception:
        # Tolerância mínima: vírgula sobrando antes de fechar
        try:
            data = json.loads(re.sub(r",\s*([}\]])", r"\1", blob))
        except Exception:
            logger.debug("[Proactive] JSON inválido do classificador: %r", blob[:200])
            return InterestSignal(interest=0.0, reason="parse_error:invalid_json")
    if not isinstance(data, dict):
        return InterestSignal(interest=0.0, reason="parse_error:not_object")

    raw_interest = data.get("interest")
    try:
        interest = float(raw_interest)
    except (TypeError, ValueError):
        return InterestSignal(interest=0.0, reason="parse_error:interest")
    if interest != interest:  # NaN
        return InterestSignal(interest=0.0, reason="parse_error:interest")
    if interest >= 10.0:
        interest = interest / 100.0   # modelo respondeu em porcentagem ("85")
    elif interest > 1.0:
        interest = interest / 10.0    # modelo respondeu numa escala de 0 a 10 ("7")
    interest = min(1.0, max(0.0, interest))

    entity_type = _as_str(data.get("entity_type"), 40).lower().replace(" ", "_")
    if entity_type not in ENTITY_TYPES:
        entity_type = "other"
    category = _as_str(data.get("category"), 40).lower()
    if category not in CATEGORIES:
        category = "other"

    return InterestSignal(
        interest=round(interest, 3),
        topic=_as_str(data.get("topic"), 120),
        entities=_as_entities(data.get("entities")),
        entity_type=entity_type,
        category=category,
        suggested_query=_as_str(data.get("suggested_query"), 160),
        time_sensitive=_as_bool(data.get("time_sensitive")),
        emotion=_as_str(data.get("emotion"), 40).lower() or "neutral",
        language=normalize_language(data.get("language")),
        reason=_as_str(data.get("reason"), 200),
    )


def _message_text(content: Any) -> str:
    """Extrai texto de conteúdo string ou multimodal (lista de partes)."""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return " ".join(
            str(p.get("text", "")) for p in content if isinstance(p, dict) and p.get("type") == "text"
        )
    return "" if content is None else str(content)


def build_classifier_messages(
    message: str,
    context_msgs: Optional[Sequence[Any]] = None,
    *,
    language_hint: Optional[str] = None,
    now: Optional[datetime] = None,
) -> list[dict[str, str]]:
    """Monta as mensagens do classificador (F1.2.2).

    ``context_msgs``: dicts ``{"role", "content"}`` (ou tuplas ``(role, content)``),
    do mais antigo para o mais novo. Só as **3 últimas** entram, truncadas a 600 chars.
    """
    from backend.proactive.prompts import CLASSIFIER_SYSTEM_PROMPT, render_classifier_user_prompt

    context_lines: list[str] = []
    for item in list(context_msgs or [])[-MAX_CONTEXT_MESSAGES:]:
        if isinstance(item, dict):
            role, content = item.get("role", "user"), item.get("content", "")
        else:
            role, content = item[0], item[1]
        text = _WS.sub(" ", _message_text(content)).strip()
        if not text:
            continue
        if len(text) > MAX_CONTEXT_CHARS:
            text = text[:MAX_CONTEXT_CHARS].rstrip() + "…"
        context_lines.append(f"{str(role).upper()}: {text}")

    user_prompt = render_classifier_user_prompt(
        message=(message or "").strip()[:MAX_ANALYSIS_CHARS],
        context_block="\n".join(context_lines) if context_lines else "(none)",
        today=(now or datetime.now()).strftime("%Y-%m-%d"),
        language_hint=language_hint or "unknown",
    )
    return [
        {"role": "system", "content": CLASSIFIER_SYSTEM_PROMPT},
        {"role": "user", "content": user_prompt},
    ]


async def classify_with_meta(
    message: str,
    context_msgs: Optional[Sequence[Any]] = None,
    *,
    provider: Any,
    model_name: str,
    timeout: float = 8.0,
    language_hint: Optional[str] = None,
    max_tokens: int = CLASSIFIER_MAX_TOKENS,
    now: Optional[datetime] = None,
) -> tuple[InterestSignal, ClassifyMeta]:
    """Igual a :func:`classify`, mas devolve também telemetria (latência, chars, bruto)."""
    messages = build_classifier_messages(message, context_msgs, language_hint=language_hint, now=now)
    meta = ClassifyMeta(prompt_chars=sum(len(m["content"]) for m in messages))
    chunks: list[str] = []

    async def _collect() -> None:
        async for token in provider.stream_chat(
            model=model_name, messages=messages, temperature=0.0, max_tokens=max_tokens
        ):
            chunks.append(str(token))

    started = time.perf_counter()
    try:
        await asyncio.wait_for(_collect(), timeout=timeout)
    except asyncio.TimeoutError:
        meta.latency_ms = (time.perf_counter() - started) * 1000
        meta.error = "timeout"
        meta.raw = "".join(chunks)
        return InterestSignal(interest=0.0, language=language_hint or "unknown", reason="timeout"), meta
    except Exception as exc:  # fail-closed: provedor fora, chave inválida, 429...
        meta.latency_ms = (time.perf_counter() - started) * 1000
        meta.error = f"provider_error:{type(exc).__name__}"
        meta.raw = "".join(chunks)
        logger.debug("[Proactive] erro do provedor no classificador: %s", exc)
        return InterestSignal(interest=0.0, language=language_hint or "unknown", reason=meta.error), meta

    meta.latency_ms = (time.perf_counter() - started) * 1000
    meta.raw = "".join(chunks)
    meta.response_chars = len(meta.raw)
    signal = parse_interest_signal(meta.raw)
    if signal.language == "unknown" and language_hint:
        signal.language = normalize_language(language_hint)
    if signal.reason.startswith("parse_error"):
        meta.error = signal.reason
    return signal, meta


async def classify(
    message: str,
    context_msgs: Optional[Sequence[Any]] = None,
    *,
    provider: Any,
    model_name: str,
    timeout: float = 8.0,
    language_hint: Optional[str] = None,
    max_tokens: int = CLASSIFIER_MAX_TOKENS,
) -> InterestSignal:
    """Classificador (F1.2.5): ``stream_chat`` com ``temperature=0`` e ``max_tokens≈300``.

    Nunca levanta exceção: timeout, erro de provedor ou JSON inválido viram
    ``InterestSignal(interest=0, reason=...)``.
    """
    signal, _meta = await classify_with_meta(
        message, context_msgs, provider=provider, model_name=model_name,
        timeout=timeout, language_hint=language_hint, max_tokens=max_tokens,
    )
    return signal


# ─────────────────────────────────────────────────────────────────────────────
# Regras pós-classificação
# ─────────────────────────────────────────────────────────────────────────────

def threshold_for(sensitivity: Optional[str]) -> float:
    """``low=0.8``, ``medium=0.7`` (padrão), ``high=0.6`` (F1.2.7)."""
    return SENSITIVITY_THRESHOLDS.get((sensitivity or DEFAULT_SENSITIVITY).lower(),
                                      SENSITIVITY_THRESHOLDS[DEFAULT_SENSITIVITY])


def build_fallback_query(topic: str, entities: Sequence[str], limit: int = MAX_QUERY_CHARS) -> str:
    """``topic + entities`` sem repetição, ≤ 120 chars (F1.2.6)."""
    parts: list[str] = []
    seen: set[str] = set()
    for piece in [topic, *entities]:
        piece = _WS.sub(" ", (piece or "")).strip()
        key = normalize(piece)
        if not key or key in seen:
            continue
        # Evita repetir entidade já contida no tópico
        if any(key in s or s in key for s in seen):
            continue
        seen.add(key)
        parts.append(piece)
    query = " ".join(parts)
    if len(query) > limit:
        query = query[:limit].rsplit(" ", 1)[0].strip() or query[:limit]
    return query


def evaluate(
    signal: InterestSignal,
    sensitivity: Optional[str] = DEFAULT_SENSITIVITY,
    *,
    threshold: Optional[float] = None,
) -> Decision:
    """Regras pós-classificação (F1.2.6/F1.2.7).

    Ordem: falha do classificador → pessoa privada → threshold → categoria
    pesquisável → query (fallback ``topic + entities``).

    ``threshold`` explícito sobrepõe o derivado de ``sensitivity`` (usado na
    varredura de calibração da F1.4).
    """
    threshold = threshold_for(sensitivity) if threshold is None else float(threshold)
    reason = signal.reason or ""
    if reason.startswith(("parse_error", "timeout", "provider_error")):
        return Decision(False, reason, threshold, signal)
    if signal.entity_type == "private_person":
        return Decision(False, "private_person", threshold, signal)
    if signal.interest < threshold:
        return Decision(False, "below_threshold", threshold, signal)
    if signal.category not in RESEARCHABLE_CATEGORIES:
        return Decision(False, "category_other", threshold, signal)
    if not signal.suggested_query.strip():
        signal.suggested_query = build_fallback_query(signal.topic, signal.entities)
    if not signal.suggested_query:
        return Decision(False, "no_query", threshold, signal)
    if len(signal.suggested_query) > MAX_QUERY_CHARS:
        signal.suggested_query = build_fallback_query(signal.suggested_query, [])
    return Decision(True, "accepted", threshold, signal)


# ─────────────────────────────────────────────────────────────────────────────
# Resolução do modelo (F1.2.4)
# ─────────────────────────────────────────────────────────────────────────────

async def resolve_detector_model(db: Any, user_id: Optional[str], fallback_provider_id: str,
                                 fallback_model_id: str) -> tuple[Any, str, str]:
    """``(provider, model_name, source)`` para o detector.

    Cascata de :func:`backend.providers.utility_model.resolve_utility_model`
    com override por ``meta.proactive_detector_provider_id/model_id`` (admin, F4).
    """
    from backend.providers.utility_model import resolve_utility_model

    return await resolve_utility_model(
        db, user_id, fallback_provider_id, fallback_model_id, override_meta_keys=DETECTOR_META_KEYS
    )
