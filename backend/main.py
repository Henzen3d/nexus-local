from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pathlib import Path
import asyncio
from dotenv import load_dotenv

load_dotenv()

from backend.logging_config import configure_logging, get_logger
configure_logging(log_file="/app/logs/app.log")
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
from backend.routers.attachments import router as attachments_router, files_router as attachment_files_router
from backend.routers.vision_relay import router as vision_relay_router
from backend.routers.web_search import router as web_search_router
from backend.routers.families import router as families_router
from backend.routers.dashboard import router as dashboard_router

from backend.routers.auth import router as auth_router
from backend.routers.account import router as account_router
from backend.routers.memory import router as memory_router
from backend.routers.projects import router as projects_router
from backend.routers.tts import router as tts_router
from backend.routers.image_gen import router as image_gen_router
from backend.routers.proactive import router as proactive_router
from backend.routers.intelligent_ui import router as intelligent_ui_router
from backend.routers.push import router as push_router
from backend.routers.logs import router as logs_router
from backend.routers.tools import router as tools_router
from backend.ws_origin import allowed_origins_from_env

app = FastAPI(title="NexusLocal", version="1.0.0")

# Diretório de anexos. NÃO é mais montado como StaticFiles público: os arquivos
# são servidos por GET /attachments/{path} com URL assinada (routers/attachments.py).
attachments_dir = Path(__file__).parent / "storage" / "attachments"
attachments_dir.mkdir(parents=True, exist_ok=True)

# A mesma lista vale para o CORS (HTTP) e para o Origin do WebSocket (backend/ws_origin.py).
allow_origins = allowed_origins_from_env()

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
app.include_router(attachment_files_router)
app.include_router(vision_relay_router)
app.include_router(web_search_router)
app.include_router(families_router)
app.include_router(dashboard_router)
app.include_router(ranking_router)
app.include_router(tts_router)
app.include_router(image_gen_router)
app.include_router(proactive_router)
app.include_router(intelligent_ui_router)
app.include_router(push_router)
app.include_router(logs_router)
app.include_router(tools_router)



async def run_auto_sync():
    from backend.database import get_db
    from backend.routers.admin import sync_provider_models
    import datetime

    async def sync_task(pid):
        conn = await get_db()
        try:
            # Não recalcula scores durante cada provedor individual
            await sync_provider_models(pid, conn, recompute_scores=False)
        except Exception as e:
            logger.error("Failed background sync for %s", pid, exc_info=e)
        finally:
            await conn.close()

    db = await get_db()
    providers_to_sync = []
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
                providers_to_sync.append(provider_id)
    except Exception as e:
        logger.error("Error initiating auto sync", exc_info=e)
    finally:
        await db.close()

    if providers_to_sync:
        logger.info(
            "Auto-sync: iniciando sincronização consolidada para %d provedores: %s",
            len(providers_to_sync), providers_to_sync
        )
        for pid in providers_to_sync:
            await sync_task(pid)

        # Colapso da tempestade de escrita (B2 / BUG-5):
        # Recalcula e persiste o scorer exatamente UMA ÚNICA VEZ ao final de todos os syncs
        final_conn = await get_db()
        try:
            from backend.ranking.scorer import compute_all_scores, persist_scores
            scored = await compute_all_scores(final_conn)
            persisted = await persist_scores(final_conn, scored)
            logger.info("Auto-sync: scores consolidados recalculados e persistidos (%d modelos).", persisted)
        except Exception as sc_err:
            logger.error("Erro ao consolidar scores após auto-sync: %s", sc_err)
        finally:
            await final_conn.close()


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


async def run_ranking_sync_job():
    """Sincroniza o ranking de modelos (qualidade determinística + popularidade OpenRouter)
    ~45 s após o boot (depois do auto-sync de provedores) e a cada 24 h."""
    from backend.ranking.sync import start_periodic_sync_job
    await start_periodic_sync_job(interval_hours=24.0, initial_delay_s=45.0)


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


from backend.memory_lock import memory_pipeline_lock as _memory_pipeline_lock


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


async def run_proactive_housekeeping_job():
    """F3.2.7: a cada 15 min expira insights vencidos, falha pipelines travados
    (> 5 min em ``researching``) e apaga insights terminais com > 30 dias."""
    from backend.database import get_db
    from backend.proactive.service import run_housekeeping

    await asyncio.sleep(60)
    while True:
        try:
            db = await get_db()
            try:
                await run_housekeeping(db)
            finally:
                await db.close()
        except Exception as e:
            logger.error("Error in proactive housekeeping job", exc_info=e)
        await asyncio.sleep(15 * 60)


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


