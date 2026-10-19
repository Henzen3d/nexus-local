"""
Testes unitários para o Montador de Contexto Único, Capacidade e Isolamento de Projetos (F1).
"""

from __future__ import annotations

import asyncio
import os
import sys
import tempfile
import uuid
import hashlib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import aiosqlite
import pytest

from backend import database as dbmod
import backend.projects.vector_store as vs
import backend.projects.indexer as idx
import backend.projects.memory_job as mj
import backend.projects.context_builder as cb
import backend.projects.context_assembler as ca


@pytest.fixture
async def tmp_db():
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    old_db = dbmod.DB_PATH
    dbmod.DB_PATH = Path(path)
    vs.DB_PATH = dbmod.DB_PATH
    idx.DB_PATH = dbmod.DB_PATH
    mj.DB_PATH = dbmod.DB_PATH
    cb.DB_PATH = dbmod.DB_PATH
    ca.DB_PATH = dbmod.DB_PATH

    await dbmod.init_db()
    try:
        yield Path(path)
    finally:
        dbmod.DB_PATH = old_db
        vs.DB_PATH = old_db
        idx.DB_PATH = old_db
        mj.DB_PATH = old_db
        cb.DB_PATH = old_db
        ca.DB_PATH = old_db
        try:
            os.remove(path)
        except Exception:
            pass


@pytest.mark.asyncio
async def test_precedence_and_full_mode(tmp_db):
    """
    Testa a ordem de precedência:
    Instruções > Memória > Manifesto > Conteúdo de Arquivos
    e verifica que arquivos pequenos são injetados integralmente no modo 'full'.
    """
    user_id = str(uuid.uuid4())
    project_id = str(uuid.uuid4())
    file_id = str(uuid.uuid4())

    async with aiosqlite.connect(tmp_db) as db:
        await db.execute(
            "INSERT INTO users (id, username, password_hash) VALUES (?, ?, ?)",
            (user_id, f"u_{user_id[:8]}", "pass"),
        )
        await db.execute(
            """INSERT INTO projects (id, user_id, name, description, instructions)
               VALUES (?, ?, ?, ?, ?)""",
            (project_id, user_id, "Robô ESP32", "Projeto de automação", "Responda sempre em C++ e comente o código."),
        )
        await db.execute(
            """INSERT INTO project_memory (id, project_id, summary_text, token_count)
               VALUES (?, ?, ?, ?)""",
            (str(uuid.uuid4()), project_id, "O microcontrolador utilizado opera a 3.3V.", 12),
        )
        await db.execute(
            """INSERT INTO project_files
               (id, project_id, filename, mime_type, raw_path, extracted_text, size_bytes, file_size, token_count, index_status)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 'ready')""",
            (
                file_id,
                project_id,
                "pinout.md",
                "text/markdown",
                "storage/pinout.md",
                "# Pinout\nGPIO2: LED integrado\nGPIO4: Sensor I2C SDA",
                54,
                54,
                14,
            ),
        )
        await db.commit()

    # Monta contexto
    pctx = await ca.assemble_project_context(
        project_id=project_id,
        query="qual o pino do LED?",
        safe_input_tokens=10000,
        db_path=str(tmp_db),
    )

    sys_text = pctx.system_content

    # 1. Modo integral ativo
    assert pctx.mode == "full"
    assert pctx.instructions_used is True
    assert pctx.memory_project_used is True
    assert pctx.manifest_used is True

    # 2. Ordem estrita no prompt
    pos_inst = sys_text.find("Instruções do Projeto")
    pos_mem = sys_text.find("Memória do Projeto")
    pos_man = sys_text.find("Índice do Acervo de Arquivos")
    pos_file = sys_text.find("Conteúdo Integral dos Arquivos")

    assert pos_inst != -1, "Instruções devem estar presentes"
    assert pos_mem != -1, "Memória deve estar presente"
    assert pos_man != -1, "Manifesto deve estar presente"
    assert pos_file != -1, "Conteúdo de arquivos deve estar presente"

    assert pos_inst < pos_mem < pos_man < pos_file, (
        f"Precedência violada: inst={pos_inst}, mem={pos_mem}, man={pos_man}, file={pos_file}"
    )

    # 3. Conteúdo integral do arquivo injetado
    assert "GPIO2: LED integrado" in sys_text


