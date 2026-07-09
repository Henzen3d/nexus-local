import re
import json
import uuid
import asyncio
import html as _html_lib        # stdlib — html.unescape() para decodificar entidades HTML
from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from backend.database import get_db, check_and_deactivate_model
from backend.providers.registry import get_provider, get_model_name
from backend.cache.manager import cache_manager
from backend.auth import decode_token
from backend.web_search import resolve_and_execute_search, get_web_search_config, should_search, format_search_results
from backend.ranking import (
    resolve_model_with_failover,
    NoAvailableModelError,
    mark_model_exhausted,
    mark_model_success,
)
from backend.ranking.quota_tracker import record_request
from backend.providers.base import RateLimitError

router = APIRouter()

# Fake-streaming delay por token (ms) — dá UX consistente vindo do cache
_CACHE_STREAM_DELAY = 0.004

# Linguagens cujo tratamento já está nas regras específicas de html/svg/jsx
# (não caem no detector genérico de blocos de código ≥ 15 linhas)
_EXCLUDED_LANGS_FROM_CODE = {
    "html", "svg", "xml", "jsx", "tsx", "markdown", "md",
    "bash", "sh", "shell", "zsh", "powershell", "ps1", "cmd", "bat", "plaintext", "txt"
}


def _extract_html_svg_title(content: str, fallback: str) -> str:
    """
    Extrai o conteúdo da tag <title> de HTML ou SVG gerado por LLM.

    Camadas de defesa (em ordem de aplicação):
    1. Guarda contra conteúdo vazio/inválido.
    2. Remove comentários HTML/XML (<!-- ... -->) ANTES de buscar a tag,
       para não capturar <title> falso dentro de um comentário.
    3. Regex tolerante: aceita atributos na tag (<title lang="en">) e
       conteúdo mulitlinha.
    4. Detecta e extrai conteúdo CDATA (<![CDATA[...]]>) quando presente.
    5. Decodifica entidades HTML (&amp; → &, &lt; → <, &#160; etc.).
    6. Normaliza espaços (colapsa newlines, tabs, múltiplos espaços).
    7. Trunca a 80 caracteres (LLMs às vezes geram títulos muito longos).
    """
    if not content:
        return fallback

    # Passo 2 — remove comentários: <!-- qualquer coisa -->
    stripped = re.sub(r'<!--.*?-->', '', content, flags=re.DOTALL)

    # Passo 3 — busca <title [atributos]>...</title> (case-insensitive, multilinha)
    m = re.search(r'<title[^>]*>(.*?)</title>', stripped, re.IGNORECASE | re.DOTALL)
    if not m:
        return fallback

    raw = m.group(1)

    # Passo 4 — CDATA: <title><![CDATA[texto]]></title>
    cdata = re.match(r'\s*<!\[CDATA\[(.*?)\]\]>\s*$', raw, re.DOTALL)
    if cdata:
        raw = cdata.group(1)

    # Passo 5 — decodifica entidades HTML (&amp; → &, &lt; → <, &#169; → © etc.)
    unescaped = _html_lib.unescape(raw)

    # Passo 6 — normaliza espaços (colapsa \n, \t, espaços múltiplos)
    title = ' '.join(unescaped.split())

    if not title:
        return fallback

    # Passo 7 — trunca a 80 caracteres
    return title[:80]


def _extract_markdown_title(content: str, fallback: str = "Document") -> str:
    """
    Extrai o primeiro heading real (# a ######) de um documento Markdown.

    Estratégia:
    - Remove blocos de código fenced (``` ... ```) antes de buscar,
      para não capturar headings dentro de código (ex: exemplos de Markdown).
    - Busca linha começando com # seguido de espaço e conteúdo não vazio.
    - Remove # finais (setext-style trailing ###).
    - Trunca a 80 caracteres.
    """
    if not content:
        return fallback

    # Remove blocos fenced para não capturar headings dentro de código
    no_code = re.sub(r'```[\s\S]*?```', '', content)

    # Primeiro heading real: ^ seguido de 1-6 # e pelo menos um caractere não-espaço
    m = re.search(r'^#{1,6}\s+(.+)$', no_code, re.MULTILINE)
    if not m:
        return fallback

    title = m.group(1).strip().rstrip('#').strip()
    return title[:80] if title else fallback


