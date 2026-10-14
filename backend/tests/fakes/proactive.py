"""F5.1.2 — fakes do Assistente Proativo, compartilhados por toda a suíte.

* :class:`FakeProvider` — imita ``provider.stream_chat`` e responde ao
  classificador ou à síntese conforme o *system prompt* recebido (respostas
  JSON programáveis, ``delay`` opcional, contador de chamadas simultâneas).
* :class:`FakeSearch` — resultados fixos (ou por consulta) para ``search_fn``.
* :class:`FakeReader` — páginas fixas para ``fetch_fn`` (deep read), com
  registro das URLs pedidas.
* :class:`FakeSocket` — captura ``send_json`` (ordem dos eventos no WS).

Nenhum deles toca a rede nem o banco. ``FakeLLM`` continua existindo como
apelido de ``FakeProvider`` para os testes escritos nas fases anteriores.
"""
from __future__ import annotations

import asyncio
import json
from typing import Any, Callable, Optional, Sequence

CLASSIFIER_SYSTEM_PREFIX = "You are the interest detector"

CLASSIFIER_JSON: dict[str, Any] = {
    "interest": 0.92, "topic": "show do Coldplay em Curitiba", "entities": ["Coldplay", "Curitiba"],
    "entity_type": "event", "category": "event", "suggested_query": "Coldplay show Curitiba ingressos",
    "time_sensitive": True, "emotion": "excited", "language": "pt-BR", "reason": "Quer ir ao show.",
}
SYNTH_JSON: dict[str, Any] = {
    "text": "O show do Coldplay em Curitiba está marcado para 21 de março no Couto Pereira, e os ingressos "
            "abrem na terça pelo site da Eventim. Quer que eu fique de olho na abertura das vendas?",
    "reason_line": "Pesquisei porque você pareceu animado com o show do Coldplay.",
    "follow_ups": ["Quanto custam os ingressos?", "Tem setor pista?", "Qual o horário?"],
    "used_source_urls": ["https://www.eventim.com.br/coldplay?utm_source=x"],
    "event_date": "2027-03-21",
}
USER_MESSAGE = "Gente, o Coldplay vai tocar em Curitiba!!! Não vejo a hora, quero muito ir nesse show!"
SOURCES_RAW: list[dict[str, Any]] = [
    {"title": "Coldplay em Curitiba — ingressos", "url": "https://www.eventim.com.br/coldplay?utm_source=x",
     "snippet": "Vendas abrem terça."},
    {"title": "Coldplay anuncia show em Curitiba", "url": "https://g1.globo.com/pr/coldplay-curitiba",
     "snippet": "Banda toca no Couto Pereira em 21 de março."},
    {"title": "Coldplay - Wikipedia", "url": "https://pt.wikipedia.org/wiki/Coldplay", "snippet": "Banda britânica."},
    {"title": "post no insta", "url": "https://www.instagram.com/p/abc", "snippet": "🔥"},
]
PAGES: dict[str, dict[str, Any]] = {
    "eventim": {"title": "Eventim — Coldplay Curitiba", "published_date": "2027-01-10",
                "articles": [], "text_sample": "Coldplay Music of the Spheres Tour — Curitiba, 21 de março de 2027."},
}


class FakeProvider:
    """Responde ao classificador e à síntese conforme o system prompt recebido.

    ``classifier``/``synth`` são os JSONs devolvidos; ``synth_raw`` força um
    texto bruto (para testar parse tolerante); ``delay`` dorme antes de
    responder (cancelamento/concorrência); ``fail_with`` levanta a exceção na
    chamada do tipo indicado (``"classifier"`` | ``"synth"`` | ``"any"``).
    """

    def __init__(
        self,
        classifier: Optional[dict] = None,
        synth: Optional[dict] = None,
        *,
        synth_raw: str | None = None,
        delay: float = 0.0,
        fail_with: tuple[str, BaseException] | None = None,
    ):
        self.classifier = classifier if classifier is not None else CLASSIFIER_JSON
        self.synth = synth if synth is not None else SYNTH_JSON
        self.synth_raw = synth_raw
        self.delay = delay
        self.fail_with = fail_with
        self.calls: list[dict] = []
        self.active = 0
        self.max_active = 0

    def calls_of(self, kind: str) -> list[dict]:
        return [c for c in self.calls if c["kind"] == kind]

    async def stream_chat(self, model, messages, temperature=0.7, max_tokens=4096, **kwargs):
        system = messages[0]["content"]
        kind = "classifier" if system.startswith(CLASSIFIER_SYSTEM_PREFIX) else "synth"
        self.calls.append({"kind": kind, "model": model, "messages": messages})
        self.active += 1
        self.max_active = max(self.max_active, self.active)
        try:
            if self.delay:
                await asyncio.sleep(self.delay)
            if self.fail_with and self.fail_with[0] in (kind, "any"):
                raise self.fail_with[1]
            if kind == "classifier":
                payload = json.dumps(self.classifier, ensure_ascii=False)
            else:
                payload = self.synth_raw if self.synth_raw is not None else json.dumps(self.synth, ensure_ascii=False)
            for i in range(0, len(payload), 11):
                yield payload[i:i + 11]
        finally:
            self.active -= 1


FakeLLM = FakeProvider  # nome usado pelos testes de F2–F4


class FakeSearch:
    """``search_fn`` com resultados fixos; ``by_query`` permite respostas por consulta
    e ``error`` simula a falha do provedor de busca."""

    def __init__(self, results: Optional[Sequence[dict]] = None, *, by_query: Optional[dict] = None,
                 error: BaseException | None = None, delay: float = 0.0):
        self.results = list(results) if results is not None else list(SOURCES_RAW)
        self.by_query = by_query or {}
        self.error = error
        self.delay = delay
        self.queries: list[str] = []

    async def __call__(self, query: str, db) -> list[dict]:
        self.queries.append(query)
        if self.delay:
            await asyncio.sleep(self.delay)
        if self.error:
            raise self.error
        for key, value in self.by_query.items():
            if key in query:
                return list(value)
        return list(self.results)


class FakeReader:
    """``fetch_fn`` do deep read: devolve a página cujo *marcador* aparece na URL,
    levanta ``RuntimeError`` para ``fail_on`` (1 página falhando é tolerado) e
    ``None`` para o resto. Registra as URLs pedidas (teste anti-SSRF)."""

    def __init__(self, pages: Optional[dict] = None, *, fail_on: Sequence[str] = ("g1",)):
        self.pages = dict(pages) if pages is not None else dict(PAGES)
        self.fail_on = tuple(fail_on)
        self.requested: list[str] = []

    async def __call__(self, url: str, timeout: float = 6.0):
        self.requested.append(url)
        for marker in self.fail_on:
            if marker in url:
                raise RuntimeError("boom")
        for marker, page in self.pages.items():
            if marker in url:
                return dict(page)
        return None


class FakeSocket:
    """WebSocket falso: guarda tudo que o servidor enviaria."""

    def __init__(self):
        self.sent: list[dict] = []
        self.closed = False

    async def send_json(self, message: dict):
        if self.closed:
            raise RuntimeError("socket fechado")
        self.sent.append(message)

    def of_type(self, kind: str) -> list[dict]:
        return [m for m in self.sent if m.get("type") == kind]

    def types(self) -> list[str]:
        return [str(m.get("type")) for m in self.sent]


# Funções simples (assinatura de ``search_fn``/``fetch_fn``) para quem não precisa de estado
fake_search: Callable = FakeSearch()
fake_fetch: Callable = FakeReader()