async def run_dream_consolidation_cycle(
    *,
    consolidator=None,
    now_fn=None,
    inter_user_delay_s: float = 2.0,
) -> dict:
    """
    Executa uma passagem completa de elegibilidade e consolidação Dream para todos os usuários.
    Lê as configurações (incluindo `dream_breaker_cooldown_minutes`) uma única vez por ciclo.
    """
    from backend.memory_dream import run_dream_with_breaker
    from backend.database import (
        get_db,
        count_active_memory_facts,
        get_last_dream_success_at,
        parse_utc_timestamp,
        clamp_dream_breaker_cooldown_minutes,
    )
    from datetime import datetime, timezone, timedelta

    now_getter = now_fn or (lambda: datetime.now(timezone.utc))
    summary = {"checked": 0, "executed": 0, "skipped_breaker": 0, "failed": 0}

    db = await get_db()
    try:
        async with db.execute(
            """SELECT key, value FROM meta
               WHERE key IN (
                   'dream_enabled',
                   'dream_min_idle_minutes',
                   'dream_min_hours_between_runs',
                   'dream_min_active_facts',
                   'dream_breaker_cooldown_minutes'
               )"""
        ) as cur:
            meta_rows = dict(await cur.fetchall())

        raw_enabled = meta_rows.get("dream_enabled")
        dream_enabled = raw_enabled not in ("0", "false", "False", "no") if raw_enabled is not None else True

        raw_idle = meta_rows.get("dream_min_idle_minutes")
        min_idle_m = int(raw_idle) if raw_idle and str(raw_idle).isdigit() else 15

        raw_hours = meta_rows.get("dream_min_hours_between_runs")
        min_hours = int(raw_hours) if raw_hours and str(raw_hours).isdigit() else 24

        raw_facts = meta_rows.get("dream_min_active_facts")
        min_facts = int(raw_facts) if raw_facts and str(raw_facts).isdigit() else 5

        cooldown_min = clamp_dream_breaker_cooldown_minutes(
            meta_rows.get("dream_breaker_cooldown_minutes")
        )

        if not dream_enabled:
            return summary

        async with db.execute("SELECT id FROM users") as cur:
            user_rows = await cur.fetchall()

        for (uid,) in user_rows:
            summary["checked"] += 1
            try:
                now_dt = now_getter()
                if now_dt.tzinfo is None:
                    now_dt = now_dt.replace(tzinfo=timezone.utc)

                # 1. Idle check: no messages in the last min_idle_m minutes
                async with db.execute(
                    """SELECT created_at FROM messages
                       WHERE conversation_id IN (SELECT id FROM conversations WHERE user_id = ?)
                       ORDER BY created_at DESC LIMIT 1""",
                    (uid,),
                ) as cur:
                    msg_row = await cur.fetchone()

                if msg_row and msg_row[0]:
                    msg_time = parse_utc_timestamp(msg_row[0])
                    if msg_time is not None and (now_dt - msg_time) < timedelta(minutes=min_idle_m):
                        continue  # Active recently; skip for now

                # 2. Check active facts count via COUNT(*)
                active_count = await count_active_memory_facts(uid)
                if active_count < min_facts:
                    continue

                # 3. Check time since last operational success (independent of recent failures)
                last_success_time = await get_last_dream_success_at(uid)

                should_run = False
                if not last_success_time:
                    should_run = True
                else:
                    last_dt = parse_utc_timestamp(last_success_time)
                    if last_dt is None:
                        should_run = True
                    else:
                        hours_since = (now_dt - last_dt).total_seconds() / 3600.0
                        if hours_since >= float(min_hours):
                            should_run = True
                        else:
                            async with db.execute(
                                "SELECT COUNT(*) FROM conversations WHERE user_id = ? AND created_at > ?",
                                (uid, last_success_time),
                            ) as c_cur:
                                (new_convs,) = await c_cur.fetchone()
                            if new_convs >= 5:
                                should_run = True

                if not should_run:
                    continue

                # 4. Run through shared breaker-guarded service (acquires probe atomically, releases DB tx before LLM)
                res = await run_dream_with_breaker(
                    uid,
                    trigger_type="dream_activity",
                    respect_breaker=True,
                    cooldown_minutes=cooldown_min,
                    consolidator=consolidator,
                    now_fn=now_getter,
                )
                if isinstance(res, dict) and res.get("status") == "skipped_breaker":
                    summary["skipped_breaker"] += 1
                    continue

                summary["executed"] += 1
                if inter_user_delay_s > 0:
                    await asyncio.sleep(inter_user_delay_s)
            except asyncio.CancelledError:
                raise
            except Exception as u_err:
                summary["failed"] += 1
                logger.error("[Dream Job] Erro na consolidação do usuário %s:", uid, exc_info=u_err)
    finally:
        await db.close()

    return summary


