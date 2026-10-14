"""Testes da Fase 1 do Assistente Proativo — detector de interesse.

Cobertura:
* F1.1 — cada regra do porteiro (positivo e negativo), candidatos a entidade,
  idioma, pureza/latência.
* F1.2 — parser tolerante, ``classify()`` com provedor fake (bem-formado,
  quebrado, erro, timeout, truncamento de contexto), regras pós-classificação,
  thresholds por sensibilidade, resolução do modelo utilitário (DB temporário).
* F1.3/F1.4 — validade do dataset gold, métricas do porteiro e (opcional, com
  ``PROACTIVE_EVAL_PROVIDER``) métricas do classificador contra um modelo real.

Banco: o ``conftest.py`` já redireciona ``DB_PATH`` para um arquivo temporário
antes de importar ``backend.database``; os testes com banco usam ``init_db()``
em cima dele e nunca tocam ``backend/nexuslocal.db``.
"""
from __future__ import annotations

import asyncio
import json
import os
import time
from collections import Counter
from pathlib import Path

import aiosqlite
import pytest

from backend import database as dbmod
from backend.proactive import evaluation as ev
from backend.proactive.detector import (
    CATEGORIES,
    DETECTOR_META_KEYS,
    ENTITY_TYPES,
    MAX_CONTEXT_CHARS,
    MAX_CONTEXT_MESSAGES,
    Decision,
    GateResult,
    InterestSignal,
    build_classifier_messages,
    build_fallback_query,
    classify,
    classify_with_meta,
    detect_language,
    evaluate,
    extract_entity_candidates,
    find_emotion_hits,
    gate,
    normalize,
    parse_interest_signal,
    resolve_detector_model,
    threshold_for,
)
from backend.proactive.prompts import CLASSIFIER_SYSTEM_PROMPT

GOLD_PATH = Path(__file__).parent / "fixtures" / "proactive_gold.jsonl"


# ─────────────────────────────────────────────────────────────────────────────
# F1.1 — porteiro léxico
# ─────────────────────────────────────────────────────────────────────────────