@pytest.mark.asyncio
async def test_rag_fallback_and_manifest_always_present(tmp_db):
    """
    Testa que arquivos que excedem o limite ativam o modo RAG,
    mas o Manifesto de Arquivos permanece SEMPRE presente no prompt.
    """
    user_id = str(uuid.uuid4())
    project_id = str(uuid.uuid4())
    file_id = str(uuid.uuid4())

    # Texto longo para forçar estouro da cota de injeção direta
    large_text = ("Texto detalhado do manual de arquitetura e especificações. " * 500)

    async with aiosqlite.connect(tmp_db) as db:
        await db.execute(
            "INSERT INTO users (id, username, password_hash) VALUES (?, ?, ?)",
            (user_id, f"u_{user_id[:8]}", "pass"),
        )
        await db.execute(
            """INSERT INTO projects (id, user_id, name, description, instructions)
               VALUES (?, ?, ?, ?, ?)""",
            (project_id, user_id, "Manual Pesado", "Docs", "Siga o manual."),
        )
        await db.execute(
            """INSERT INTO project_files
               (id, project_id, filename, mime_type, raw_path, extracted_text, size_bytes, file_size, token_count, index_status)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 'ready')""",
            (
                file_id,
                project_id,
                "manual_gigante.pdf",
                "application/pdf",
                "storage/manual.pdf",
                large_text,
                len(large_text),
                len(large_text),
                ca.estimate_tokens(large_text),
            ),
        )
        await db.commit()

    # Orçamento pequeno para forçar comutação para RAG
    pctx = await ca.assemble_project_context(
        project_id=project_id,
        query="qual a especificação?",
        safe_input_tokens=2500,
        db_path=str(tmp_db),
    )

    # Modo RAG deve estar ativo
    assert pctx.mode == "rag"
    # Manifesto DEVE estar presente mesmo em RAG
    assert "Índice do Acervo de Arquivos" in pctx.system_content
    assert "manual_gigante.pdf" in pctx.system_content


@pytest.mark.asyncio
async def test_strict_isolation_between_projects(tmp_db):
    """
    Garante isolamento absoluto:
    Arquivos, instruções e memória do Projeto A NUNCA vazam para o Projeto B.
    """
    user_id = str(uuid.uuid4())
    proj_a = str(uuid.uuid4())
    proj_b = str(uuid.uuid4())

    async with aiosqlite.connect(tmp_db) as db:
        await db.execute(
            "INSERT INTO users (id, username, password_hash) VALUES (?, ?, ?)",
            (user_id, f"u_{user_id[:8]}", "pass"),
        )
        # Projeto A
        await db.execute(
            """INSERT INTO projects (id, user_id, name, instructions)
               VALUES (?, ?, ?, ?)""",
            (proj_a, user_id, "Projeto Secreto A", "SENHA_PROJETO_A = 12345"),
        )
        await db.execute(
            """INSERT INTO project_memory (id, project_id, summary_text)
               VALUES (?, ?, ?)""",
            (str(uuid.uuid4()), proj_a, "Fato confidencial de A: cliente Alpha"),
        )
        await db.execute(
            """INSERT INTO project_files
               (id, project_id, filename, extracted_text, size_bytes, token_count, index_status)
               VALUES (?, ?, ?, ?, ?, ?, 'ready')""",
            (str(uuid.uuid4()), proj_a, "segredo_a.txt", "CONTEUDO_RESTRITO_A", 20, 5),
        )

        # Projeto B
        await db.execute(
            """INSERT INTO projects (id, user_id, name, instructions)
               VALUES (?, ?, ?, ?)""",
            (proj_b, user_id, "Projeto Público B", "Instruções públicas de B"),
        )
        await db.execute(
            """INSERT INTO project_memory (id, project_id, summary_text)
               VALUES (?, ?, ?)""",
            (str(uuid.uuid4()), proj_b, "Fato de B: cliente Beta"),
        )
        await db.execute(
            """INSERT INTO project_files
               (id, project_id, filename, extracted_text, size_bytes, token_count, index_status)
               VALUES (?, ?, ?, ?, ?, ?, 'ready')""",
            (str(uuid.uuid4()), proj_b, "documento_b.txt", "CONTEUDO_PUBLICO_B", 20, 5),
        )
        await db.commit()

    # Monta contexto do Projeto B
    ctx_b = await ca.assemble_project_context(
        project_id=proj_b,
        query="qualquer pergunta",
        safe_input_tokens=8000,
        db_path=str(tmp_db),
    )

    sys_b = ctx_b.system_content

    # Dados de B devem estar presentes
    assert "Projeto Público B" in sys_b
    assert "Instruções públicas de B" in sys_b
    assert "Fato de B: cliente Beta" in sys_b
    assert "documento_b.txt" in sys_b
    assert "CONTEUDO_PUBLICO_B" in sys_b

    # NADA de A pode vazar para B!
    assert "Projeto Secreto A" not in sys_b
    assert "SENHA_PROJETO_A" not in sys_b
    assert "cliente Alpha" not in sys_b
    assert "segredo_a.txt" not in sys_b
    assert "CONTEUDO_RESTRITO_A" not in sys_b


