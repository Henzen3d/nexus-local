"""Idade do titular não vira filho, e ano de nascimento inventado não entra."""

from backend.memory import child_age_impossible, is_adult_holder_age_text
from backend.memory_dream import DreamOperation, NewFactPayload, drop_impossible_age_rewrites


def test_adult_age_is_holder_not_child():
    text = (
        "Idade: ~49 anos (em 2026, nascido ~1977). "
        "Anteriormente registrado como ~46 (maio/2026)."
    )
    assert is_adult_holder_age_text(text) is True
    assert child_age_impossible(
        "Filho(a) " + text,
        46,
    ) is True
    assert child_age_impossible(
        "Filho: Nicolas/Héron, nascido em maio de 2016 (10 anos em 2026).",
        46,
    ) is False


def test_drop_invented_child_birth_year():
    facts = [
        {
            "id": "age1",
            "fact": "Idade: ~46 anos (maio de 2026).",
            "fact_key": "identity.age",
            "category": "identity",
            "is_pinned": 0,
        },
        {
            "id": "son1",
            "fact": "Filho: Nicolas, nascido em maio de 2016 (10 anos).",
            "fact_key": "family.son",
            "category": "personal",
            "is_pinned": 0,
        },
    ]
    ops = [
        DreamOperation(
            action="supersede",
            old_fact_id="age1",
            new_fact=NewFactPayload(
                category="personal",
                fact_key="family.child_profile",
                fact=(
                    "Filho(a) Idade: ~49 anos (em 2026, nascido ~1977). "
                    "Anteriormente registrado como ~46, ajustado por consistência com nascimento ~1977."
                ),
                confidence=0.98,
                is_pinned=False,
            ),
        ),
        DreamOperation(action="keep", fact_id="son1"),
    ]
    kept = drop_impossible_age_rewrites(facts, ops)
    assert [op.action for op in kept] == ["keep"]


def test_drop_ungrounded_age_without_birth_year():
    """46 reescrito como 49, sem ano, também cai. Não é caso especial de 1977."""
    facts = [
        {
            "id": "age1",
            "fact": "Idade: ~46 anos (maio de 2026).",
            "fact_key": "identity.age",
            "category": "identity",
            "is_pinned": 0,
        }
    ]
    ops = [
        DreamOperation(
            action="supersede",
            old_fact_id="age1",
            new_fact=NewFactPayload(
                category="identity",
                fact_key="identity.age",
                fact="Idade: ~49 anos (em 2026), ajustado por consistência.",
                confidence=0.9,
                is_pinned=False,
            ),
        )
    ]
    assert drop_impossible_age_rewrites(facts, ops) == []


def test_drop_child_age_bump():
    facts = [
        {
            "id": "son1",
            "fact": "Filho: Nicolas, nascido em maio de 2016 (10 anos).",
            "fact_key": "family.son",
            "category": "personal",
            "is_pinned": 0,
        }
    ]
    ops = [
        DreamOperation(
            action="supersede",
            old_fact_id="son1",
            new_fact=NewFactPayload(
                category="personal",
                fact_key="family.son",
                fact="Filho: Nicolas, 12 anos, ajustado por consistência com a série.",
                confidence=0.9,
                is_pinned=False,
            ),
        )
    ]
    assert drop_impossible_age_rewrites(facts, ops) == []


def test_surname_filho_is_not_a_child():
    from backend.memory import _sanitize_extracted_item, has_family_word, is_adult_holder_age_text

    name = "Nome completo: Osmar Gonçalves Filho, 46 anos."
    assert has_family_word(name) is False
    assert has_family_word("meu filho Nicolas tem 10 anos") is True
    assert is_adult_holder_age_text(name) is True
    san = _sanitize_extracted_item({
        "action": "upsert",
        "fact_key": "identity.full_name",
        "category": "identity",
        "fact": name,
        "confidence": 0.9,
    })
    assert san["fact_key"] == "identity.full_name"
    assert san["category"] == "identity"


def test_keep_real_child_merge():
    facts = [
        {
            "id": "a",
            "fact": "Filho Nicolas nascido em maio de 2016.",
            "fact_key": "family.child_name",
            "category": "personal",
            "is_pinned": 0,
        },
        {
            "id": "b",
            "fact": "Filho tem 10 anos em 2026.",
            "fact_key": "family.child_age",
            "category": "personal",
            "is_pinned": 0,
        },
    ]
    ops = [
        DreamOperation(
            action="merge",
            source_fact_ids=["a", "b"],
            new_fact=NewFactPayload(
                category="personal",
                fact_key="family.son_profiles_main",
                fact="Filho: Nicolas, nascido em maio de 2016 (10 anos em 2026).",
                confidence=0.95,
                is_pinned=False,
            ),
        )
    ]
    kept = drop_impossible_age_rewrites(facts, ops)
    assert len(kept) == 1
    assert kept[0].action == "merge"


