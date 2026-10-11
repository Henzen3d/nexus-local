import uuid
from typing import Any, Dict, List, Optional
import aiosqlite


async def _resolve_db(passed_db: Optional[aiosqlite.Connection] = None):
    if passed_db is not None:
        return passed_db, False
    from backend.database import get_db
    return await get_db(), True


async def insert_image_task(
    *args,
    **kwargs,
) -> str:
    """
    Insere uma nova tarefa na fila com status 'pending'.
    Suporta:
      - insert_image_task(db, conversation_id, user_id, message_id, prompt, model_id=None)
      - insert_image_task(conversation_id, user_id, message_id, prompt, provider_id=..., model_id=..., db=None)
    """
    task_id = f"img_{uuid.uuid4().hex}"
    db = kwargs.get("db")

    if args and isinstance(args[0], aiosqlite.Connection):
        db = args[0]
        conversation_id = args[1]
        user_id = args[2]
        message_id = args[3]
        prompt = args[4]
        model_id = args[5] if len(args) > 5 else kwargs.get("model_id")
    else:
        conversation_id = args[0] if len(args) > 0 else kwargs.get("conversation_id")
        user_id = args[1] if len(args) > 1 else kwargs.get("user_id")
        message_id = args[2] if len(args) > 2 else kwargs.get("message_id")
        prompt = args[3] if len(args) > 3 else kwargs.get("prompt")
        model_id = kwargs.get("model_id") or (args[5] if len(args) > 5 else None)

    conn, should_close = await _resolve_db(db)
    try:
        await conn.execute(
            """INSERT INTO image_gen_tasks (id, conversation_id, user_id, message_id, prompt, status, model_id)
               VALUES (?, ?, ?, ?, ?, 'pending', ?)""",
            (task_id, conversation_id, user_id, message_id, prompt, model_id),
        )
        await conn.commit()
        return task_id
    finally:
        if should_close:
            await conn.close()


async def claim_next_task(db: Optional[aiosqlite.Connection] = None) -> Optional[Dict[str, Any]]:
    """
    Reivindica atomicamente a próxima tarefa pendente.
    Usa UPDATE atômico com status 'processing'.
    """
    conn, should_close = await _resolve_db(db)
    try:
        async with conn.execute(
            """SELECT id, conversation_id, user_id, message_id, prompt, model_id, created_at
               FROM image_gen_tasks
               WHERE status = 'pending'
               ORDER BY created_at ASC
               LIMIT 1"""
        ) as cur:
            row = await cur.fetchone()
            if not row:
                return None

        task_id = row[0]
        cursor = await conn.execute(
            """UPDATE image_gen_tasks
               SET status = 'processing', started_at = datetime('now')
               WHERE id = ? AND status = 'pending'""",
            (task_id,),
        )
        await conn.commit()

        if cursor.rowcount == 0:
            return None

        return {
            "id": row[0],
            "conversation_id": row[1],
            "user_id": row[2],
            "message_id": row[3],
            "prompt": row[4],
            "model_id": row[5],
            "status": "processing",
            "created_at": row[6],
        }
    finally:
        if should_close:
            await conn.close()


async def recover_stale_tasks(*args, **kwargs) -> int:
    """
    Recupera tarefas travadas em 'processing'.
    Suporta:
      - recover_stale_tasks(db, timeout_seconds=180)
      - recover_stale_tasks(timeout_seconds=180, db=None)
    """
    db = kwargs.get("db")
    timeout_seconds = kwargs.get("timeout_seconds", 180)

    if args and isinstance(args[0], aiosqlite.Connection):
        db = args[0]
        if len(args) > 1:
            timeout_seconds = args[1]
    elif args:
        timeout_seconds = args[0]

    conn, should_close = await _resolve_db(db)
    try:
        mod = f"-{int(timeout_seconds)} seconds"
        cursor = await conn.execute(
            """UPDATE image_gen_tasks
               SET status = 'pending', started_at = NULL
               WHERE status IN ('processing', 'generating')
                 AND started_at <= datetime('now', ?)""",
            (mod,),
        )
        await conn.commit()
        return cursor.rowcount
    finally:
        if should_close:
            await conn.close()


