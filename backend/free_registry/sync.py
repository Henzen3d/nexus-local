import asyncio
from backend.free_registry.fetcher import fetch_mnfst_registry, is_registry_stale
from backend.free_registry.rate_limit_parser import parse_rate_limit

async def clear_and_reload_registry(data: dict, db) -> int:
    """
    Limpa a tabela free_model_registry e reinsere todas as entradas do JSON baixado.
    Salva também o lastUpdated na tabela meta.
    """
    # Inicia uma transação
    await db.execute("DELETE FROM free_model_registry")
    
    count = 0
    providers = data.get("providers", [])
    
    for provider in providers:
        provider_name = provider.get("name", "Unknown")
        base_url = provider.get("baseUrl", "")
        models = provider.get("models", [])
        
        for model in models:
            model_id_raw = model.get("id") or model.get("name")
            if not model_id_raw:
                continue
                
            context_raw = model.get("context")
            max_output_raw = model.get("maxOutput")
            modality = model.get("modality")
            rate_limit_raw = model.get("rateLimit", "")
            
            # Executa o parse de limites de taxa
            parsed_limits = parse_rate_limit(rate_limit_raw)
            rpm = parsed_limits.get("rpm")
            rpd = parsed_limits.get("rpd")
            tpm = parsed_limits.get("tpm")
            tpd = parsed_limits.get("tpd")
            rps = parsed_limits.get("rps")
            parse_confidence = parsed_limits.get("parse_confidence", "unparseable")
            
            # Gera um ID único para cada entrada do registry
            entry_id = f"mnfst:{provider_name}:{model_id_raw}"
            
            await db.execute("""
                INSERT INTO free_model_registry (
                    id, source, provider_name, model_id_raw,
                    context_raw, max_output_raw, modality, rate_limit_raw,
                    rpm, rpd, tpm, tpd, rps, parse_confidence, base_url
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                entry_id, "mnfst", provider_name, model_id_raw,
                context_raw, max_output_raw, modality, rate_limit_raw,
                rpm, rpd, tpm, tpd, rps, parse_confidence, base_url
            ))
            count += 1
            
    # Salva a data da última atualização
    last_updated = data.get("lastUpdated", "")
    if last_updated:
        await db.execute("""
            INSERT INTO meta (key, value)
            VALUES ('free_registry_last_updated', ?)
            ON CONFLICT(key) DO UPDATE SET value = excluded.value
        """, (last_updated,))
        
    await db.commit()
    return count

import uuid
from backend.free_registry.matcher import match_registry_to_models

async def sync_free_registry(db) -> dict:
    """
    Orquestra a sincronização do awesome-free-llm-apis.
    Retorna o status do processo.
    """
    # Garante que o provedor dummy 'free_registry' exista para poder escrever no sync_log
    await db.execute(
        """INSERT OR IGNORE INTO providers (id, name, base_url, enabled, is_free)
           VALUES ('free_registry', 'Free Model Registry', 'https://github.com/mnfst/awesome-free-llm-apis', 0, 1)"""
    )
    await db.commit()

    log_id = str(uuid.uuid4())
    
    try:
        data = await fetch_mnfst_registry()
    except Exception as e:
        error_msg = str(e)
        await db.execute(
            """INSERT INTO sync_log (id, provider_id, synced_at, models_updated, status, error_msg)
               VALUES (?, 'free_registry', datetime('now'), 0, 'error', ?)""",
            (log_id, error_msg)
        )
        await db.commit()
        return {
            "status": "error",
            "error_msg": error_msg
        }

    last_updated = data.get("lastUpdated", "")
    
    stale = await is_registry_stale(last_updated, db)
    if not stale:
        # Se não estiver obsoleto, registramos no log que sincronizou e atualizou 0 modelos
        await db.execute(
            """INSERT INTO sync_log (id, provider_id, synced_at, models_updated, status)
               VALUES (?, 'free_registry', datetime('now'), 0, 'ok')""",
            (log_id,)
        )
        await db.commit()
        return {
            "status": "up_to_date",
            "last_updated": last_updated
        }
        
    try:
        inserted_count = await clear_and_reload_registry(data, db)
        # Cruza o registry novo com os modelos existentes no banco de dados local
        report = await match_registry_to_models(db)
        
        await db.execute(
            """INSERT INTO sync_log (id, provider_id, synced_at, models_updated, status)
               VALUES (?, 'free_registry', datetime('now'), ?, 'ok')""",
            (log_id, inserted_count)
        )
        await db.commit()
        
        return {
            "status": "updated",
            "last_updated": last_updated,
            "inserted_count": inserted_count,
            "match_report": report
        }
    except Exception as e:
        error_msg = str(e)
        await db.execute(
            """INSERT INTO sync_log (id, provider_id, synced_at, models_updated, status, error_msg)
               VALUES (?, 'free_registry', datetime('now'), 0, 'error', ?)""",
            (log_id, error_msg)
        )
        await db.commit()
        return {
            "status": "error",
            "error_msg": error_msg
        }