@pytest.mark.asyncio
async def test_capacity_calculation_and_backfill(tmp_db):
    """
    Testa o cálculo da Barra de Capacidade, porcentagem de uso, flags de alerta
    e o backfill automático de file_size e token_count.
    """
    user_id = str(uuid.uuid4())
    project_id = str(uuid.uuid4())
    file_id = str(uuid.uuid4())

    async with aiosqlite.connect(tmp_db) as db:
        await db.execute(
            "INSERT INTO users (id, username, password_hash) VALUES (?, ?, ?)",
            (user_id, f"u_{user_id[:8]}", "pass"),
        )
        await db.execute(
            """INSERT INTO projects (id, user_id, name, instructions)
               VALUES (?, ?, ?, ?)""",
            (project_id, user_id, "Projeto Capacidade", "Instrução de 20 chars!"),
        )
        await db.execute(
            """INSERT INTO project_memory (id, project_id, summary_text, token_count)
               VALUES (?, ?, ?, 0)""",
            (str(uuid.uuid4()), project_id, "Memória com quarenta caracteres teste."),
        )
        # Arquivo com file_size e token_count zerados para testar o backfill automático
        await db.execute(
            """INSERT INTO project_files
               (id, project_id, filename, extracted_text, size_bytes, file_size, token_count, index_status)
               VALUES (?, ?, ?, ?, ?, 0, 0, 'ready')""",
            (file_id, project_id, "dados.txt", "1234567890" * 40, 400),
        )
        await db.commit()

    cap = await ca.calculate_project_capacity(
        project_id=project_id,
        capacity_limit=1000,
        db_path=str(tmp_db),
    )

    assert cap["total_tokens"] > 0
    assert cap["breakdown"]["instructions_tokens"] > 0
    assert cap["breakdown"]["memory_tokens"] > 0
    assert cap["breakdown"]["files_tokens"] > 0
    assert cap["breakdown"]["file_count"] == 1
    assert cap["usage_percent"] > 0.0

    # Verifica que o backfill atualizou o registro no SQLite
    async with aiosqlite.connect(tmp_db) as db:
        async with db.execute(
            "SELECT file_size, token_count FROM project_files WHERE id = ?",
            (file_id,),
        ) as cur:
            row = await cur.fetchone()
            assert row[0] == 400, "file_size deve ter sido backfilled para 400"
            assert row[1] > 0, "token_count deve ter sido calculado"


