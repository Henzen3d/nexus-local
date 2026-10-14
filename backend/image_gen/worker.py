import asyncio
import hashlib
import os
import re
import uuid
from typing import Optional

from backend.database import get_db
from backend.image_gen.config import get_image_gen_config
from backend.image_gen.queue import (
    claim_next_task,
    complete_image_task,
    count_daily_tasks,
    fail_image_task,
    recover_stale_tasks,
)
from backend.attachments.storage import save_attachment_for_conversation
from backend.attachments.signing import attachment_url
from backend.logging_config import get_logger
from backend.providers.base import CloudflareProvider, RateLimitError

logger = get_logger(__name__)

_ACCOUNT_RE = re.compile(r"/accounts/([^/]+)/ai")


def resolve_cloudflare_account_id(
    explicit: str | None,
    base_url: str | None = None,
    env_value: str | None = None,
) -> str | None:
    """Account ID da linha do usuário, senão da URL do provedor, senão do ambiente."""
    for candidate in (explicit,):
        if candidate and candidate.strip() and candidate.strip() != "{account_id}":
            return candidate.strip()
    if base_url:
        match = _ACCOUNT_RE.search(base_url)
        if match and match.group(1) != "{account_id}":
            return match.group(1)
    if env_value is None:
        env_value = os.getenv("CLOUDFLARE_ACCOUNT_ID", "")
    if env_value and env_value.strip() and env_value.strip() != "{account_id}":
        return env_value.strip()
    return None


def image_failed_event(task_id: str, message_id: str, conversation_id: str, error: str) -> dict:
    return {
        "type": "image_failed",
        "task_id": task_id,
        "message_id": message_id,
        "conversation_id": conversation_id,
        "error": error,
    }

task_notify_event = asyncio.Event()
shutdown_event = asyncio.Event()
_worker_task: Optional[asyncio.Task] = None


def notify_new_task():
    """Acorda o worker imediatamente quando uma nova task é inserida."""
    task_notify_event.set()


async def process_image_task(task: dict):
    """Executa a geração de uma imagem pendente."""
    task_id = task["id"]
    conv_id = task["conversation_id"]
    user_id = task["user_id"]
    msg_id = task["message_id"]
    prompt = task["prompt"]
    model_id = task.get("model_id") or "cloudflare/flux-1-schnell"

    db = await get_db()
    try:
        # 1. Validação de chaves pessoais do usuário
        async with db.execute(
            "SELECT api_key, account_id FROM user_api_keys WHERE user_id = ? AND provider_id = 'cloudflare'",
            (user_id,),
        ) as cur:
            row = await cur.fetchone()

        api_key = row[0].strip() if row and row[0] else None
        account_id = row[1].strip() if row and row[1] else None

        if api_key and not account_id:
            async with db.execute(
                "SELECT base_url FROM providers WHERE id = 'cloudflare'"
            ) as cur:
                prow = await cur.fetchone()
            account_id = resolve_cloudflare_account_id(
                None, prow[0] if prow else None
            )
            if account_id:
                await db.execute(
                    """UPDATE user_api_keys
                       SET account_id = ?
                       WHERE user_id = ? AND provider_id = 'cloudflare'
                         AND (account_id IS NULL OR trim(account_id) = '')""",
                    (account_id, user_id),
                )
                await db.commit()

        if not api_key or not account_id:
            err_msg = "Falta configurar o API Token e Account ID da Cloudflare nas configurações da sua conta."
            logger.warning("[image_gen worker] Task %s abortada: usuário %s sem chaves Cloudflare", task_id, user_id)
            await fail_image_task(db, task_id, err_msg)
            await db.execute("UPDATE messages SET content = ? WHERE id = ?", (err_msg, msg_id))
            await db.commit()
            await _safe_notify_sockets(
                user_id, image_failed_event(task_id, msg_id, conv_id, err_msg)
            )
            return

        # 2. Configurações gerais e modelo
        cfg = await get_image_gen_config(db)

        # Revalidação de teto diário
        daily_used = await count_daily_tasks(db, user_id)
        if daily_used > cfg.daily_cap_per_user:
            err_msg = f"Limite diário de imagens atingido ({cfg.daily_cap_per_user}/dia)."
            await fail_image_task(db, task_id, err_msg)
            await db.execute("UPDATE messages SET content = ? WHERE id = ?", (err_msg, msg_id))
            await db.commit()
            await _safe_notify_sockets(
                user_id, image_failed_event(task_id, msg_id, conv_id, err_msg)
            )
            return

        # Busca nome do modelo na tabela image_models
        model_name = "@cf/black-forest-labs/flux-1-schnell"
        async with db.execute("SELECT name FROM image_models WHERE id = ?", (model_id,)) as cur:
            m_row = await cur.fetchone()
            if m_row and m_row[0]:
                model_name = m_row[0]

        logger.info(
            "[image_gen worker] Iniciando geração da task %s (usuário=%s, modelo=%s, steps=%s)",
            task_id, user_id, model_name, cfg.steps
        )

        # 3. Execução na Cloudflare
        provider = CloudflareProvider(api_key=api_key, base_url="")
        try:
            jpeg_bytes = await provider.run_image(
                model=model_name,
                prompt=prompt,
                steps=cfg.steps,
                account_id=account_id,
            )
        except RateLimitError:
            err_msg = "Cota diária da Cloudflare esgotada (reset às 00:00 UTC). Tente novamente mais tarde."
            logger.warning("[image_gen worker] Rate limit Cloudflare para task %s (user %s)", task_id, user_id)
            await fail_image_task(db, task_id, err_msg)
            await db.execute("UPDATE messages SET content = ? WHERE id = ?", (err_msg, msg_id))
            await db.commit()
            await _safe_notify_sockets(
                user_id, image_failed_event(task_id, msg_id, conv_id, err_msg)
            )
            return
        except Exception as e:
            err_msg = f"Não foi possível gerar a imagem: {str(e)}"
            logger.error("[image_gen worker] Falha na chamada da API para task %s:", task_id, exc_info=e)
            await fail_image_task(db, task_id, err_msg)
            await db.execute("UPDATE messages SET content = ? WHERE id = ?", (err_msg, msg_id))
            await db.commit()
            await _safe_notify_sockets(
                user_id, image_failed_event(task_id, msg_id, conv_id, err_msg)
            )
            return

        # 4. Gravação do arquivo JPEG gerado e criação do attachment
        att_id = f"att_{uuid.uuid4().hex}"
        filename = "image.jpg"
        file_rel, thumb_rel = save_attachment_for_conversation(
            file_content=jpeg_bytes,
            filename=filename,
            attachment_id=att_id,
            conversation_id=conv_id,
        )

        file_hash = hashlib.sha256(jpeg_bytes).hexdigest()
        size_bytes = len(jpeg_bytes)

        await db.execute(
            """INSERT INTO attachments (id, message_id, filename, mime_type, file_type, size_bytes, file_hash, storage_path, thumbnail_path, user_id)
               VALUES (?, ?, ?, 'image/jpeg', 'image', ?, ?, ?, ?, ?)""",
            (att_id, msg_id, filename, size_bytes, file_hash, file_rel, thumb_rel, user_id),
        )

        # Limpa o texto residual provisório do placeholder ("Gerando imagem…")
        await db.execute("UPDATE messages SET content = '' WHERE id = ?", (msg_id,))

        # Conclui a tarefa no banco vinculando o attachment_id
        await complete_image_task(db, task_id, att_id)
        await db.commit()

        logger.info("[image_gen worker] Imagem gerada e salva com sucesso para task %s (anexo=%s)", task_id, att_id)

        # 5. Notifica o socket aberto
        await _safe_notify_sockets(user_id, {
            "type": "image_ready",
            "task_id": task_id,
            "message_id": msg_id,
            "conversation_id": conv_id,
            "attachment": {
                "id": att_id,
                "filename": filename,
                "mime_type": "image/jpeg",
                "file_type": "image",
                "size_bytes": size_bytes,
                "file_url": attachment_url(file_rel),
                "thumbnail_url": attachment_url(thumb_rel),
            },
        })

    except Exception as e:
        logger.error("[image_gen worker] Erro inesperado ao processar task %s:", task_id, exc_info=e)
        try:
            await fail_image_task(db, task_id, f"Erro interno: {str(e)}")
            await db.execute("UPDATE messages SET content = 'Erro ao processar imagem.' WHERE id = ?", (msg_id,))
            await db.commit()
            await _safe_notify_sockets(
                user_id,
                image_failed_event(task_id, msg_id, conv_id, f"Erro ao gerar imagem: {e}"),
            )
        except Exception:
            pass
    finally:
        await db.close()


