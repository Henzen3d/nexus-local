import shutil
import os
import tempfile
import sqlite3

SRC = r"j:\Arquivos Osmar\Multi+\backend\nexuslocal.db"
DST = os.path.join(tempfile.gettempdir(), "fable5_migration_test.db")

shutil.copyfile(SRC, DST)
db = sqlite3.connect(DST)
try:
    # Reproduz exatamente a migração adicionada em init_db()
    try:
        db.execute("SELECT grounding_enabled FROM fusion_config LIMIT 1")
        print("coluna ja existia antes da migracao (inesperado em DB antigo)")
    except sqlite3.OperationalError:
        db.execute("ALTER TABLE fusion_config ADD COLUMN grounding_enabled INTEGER DEFAULT 1")
        db.commit()
        print("migracao aplicada")

    cols = [r[1] for r in db.execute("PRAGMA table_info(fusion_config)").fetchall()]
    print("colunas:", cols)
    assert "grounding_enabled" in cols

    row = db.execute(
        "SELECT judge_provider_id, judge_model_id, grounding_enabled FROM fusion_config WHERE id = 1"
    ).fetchone()
    print("linha fusion_config:", row)
    print("MIGRATION_OK")
finally:
    db.close()
    os.remove(DST)
