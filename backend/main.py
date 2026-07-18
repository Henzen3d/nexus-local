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
from backend.routers.memory import router as memory_router
from backend.routers.projects import router as projects_router

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


async def run_memory_idle_extraction_job():
    """
    M4: every 15 minutes, extract memory from conversations that have been
    idle for ~2 hours and not yet processed after last activity.
    """
    from backend.memory import process_idle_memory_extractions

    # Delay startup so DB and providers are ready
    await asyncio.sleep(90)
    while True:
        try:
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


@app.on_event("startup")
async def startup():
    await init_db()
    logger.info("NexusLocal iniciado - banco de dados pronto.")
    # Warm-up embedder before accepting heavy traffic (background task still lets HTTP start)
    asyncio.create_task(warm_up_fastembed())
    asyncio.create_task(run_auto_sync())
    asyncio.create_task(run_quota_release_job())
    asyncio.create_task(run_minute_reset_job())
    asyncio.create_task(run_day_reset_job())
    asyncio.create_task(run_free_registry_sync_job())
    asyncio.create_task(run_memory_idle_extraction_job())
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
