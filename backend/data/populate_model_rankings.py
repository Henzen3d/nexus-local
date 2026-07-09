import sqlite3
import json
from pathlib import Path

# Paths
BASE_DIR = Path(__file__).resolve().parents[2]  # project root
DB_PATH = BASE_DIR / 'backend' / 'nexuslocal.db'
RANKINGS_JSON_PATH = BASE_DIR / 'backend' / 'data' / 'model_rankings.json'

def populate_model_rankings():
    if not DB_PATH.exists():
        print(f"Error: database not found at {DB_PATH}")
        return
    if not RANKINGS_JSON_PATH.exists():
        print(f"Error: rankings JSON not found at {RANKINGS_JSON_PATH}")
        return

    with open(RANKINGS_JSON_PATH, 'r', encoding='utf-8') as f:
        data = json.load(f)
    rankings = data.get('rankings', {})

    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    for key, val in rankings.items():
        # Find matching model ids in models table (partial match)
        cur.execute("SELECT id FROM models WHERE id LIKE ?", (f"%{key}%",))
        matches = cur.fetchall()
        for (model_id,) in matches:
            cur.execute(
                "INSERT OR REPLACE INTO model_rankings (model_id, quality_score, popularity_rank, nexuslocal_score, source) VALUES (?, ?, ?, ?, 'manual')",
                (model_id, val.get('quality_score', 0), val.get('popularity_rank', None), val.get('quality_score', 0))
            )
            # Ensure quota entry exists
            cur.execute(
                "INSERT OR IGNORE INTO model_quota_status (model_id, status, consecutive_errors) VALUES (?, 'available', 0)",
                (model_id,)
            )
            print(f"Inserted ranking for {model_id}")
    conn.commit()
    conn.close()
    print("Model rankings population complete.")

if __name__ == '__main__':
    populate_model_rankings()
