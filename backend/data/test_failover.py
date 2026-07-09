"""
Teste da subtarefa 9.3 — Testes de Borda para Cascata de Failover.
Cenários validados:
1. Modelo sem família cadastrada
2. Família com 1 membro só (o próprio modelo primário exaurido)
3. Família com múltiplos membros, todos esgotados
4. Fallback bem sucedido para membro subsequente
"""
import asyncio
import sys
from pathlib import Path
import sqlite3

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

import tempfile
import os
import backend.database

# Setup a temporary database path instead of in-memory to allow multiple connections
# and properly apply migrations inside init_db()
TEMP_DB_PATH = os.path.join(tempfile.gettempdir(), "test_failover_temp.db")
if os.path.exists(TEMP_DB_PATH):
    try:
        os.remove(TEMP_DB_PATH)
    except Exception:
        pass

backend.database.DB_PATH = TEMP_DB_PATH

from backend.database import get_db, SCHEMA
from backend.ranking.failover import resolve_model_with_failover, NoAvailableModelError
import aiosqlite


async def setup_test_data(db):
    # Insere provedor mock
    await db.execute(
        "INSERT INTO providers (id, name, base_url, enabled, is_free) VALUES (?, ?, ?, ?, ?)",
        ("test_provider", "Test Provider", "http://test", 1, 0)
    )

    # Insere modelos mock
    models = [
        ("test_model_alone", "test_model_alone", "Test Alone", "test_provider", 1),
        ("test_model_f1_1", "test_model_f1_1", "Test F1-1", "test_provider", 1),
        ("test_model_f2_1", "test_model_f2_1", "Test F2-1", "test_provider", 1),
        ("test_model_f2_2", "test_model_f2_2", "Test F2-2", "test_provider", 1),
        ("test_model_f3_1", "test_model_f3_1", "Test F3-1", "test_provider", 1),
        ("test_model_f3_2", "test_model_f3_2", "Test F3-2", "test_provider", 1),
        ("test_model_f3_3", "test_model_f3_3", "Test F3-3", "test_provider", 1),
    ]
    for m in models:
        await db.execute(
            "INSERT INTO models (id, name, display_name, provider_id, enabled) VALUES (?, ?, ?, ?, ?)",
            m
        )
        
    # Insere Famílias
    await db.execute("INSERT INTO model_families (id, display_name) VALUES ('test_fam_1', 'Fam 1')")
    await db.execute("INSERT INTO model_families (id, display_name) VALUES ('test_fam_2', 'Fam 2')")
    await db.execute("INSERT INTO model_families (id, display_name) VALUES ('test_fam_3', 'Fam 3')")

    # Família 1: Apenas 1 membro
    await db.execute("INSERT INTO model_family_members (family_id, model_id, fallback_order) VALUES ('test_fam_1', 'test_model_f1_1', 1)")

    # Família 2: 2 membros
    await db.execute("INSERT INTO model_family_members (family_id, model_id, fallback_order) VALUES ('test_fam_2', 'test_model_f2_1', 1)")
    await db.execute("INSERT INTO model_family_members (family_id, model_id, fallback_order) VALUES ('test_fam_2', 'test_model_f2_2', 2)")

    # Família 3: 3 membros
    await db.execute("INSERT INTO model_family_members (family_id, model_id, fallback_order) VALUES ('test_fam_3', 'test_model_f3_1', 1)")
    await db.execute("INSERT INTO model_family_members (family_id, model_id, fallback_order) VALUES ('test_fam_3', 'test_model_f3_2', 2)")
    await db.execute("INSERT INTO model_family_members (family_id, model_id, fallback_order) VALUES ('test_fam_3', 'test_model_f3_3', 3)")
    
    await db.commit()


async def mark_exhausted(db, model_id):
    await db.execute(
        "INSERT OR REPLACE INTO model_quota_status (model_id, status) VALUES (?, ?)",
        (model_id, "exhausted")
    )
    await db.commit()


async def mark_available(db, model_id):
    await db.execute(
        "INSERT OR REPLACE INTO model_quota_status (model_id, status) VALUES (?, ?)",
        (model_id, "available")
    )
    await db.commit()