async def run_dream_consolidation_job():
    """
    Periodic background job for Dream Memory consolidation.
    Checks user activity & idle state every 20 minutes:
    - User has >= dream_min_active_facts active facts
    - User idle for >= dream_min_idle_minutes (no messages in last 15 min)
    - Min hours passed (e.g. 24h) since last successful dream OR >= 5 new conversations
    - Circuit breaker: persistent per-user state with cooldown & half-open probe
    - Coordinated via memory_pipeline_lock so it never collides with idle extractor.
    """
    await asyncio.sleep(180)  # Initial delay after server boot
    while True:
        try:
            await run_dream_consolidation_cycle()
        except asyncio.CancelledError:
            raise
        except Exception as loop_err:
            logger.error("[Dream Job] Erro no loop de consolidação periódica:", exc_info=loop_err)

        await asyncio.sleep(20 * 60)  # Check every 20 minutes


async def recover_interrupted_dreams():
    """Detects dream_logs left with status='running' from abrupt shutdowns, restores safely, and clears orphan probes."""
    from backend.database import (
        DB_PATH,
        rollback_memory_snapshot,
        update_dream_log,
        clear_orphan_dream_probes,
    )
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
        cleared = await clear_orphan_dream_probes()
        if cleared:
            logger.info("[Dream Startup Recovery] Liberadas %d sondas órfãs do circuit breaker", cleared)
    except Exception as e:
        logger.error("[Dream Startup Recovery] Erro ao recuperar sonhos interrompidos:", exc_info=e)


async def recover_interrupted_proactive():
    """F5.2.2: insights ``detected|researching`` de antes do restart viram
    ``failed:restart`` (as tasks morreram com o processo). Padrão de
    ``recover_interrupted_dreams``: best-effort, nunca impede o boot."""
    from backend.database import get_db
    from backend.proactive.service import recover_interrupted

    try:
        db = await get_db()
        try:
            recovered = await recover_interrupted(db)
        finally:
            await db.close()
        if recovered:
            logger.warning("[Proactive Startup Recovery] %d insight(s) interrompido(s) marcados como failed:restart", recovered)
    except Exception as e:
        logger.error("[Proactive Startup Recovery] erro ao recuperar insights interrompidos:", exc_info=e)


async def run_tool_maintenance_job():
    """Libera cotas expiradas de ferramentas e limpa cache expirado a cada 5 min."""
    from backend.database import get_db
    from backend.tools.cache import evict_expired
    from backend.tools.failover import release_expired_tool_quotas
    from backend.tools.registry import ToolRegistry

    await asyncio.sleep(45)
    while True:
        try:
            db = await get_db()
            try:
                released = await release_expired_tool_quotas(db)
                evicted = await evict_expired(db)
                await ToolRegistry.get_instance().sync_with_db(db)
                if released or evicted:
                    logger.debug("[ToolMaintenance] %d quotas liberadas, %d caches expirados removidos", released, evicted)
            finally:
                await db.close()
        except Exception as e:
            logger.error("Erro no job de manutenção de ferramentas", exc_info=e)
        await asyncio.sleep(5 * 60)


async def run_public_apis_weekly_sync_job():
    """Executa sincronização periódica semanal do repositório public-apis."""
    from backend.database import get_db
    from backend.tools.sync_public_apis import sync_public_apis

    await asyncio.sleep(300)
    while True:
        try:
            db = await get_db()
            try:
                await sync_public_apis(db)
            finally:
                await db.close()
        except Exception as e:
            logger.error("Erro na sincronização semanal de public-apis", exc_info=e)
        await asyncio.sleep(7 * 24 * 60 * 60)