class TestGateRules:
    def test_web_search_used_rejects_before_anything(self):
        result = gate("Gente, o Coldplay anunciou show em Curitiba!!! Não vejo a hora", web_search_used=True)
        assert result == GateResult(False, "web_search_used")

    def test_too_short(self):
        assert gate("Coldplay!!! 🤩").reason == "too_short"
        assert gate("").reason == "too_short"
        assert gate("   \n  ").reason == "too_short"

    @pytest.mark.parametrize(
        "text",
        [
            "```python\nfor i in range(10):\n    print(i)\n```\nwhy does this print twice?",
            "SELECT * FROM messages WHERE user_id = ? ORDER BY created_at DESC LIMIT 50; tá lento demais",
            "TypeError: Cannot read properties of undefined (reading 'map') at App.tsx:42 — alguém sabe o que é?",
            "{\"a\": [1, 2, 3], \"b\": {\"c\": null}} === {} || [] && () => {}",
            "https://example.com/a/b/c?x=1&y=2",
        ],
    )
    def test_code_or_paste(self, text):
        assert gate(text).reason == "code_or_paste"

    @pytest.mark.parametrize(
        "text",
        [
            "Pesquisa pra mim os horários da Oktoberfest desse ano",
            "Dá uma procurada aí sobre o novo parque aquático de Penha",
            "Você pode pesquisar quando o Coldplay vem pro Brasil? Tô animado!!",
            "Can you look up the Bluesfest lineup for me?",
            "Search for the new Kindle Scribe release date please",
            "¿Puedes buscar cuándo sale el nuevo álbum de Rosalía?",
            "Busca en internet las fechas de la Feria de Abril",
        ],
    )
    def test_explicit_search_request(self, text):
        assert gate(text).reason == "explicit_search_request"

    def test_user_intention_to_search_is_not_a_request(self):
        # "vou procurar ingresso" é intenção do usuário, não pedido à IA
        result = gate("O Coldplay vem pra Curitiba em março!!! vou procurar ingresso agora mesmo")
        assert result.passed, result

    @pytest.mark.parametrize(
        "text",
        [
            "Quando é o show do Coldplay em Curitiba?",
            "Qual o preço do iPhone 17 no Brasil?",
            "When does the new Kindle Scribe come out?",
            "¿Cuándo juega el Real Madrid en Buenos Aires?",
            "Você sabe se a Oktoberfest de Blumenau vai ter desfile esse ano",
            "Me diz quando lança o GTA 6 no PlayStation",
        ],
    )
    def test_direct_question_without_emotion(self, text):
        assert gate(text).reason == "direct_question"

    def test_question_with_emotion_goes_to_classifier(self):
        result = gate("Sério que o Coldplay vem pra Curitiba?! Quando vai ser isso, não acredito!!")
        assert result.passed and result.reason == "passed"

    @pytest.mark.parametrize(
        "text",
        [
            "Minha mãe foi diagnosticada com câncer, tô arrasada e com muito medo",
            "Fui demitido hoje e tô desesperado com as dívidas, não sei o que fazer",
            "I've been having panic attacks again and my therapist is on vacation, I'm so worried",
            "Meu cachorro morreu ontem 😭 tô arrasado demais",
            "Mi hermana está embarazada y yo estoy muy preocupada por su salud",
        ],
    )
    def test_sensitive_first_person(self, text):
        assert gate(text).reason == "sensitive_topic"

    @pytest.mark.parametrize(
        "text",
        [
            "Nossa, o Ozzy Osbourne morreu 😭 que tristeza, era meu ídolo",
            "O Flamengo demitiu o técnico!! não acredito, quem vem agora",
            "Fiquei sabendo que o Faustão fez outra cirurgia, tomara que fique bem!!",
        ],
    )
    def test_public_news_with_sensitive_words_passes(self, text):
        # Termo sensível sem primeira pessoa por perto = notícia pública, não desabafo
        result = gate(text)
        assert result.passed, result

    @pytest.mark.parametrize(
        "text",
        [
            "Reunião com o João às 15h na sala 2 sobre o orçamento do trimestre.",
            "Preciso comprar leite, pão e pilhas AA no Angeloni hoje",
            "The meeting with Microsoft was moved to Thursday at 10am.",
            "Mañana tengo cita en el banco Santander a las 9.",
        ],
    )
    def test_entity_without_emotion(self, text):
        assert gate(text).reason == "no_emotion"

    @pytest.mark.parametrize(
        "text",
        [
            "Tô muito feliz hoje!!! Dia maravilhoso",
            "nossa que dia cansativo, só quero dormir 😭",
            "I'm so excited I can't even focus today lol",
            "¡Qué ganas de que llegue el finde ya! Estoy agotada",
        ],
    )
    def test_emotion_without_entity(self, text):
        result = gate(text)
        assert result.reason == "no_entity"
        assert result.emotion_hits, "deveria registrar os marcadores de emoção encontrados"
        assert result.entity_candidates == []

    @pytest.mark.parametrize(
        "text, lang, entity",
        [
            ("Gente, o Coldplay anunciou show em Curitiba em março!!! Não vejo a hora 🤩", "pt-BR", "Coldplay"),
            ("OMG Taylor Swift just announced a new tour date in São Paulo, I need to be there!!", "en-US", "Taylor Swift"),
            ("¡Me muero por ir a la Feria de Abril en Sevilla este año, ojalá consiga días libres!", "es-ES", "Feria de Abril"),
        ],
    )
    def test_passes_with_emotion_and_entity(self, text, lang, entity):
        result = gate(text)
        assert result.passed and result.reason == "passed"
        assert result.language == lang
        assert entity in result.entity_candidates
        assert result.emotion_hits

    def test_gate_is_pure_and_fast(self):
        text = "Gente, o Coldplay anunciou show em Curitiba em março!!! Não vejo a hora, preciso de ingresso 🤩"
        first = gate(text)
        assert gate(text) == first  # determinístico
        started = time.perf_counter()
        for _ in range(500):
            gate(text)
        avg_ms = (time.perf_counter() - started) / 500 * 1000
        assert avg_ms < 1.0, f"porteiro lento: {avg_ms:.3f} ms por chamada"

    def test_huge_message_is_truncated_not_slow(self):
        text = "Não vejo a hora do show do Coldplay!!! " * 2000  # ~80 KB
        started = time.perf_counter()
        result = gate(text)
        assert (time.perf_counter() - started) < 0.05
        assert result.passed