async def _safe_notify_sockets(user_id: str, message: dict):
    """Envia evento aos sockets conectados do usuário."""
    try:
        from backend.routers.chat import notify_user_sockets
        await notify_user_sockets(user_id, message)
    except Exception as e:
        logger.warning("[image_gen worker] Falha ao notificar sockets para user %s: %s", user_id, e)


async def image_worker_loop():
    """Loop principal do worker em background."""
    logger.info("[image_gen worker] Worker de geração de imagem iniciado.")
    while not shutdown_event.is_set():
        try:
            try:
                # Aguarda notificação de nova task ou timeout de 60s para heartbeat de recover
                await asyncio.wait_for(task_notify_event.wait(), timeout=60.0)
            except asyncio.TimeoutError:
                pass

            task_notify_event.clear()

            if shutdown_event.is_set():
                break

            # 1. Heartbeat recovery de tarefas travadas em 'generating'
            db = await get_db()
            try:
                recovered = await recover_stale_tasks(db, timeout_seconds=180)
                if recovered > 0:
                    logger.info("[image_gen worker] Recuperadas %s tarefas zumbis para 'pending'", recovered)
            finally:
                await db.close()

            # 2. Processamento sequencial (paralelismo 1)
            while not shutdown_event.is_set():
                db = await get_db()
                try:
                    task = await claim_next_task(db)
                finally:
                    await db.close()

                if not task:
                    break

                await process_image_task(task)

        except asyncio.CancelledError:
            break
        except Exception as e:
            logger.error("[image_gen worker] Erro no loop de execução:", exc_info=e)
            await asyncio.sleep(2)

    logger.info("[image_gen worker] Worker de geração de imagem finalizado.")


async def start_image_worker():
    """Inicia o worker assíncrono."""
    global _worker_task
    shutdown_event.clear()
    task_notify_event.clear()
    _worker_task = asyncio.create_task(image_worker_loop())


async def stop_image_worker():
    """Para o worker assíncrono graciosamente."""
    global _worker_task
    shutdown_event.set()
    task_notify_event.set()
    if _worker_task:
        _worker_task.cancel()
        try:
            await _worker_task
        except (asyncio.CancelledError, Exception):
            pass
        _worker_task = None