def test_drop_identity_mixed_with_spouse():
    facts = [
        {
            "id": "a",
            "fact": "Osmar Gonçalves, 46 anos, reside em Blumenau/SC.",
            "fact_key": "identity.profile",
            "category": "identity",
            "is_pinned": 0,
        },
        {
            "id": "b",
            "fact": "Esposa Vera Lúcia (~42 anos), casados há 19 anos.",
            "fact_key": "family.wife",
            "category": "personal",
            "is_pinned": 0,
        },
    ]
    ops = [
        DreamOperation(
            action="merge",
            source_fact_ids=["a", "b"],
            new_fact=NewFactPayload(
                category="identity",
                fact_key="identity.family",
                fact="Osmar Gonçalves, 46 anos. Casal com Vera Lúcia (~42 anos), casados há 19 anos.",
                confidence=0.95,
                is_pinned=False,
            ),
        )
    ]
    assert drop_impossible_age_rewrites(facts, ops) == []


def test_drop_synthesis_phrase_even_if_number_matches():
    facts = [{
        "id": "age1",
        "fact": "Idade: ~46 anos.",
        "fact_key": "identity.age",
        "category": "identity",
        "is_pinned": 0,
    }]
    ops = [DreamOperation(
        action="supersede",
        old_fact_id="age1",
        new_fact=NewFactPayload(
            category="identity",
            fact_key="identity.age",
            fact="Idade: ~46 anos, ajustado por consistência.",
            confidence=0.9,
            is_pinned=False,
        ),
    )]
    assert drop_impossible_age_rewrites(facts, ops) == []


def test_drop_cross_project_merge():
    facts = [
        {"id": "a", "fact": "Site em Astro.", "fact_key": "project.fix.site", "category": "project", "is_pinned": 0},
        {"id": "b", "fact": "Backtest de trading.", "fact_key": "project.nof1.backtest", "category": "project", "is_pinned": 0},
    ]
    ops = [DreamOperation(
        action="merge",
        source_fact_ids=["a", "b"],
        new_fact=NewFactPayload(
            category="project",
            fact_key="project.mix",
            fact="Site em Astro e backtest de trading.",
            confidence=0.9,
            is_pinned=False,
        ),
    )]
    assert drop_impossible_age_rewrites(facts, ops) == []


def test_drop_invented_number_and_allow_today_and_anchor():
    facts = [{"id": "a", "fact": "Mora em Blumenau.", "fact_key": "identity.city", "category": "identity", "is_pinned": 0}]
    ops = [DreamOperation(
        action="supersede",
        old_fact_id="a",
        new_fact=NewFactPayload(
            category="identity",
            fact_key="identity.city",
            fact="Mora em Blumenau, CEP 89046.",
            confidence=0.9,
            is_pinned=False,
        ),
    )]
    assert drop_impossible_age_rewrites(facts, ops) == []

    facts = [{"id": "b", "fact": "Comecei no emprego semana passada.", "fact_key": "work.start", "category": "professional", "is_pinned": 0}]
    ops = [DreamOperation(
        action="supersede",
        old_fact_id="b",
        new_fact=NewFactPayload(
            category="professional",
            fact_key="work.start",
            fact="Iniciou no emprego em 2026-03-03.",
            confidence=0.9,
            is_pinned=True,
        ),
    )]
    kept = drop_impossible_age_rewrites(facts, ops)
    assert len(kept) == 1
    assert kept[0].new_fact.is_pinned is False


def test_keep_tech_stack_merge():
    facts = [
        {"id": "a", "fact": "Usa React no frontend", "fact_key": "tech.react", "category": "tech", "is_pinned": 0},
        {"id": "b", "fact": "Prefere Tailwind e TypeScript", "fact_key": "tech.css", "category": "tech", "is_pinned": 0},
    ]
    ops = [DreamOperation(
        action="merge",
        source_fact_ids=["a", "b"],
        new_fact=NewFactPayload(
            category="tech",
            fact_key="tech.frontend_stack",
            fact="Stack frontend: React com TypeScript e Tailwind CSS.",
            confidence=0.95,
            is_pinned=False,
        ),
    )]
    kept = drop_impossible_age_rewrites(facts, ops)
    assert len(kept) == 1
    assert kept[0].action == "merge"
