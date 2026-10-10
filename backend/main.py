from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from pathlib import Path
import asyncio
import os
from dotenv import load_dotenv

load_dotenv()

from backend.logging_config import configure_logging, get_logger
configure_logging()
logger = get_logger(__name__)

from backend.database import init_db
from backend.routers.chat import router as chat_router
from backend.routers.ranking import router as ranking_router
from backend.routers.conversations import router as conv_router
from backend.routers.admin import router as admin_router
from backend.routers.cache_admin import router as cache_router
from backend.routers.enhancer import router as enhancer_router
from backend.routers.fusion import router as fusion_router
from backend.routers.artifacts import router as artifacts_router
from backend.routers.attachments import router as attachments_router
from backend.routers.vision_relay import router as vision_relay_router
from backend.routers.web_search import router as web_search_router
from backend.routers.families import router as families_router
from backend.routers.dashboard import router as dashboard_router

from backend.routers.auth import router as auth_router
from backend.routers.account import router as account_router
from backend.routers.memory import router as memory_router
from backend.routers.projects import router as projects_router
from backend.routers.tts import router as tts_router

app = FastAPI(title="NexusLocal", version="1.0.0")

# Mount attachments static files directory
attachments_dir = Path(__file__).parent / "storage" / "attachments"
attachments_dir.mkdir(parents=True, exist_ok=True)
app.mount("/attachments", StaticFiles(directory=str(attachments_dir)), name="attachments")

origins_env = os.getenv("ALLOWED_ORIGINS")
if origins_env:
    allow_origins = [origin.strip() for origin in origins_env.split(",") if origin.strip()]
else:
    allow_origins = ["http://localhost:5173", "http://127.0.0.1:5173"]

app.add_middleware(
    CORSMiddleware,
    allow_origins=allow_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth_router)
app.include_router(account_router)
app.include_router(memory_router)
app.include_router(projects_router)
app.include_router(chat_router)
app.include_router(conv_router)
app.include_router(admin_router)
app.include_router(cache_router)
app.include_router(enhancer_router)
app.include_router(fusion_router)
app.include_router(artifacts_router)
app.include_router(attachments_router)
app.include_router(vision_relay_router)
app.include_router(web_search_router)
app.include_router(families_router)
app.include_router(dashboard_router)
app.include_router(ranking_router)
app.include_router(tts_router)



async def run_auto_sync():
    from backend.database import get_db
    from backend.routers.admin import sync_provider_models
    import datetime
    
    async def sync_task(pid):
        conn = await get_db()
        try:
            await sync_provider_models(pid, conn)
        except Exception as e:
            logger.error("Failed background sync for %s", pid, exc_info=e)
        finally:
            await conn.close()
            
    db = await get_db()
    try:
        async with db.execute("SELECT id FROM providers WHERE enabled = 1 AND api_key != ''") as cur:
            providers = await cur.fetchall()
        
        for (provider_id,) in providers:
            last_sync = None
            try:
                async with db.execute("SELECT value FROM meta WHERE key = ?", (f"last_sync_{provider_id}",)) as cur:
                    row = await cur.fetchone()
                    if row:
                        last_sync = row[0]
            except Exception:
                pass
            
            should_sync = False
            if not last_sync:
                should_sync = True
            else:
                try:
                    last_dt = datetime.datetime.strptime(last_sync, "%Y-%m-%d %H:%M:%S")
                    delta = datetime.datetime.utcnow() - last_dt
                    if delta.total_seconds() > 24 * 3600:
                        should_sync = True
                except Exception:
                    should_sync = True
            
            if should_sync:
                logger.info("Auto-sync: iniciando sync em background para o provider '%s'", provider_id)
                asyncio.create_task(sync_task(provider_id))
    except Exception as e:
        logger.error("Error initiating auto sync", exc_info=e)
    finally:
        await db.close()


async def run_quota_release_job():
    from backend.database import get_db
    from backend.ranking.quota import release_expired_quotas
    while True:
        try:
            db = await get_db()
            try:
                await release_expired_quotas(db)
            finally:
                await db.close()
        except Exception as e:
            logger.error("Error in quota release job", exc_info=e)
        
        await asyncio.sleep(60)  # Verify every 60 seconds

async def run_minute_reset_job():
    from backend.database import get_db
    from backend.ranking.quota_tracker import reset_minute_windows
    while True:
        await asyncio.sleep(60)
        try:
            db = await get_db()
            try:
                await reset_minute_windows(db)
            finally:
                await db.close()
        except Exception as e:
            logger.error("Error in minute reset job", exc_info=e)

async def run_day_reset_job():
    from backend.database import get_db
    from backend.ranking.quota_tracker import reset_day_windows
    import datetime
    
    last_day = datetime.datetime.utcnow().day
    while True:
        await asyncio.sleep(60)
        try:
            current_day = datetime.datetime.utcnow().day
            if current_day != last_day:
                db = await get_db()
                try:
                    await reset_day_windows(db)
                finally:
                    await db.close()
                last_day = current_day
                logger.info("Auto-sync: reset_day_windows executado para novo dia UTC")
        except Exception as e:
            logger.error("Error in day reset job", exc_info=e)