class TestEntityCandidates:
    def test_capitalized_sequences_outside_sentence_start(self):
        ents = extract_entity_candidates("Fiquei sabendo que a Ana Castela vai tocar no Parque Vila Germânica")
        assert "Ana Castela" in ents
        assert "Parque Vila Germânica" in ents
        assert "Fiquei" not in ents

    def test_names_joined_by_connector(self):
        ents = extract_entity_candidates("Gabriel e Shirley vão tocar aqui em Blumenau!!")
        assert "Gabriel e Shirley" in ents
        assert "Blumenau" in ents

    def test_quoted_terms_and_hashtags(self):
        ents = extract_entity_candidates('Comprei o livro "Torto Arado" e tô amando #leitura')
        assert "Torto Arado" in ents
        assert "#leitura" in ents

    def test_apostrophes_are_not_quotes(self):
        ents = extract_entity_candidates("Heard the Bluesfest lineup drops next week, I'm so hyped to see who's playing")
        assert "Bluesfest" in ents
        assert all("hyped" not in e for e in ents)

    def test_camel_case_and_alnum_products(self):
        ents = extract_entity_candidates("O iPhone 17 vai sair mes que vem e eu to muito tentado")
        assert "iPhone 17" in ents
        ents = extract_entity_candidates("GTA 6 finalmente tem data!!! RTX5090 também")
        assert "GTA 6" in ents and "RTX5090" in ents

    def test_leading_articles_are_stripped(self):
        assert "Flamengo" in extract_entity_candidates("O Flamengo demitiu o técnico!! não acredito")
        assert not any(e.startswith("O ") for e in extract_entity_candidates("O Flamengo demitiu o técnico!!"))

    def test_sentence_initial_entity_followed_by_event_verb(self):
        assert "Coldplay" in extract_entity_candidates("Coldplay anunciou turnê!! não acredito")
        # Verbo comum capitalizado no início da frase não vira entidade
        assert extract_entity_candidates("Terminei o relatório hoje!!") == []

    def test_single_word_exclamation_sentence(self):
        assert "Coldplay" in extract_entity_candidates("Coldplay!!! Não acredito!!! Vem pro Brasil!!")
        assert extract_entity_candidates("Mentira!!! Finalmente!!! Nossa!!!") == []

    def test_event_noun_with_temporal_marker_without_capitals(self):
        ents = extract_entity_candidates("vai ter um festival de cerveja artesanal aqui em blumenau no mês que vem")
        assert any(e.startswith("festival") for e in ents), ents

    def test_date_near_event_verb(self):
        ents = extract_entity_candidates("o jogo novo lança em março e eu tô contando os dias")
        assert any("marco" in normalize(e) for e in ents), ents

    def test_interjection_caps_are_not_acronyms(self):
        assert extract_entity_candidates("KKKK que dia, OMG que cansaço") == []


class TestLanguageDetection:
    @pytest.mark.parametrize(
        "text, lang",
        [
            ("tô muito animado pra ir no show, não vejo a hora", "pt-BR"),
            ("I'm so excited for the concert, can't wait", "en-US"),
            ("estoy muy emocionada por el concierto, no veo la hora", "es-ES"),
            ("¿Cuándo juega el Real Madrid?", "es-ES"),
            ("1234 5678", "unknown"),
        ],
    )
    def test_detect_language(self, text, lang):
        assert detect_language(text) == lang

    def test_emotion_hits_cover_three_languages(self):
        assert find_emotion_hits("não vejo a hora!!") and find_emotion_hits("can't wait!!") and find_emotion_hits("no veo la hora!!")
        assert "emoji:🤩" in find_emotion_hits("Coldplay em Curitiba 🤩")


# ─────────────────────────────────────────────────────────────────────────────
# F1.2 — classificador
# ─────────────────────────────────────────────────────────────────────────────

WELL_FORMED = {
    "interest": 0.92, "topic": "show do Coldplay em Curitiba", "entities": ["Coldplay", "Curitiba"],
    "entity_type": "event", "category": "event", "suggested_query": "Coldplay show Curitiba março ingressos",
    "time_sensitive": True, "emotion": "excited", "language": "pt-BR", "reason": "Quer ir ao show.",
}


class FakeProvider:
    """Imita ``BaseProvider.stream_chat`` sem rede."""

    def __init__(self, response: str = "", *, error: Exception | None = None, delay: float = 0.0, chunk: int = 7):
        self.response = response
        self.error = error
        self.delay = delay
        self.chunk = chunk
        self.calls: list[dict] = []

    async def stream_chat(self, model, messages, temperature=0.7, max_tokens=4096, **kwargs):
        self.calls.append({"model": model, "messages": messages, "temperature": temperature, "max_tokens": max_tokens})
        if self.error:
            raise self.error
        if self.delay:
            await asyncio.sleep(self.delay)
        for i in range(0, len(self.response), self.chunk):
            yield self.response[i:i + self.chunk]