@app.on_event("startup")
async def startup():
    await init_db()
    try:
        import aiosqlite
        from backend.database import DB_PATH
        async with aiosqlite.connect(DB_PATH) as _boot_db:
            async with _boot_db.execute("PRAGMA integrity_check(1);") as _cur:
                _chk = await _cur.fetchone()
                if _chk and _chk[0] == "ok":
                    logger.info("[SQLite Boot] Integridade verificada com sucesso: ok")
                else:
                    logger.warning("[SQLite Boot] Alerta de integridade no banco: %s", _chk)
    except Exception as _ie:
        logger.warning("[SQLite Boot] Não foi possível rodar integrity_check: %s", _ie)
    await recover_interrupted_dreams()
    await recover_interrupted_proactive()

    # Auto-registra todos os provedores embutidos das 10 famílias de ferramentas
    try:
        from backend.tools.registry import auto_register_default_providers
        auto_register_default_providers()
    except Exception as e:
        logger.error("[Tools] Erro ao registrar provedores de ferramentas:", exc_info=e)

    logger.info("NexusLocal iniciado - banco de dados pronto.")
    # Warm-up embedder before accepting heavy traffic (background task still lets HTTP start)
    # As referências ficam em app.state para os jobs não serem coletados pelo GC
    # no meio da execução (comportamento documentado de asyncio.create_task).
    app.state.background_tasks = set()
    for coro in (
        warm_up_fastembed(),
        run_auto_sync(),
        run_quota_release_job(),
        run_minute_reset_job(),
        run_day_reset_job(),
        run_free_registry_sync_job(),
        run_ranking_sync_job(),
        run_memory_idle_extraction_job(),
        run_dream_consolidation_job(),
        run_project_memory_synthesis_job(),
        run_proactive_housekeeping_job(),
        run_tool_maintenance_job(),
        run_public_apis_weekly_sync_job(),
    ):
        task = asyncio.create_task(coro)
        app.state.background_tasks.add(task)
        task.add_done_callback(app.state.background_tasks.discard)

    # Warm-up do cache semântico (fastembed)
    try:
        from backend.cache.manager import cache_manager
        task = asyncio.create_task(cache_manager.warmup())
        app.state.background_tasks.add(task)
        task.add_done_callback(app.state.background_tasks.discard)
    except Exception as e:
        logger.warning("Falha ao iniciar warm-up do cache", exc_info=e)

    # Iniciar background worker de Image Generation
    try:
        from backend.image_gen.worker import start_image_worker
        await start_image_worker()
        logger.info("[ImageGen Worker] Worker iniciado no startup")
    except Exception as e:
        logger.warning("[ImageGen Worker] Falha ao iniciar worker de imagem", exc_info=e)

    # Iniciar background flush do HealthRegistry (B2/B3)
    try:
        from backend.ranking.health_registry import health_registry
        from backend.database import get_db
        health_registry._flush_task = asyncio.create_task(
            health_registry.start_background_flush_loop(get_db)
        )
        logger.info("[HealthRegistry] Loop de flush em background iniciado")
    except Exception as e:
        logger.warning("[HealthRegistry] Falha ao iniciar loop de flush", exc_info=e)


@app.on_event("shutdown")
async def shutdown():
    try:
        from backend.image_gen.worker import stop_image_worker
        await stop_image_worker()
        logger.info("[ImageGen Worker] Worker finalizado no shutdown")
    except Exception as e:
        logger.warning("[ImageGen Worker] Falha ao parar worker de imagem", exc_info=e)
    try:
        from backend.ranking.health_registry import health_registry
        health_registry.stop_background_flush()
        if getattr(health_registry, "_flush_task", None) and not health_registry._flush_task.done():
            try:
                await health_registry._flush_task
            except (asyncio.CancelledError, Exception):
                pass
        from backend.database import get_db
        db = await get_db()
        try:
            await health_registry.flush_dirty_records(db)
        finally:
            await db.close()
        logger.info("[HealthRegistry] Flush no shutdown concluído com sucesso")
    except Exception as e:
        logger.warning("[HealthRegistry] Falha ao persistir no shutdown", exc_info=e)
    try:
        from backend.providers.base import close_http_client
        await close_http_client()
    except Exception as e:
        logger.warning("Falha ao fechar pool HTTP dos provedores", exc_info=e)


@app.get("/health")
async def health():
    tools_status = "healthy"
    try:
        from backend.database import get_db
        db = await get_db()
        try:
            async with db.execute("SELECT count(*) FROM tool_provider_quota WHERE status = 'exhausted'") as cur:
                r = await cur.fetchone()
                exhausted = r[0] if r else 0
                if exhausted > 5:
                    tools_status = "degraded"
        finally:
            await db.close()
    except Exception:
        tools_status = "unknown"

    return {
        "status": "ok",
        "app": "NexusLocal",
        "tools": {
            "status": tools_status,
        },
    }