@pytest.mark.asyncio
async def test_upload_duplicate_detection(tmp_db):
    """
    Testa a detecção de arquivos duplicados por hash SHA-256 e por nome+tamanho.
    """
    user_id = str(uuid.uuid4())
    project_id = str(uuid.uuid4())
    content = b"Conteudo unico para teste de deduplicacao"
    file_hash = hashlib.sha256(content).hexdigest()
    size_bytes = len(content)

    async with aiosqlite.connect(tmp_db) as db:
        await db.execute(
            "INSERT INTO users (id, username, password_hash) VALUES (?, ?, ?)",
            (user_id, f"u_{user_id[:8]}", "pass"),
        )
        await db.execute(
            "INSERT INTO projects (id, user_id, name) VALUES (?, ?, ?)",
            (project_id, user_id, "Projeto Dedupe"),
        )
        await db.execute(
            """INSERT INTO project_files
               (id, project_id, filename, file_hash, size_bytes, file_size, token_count, index_status)
               VALUES (?, ?, ?, ?, ?, ?, ?, 'ready')""",
            (str(uuid.uuid4()), project_id, "original.txt", file_hash, size_bytes, size_bytes, 10),
        )
        await db.commit()

        # 1. Simula verificação de upload com mesmo hash
        async with db.execute(
            """SELECT id, filename FROM project_files
               WHERE project_id = ? AND (file_hash = ? OR (filename = ? AND size_bytes = ?))""",
            (project_id, file_hash, "copia_renomeada.txt", size_bytes),
        ) as cur:
            dup1 = await cur.fetchone()
            assert dup1 is not None, "Deve detectar duplicata por hash mesmo com nome diferente"
            assert dup1[1] == "original.txt"

        # 2. Simula verificação com mesmo nome e tamanho
        async with db.execute(
            """SELECT id, filename FROM project_files
               WHERE project_id = ? AND (file_hash = ? OR (filename = ? AND size_bytes = ?))""",
            (project_id, "outro_hash_fake", "original.txt", size_bytes),
        ) as cur:
            dup2 = await cur.fetchone()
            assert dup2 is not None, "Deve detectar duplicata por nome e tamanho"


@pytest.mark.asyncio
async def test_project_memory_synthesis_conscious(tmp_db):
    """
    Testa que a síntese de memória extrai decisões de conversas existentes,
    evitando duplicar instruções do projeto e persistindo o token_count.
    """
    user_id = str(uuid.uuid4())
    project_id = str(uuid.uuid4())
    conv_id = str(uuid.uuid4())

    async with aiosqlite.connect(tmp_db) as db:
        await db.execute(
            "INSERT INTO users (id, username, password_hash) VALUES (?, ?, ?)",
            (user_id, f"u_{user_id[:8]}", "pass"),
        )
        await db.execute(
            """INSERT INTO projects (id, user_id, name, instructions)
               VALUES (?, ?, ?, ?)""",
            (project_id, user_id, "App Finanças", "Sempre responda em português com foco em segurança."),
        )
        await db.execute(
            "INSERT INTO project_memory (id, project_id, summary_text) VALUES (?, ?, '')",
            (str(uuid.uuid4()), project_id),
        )
        await db.execute(
            "INSERT INTO conversations (id, user_id, project_id, title) VALUES (?, ?, ?, ?)",
            (conv_id, user_id, project_id, "Planejamento Arquitetural"),
        )
        await db.execute(
            """INSERT INTO messages (id, conversation_id, role, content)
               VALUES (?, ?, 'user', 'Decidimos que o banco de dados oficial será PostgreSQL com schema isolado.')""",
            (str(uuid.uuid4()), conv_id),
        )
        await db.execute(
            """INSERT INTO messages (id, conversation_id, role, content)
               VALUES (?, ?, 'assistant', 'Perfeito, arquitetura registrada com PostgreSQL e schemas isolados.')""",
            (str(uuid.uuid4()), conv_id),
        )
        await db.commit()

    # Força síntese de memória a partir do histórico existente
    summary = await mj.maybe_synthesize_project_memory(project_id, force=True)

    assert summary is not None
    assert "PostgreSQL" in summary or "arquitetura" in summary.lower()

    # Verifica persistência e token_count na tabela project_memory
    async with aiosqlite.connect(tmp_db) as db:
        async with db.execute(
            "SELECT summary_text, token_count FROM project_memory WHERE project_id = ?",
            (project_id,),
        ) as cur:
            row = await cur.fetchone()
            assert row is not None
            assert len(row[0]) > 0
            assert row[1] > 0, "token_count da memória deve ser maior que 0"