async def count_daily_tasks(*args, **kwargs) -> int:
    """
    Conta o número de imagens requisitadas pelo usuário no dia corrente (UTC).
    Suporta:
      - count_daily_tasks(db, user_id)
      - count_daily_tasks(user_id, db=None)
    """
    db = kwargs.get("db")
    if args and isinstance(args[0], aiosqlite.Connection):
        db = args[0]
        user_id = args[1]
    else:
        user_id = args[0] if args else kwargs.get("user_id")

    conn, should_close = await _resolve_db(db)
    try:
        async with conn.execute(
            """SELECT COUNT(*) FROM image_gen_tasks
               WHERE user_id = ?
                 AND status != 'failed'
                 AND created_at >= date('now', 'start of day')""",
            (user_id,),
        ) as cur:
            row = await cur.fetchone()
            return row[0] if row else 0
    finally:
        if should_close:
            await conn.close()


async def complete_image_task(*args, **kwargs) -> None:
    """
    Marca tarefa como 'completed'.
    Suporta:
      - complete_image_task(db, task_id, attachment_id=None)
      - complete_image_task(task_id, attachment_id=None, db=None)
    """
    db = kwargs.get("db")
    attachment_id = kwargs.get("attachment_id")

    if args and isinstance(args[0], aiosqlite.Connection):
        db = args[0]
        task_id = args[1]
        if len(args) > 2:
            attachment_id = args[2]
    else:
        task_id = args[0]
        if len(args) > 1:
            attachment_id = args[1]

    conn, should_close = await _resolve_db(db)
    try:
        await conn.execute(
            """UPDATE image_gen_tasks
               SET status = 'completed', attachment_id = ?, completed_at = datetime('now')
               WHERE id = ?""",
            (attachment_id, task_id),
        )
        await conn.commit()
    finally:
        if should_close:
            await conn.close()


async def fail_image_task(*args, **kwargs) -> None:
    """
    Marca tarefa como 'failed' com mensagem de erro.
    Suporta:
      - fail_image_task(db, task_id, error_message)
      - fail_image_task(task_id, error_message, db=None)
    """
    db = kwargs.get("db")
    if args and isinstance(args[0], aiosqlite.Connection):
        db = args[0]
        task_id = args[1]
        error_message = args[2]
    else:
        task_id = args[0]
        error_message = args[1] if len(args) > 1 else kwargs.get("error_message", "Erro desconhecido")

    conn, should_close = await _resolve_db(db)
    try:
        await conn.execute(
            """UPDATE image_gen_tasks
               SET status = 'failed', error_message = ?, completed_at = datetime('now')
               WHERE id = ?""",
            (error_message, task_id),
        )
        await conn.commit()
    finally:
        if should_close:
            await conn.close()


async def list_user_tasks(*args, **kwargs) -> List[Dict[str, Any]]:
    """
    Lista tarefas recentes do usuário.
    Suporta:
      - list_user_tasks(db, user_id, limit=20)
      - list_user_tasks(user_id, conversation_id=None, limit=20, db=None)
    """
    db = kwargs.get("db")
    conversation_id = kwargs.get("conversation_id")
    limit = kwargs.get("limit", 20)

    if args and isinstance(args[0], aiosqlite.Connection):
        db = args[0]
        user_id = args[1]
        if len(args) > 2:
            limit = args[2]
    else:
        user_id = args[0]
        if len(args) > 1:
            conversation_id = args[1]
        if len(args) > 2:
            limit = args[2]

    conn, should_close = await _resolve_db(db)
    try:
        if conversation_id:
            query = """SELECT id, conversation_id, message_id, prompt, status, model_id, error_message, attachment_id, created_at, completed_at
                       FROM image_gen_tasks
                       WHERE user_id = ? AND conversation_id = ?
                       ORDER BY created_at DESC
                       LIMIT ?"""
            params = (user_id, conversation_id, limit)
        else:
            query = """SELECT id, conversation_id, message_id, prompt, status, model_id, error_message, attachment_id, created_at, completed_at
                       FROM image_gen_tasks
                       WHERE user_id = ?
                       ORDER BY created_at DESC
                       LIMIT ?"""
            params = (user_id, limit)

        async with conn.execute(query, params) as cur:
            rows = await cur.fetchall()
            return [
                {
                    "id": r[0],
                    "conversation_id": r[1],
                    "message_id": r[2],
                    "prompt": r[3],
                    "status": r[4],
                    "model_id": r[5],
                    "error_message": r[6],
                    "attachment_id": r[7],
                    "created_at": r[8],
                    "completed_at": r[9],
                }
                for r in rows
            ]
    finally:
        if should_close:
            await conn.close()