def _extract_jsx_title(content: str, fallback: str = "React Component") -> str:
    """
    Extrai um título significativo de código JSX/TSX.

    Estratégia:
    - Busca o último identificador com nome iniciado em maiúscula (convenção
      React para componentes) definido com function/class/const/let.
    - Converte CamelCase para palavras separadas: "MyDashboard" → "My Dashboard".
    - Trunca a 80 caracteres.
    """
    m = re.search(r'(?:function|class|const|let)\s+([A-Z][a-zA-Z0-9_$]*)', content)
    if m:
        name = m.group(1)
        spaced = re.sub(r'(?<=[a-z0-9])(?=[A-Z])', ' ', name)
        return spaced[:80]
    return fallback


def detect_artifacts(content: str) -> list[dict]:
    """
    Analisa o conteúdo de uma resposta e extrai todos os Artifacts presentes.
    Retorna uma lista de dicts {"type": ..., "title": ..., "content": ...}.
    """
    artifacts = []

    # 1. Procurar blocos fenced de código (```lang ... ```)
    for m in re.finditer(r'```(\w*)\s*([\s\S]+?)```', content):
        lang = m.group(1).lower()
        body = m.group(2).strip()
        line_count = len(body.split("\n"))

        if lang == "html":
            artifacts.append({
                "type": "html",
                "title": _extract_html_svg_title(body, fallback="HTML Document"),
                "content": body,
            })
        elif lang == "svg":
            artifacts.append({
                "type": "svg",
                "title": _extract_html_svg_title(body, fallback="SVG Image"),
                "content": body,
            })
        elif lang in ("jsx", "tsx"):
            if line_count >= 8:
                artifacts.append({
                    "type": "jsx",
                    "title": _extract_jsx_title(body, fallback="React Component"),
                    "content": body,
                })
        elif lang in ("markdown", "md"):
            if line_count >= 8:
                artifacts.append({
                    "type": "markdown",
                    "title": _extract_markdown_title(body, fallback="Markdown Document"),
                    "content": body,
                })
        elif lang not in _EXCLUDED_LANGS_FROM_CODE:
            # Outros blocos de código se tiverem 15 ou mais linhas
            if line_count >= 15:
                artifacts.append({
                    "type": "code",
                    "title": f"{lang.upper() if lang else 'CODE'} Code",
                    "content": body,
                })

    # 2. Se nenhum bloco fenced foi encontrado, tentar bare HTML/SVG
    if not artifacts:
        # Bare HTML
        html_bare = re.search(
            r'(<!DOCTYPE\s+html[\s\S]+?</html>|<html[\s\S]+?</html>)',
            content,
            re.IGNORECASE,
        )
        if html_bare:
            body = html_bare.group(1).strip()
            artifacts.append({
                "type": "html",
                "title": _extract_html_svg_title(body, fallback="HTML Document"),
                "content": body,
            })

        # Bare SVG
        svg_bare = re.search(r'(<svg[\s\S]+?</svg>)', content, re.IGNORECASE)
        if svg_bare:
            body = svg_bare.group(1).strip()
            artifacts.append({
                "type": "svg",
                "title": _extract_html_svg_title(body, fallback="SVG Image"),
                "content": body,
            })

    # 3. Se nenhum artefato de código/HTML/SVG foi detectado,
    # verificar se a mensagem inteira é um Markdown estruturado longo
    if not artifacts:
        lines = content.split("\n")
        real_heading_count = sum(
            1 for line in lines if re.match(r'^#{1,6}\s+\S', line)
        )
        if len(lines) >= 20 and real_heading_count >= 2:
            artifacts.append({
                "type": "markdown",
                "title": _extract_markdown_title(content.strip(), fallback="Document"),
                "content": content.strip(),
            })

    return artifacts


def detect_artifact(content: str) -> dict | None:
    """
    Analisa o conteúdo e retorna o primeiro Artifact detectado (retrocompatibilidade).
    """
    arts = detect_artifacts(content)
    return arts[0] if arts else None