async def run_free_registry_sync_job():
    from backend.database import get_db
    from backend.free_registry.sync import sync_free_registry
    import datetime
    
    # 1. Roda o sync inicial ao subir o servidor em background
    # Esperamos um pouco para não engargalar o startup do app
    await asyncio.sleep(5)
    try:
        db = await get_db()
        try:
            logger.info("Auto-sync: Iniciando sincronização em background do Free Model Registry")
            res = await sync_free_registry(db)
            logger.info("Auto-sync Free Model Registry: %s", res.get('status'))
        finally:
            await db.close()
    except Exception as e:
        logger.error("Error in initial free registry sync job", exc_info=e)
        
    while True:
        # Roda a cada 24 horas
        await asyncio.sleep(24 * 3600)
        try:
            db = await get_db()
            try:
                logger.info("Auto-sync: Rodando sync periódico do Free Model Registry")
                res = await sync_free_registry(db)
                logger.info("Auto-sync Free Model Registry periódico: %s", res.get('status'))
            finally:
                await db.close()
        except Exception as e:
            logger.error("Error in periodic free registry sync job", exc_info=e)


_memory_pipeline_lock = asyncio.Lock()


async def run_memory_idle_extraction_job():
    """
    M4: every 15 minutes, extract memory from conversations that have been
    idle for ~2 hours and not yet processed after last activity.
    Coordinated via _memory_pipeline_lock with Dream Consolidator.
    """
    from backend.memory import process_idle_memory_extractions

    # Delay startup so DB and providers are ready
    await asyncio.sleep(90)
    while True:
        try:
            async with _memory_pipeline_lock:
                n = await process_idle_memory_extractions()
            if n:
                logger.info("Memory idle job: %s conversa(s) processada(s)", n)
        except Exception as e:
            logger.error("Error in memory idle extraction job", exc_info=e)
        await asyncio.sleep(15 * 60)  # 15 minutes


async def run_project_memory_synthesis_job():
    """Periodic light cron: synthesize project_memory from recent chat_chunks."""
    from backend.projects.memory_job import synthesize_all_active_projects

    await asyncio.sleep(120)
    while True:
        try:
            n = await synthesize_all_active_projects()
            if n:
                logger.info("Project memory job: %s projeto(s) sintetizado(s)", n)
        except Exception as e:
            logger.error("Error in project memory synthesis job", exc_info=e)
        await asyncio.sleep(30 * 60)  # 30 minutes


async def warm_up_fastembed():
    """Load fastembed model once at boot so first request is not cold."""
    try:
        from backend.projects.embedder import warm_up_embedder_async

        ok = await warm_up_embedder_async()
        if ok:
            logger.info("fastembed warm-up concluído no startup")
        else:
            logger.warning("fastembed warm-up não disponível (cache semântico/Projects RAG degradado)")
    except Exception as e:
        logger.warning("fastembed warm-up falhou", exc_info=e)


