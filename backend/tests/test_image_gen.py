"""
Testes unitários para o módulo de Geração de Imagens (melhorias/image-gen).
Garante classificação de intenção, isolamento de banco de dados temporário,
gerenciamento de configurações e ciclo de vida atômico da fila de tarefas.
"""

from __future__ import annotations

import asyncio
import os
import tempfile
import pytest
import aiosqlite

from backend.image_gen.intent import classify_image_intent
from backend.image_gen.config import (
    get_image_gen_config,
    update_image_gen_config,
    list_image_models,
)
from backend.image_gen.queue import (
    insert_image_task,
    claim_next_task,
    complete_image_task,
    fail_image_task,
    count_daily_tasks,
    recover_stale_tasks,
    list_user_tasks,
)


def test_classify_image_intent_raster():
    """Identifica prompts raster normais e comandos slash."""
    assert classify_image_intent("desenhe um gato fofo no estilo anime") == "raster"
    assert classify_image_intent("gere uma imagem de uma floresta à noite") == "raster"
    assert classify_image_intent("/imagem um carro esportivo futurista com neon") == "raster"
    assert classify_image_intent("crie uma foto ultra-realista de uma montanha ao pôr do sol") == "raster"
    assert classify_image_intent("faça uma pintura a óleo de uma praia") == "raster"


def test_classify_image_intent_vector():
    """Garante prioridade para SVGs e vetores."""
    assert classify_image_intent("gere um logotipo em vetor svg com fundo transparente") == "vector"
    assert classify_image_intent("crie um svg de um ícone de bateria") == "vector"
    assert classify_image_intent("desenhe um ícone vetorial para meu site") == "vector"


def test_classify_image_intent_none():
    """Descarta mensagens de texto comum, código e perguntas gerais."""
    assert classify_image_intent("como funciona o algoritmo de dijkstra?") == "none"
    assert classify_image_intent("escreva uma função em python para ordenar uma lista") == "none"
    assert classify_image_intent("olá, como você está?") == "none"
    assert classify_image_intent("qual a capital da frança?") == "none"


@pytest.mark.asyncio
async def test_image_gen_db_and_queue(monkeypatch):
    """
    Testa o ciclo de vida completo no banco temporário isolado descartável.
    NUNCA toca o nexuslocal.db vivo.
    """
    # 1. Cria banco temporário descartável
    fd, tmp_db_path = tempfile.mkstemp(suffix="_test_image_gen.db")
    os.close(fd)

    try:
        import backend.database as db_mod
        monkeypatch.setattr(db_mod, "DB_PATH", tmp_db_path)

        # 2. Inicializa o schema completo no banco temporário
        await db_mod.init_db()

        # Cria usuário e conversa de teste
        async with aiosqlite.connect(tmp_db_path) as db:
            await db.execute(
                "INSERT INTO users (id, username, password_hash, role) VALUES ('u1', 'test_user', 'hash', 'user')"
            )
            await db.execute(
                "INSERT INTO conversations (id, user_id, title) VALUES ('c1', 'u1', 'Chat Teste')"
            )
            await db.commit()

        # 3. Testa leitura e alteração de ImageGenConfig
        cfg = await get_image_gen_config()
        assert cfg["id"] == 1
        assert cfg["model_id"] == "cloudflare/flux-1-schnell"
        assert cfg["steps"] == 4

        updated_cfg = await update_image_gen_config({
            "enabled": True,
            "steps": 6,
            "daily_cap_per_user": 35,
        })
        assert updated_cfg["enabled"] is True
        assert updated_cfg["steps"] == 6
        assert updated_cfg["daily_cap_per_user"] == 35

        # 4. Testa listagem de modelos
        models = await list_image_models()
        assert len(models) >= 1
        assert any(m["model_id"] == "cloudflare/flux-1-schnell" for m in models)

        # 5. Testa inserção de tarefa na fila
        assert await count_daily_tasks("u1") == 0
        task_id = await insert_image_task(
            conversation_id="c1",
            message_id="m1",
            user_id="u1",
            prompt="um astronauta tocando guitarra na lua",
            provider_id="cloudflare",
            model_id="cloudflare/flux-1-schnell",
        )
        assert task_id.startswith("img_")
        assert await count_daily_tasks("u1") == 1

        # 6. Reivindica tarefa (claim)
        claimed = await claim_next_task()
        assert claimed is not None
        assert claimed["id"] == task_id
        assert claimed["status"] == "processing"

        # Nenhuma outra tarefa deve ser encontrada
        assert await claim_next_task() is None

        # 7. Conclui tarefa (complete)
        await complete_image_task(task_id, attachment_id="att-12345")

        tasks = await list_user_tasks("u1", conversation_id="c1")
        assert len(tasks) == 1
        assert tasks[0]["status"] == "completed"
        assert tasks[0]["attachment_id"] == "att-12345"

        # 8. Testa falha de tarefa
        task_id_2 = await insert_image_task(
            conversation_id="c1",
            message_id="m2",
            user_id="u1",
            prompt="um erro simulado",
            provider_id="cloudflare",
            model_id="cloudflare/flux-1-schnell",
        )
        claimed_2 = await claim_next_task()
        assert claimed_2["id"] == task_id_2
        await fail_image_task(task_id_2, error_message="Simulated error")

        tasks_after = await list_user_tasks("u1")
        failed = [t for t in tasks_after if t["id"] == task_id_2][0]
        assert failed["status"] == "failed"
        assert failed["error_message"] == "Simulated error"

    finally:
        # Remove arquivo temporário
        if os.path.exists(tmp_db_path):
            try:
                os.remove(tmp_db_path)
            except Exception:
                pass