async def _save_artifact(db, conv_id: str, msg_id: str, detected: dict) -> str:
    """
    Persiste o artifact detectado no banco.

    Lógica de versionamento:
    - Se já existe um artifact do mesmo `type` nesta conversa, cria uma nova
      versão (v+1) dentro do mesmo grupo (artifact_group_id compartilhado).
    - Caso contrário, gera um novo group_id e começa em v1.

    Isso mapeia ao uso real: "refaça o dashboard com gráficos de barras"
    → v2 do mesmo HTML, sem criar um artifact paralelo.
    """
    # Busca o artifact mais recente do mesmo tipo nesta conversa
    async with db.execute(
        """SELECT artifact_group_id, version FROM artifacts
           WHERE conv_id = ? AND type = ?
           ORDER BY version DESC LIMIT 1""",
        (conv_id, detected["type"])
    ) as cur:
        existing = await cur.fetchone()

    if existing:
        group_id = existing[0]
        new_version = existing[1] + 1
    else:
        group_id = str(uuid.uuid4())
        new_version = 1

    artifact_id = str(uuid.uuid4())
    await db.execute(
        """INSERT INTO artifacts (id, conv_id, msg_id, type, title, content, version, artifact_group_id)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
        (
            artifact_id,
            conv_id,
            msg_id,
            detected["type"],
            detected["title"],
            detected["content"],
            new_version,
            group_id,
        ),
    )
    await db.commit()
    return artifact_id


@router.websocket("/ws/chat")
async def websocket_chat(ws: WebSocket):
    token = ws.query_params.get("token")
    user = None
    if token:
        user = decode_token(token)
    
    if not user:
        await ws.accept()
        await ws.send_json({"type": "error", "message": "Autenticação requerida."})
        await ws.close(code=4001)
        return

    await ws.accept()
    db = await get_db()

    try:
        while True:
            raw = await ws.receive_text()
            req = json.loads(raw)

            conversation_id = req.get("conversation_id")
            user_message = req.get("message", "").strip()
            model_id = req.get("model_id")
            provider_id = req.get("provider_id")
            bypass_cache = req.get("bypass_cache", False)
            attachment_ids = req.get("attachment_ids", [])

            fusion_mode = req.get("fusion", False)

            if not user_message or not model_id or not provider_id:
                await ws.send_json({"type": "error", "message": "Campos obrigatórios faltando."})
                continue

            # ── Ensure conversation exists ──────────────────────────────────
            if not conversation_id:
                conversation_id = str(uuid.uuid4())
                # Auto-title: first 60 chars of message
                title = user_message[:60] + ("…" if len(user_message) > 60 else "")
                await db.execute(
                    """INSERT INTO conversations (id, user_id, title, model_id, provider_id)
                       VALUES (?, ?, ?, ?, ?)""",
                    (conversation_id, user["id"], title, model_id, provider_id),
                )
                await db.commit()
                await ws.send_json({
                    "type": "conversation_created",
                    "conversation_id": conversation_id,
                    "title": title,
                })

            # ── Save user message ───────────────────────────────────────────
            user_msg_id = str(uuid.uuid4())
            await db.execute(
                """INSERT INTO messages (id, conversation_id, role, content, model_id, provider)
                   VALUES (?, ?, 'user', ?, ?, ?)""",
                (user_msg_id, conversation_id, user_message, model_id, provider_id),
            )
            await db.commit()

            # ── Move and associate attachments ──────────────────────────────
            if attachment_ids:
                from backend.attachments import move_attachments_to_conversation
                await move_attachments_to_conversation(attachment_ids, conversation_id, user_msg_id, db)

            # ── Web Search Resolution ────────────────────────────────────────
            web_search_requested = req.get("web_search", False)
            web_search_used = 0
            web_search_query = ""
            web_search_sources = []
            
            search_config = await get_web_search_config(db)
            search_results = []
            
            should_do_search = False
            trigger_type = None
            
            if search_config and search_config["enabled"]:
                if web_search_requested:
                    should_do_search = True
                    trigger_type = "manual"
                elif search_config["heuristic_enabled"]:
                    should, score = should_search(user_message, search_config["heuristic_sensitivity"])
                    if should:
                        should_do_search = True
                        trigger_type = "heuristic"
            
            if should_do_search:
                web_search_query = user_message
                await ws.send_json({"type": "search_start", "query": web_search_query})
                
                try:
                    search_results = await resolve_and_execute_search(web_search_query, db, search_config)
                    if search_results:
                        web_search_used = 1
                        web_search_sources = [{"title": r["title"], "url": r["url"]} for r in search_results]
                        
                        log_id = str(uuid.uuid4())
                        await db.execute(
                            """INSERT INTO web_search_log (id, conversation_id, message_id, query, trigger_type, results_count)
                               VALUES (?, ?, ?, ?, ?, ?)""",
                            (log_id, conversation_id, user_msg_id, web_search_query, trigger_type, len(search_results))
                        )
                        await db.commit()
                except Exception as e:
                    print(f"[Web Search Error] resolving/executing search: {e}")
                    search_results = []

            # ── Load conversation history with attachment support ───────────
            async with db.execute(
                """SELECT id, role, content FROM messages
                   WHERE conversation_id = ?
                   ORDER BY created_at ASC""",
                (conversation_id,),
            ) as cur:
                messages_rows = [{"id": r[0], "role": r[1], "content": r[2]} for r in await cur.fetchall()]

            # Fetch all attachments for this conversation's messages
            async with db.execute(
                """SELECT id, message_id, filename, mime_type, file_type, storage_path, file_hash 
                   FROM attachments 
                   WHERE message_id IN (SELECT id FROM messages WHERE conversation_id = ?)""",
                (conversation_id,)
            ) as cur:
                att_rows = await cur.fetchall()

            attachments_by_msg = {}
            for row in att_rows:
                att_id, m_id, filename, mime_type, file_type, storage_path, file_hash = row
                if m_id:
                    if m_id not in attachments_by_msg:
                        attachments_by_msg[m_id] = []
                    attachments_by_msg[m_id].append({
                        "id": att_id,
                        "filename": filename,
                        "mime_type": mime_type,
                        "file_type": file_type,
                        "storage_path": storage_path,
                        "file_hash": file_hash
                    })

            # Check if active model supports vision
            async with db.execute("SELECT supports_vision FROM models WHERE id = ?", (model_id,)) as cur:
                row = await cur.fetchone()
            model_supports_vision = bool(row[0]) if row else False

            relay_used = 0
            relay_model_id = None

            history = []
            for msg in messages_rows:
                msg_atts = attachments_by_msg.get(msg["id"], [])
                text_content = msg["content"]
                
                # 0. Web Search: Inject search results if available
                if msg["id"] == user_msg_id and web_search_used and search_results:
                    search_context = format_search_results(
                        search_results, 
                        web_search_query, 
                        template=search_config.get("injection_template")
                    )
                    text_content = f"{search_context}\n\n---\n\n{text_content}"
                
                # 1. Documents: Extract text and inject into text_content
                docs = [a for a in msg_atts if a["file_type"] == "document"]
                if docs:
                    doc_context = ""
                    for d in docs:
                        async with db.execute("SELECT extracted_text FROM attachments WHERE id = ?", (d["id"],)) as cur:
                            r = await cur.fetchone()
                        ext_text = r[0] if r else ""
                        doc_context += f"\n\n--- Conteúdo de {d['filename']} ---\n{ext_text}\n"
                    text_content = f"{doc_context}\n\n---\n\n{text_content}"

                # 2. Images: Direct multimodal or Vision Relay
                images = [a for a in msg_atts if a["file_type"] == "image"]
                if images:
                    if model_supports_vision:
                        # Direct multimodal
                        parts = [{"type": "text", "text": text_content}]
                        for img in images:
                            from backend.attachments.storage import get_absolute_path
                            import base64
                            try:
                                abs_img_path = get_absolute_path(img["storage_path"])
                                with open(abs_img_path, "rb") as f:
                                    b64 = base64.b64encode(f.read()).decode("utf-8")
                                parts.append({
                                    "type": "image_url",
                                    "image_url": {"url": f"data:{img['mime_type']};base64,{b64}"}
                                })
                            except Exception as e:
                                print(f"Error reading base64 image: {e}")
                        history.append({"role": msg["role"], "content": parts})
                    else:
                        # Vision Relay
                        image_descriptions = []
                        for img in images:
                            from backend.vision_relay.relay import describe_image_via_relay
                            try:
                                res = await describe_image_via_relay(
                                    img["storage_path"],
                                    img["mime_type"],
                                    img["file_hash"],
                                    user_id=user["id"],
                                    conversation_id=conversation_id
                                )
                                desc = res["description"]
                                image_descriptions.append(f"[Descrição da imagem {img['filename']}]: {desc}")
                                if msg["id"] == user_msg_id:
                                    relay_used = 1
                                    relay_model_id = res["relay_model"]
                            except Exception as e:
                                await ws.send_json({
                                    "type": "error",
                                    "message": f"Erro no Vision Relay: {str(e)}"
                                })
                                raise e
                        
                        if image_descriptions:
                            descriptions_block = "\n\n".join(image_descriptions)
                            text_content = f"{descriptions_block}\n\n---\n\n{text_content}"
                        history.append({"role": msg["role"], "content": text_content})
                else:
                    history.append({"role": msg["role"], "content": text_content})

            system_instruction = (
                "Você é o NexusLocal, uma IA assistente útil.\n"
                "Sempre que o usuário solicitar a criação de arquivos, códigos ou documentos (como HTML, SVG, Markdown, CSS, JS ou JSX), "
                "forneça o código completo diretamente dentro de um único bloco de código markdown correspondente (fenced code block).\n"
                "Importante: NÃO dê instruções de empacotamento, compactação ZIP, instalação de pipelines de CI/CD ou "
                "scripts de automação (como scripts BASH ou Node.js para criar o arquivo), a menos que o usuário "
                "solicite isso explicitamente. O download e a visualização do arquivo são gerenciados automaticamente pela interface."
            )
            history = [{"role": "system", "content": system_instruction}] + history

            # ── Fusion mode: delegate to orchestrator ──────────────────────
            # (detecção de artifact em Fusion é responsabilidade do orchestrator)
            if fusion_mode:
                from backend.fusion.orchestrator import executar_fusion
                # (Detecção de artifact em Fusion é responsabilidade do orchestrator)
                await executar_fusion(
                    user_message,
                    history,
                    ws,
                    conversation_id,
                    user.get("id") if user else None,
                    force_grounding=req.get("web_search", False)
                )
                continue

            # ── Check cache (before calling LLM) ───────────────────────────
            cache_hit = None
            if not bypass_cache:
                try:
                    cache_hit = await cache_manager.get(model_id, history)
                except Exception as e:
                    print(f"[cache] erro ao consultar: {e}")

            full_response = ""
            assistant_msg_id = str(uuid.uuid4())

            if cache_hit:
                # ── Serve from cache (with simulated streaming for UX) ──────
                await ws.send_json({
                    "type": "stream_start",
                    "conversation_id": conversation_id,
                    "from_cache": True,
                    "cache_type": cache_hit.cache_type,
                    "cache_similarity": round(cache_hit.similarity, 4),
                })

                full_response = cache_hit.response
                # Stream em chunks de ~4 chars para manter UX fluída
                chunk_size = 4
                for i in range(0, len(full_response), chunk_size):
                    chunk = full_response[i:i + chunk_size]
                    await ws.send_json({"type": "token", "content": chunk})
                    await asyncio.sleep(_CACHE_STREAM_DELAY)

            else:
                # ── Call LLM provider with Failover Cascade ─────────────────
                max_attempts = 3
                attempt = 0
                success = False
                original_model_id = model_id
                
                while attempt < max_attempts and not success:
                    attempt += 1
                    
                    try:
                        resolved = await resolve_model_with_failover(
                            model_id if attempt == 1 else original_model_id,
                            db,
                            failover_enabled=True # futuramente lido de config
                        )
                    except NoAvailableModelError as e:
                        await ws.send_json({"type": "error", "message": str(e)})
                        break
                        
                    if resolved.was_failover:
                        await ws.send_json({
                            "type": "failover_notice",
                            "original_model": original_model_id,
                            "fallback_model": resolved.display_name,
                            "reason": resolved.failover_reason or "rate_limit"
                        })
                        
                    current_model_id = resolved.model_id
                    current_provider_id = resolved.provider_id
                    
                    try:
                        provider = await get_provider(current_provider_id, db, user_id=user["id"])
                        model_name = await get_model_name(current_model_id, db)
                    except ValueError as e:
                        await ws.send_json({"type": "error", "message": str(e)})
                        break
                        
                    if attempt == 1:
                        await ws.send_json({
                            "type": "stream_start",
                            "conversation_id": conversation_id,
                            "from_cache": False,
                        })
                        
                    try:
                        async for token in provider.stream_chat(model=model_name, messages=history):
                            token_str = str(token)
                            full_response += token_str
                            await ws.send_json({"type": "token", "content": token_str})
                            
                        await mark_model_success(current_model_id, db)
                        await record_request(current_model_id, db)
                        success = True
                        
                        if resolved.was_failover:
                            log_id = str(uuid.uuid4())
                            await db.execute(
                                """INSERT INTO model_usage_log 
                                   (id, model_id, provider_id, conversation_id, user_id, was_fallback, fallback_from_model_id, fallback_reason)
                                   VALUES (?, ?, ?, ?, ?, 1, ?, ?)""",
                                (log_id, current_model_id, current_provider_id, conversation_id, user["id"], original_model_id, resolved.failover_reason or "rate_limit")
                            )
                            await db.commit()
                            
                        model_id = current_model_id
                        provider_id = current_provider_id
                        
                    except RateLimitError as e:
                        await mark_model_exhausted(current_model_id, db, e.retry_after, str(e))
                        if attempt == max_attempts:
                            await ws.send_json({"type": "error", "message": "Limite de tentativas de failover excedido. O modelo está esgotado."})
                        else:
                            continue
                            
                    except Exception as e:
                        error_msg = str(e)
                        await ws.send_json({"type": "error", "message": f"Erro ao chamar modelo: {error_msg}"})
                        await check_and_deactivate_model(current_model_id, error_msg, db)
                        break
                
                if not success:
                    continue

                # Save to cache in background
                if full_response:
                    asyncio.create_task(
                        cache_manager.set(model_id, history, full_response)
                    )

            # ── Save assistant message ──────────────────────────────────────
            await db.execute(
                """INSERT INTO messages (id, conversation_id, role, content, model_id, provider, relay_used, relay_model)
                   VALUES (?, ?, 'assistant', ?, ?, ?, ?, ?)""",
                (assistant_msg_id, conversation_id, full_response, model_id, provider_id, relay_used, relay_model_id),
            )
            await db.execute(
                "UPDATE conversations SET updated_at = datetime('now') WHERE id = ?",
                (conversation_id,),
            )
            await db.commit()

            # ── Save web search metadata to user message ───────────────────
            if web_search_used:
                await db.execute(
                    """UPDATE messages 
                       SET web_search_used = ?, web_search_query = ?, web_search_sources = ?
                       WHERE id = ?""",
                    (1, web_search_query, json.dumps(web_search_sources), user_msg_id),
                )
                await db.commit()

            # ── Detectar e salvar múltiplos artifacts (após stream completo) ───
            # Rodado DEPOIS do commit da mensagem para garantir que msg_id exista no banco.
            artifacts_list = []

            if full_response:
                try:
                    detected_list = detect_artifacts(full_response)
                    for detected in detected_list:
                        art_id = await _save_artifact(
                            db, conversation_id, assistant_msg_id, detected
                        )
                        artifacts_list.append({
                            "id": art_id,
                            "type": detected["type"],
                            "title": detected["title"]
                        })

                        # Emite evento de artifact individual para que a UI reaja
                        await ws.send_json({
                            "type": "artifact",
                            "id": art_id,
                            "artifact_type": detected["type"],
                            "title": detected["title"],
                            "conv_id": conversation_id,
                            "msg_id": assistant_msg_id,
                        })
                except Exception as e:
                    print(f"[artifact] erro ao detectar/salvar múltiplos: {e}")

            # ── Notifica fim do stream ──────────────────────────────────────
            await ws.send_json({
                "type": "stream_end",
                "message_id": assistant_msg_id,
                "conversation_id": conversation_id,
                "from_cache": cache_hit is not None,
                "cache_type": cache_hit.cache_type if cache_hit else None,
                "cache_similarity": round(cache_hit.similarity, 4) if cache_hit else None,
                # Retrocompatibilidade para o primeiro artifact
                "artifact_id": artifacts_list[0]["id"] if artifacts_list else None,
                "artifact_type": artifacts_list[0]["type"] if artifacts_list else None,
                "artifact_title": artifacts_list[0]["title"] if artifacts_list else None,
                "artifacts": artifacts_list,
                "relay_used": bool(relay_used),
                "relay_model": relay_model_id,
                "web_search_used": bool(web_search_used),
                "web_search_query": web_search_query,
                "web_search_sources": web_search_sources
            })

    except WebSocketDisconnect:
        pass
    finally:
        await db.close()