async def run_dream_consolidation_job():
    """
    Periodic background job for Dream Memory consolidation.
    Checks user activity & idle state every 20 minutes:
    - User has >= 5 active facts
    - User idle for >= dream_min_idle_minutes (no messages in last 15 min)
    - Min hours passed (e.g. 24h) since last successful dream OR >= 5 new conversations
    - Circuit breaker: < 3 consecutive failures
    - Coordinated via _memory_pipeline_lock so it never collides with idle extractor.
    """
    from backend.memory_dream import execute_dream_consolidation
    from backend.database import get_db, list_dream_logs, get_user_memory
    from datetime import datetime, timezone, timedelta

    await asyncio.sleep(180)  # Initial delay after server boot
    while True:
        try:
            db = await get_db()
            try:
                async with db.execute("SELECT value FROM meta WHERE key = 'dream_enabled'") as cur:
                    row = await cur.fetchone()
                    dream_enabled = row[0] not in ("0", "false", "False", "no") if row and row[0] else True

                async with db.execute("SELECT value FROM meta WHERE key = 'dream_min_idle_minutes'") as cur:
                    row = await cur.fetchone()
                    min_idle_m = int(row[0]) if row and str(row[0]).isdigit() else 15

                async with db.execute("SELECT value FROM meta WHERE key = 'dream_min_hours_between_runs'") as cur:
                    row = await cur.fetchone()
                    min_hours = int(row[0]) if row and str(row[0]).isdigit() else 24

                async with db.execute("SELECT value FROM meta WHERE key = 'dream_min_active_facts'") as cur:
                    row = await cur.fetchone()
                    min_facts = int(row[0]) if row and str(row[0]).isdigit() else 5

                if dream_enabled:
                    async with db.execute("SELECT id FROM users") as cur:
                        user_rows = await cur.fetchall()

                    for (uid,) in user_rows:
                        try:
                            # 1. Idle check: no messages in the last min_idle_m minutes
                            async with db.execute(
                                """SELECT created_at FROM messages
                                   WHERE conversation_id IN (SELECT id FROM conversations WHERE user_id = ?)
                                   ORDER BY created_at DESC LIMIT 1""",
                                (uid,),
                            ) as cur:
                                msg_row = await cur.fetchone()

                            if msg_row and msg_row[0]:
                                try:
                                    msg_time = datetime.fromisoformat(msg_row[0].replace("Z", "+00:00"))
                                    if datetime.now(timezone.utc) - msg_time < timedelta(minutes=min_idle_m):
                                        continue  # Active recently; skip for now
                                except Exception:
                                    pass

                            # 2. Check active facts count
                            active_facts = await get_user_memory(uid, limit=200, active_only=True)
                            if len(active_facts) < min_facts:
                                continue

                            # 3. Check circuit breaker (< 3 consecutive failures)
                            logs = await list_dream_logs(uid, limit=3)
                            if len(logs) >= 3 and all(l["status"] == "failed" for l in logs[:3]):
                                logger.warning("[Dream Circuit Breaker] Pausando consolidação para usuário %s devido a 3 falhas seguidas", uid)
                                continue

                            # 4. Check time since last success
                            last_success_time = None
                            for l in logs:
                                if l["status"] == "success":
                                    last_success_time = l["created_at"]
                                    break

                            should_run = False
                            if not last_success_time:
                                should_run = True
                            else:
                                try:
                                    last_dt = datetime.fromisoformat(last_success_time.replace("Z", "+00:00"))
                                    hours_since = (datetime.now(timezone.utc) - last_dt).total_seconds() / 3600.0
                                    if hours_since >= float(min_hours):
                                        should_run = True
                                    else:
                                        # Check new conversations since last dream
                                        async with db.execute(
                                            "SELECT COUNT(*) FROM conversations WHERE user_id = ? AND created_at > ?",
                                            (uid, last_success_time),
                                        ) as c_cur:
                                            (new_convs,) = await c_cur.fetchone()
                                        if new_convs >= 5:
                                            should_run = True
                                except Exception:
                                    should_run = True

                            if should_run:
                                async with _memory_pipeline_lock:
                                    logger.info("[Dream Job] Executando consolidação automática para usuário %s...", uid)
                                    await execute_dream_consolidation(uid, trigger_type="dream_activity")
                                await asyncio.sleep(2)  # Cooldown between users
                        except Exception as u_err:
                            logger.error("[Dream Job] Erro na consolidação do usuário %s:", uid, exc_info=u_err)
            finally:
                await db.close()
        except Exception as loop_err:
            logger.error("[Dream Job] Erro no loop de consolidação periódica:", exc_info=loop_err)

        await asyncio.sleep(20 * 60)  # Check every 20 minutes


async def recover_interrupted_dreams():
    """Detects dream_logs left with status='running' from abrupt shutdowns and restores safely."""
    from backend.database import DB_PATH, rollback_memory_snapshot, update_dream_log
    import aiosqlite
    try:
        async with aiosqlite.connect(DB_PATH) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute(
                "SELECT id, user_id, snapshot_id FROM dream_logs WHERE status = 'running'"
            ) as cur:
                rows = await cur.fetchall()

        for r in rows:
            lid = r["id"]
            uid = r["user_id"]
            sid = r["snapshot_id"]
            logger.warning("[Dream Startup Recovery] Reparando sonho interrompido %s do usuário %s", lid, uid)
            if sid:
                await rollback_memory_snapshot(uid, sid)
            await update_dream_log(lid, {
                "status": "failed",
                "error_message": "Servidor reiniciado abruptamente durante consolidação (recuperado).",
                "interrupted_fixed": 1,
            })
    except Exception as e:
        logger.error("[Dream Startup Recovery] Erro ao recuperar sonhos interrompidos:", exc_info=e)


@app.on_event("startup")
async def startup():
    await init_db()
    await recover_interrupted_dreams()
    logger.info("NexusLocal iniciado - banco de dados pronto.")
    # Warm-up embedder before accepting heavy traffic (background task still lets HTTP start)
    asyncio.create_task(warm_up_fastembed())
    asyncio.create_task(run_auto_sync())
    asyncio.create_task(run_quota_release_job())
    asyncio.create_task(run_minute_reset_job())
    asyncio.create_task(run_day_reset_job())
    asyncio.create_task(run_free_registry_sync_job())
    asyncio.create_task(run_memory_idle_extraction_job())
    asyncio.create_task(run_dream_consolidation_job())
    asyncio.create_task(run_project_memory_synthesis_job())
    
    # Warm-up do cache semântico (fastembed)
    try:
        from backend.cache.manager import cache_manager
        asyncio.create_task(cache_manager.warmup())
    except Exception as e:
        logger.warning("Falha ao iniciar warm-up do cache", exc_info=e)



@app.get("/health")
async def health():
    return {"status": "ok", "app": "NexusLocal"}