class TestParser:
    def test_well_formed(self):
        sig = parse_interest_signal(json.dumps(WELL_FORMED))
        assert sig.interest == 0.92 and sig.entity_type == "event" and sig.category == "event"
        assert sig.entities == ["Coldplay", "Curitiba"] and sig.time_sensitive is True and sig.language == "pt-BR"

    @pytest.mark.parametrize(
        "wrapper",
        [
            "```json\n{json}\n```",
            "Claro! Aqui está a análise:\n{json}\nEspero ter ajudado.",
            "<think>o usuário parece animado...</think>\n{json}",
            "{json}\n{{\"outro\": 1}}",
        ],
    )
    def test_tolerates_fences_prose_and_think(self, wrapper):
        sig = parse_interest_signal(wrapper.format(json=json.dumps(WELL_FORMED)))
        assert sig.interest == 0.92 and sig.topic == WELL_FORMED["topic"]

    def test_braces_inside_strings_do_not_break_slicing(self):
        payload = dict(WELL_FORMED, reason="texto com } chave { solta")
        assert parse_interest_signal(json.dumps(payload)).reason == "texto com } chave { solta"

    @pytest.mark.parametrize(
        "raw, reason",
        [
            ("", "parse_error:no_json"),
            ("Não consigo classificar isso.", "parse_error:no_json"),
            ("{interest: 0.9, topic: show}", "parse_error:invalid_json"),
            ("{\"topic\": \"x\"}", "parse_error:interest"),
            ("{\"interest\": \"alto\"}", "parse_error:interest"),
            ("[1, 2, 3]", "parse_error:no_json"),
        ],
    )
    def test_fail_closed(self, raw, reason):
        sig = parse_interest_signal(raw)
        assert sig.interest == 0.0 and sig.reason == reason

    def test_trailing_comma_is_tolerated(self):
        assert parse_interest_signal('{"interest": 0.8, "topic": "x",}').interest == 0.8

    def test_ranges_and_enums_are_normalized(self):
        sig = parse_interest_signal(json.dumps({
            "interest": 1.7, "entity_type": "Celebrity", "category": "concert", "entities": "Coldplay, Curitiba",
            "time_sensitive": "yes", "language": "pt", "emotion": "EXCITED",
        }))
        assert sig.interest == 0.17 and sig.entity_type == "other" and sig.category == "other"
        assert sig.entities == ["Coldplay", "Curitiba"] and sig.time_sensitive is True
        assert sig.language == "pt-BR" and sig.emotion == "excited"
        assert parse_interest_signal('{"interest": 85}').interest == 0.85   # porcentagem
        assert parse_interest_signal('{"interest": 7}').interest == 0.7     # escala 0-10
        assert parse_interest_signal('{"interest": 1}').interest == 1.0
        assert parse_interest_signal('{"interest": -3}').interest == 0.0
        assert parse_interest_signal('{"interest": 0.5, "language": "Spanish"}').language == "es-ES"

    def test_long_fields_are_truncated(self):
        sig = parse_interest_signal(json.dumps({"interest": 0.5, "topic": "x" * 500, "suggested_query": "q" * 500,
                                                "entities": [f"e{i}" for i in range(50)]}))
        assert len(sig.topic) == 120 and len(sig.suggested_query) == 160 and len(sig.entities) == 10

    def test_enums_match_module_constants(self):
        assert set(CATEGORIES) == {"event", "news", "product", "place", "other"}
        assert "private_person" in ENTITY_TYPES


class TestPromptBuilding:
    def test_context_is_limited_to_last_three_truncated_messages(self):
        ctx = [{"role": "user", "content": f"msg{i} " + "x" * 1000} for i in range(6)]
        messages = build_classifier_messages("Coldplay vem!!", ctx, language_hint="pt-BR")
        assert messages[0]["role"] == "system" and messages[0]["content"] == CLASSIFIER_SYSTEM_PROMPT
        user = messages[1]["content"]
        assert "msg3" in user and "msg4" in user and "msg5" in user
        assert "msg0" not in user and "msg2" not in user
        for line in user.splitlines():
            if line.startswith("USER:"):
                assert len(line) <= len("USER: ") + MAX_CONTEXT_CHARS + 1
        assert "Language hint from heuristics: pt-BR" in user
        assert "Coldplay vem!!" in user

    def test_multimodal_context_and_tuples(self):
        ctx = [("assistant", [{"type": "text", "text": "olá"}, {"type": "image_url", "image_url": {"url": "data:x"}}])]
        user = build_classifier_messages("mensagem", ctx)[1]["content"]
        assert "ASSISTANT: olá" in user and "data:x" not in user
        assert "(none)" in build_classifier_messages("mensagem", [])[1]["content"]

    def test_constants(self):
        assert MAX_CONTEXT_MESSAGES == 3 and MAX_CONTEXT_CHARS == 600


