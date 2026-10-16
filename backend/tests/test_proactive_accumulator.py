"""F9.1.4 — Testes unitários do MemoryTopicAccumulator em banco temporário.

Testa:
1. Criação de nova memória temporal com signal_count=1
2. Acúmulo de sinais correlacionados (ex: viagem Natal)
3. Disparo do TriggerThreshold ao atingir a contagem necessária
4. Normalização de topic_key
5. Vinculação com insight_ready_id e transições de status
"""
from __future__ import annotations

import uuid
import pytest

from backend.database import get_db, init_db
from backend.proactive.accumulator import (
    MemoryTopicAccumulator,
    normalize_topic_key,
    generate_prompt_hook,
)


@pytest.mark.asyncio
async def test_normalize_topic_key():
    assert normalize_topic_key("place", "Natal / RN - Ponta Negra") == "place:natal_rn_ponta_negra"
    assert normalize_topic_key("PRODUCT", "GeForce RTX 5090 Ti") == "product:geforce_rtx_5090_ti"
    assert normalize_topic_key("", "") == "other:geral"


@pytest.mark.asyncio
async def test_generate_prompt_hook():
    hook_place = generate_prompt_hook("place", "Natal")
    assert "Natal" in hook_place and "roteiro de viagem" in hook_place

    hook_prod = generate_prompt_hook("product", "MacBook Pro")
    assert "MacBook Pro" in hook_prod and "comparativo" in hook_prod


@pytest.mark.asyncio
async def test_accumulator_lifecycle():
    await init_db()
    db = await get_db()
    try:
        user_id = f"user_acc_{uuid.uuid4().hex[:8]}"
        await db.execute(
            "INSERT INTO users (id, username, password_hash) VALUES (?, ?, 'fake_hash')",
            (user_id, f"test_{user_id}"),
        )
        await db.commit()

        accumulator = MemoryTopicAccumulator(db, threshold=3)

        # 1. Primeiro sinal: voos para Natal
        res1 = await accumulator.record_signal(
            user_id=user_id,
            category="place",
            topic="Natal",
            entities=["Natal", "voos"],
            query="voos para Natal promocao",
        )
        assert res1.signal_count == 1
        assert res1.triggered is False
        assert res1.status == "accumulating"

        # 2. Segundo sinal: praias de Natal
        res2 = await accumulator.record_signal(
            user_id=user_id,
            category="place",
            topic="Natal",
            entities=["praias", "Ponta Negra"],
            query="melhores praias de Natal",
        )
        assert res2.signal_count == 2
        assert res2.triggered is False
        assert res2.status == "accumulating"

        # 3. Terceiro sinal: hotéis em Natal -> Ativa o gatilho!
        res3 = await accumulator.record_signal(
            user_id=user_id,
            category="place",
            topic="Natal",
            entities=["hoteis", "pousadas"],
            query="hoteis beira mar Ponta Negra",
        )
        assert res3.signal_count == 3
        assert res3.triggered is True
        assert res3.status == "ready_to_prompt"
        assert res3.action == "trigger_synthesis"
        assert "roteiro de viagem" in res3.prompt_hook

        # Verificar recuperação no banco
        ready_list = await accumulator.get_ready_memories(user_id)
        assert len(ready_list) == 1
        assert ready_list[0].id == res3.memory_id
        assert ready_list[0].signal_count == 3
        assert set(ready_list[0].accumulated_context["entities"]) >= {"Natal", "voos", "praias", "hoteis"}

        # Inserir conversa e insight reais para respeitar FK
        conv_id = f"conv_{uuid.uuid4().hex[:8]}"
        await db.execute(
            "INSERT INTO conversations (id, user_id, title) VALUES (?, ?, 'Conversa Teste')",
            (conv_id, user_id),
        )
        fake_insight_id = str(uuid.uuid4())
        await db.execute(
            """
            INSERT INTO proactive_insights (
                id, user_id, conversation_id, topic, topic_hash, category, confidence, status
            ) VALUES (?, ?, ?, 'Natal', 'hash_natal', 'place', 0.9, 'ready')
            """,
            (fake_insight_id, user_id, conv_id),
        )
        await db.commit()

        attached = await accumulator.attach_insight(res3.memory_id, fake_insight_id)
        assert attached is True

        delivered = await accumulator.mark_delivered(res3.memory_id)
        assert delivered is True

        # Não deve mais constar em ready_to_prompt
        ready_after = await accumulator.get_ready_memories(user_id)
        assert len(ready_after) == 0

    finally:
        await db.close()