async def run_tests():
    # Inicializa banco rodando as migrações necessárias para ter conhecidas colunas como known_rpm
    print("--- Executando migrações do banco de dados ---")
    await backend.database.init_db()
    
    db = await get_db()
    
    print("--- Preparando dados de teste ---")
    await setup_test_data(db)
    
    print("\n[Cenário 1] Modelo sem família cadastrada, operando normal")
    await mark_available(db, "test_model_alone")
    res = await resolve_model_with_failover("test_model_alone", db)
    assert res.model_id == "test_model_alone"
    assert res.was_failover is False
    print("[OK] Passou")

    print("\n[Cenário 1b] Modelo sem família cadastrada, esgotado")
    await mark_exhausted(db, "test_model_alone")
    try:
        res = await resolve_model_with_failover("test_model_alone", db)
        assert False, "Deveria ter levantado NoAvailableModelError"
    except NoAvailableModelError:
        print("[OK] Passou (Levantou NoAvailableModelError)")

    print("\n[Cenário 2] Família com 1 membro só (ele próprio esgotado)")
    await mark_exhausted(db, "test_model_f1_1")
    try:
        res = await resolve_model_with_failover("test_model_f1_1", db)
        assert False, "Deveria ter levantado NoAvailableModelError"
    except NoAvailableModelError:
        print("[OK] Passou (Levantou NoAvailableModelError)")

    print("\n[Cenário 3] Família 2 membros, primário esgotado, secundário disponível (Fallback Funciona)")
    await mark_exhausted(db, "test_model_f2_1")
    await mark_available(db, "test_model_f2_2")
    res = await resolve_model_with_failover("test_model_f2_1", db)
    assert res.model_id == "test_model_f2_2"
    assert res.was_failover is True
    print(f"[OK] Passou (Fez fallback para {res.model_id})")

    print("\n[Cenário 4] Família 3 membros, todos esgotados!")
    await mark_exhausted(db, "test_model_f3_1")
    await mark_exhausted(db, "test_model_f3_2")
    await mark_exhausted(db, "test_model_f3_3")
    try:
        res = await resolve_model_with_failover("test_model_f3_1", db)
        assert False, "Deveria ter levantado NoAvailableModelError"
    except NoAvailableModelError:
        print("[OK] Passou (Levantou NoAvailableModelError)")

    print("\n[Cenário 5] Família 3 membros, os 2 primeiros esgotados, o 3º disponível")
    await mark_available(db, "test_model_f3_3")
    res = await resolve_model_with_failover("test_model_f3_1", db)
    assert res.model_id == "test_model_f3_3"
    assert res.was_failover is True
    print(f"[OK] Passou (Fez fallback para {res.model_id})")

    print("\n[Cenário 6] Preemptive Quota Tracking (Fase 4.5)")
    # Limpa as cotas e insere novas informações de quota
    await db.execute("DELETE FROM model_quota_status")
    await db.commit()

    await mark_available(db, "test_model_f2_1")
    await mark_available(db, "test_model_f2_2")

    # Define limite conhecido: 10 RPM. current_minute_count = 8 (80% < 85%) -> SAFE
    await db.execute("""
        UPDATE model_quota_status 
        SET known_rpm = 10, current_minute_count = 8 
        WHERE model_id = 'test_model_f2_1'
    """)
    await db.commit()

    res = await resolve_model_with_failover("test_model_f2_1", db)
    assert res.model_id == "test_model_f2_1"
    assert res.was_failover is False
    print("[OK] Quota SAFE (80%): resolveu para o próprio modelo")

    # Define limite conhecido: 10 RPM. current_minute_count = 9 (90% >= 85%) -> NEAR_LIMIT
    await db.execute("""
        UPDATE model_quota_status 
        SET current_minute_count = 9 
        WHERE model_id = 'test_model_f2_1'
    """)
    await db.commit()

    res = await resolve_model_with_failover("test_model_f2_1", db)
    assert res.model_id == "test_model_f2_2"
    assert res.was_failover is True
    assert res.failover_reason == "preemptive_quota"
    print("[OK] Quota NEAR_LIMIT (90%): desvio preemptivo executado com sucesso")
    
    print("\n--- Limpando dados de teste ---")
    await db.close()
    try:
        os.remove(TEMP_DB_PATH)
    except Exception:
        pass
    
    print("\n[OK] TODOS OS TESTES PASSARAM!")


if __name__ == "__main__":
    asyncio.run(run_tests())