class TestClassify:
    async def test_well_formed_response(self):
        provider = FakeProvider(json.dumps(WELL_FORMED))
        sig = await classify("Gente, o Coldplay anunciou show em Curitiba!!!", [], provider=provider, model_name="fake-1")
        assert sig.interest == 0.92 and sig.entity_type == "event"
        call = provider.calls[0]
        assert call["model"] == "fake-1" and call["temperature"] == 0.0 and call["max_tokens"] == 300
        assert call["messages"][0]["role"] == "system"

    async def test_broken_response_is_fail_closed(self):
        sig = await classify("Coldplay em Curitiba!!!", [], provider=FakeProvider("sem json aqui"), model_name="m")
        assert sig.interest == 0.0 and sig.reason == "parse_error:no_json"

    async def test_provider_error_is_fail_closed(self):
        sig = await classify("Coldplay!!!", [], provider=FakeProvider(error=RuntimeError("401")), model_name="m")
        assert sig.interest == 0.0 and sig.reason == "provider_error:RuntimeError"

    async def test_timeout_is_fail_closed(self):
        provider = FakeProvider(json.dumps(WELL_FORMED), delay=0.5)
        started = time.perf_counter()
        sig, meta = await classify_with_meta("Coldplay!!!", [], provider=provider, model_name="m", timeout=0.05)
        assert sig.interest == 0.0 and sig.reason == "timeout" and meta.error == "timeout"
        assert (time.perf_counter() - started) < 0.4

    async def test_language_hint_fills_missing_language(self):
        payload = {k: v for k, v in WELL_FORMED.items() if k != "language"}
        sig = await classify("texto", [], provider=FakeProvider(json.dumps(payload)), model_name="m", language_hint="es-ES")
        assert sig.language == "es-ES"

    async def test_meta_telemetry(self):
        _sig, meta = await classify_with_meta("Coldplay!!!", [], provider=FakeProvider(json.dumps(WELL_FORMED)), model_name="m")
        assert meta.latency_ms >= 0 and meta.prompt_chars > 500 and meta.response_chars == len(json.dumps(WELL_FORMED))
        assert meta.est_tokens > 0 and meta.error == ""


class TestPostRules:
    def test_thresholds_by_sensitivity(self):
        assert threshold_for("low") == 0.8 and threshold_for("medium") == 0.7 and threshold_for("high") == 0.6
        assert threshold_for(None) == 0.7 and threshold_for("whatever") == 0.7

    def test_private_person_is_always_rejected(self):
        sig = InterestSignal(interest=0.99, topic="casamento da prima", entities=["Ana"], entity_type="private_person", category="event")
        for sensitivity in ("low", "medium", "high"):
            decision = evaluate(sig, sensitivity)
            assert not decision.accepted and decision.reason == "private_person"

    def test_threshold_rule(self):
        sig = InterestSignal(interest=0.65, topic="iPhone 17", entities=["iPhone 17"], entity_type="product", category="product")
        assert evaluate(sig, "medium").reason == "below_threshold"
        assert evaluate(sig, "high").accepted
        assert evaluate(sig, threshold=0.5).accepted and evaluate(sig, threshold=0.9).reason == "below_threshold"

    def test_category_other_is_not_researchable(self):
        sig = InterestSignal(interest=0.9, topic="xadrez", entities=[], entity_type="other", category="other")
        assert evaluate(sig).reason == "category_other"

    def test_suggested_query_fallback(self):
        sig = InterestSignal(interest=0.9, topic="show do Coldplay", entities=["Coldplay", "Curitiba"],
                             entity_type="event", category="event", suggested_query="")
        decision = evaluate(sig)
        assert decision.accepted and decision.signal.suggested_query == "show do Coldplay Curitiba"
        assert build_fallback_query("a" * 200, ["b"]) and len(build_fallback_query("a" * 200, ["b"])) <= 120
        assert len(build_fallback_query("tópico", [f"entidade{i}" for i in range(30)])) <= 120

    def test_no_query_at_all(self):
        sig = InterestSignal(interest=0.9, topic="", entities=[], entity_type="event", category="event")
        assert evaluate(sig).reason == "no_query"

    def test_classifier_failures_propagate_reason(self):
        for reason in ("parse_error:no_json", "timeout", "provider_error:RuntimeError"):
            decision = evaluate(InterestSignal(interest=0.0, reason=reason))
            assert isinstance(decision, Decision) and not decision.accepted and decision.reason == reason


