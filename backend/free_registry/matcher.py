import re

# Normalização de nome de provider: nome no registry -> provider_id no banco do NexusLocal
PROVIDER_NAME_MAP = {
    "Groq": "groq",
    "Google Gemini": "gemini",
    "OpenRouter": "openrouter",
    "Cerebras": "cerebras",
    "NVIDIA NIM": "nvidia",
    "Cloudflare Workers AI": "cloudflare",
    "Cohere": "cohere",
    "Hugging Face": "huggingface",
    "LLM7.io": "llm7",
    "Mistral AI": "mistral",
    "SambaNova": "sambanova",
    "SiliconFlow": "siliconflow",
    "Z AI (Zhipu AI)": "zai"
}

async def match_registry_to_models(db) -> dict:
    """
    Para cada entrada em free_model_registry, tenta achar o model_id
    correspondente na tabela models (match exato em models.name ou models.id).
    Se não achar exato, tenta normalização leve (lowercase, remove sufixos como ':free').
    Retorna relatório: {matched: N, unmatched: [...]}
    """
    # 1. Busca todos os registros do registry
    async with db.execute("SELECT * FROM free_model_registry") as cursor:
        registry_rows = await cursor.fetchall()
    registry_cols = [d[0] for d in cursor.description]
    registry_entries = [dict(zip(registry_cols, r)) for r in registry_rows]
    
    # 2. Busca todos os modelos locais do BD
    async with db.execute("SELECT id, name, provider_id FROM models") as cursor:
        local_rows = await cursor.fetchall()
        
    # Mapeia provider_id -> lista de models locais
    local_models_by_provider = {}
    for lid, lname, lprov in local_rows:
        local_models_by_provider.setdefault(lprov, []).append({"id": lid, "name": lname})
        
    report = {"matched": 0, "unmatched": []}
    
    def clean(s: str) -> str:
        if not s:
            return ""
        s = s.lower().strip()
        # Remove sufixos comuns de ambiente ou tipo de modelo
        s = re.sub(r'[:\-](?:free|cloud|it|instruct|preview|versatile|instant)$', '', s)
        # Pega a última parte se tiver barra (remove organização como google/, openai/, meta-llama/)
        if '/' in s:
            s = s.split('/')[-1]
        # Normaliza pontuação e separadores comuns
        s = s.replace('_', '-').replace('.', '-')
        return s
        
    for entry in registry_entries:
        provider_name = entry.get("provider_name")
        provider_id = PROVIDER_NAME_MAP.get(provider_name)
        if not provider_id:
            report["unmatched"].append({
                "provider_name": provider_name,
                "model_id_raw": entry.get("model_id_raw"),
                "reason": "Provider not mapped"
            })
            continue
            
        model_id_raw = entry.get("model_id_raw")
        local_list = local_models_by_provider.get(provider_id, [])
        
        matched_model = None
        
        # Tentativa 1: Match exato com name ou id
        for lm in local_list:
            if lm["name"] == model_id_raw or lm["id"] == model_id_raw:
                matched_model = lm
                break
                
        # Tentativa 2: Match com o id local curto (removendo prefixo de provider, ex: groq/llama-3.1-8b -> llama-3.1-8b)
        if not matched_model:
            for lm in local_list:
                local_id_short = lm["id"].split('/')[-1] if '/' in lm["id"] else lm["id"]
                if local_id_short == model_id_raw:
                    matched_model = lm
                    break
                    
        # Tentativa 3: Normalização agressiva dos dois lados
        if not matched_model:
            clean_raw = clean(model_id_raw)
            for lm in local_list:
                if clean(lm["name"]) == clean_raw or clean(lm["id"]) == clean_raw:
                    matched_model = lm
                    break
                    
        if matched_model:
            local_model_id = matched_model["id"]
            
            # Marca como confirmed_free no banco E habilita automaticamente
            await db.execute(
                "UPDATE models SET confirmed_free = 1, enabled = 1 WHERE id = ?",
                (local_model_id,)
            )
            
            # Salva no model_quota_status
            await db.execute("""
                INSERT INTO model_quota_status (
                    model_id, status, known_rpm, known_rpd, known_tpm, known_tpd, confirmed_free, registry_source
                ) VALUES (?, 'available', ?, ?, ?, ?, 1, ?)
                ON CONFLICT(model_id) DO UPDATE SET
                    known_rpm = excluded.known_rpm,
                    known_rpd = excluded.known_rpd,
                    known_tpm = excluded.known_tpm,
                    known_tpd = excluded.known_tpd,
                    confirmed_free = 1,
                    registry_source = excluded.registry_source
            """, (
                local_model_id,
                entry.get("rpm"),
                entry.get("rpd"),
                entry.get("tpm"),
                entry.get("tpd"),
                entry.get("source", "mnfst")
            ))
            
            report["matched"] += 1
        else:
            report["unmatched"].append({
                "provider_name": provider_name,
                "model_id_raw": model_id_raw,
                "reason": "Model not found in local DB"
            })
            
    await db.commit()
    return report
