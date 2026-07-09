import asyncio
import json
import sqlite3
from pathlib import Path

DB_PATH = Path(__file__).parent.parent / "nexuslocal.db"
RANKINGS_JSON_PATH = Path(__file__).parent.parent / "data" / "model_rankings.json"

FAMILIES = [
    {
        "id": "deepseek-r1",
        "display_name": "DeepSeek R1",
        "description": "Modelo de raciocínio avançado (R1) focado em programação e lógica.",
        "members": [
            {"model_id": "openrouter/deepseek-r1", "fallback_order": 1},
            {"model_id": "siliconflow/deepseek-r1", "fallback_order": 2},
            {"model_id": "freetheai/deepseek-r1", "fallback_order": 3},
            {"model_id": "deepseek/deepseek-reasoner", "fallback_order": 4}
        ]
    },
    {
        "id": "llama-3.3-70b",
        "display_name": "Llama 3.3 70B",
        "description": "Modelo open-source altamente versátil de 70 bilhões de parâmetros.",
        "members": [
            {"model_id": "cerebras/llama-3.3-70b", "fallback_order": 1},
            {"model_id": "groq/llama-3.3-70b", "fallback_order": 2},
            {"model_id": "sambanova/llama-3.3-70b", "fallback_order": 3},
            {"model_id": "siliconflow/llama-3.3-70b", "fallback_order": 4},
            {"model_id": "openrouter/llama-3.3-70b", "fallback_order": 5},
            {"model_id": "huggingface/llama-3.3-70b", "fallback_order": 6},
            {"model_id": "cloudflare/llama-3.3-70b-fast", "fallback_order": 7}
        ]
    },
    {
        "id": "deepseek-v3",
        "display_name": "DeepSeek V3",
        "description": "Modelo geral avançado e veloz da DeepSeek.",
        "members": [
            {"model_id": "siliconflow/deepseek-v3", "fallback_order": 1},
            {"model_id": "deepseek/deepseek-chat", "fallback_order": 2}
        ]
    },
    {
        "id": "gemini-2.0-flash",
        "display_name": "Gemini 2.0 Flash",
        "description": "Modelo multimodal ultra rápido do Google com janela gigante de contexto.",
        "members": [
            {"model_id": "gemini/flash-2.0", "fallback_order": 1}
        ]
    }
]

def seed_db():
    if not DB_PATH.exists():
        print(f"Erro: banco de dados {DB_PATH} não encontrado.")
        return

    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    # 1. Popular Famílias
    print("Semeando model_families...")
    for f in FAMILIES:
        cursor.execute(
            "INSERT OR REPLACE INTO model_families (id, display_name, description) VALUES (?, ?, ?)",
            (f["id"], f["display_name"], f["description"])
        )
    
    # 2. Popular Membros das Famílias
    print("Semeando model_family_members...")
    cursor.execute("DELETE FROM model_family_members") # Limpa para reinserir com a ordem correta
    for f in FAMILIES:
        for member in f["members"]:
            # Verifica se o modelo existe no banco antes de associar
            cursor.execute("SELECT id FROM models WHERE id = ?", (member["model_id"],))
            db_model = cursor.fetchone()
            if db_model:
                member_uuid = f"{f['id']}_{member['model_id']}"
                cursor.execute(
                    "INSERT OR REPLACE INTO model_family_members (id, family_id, model_id, fallback_order) VALUES (?, ?, ?, ?)",
                    (member_uuid, f["id"], member["model_id"], member["fallback_order"])
                )
                # Inicializa também a tabela de quota status
                cursor.execute(
                    "INSERT OR IGNORE INTO model_quota_status (model_id, status, consecutive_errors) VALUES (?, 'available', 0)",
                    (member["model_id"],)
                )
            else:
                print(f"Aviso: Modelo '{member['model_id']}' não existe na tabela 'models'. Pulando membro.")

    # 3. Importar e popular model_rankings com base no JSON
    if RANKINGS_JSON_PATH.exists():
        print("Semeando model_rankings a partir do JSON...")
        with open(RANKINGS_JSON_PATH, "r", encoding="utf-8") as file:
            data = json.load(file)
            rankings = data.get("rankings", {})
            for key, val in rankings.items():
                # Tenta casar a chave (ex: 'deepseek-r1') com o sufixo ou ID na tabela de modelos
                cursor.execute("SELECT id FROM models WHERE id LIKE ?", (f"%{key}%",))
                matched_models = cursor.fetchall()
                for (m_id,) in matched_models:
                    cursor.execute(
                        """INSERT OR REPLACE INTO model_rankings 
                           (model_id, quality_score, popularity_rank, nexuslocal_score, source) 
                           VALUES (?, ?, ?, ?, 'manual')""",
                        (m_id, val["quality_score"], val["popularity_rank"], val["quality_score"],)
                    )
                    # Inicializa quota para ranqueados
                    cursor.execute(
                        "INSERT OR IGNORE INTO model_quota_status (model_id, status, consecutive_errors) VALUES (?, 'available', 0)",
                        (m_id,)
                    )
                    print(f"Rank configurado para: {m_id}")
    else:
        print("Aviso: arquivo model_rankings.json não encontrado.")

    conn.commit()
    conn.close()
    print("População das sementes concluída com sucesso!")

if __name__ == "__main__":
    seed_db()