# ─────────────────────────────────────────────────────────────────────────────
# F1.2.4 — resolução do modelo utilitário (DB temporário)
# ─────────────────────────────────────────────────────────────────────────────

@pytest.fixture
async def seeded_db():
    """Banco temporário (já apontado pelo conftest) com dois provedores, chaves do usuário e modelos."""
    assert "nexuslocal-test" in str(dbmod.DB_PATH), f"DB_PATH inesperado: {dbmod.DB_PATH}"
    await dbmod.init_db()
    async with aiosqlite.connect(dbmod.DB_PATH) as db:
        await db.execute("DELETE FROM meta WHERE key IN (?, ?, ?, ?)",
                         ("memory_extractor_provider_id", "memory_extractor_model_id", *DETECTOR_META_KEYS))
        await db.execute("DELETE FROM enhancer_config WHERE id = 1")
        for pid in ("util-a", "util-b", "chat-c"):
            await db.execute(
                "INSERT OR REPLACE INTO providers (id, name, base_url, api_key, enabled, is_free) VALUES (?, ?, ?, '', 1, 1)",
                (pid, pid.upper(), f"https://{pid}.example/v1"),
            )
            await db.execute(
                "INSERT OR REPLACE INTO models (id, provider_id, name, display_name) VALUES (?, ?, ?, ?)",
                (f"{pid}/model", pid, f"{pid}-model-name", f"{pid} model"),
            )
        await db.execute("INSERT OR IGNORE INTO users (id, username, password_hash) VALUES ('u1', 'u1', '!')")
        for pid in ("util-a", "util-b", "chat-c"):
            await db.execute("INSERT OR REPLACE INTO user_api_keys (user_id, provider_id, api_key) VALUES ('u1', ?, 'k')", (pid,))
        await db.commit()
        yield db
        # Limpeza completa: o arquivo temporário é compartilhado pela sessão de testes
        await db.execute("DELETE FROM meta WHERE key IN (?, ?, ?, ?)",
                         ("memory_extractor_provider_id", "memory_extractor_model_id", *DETECTOR_META_KEYS))
        await db.execute("DELETE FROM enhancer_config WHERE id = 1")
        await db.execute("DELETE FROM user_api_keys WHERE user_id = 'u1'")
        await db.execute("DELETE FROM models WHERE provider_id IN ('util-a', 'util-b', 'chat-c')")
        await db.execute("DELETE FROM providers WHERE id IN ('util-a', 'util-b', 'chat-c')")
        await db.execute("DELETE FROM users WHERE id = 'u1'")
        await db.commit()


async def _set_meta(db, key, value):
    await db.execute("INSERT OR REPLACE INTO meta (key, value) VALUES (?, ?)", (key, value))
    await db.commit()


class TestUtilityModelResolution:
    async def test_chat_fallback_when_nothing_configured(self, seeded_db):
        provider, model_name, source = await resolve_detector_model(seeded_db, "u1", "chat-c", "chat-c/model")
        assert source == "chat_fallback" and model_name == "chat-c-model-name"
        assert provider.base_url == "https://chat-c.example/v1"

    async def test_enhancer_beats_chat_fallback(self, seeded_db):
        await seeded_db.execute(
            "INSERT OR REPLACE INTO enhancer_config (id, enhancer_provider_id, enhancer_model_id) VALUES (1, 'util-b', 'util-b/model')")
        await seeded_db.commit()
        _p, model_name, source = await resolve_detector_model(seeded_db, "u1", "chat-c", "chat-c/model")
        assert (source, model_name) == ("enhancer", "util-b-model-name")

    async def test_memory_extractor_beats_enhancer(self, seeded_db):
        await seeded_db.execute(
            "INSERT OR REPLACE INTO enhancer_config (id, enhancer_provider_id, enhancer_model_id) VALUES (1, 'util-b', 'util-b/model')")
        await _set_meta(seeded_db, "memory_extractor_provider_id", "util-a")
        await _set_meta(seeded_db, "memory_extractor_model_id", "util-a/model")
        _p, model_name, source = await resolve_detector_model(seeded_db, "u1", "chat-c", "chat-c/model")
        assert (source, model_name) == ("memory_extractor", "util-a-model-name")

    async def test_detector_override_wins(self, seeded_db):
        await _set_meta(seeded_db, "memory_extractor_provider_id", "util-a")
        await _set_meta(seeded_db, "memory_extractor_model_id", "util-a/model")
        await _set_meta(seeded_db, DETECTOR_META_KEYS[0], "util-b")
        await _set_meta(seeded_db, DETECTOR_META_KEYS[1], "util-b/model")
        _p, model_name, source = await resolve_detector_model(seeded_db, "u1", "chat-c", "chat-c/model")
        assert (source, model_name) == ("override", "util-b-model-name")

    async def test_broken_override_falls_through(self, seeded_db):
        await _set_meta(seeded_db, DETECTOR_META_KEYS[0], "util-b")
        await _set_meta(seeded_db, DETECTOR_META_KEYS[1], "util-b/does-not-exist")
        _p, model_name, source = await resolve_detector_model(seeded_db, "u1", "chat-c", "chat-c/model")
        assert (source, model_name) == ("chat_fallback", "chat-c-model-name")

    async def test_memory_extractor_entry_point_unchanged(self, seeded_db):
        """Regressão do refactor: ``memory._get_extractor_provider_and_model`` mantém contrato e rótulos."""
        from backend.memory import _get_extractor_provider_and_model

        await _set_meta(seeded_db, DETECTOR_META_KEYS[0], "util-b")       # override do detector...
        await _set_meta(seeded_db, DETECTOR_META_KEYS[1], "util-b/model")  # ...não afeta o extrator de memória
        _p, model_name, source = await _get_extractor_provider_and_model(seeded_db, "chat-c", "chat-c/model", "u1")
        assert (source, model_name) == ("chat_fallback", "chat-c-model-name")
        await _set_meta(seeded_db, "memory_extractor_provider_id", "util-a")
        await _set_meta(seeded_db, "memory_extractor_model_id", "util-a/model")
        _p, model_name, source = await _get_extractor_provider_and_model(seeded_db, "chat-c", "chat-c/model", "u1")
        assert (source, model_name) == ("memory_extractor", "util-a-model-name")


# ─────────────────────────────────────────────────────────────────────────────
# F1.3 / F1.4 — dataset gold e métricas
# ─────────────────────────────────────────────────────────────────────────────

@pytest.fixture(scope="module")
def gold():
    return ev.load_gold(GOLD_PATH)


class TestGoldDataset:
    def test_file_is_valid_and_balanced(self, gold):
        assert len(gold) == 60
        labels = Counter(item.label for item in gold)
        assert labels[1] == 30 and labels[0] == 30
        assert len({item.id for item in gold}) == 60, "ids duplicados"
        for item in gold:
            assert item.text.strip() and item.lang in {"pt-BR", "en-US", "es-ES"}
            assert item.category in CATEGORIES and item.entity_type in ENTITY_TYPES

    def test_positive_distribution(self, gold):
        positives = [i for i in gold if i.label == 1]
        cats = Counter(i.category for i in positives)
        assert cats == {"event": 10, "news": 8, "product": 6, "place": 6}
        assert sum(1 for i in positives if i.lang in {"en-US", "es-ES"}) >= 6

    def test_negative_traps_are_present(self, gold):
        negatives = [i for i in gold if i.label == 0]
        assert sum(1 for i in negatives if i.web_search_used) == 2
        assert sum(1 for i in negatives if i.entity_type == "private_person") >= 4
        assert sum(1 for i in negatives if i.lang in {"en-US", "es-ES"}) >= 6


class TestGoldMetrics:
    def test_gold_gate_metrics(self, gold):
        """F1.4.4 — metas do porteiro: ≥ 70 % das negativas rejeitadas, ≤ 10 % das positivas perdidas."""
        result = ev.evaluate_gate(gold)
        assert result.rejected_negatives_rate >= 0.70, (result.rejected_negatives_rate, result.passed_negatives)
        assert result.lost_positives_rate <= 0.10, result.lost_positives
        assert result.targets_met
        # Toda rejeição vem de uma regra conhecida
        assert set(result.reject_reasons_negatives) <= {
            "web_search_used", "too_short", "code_or_paste", "explicit_search_request",
            "direct_question", "sensitive_topic", "no_emotion", "no_entity",
        }

    def test_gold_gate_expectations_per_item(self, gold):
        """Divisão de responsabilidades: negativas marcadas ``reject`` são das regras do porteiro;
        ``llm`` (pessoa privada, sarcasmo com produto real) passam e o classificador decide."""
        result = ev.evaluate_gate(gold)
        assert {i.gate_expect for i in gold} == {"pass", "reject", "llm"}
        for item in gold:
            if item.gate_expect == "reject":
                assert not result.results[item.id].passed, (item.id, item.note)
            elif item.gate_expect == "llm":
                assert result.results[item.id].passed, (item.id, item.note)
        private_traps = [i for i in gold if i.gate_expect == "llm" and i.entity_type == "private_person"]
        assert len(private_traps) >= 4

    def test_gold_web_search_used_items_never_reach_the_classifier(self, gold):
        result = ev.evaluate_gate(gold)
        for item in gold:
            if item.web_search_used:
                assert result.results[item.id].reason == "web_search_used"

    def test_metrics_math_with_fake_records(self, gold):
        """Precisão/recall/FP e varredura, sem modelo: sinal sintético derivado do rótulo."""
        records = []
        for item in gold:
            g = gate(item.text, web_search_used=item.web_search_used)
            rec = ev.LLMRecord(id=item.id, label=item.label, lang=item.lang, category=item.category,
                               gate_passed=g.passed, gate_reason=g.reason)
            if g.passed:
                interest = 0.9 if item.label == 1 else 0.2
                rec.signal = InterestSignal(interest=interest, topic="t", entities=["e"],
                                            entity_type="event", category=item.category if item.category != "other" else "event")
                rec.meta = ev.ClassifyMeta(latency_ms=100.0, prompt_chars=4000, response_chars=200)
            records.append(rec)
        metrics = ev.compute_metrics(records)
        assert metrics.tp == 30 and metrics.fn == 0 and metrics.fp == 0 and metrics.tn == 30
        assert metrics.precision == 1.0 and metrics.recall == 1.0 and metrics.fp_rate == 0.0 and metrics.targets_met
        sweep = ev.threshold_sweep(records)
        assert [m.threshold for m in sweep] == list(ev.SWEEP_THRESHOLDS)
        assert ev.best_threshold(sweep).threshold == 0.5   # maior recall dentro das metas
        report = ev.render_markdown(ev.evaluate_gate(gold), metrics, sweep, "fake")
        assert "Estágio 1" in report and "Estágio 2" in report and "Varredura de threshold" in report

    def test_private_person_leak_is_flagged(self):
        rec = ev.LLMRecord(id="x", label=0, lang="pt-BR", category="other", gate_passed=True, gate_reason="passed")
        rec.signal = InterestSignal(interest=0.95, topic="t", entities=["Ana"], entity_type="private_person", category="event")
        metrics = ev.compute_metrics([rec])
        assert metrics.fp == 0 and metrics.private_person_leaks == []   # evaluate() barra antes

    @pytest.mark.skipif(not os.getenv("PROACTIVE_EVAL_PROVIDER"), reason="defina PROACTIVE_EVAL_PROVIDER/MODEL para avaliar um modelo real")
    async def test_gold_llm_metrics(self, gold):
        """F1.4.4 — metas do classificador com um modelo real (precisão ≥ 0,85; FP ≤ 5 %)."""
        import importlib.util

        spec = importlib.util.spec_from_file_location("proactive_eval", Path(__file__).resolve().parents[2] / "scripts" / "proactive_eval.py")
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)  # type: ignore[union-attr]
        provider_id = os.environ["PROACTIVE_EVAL_PROVIDER"]
        model = os.environ["PROACTIVE_EVAL_MODEL"]
        api_key = os.getenv("PROACTIVE_EVAL_API_KEY") or os.getenv(f"{provider_id.upper().replace('-', '_')}_API_KEY", "")
        provider = await module._build_provider(provider_id, api_key)
        records = await ev.evaluate_llm(gold, provider=provider, model_name=model, concurrency=2)
        metrics = ev.compute_metrics(records)
        assert metrics.precision >= ev.LLM_MIN_PRECISION, (metrics.precision, metrics.false_positives)
        assert metrics.fp_rate <= ev.LLM_MAX_FP_RATE, (metrics.fp_rate, metrics.false_positives)
        assert not metrics.private_person_leaks
