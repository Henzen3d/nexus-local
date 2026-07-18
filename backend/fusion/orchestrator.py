import asyncio
import json
import re
import uuid
from typing import List, Dict, Any, Optional
from fastapi import WebSocket
from backend.database import get_db, check_and_deactivate_model
from backend.logging_config import get_logger
from backend.orchestration.artifacts import detect_artifacts, save_artifact
from backend.providers.registry import get_provider, get_model_name

logger = get_logger(__name__)

# ──────────────────────────────────────────────────────────────────────────
# Configuração
# ──────────────────────────────────────────────────────────────────────────

TIMEOUT_MODELO_PARALELO = 90  # segundos — evita que 1 modelo travado segure o Fusion inteiro
TIMEOUT_BUSCA_WEB = 20
TIMEOUT_DETECCAO_CLAIMS = 30  # segundos — a detecção de claims não pode atrasar demais o Juiz
TIMEOUT_JUIZ = 180  # segundos — evita que um Juiz travado segure o Fusion indefinidamente
TIMEOUT_REFINAR = 45  # segundos — refino pré-fan-out não pode travar o Fusion inteiro

SELF_CRITIQUE_SUFFIX = (
    "\n\n---\nApós responder normalmente, adicione uma linha final no formato:\n"
    "`[CONFIANCA: alta|media|baixa — motivo em poucas palavras]`\n"
    "Use 'baixa' se você não tem certeza de algum dado, número, nome ou fato específico citado."
)

# Regex tolerante para a marcação de auto-crítica dos proposers:
# aceita acentos, maiúsculas/minúsculas e separadores variados antes do motivo.
CONFIDENCE_RE = re.compile(
    r"\[\s*CONFIAN[ÇC]A\s*[:：]?\s*(alta|m[ée]dia|baixa)\s*(?:[—–\-|:]+\s*([^\]]*))?\]",
    re.IGNORECASE,
)


def _extrair_confianca(texto: str) -> tuple[str, Optional[str], Optional[str]]:
    """Extrai a última marcação [CONFIANCA: ...] da resposta de um proposer.

    Retorna (texto_limpo, nivel, motivo). O texto limpo não contém a marcação
    crua — ela é enviada ao frontend como campo estruturado (badge) e ao Juiz
    como anotação no cabeçalho do bloco da resposta."""
    matches = list(CONFIDENCE_RE.finditer(texto))
    if not matches:
        return texto.strip(), None, None

    m = matches[-1]
    nivel = m.group(1).lower()
    nivel = "media" if nivel.startswith("m") else nivel
    motivo = (m.group(2) or "").strip() or None

    texto_limpo = CONFIDENCE_RE.sub("", texto).strip()
    # Remove um eventual separador horizontal órfão no fim (ex.: "---")
    texto_limpo = re.sub(r"\n[\s\-—–_*]+$", "", texto_limpo).strip()
    return texto_limpo, nivel, motivo


JUDGE_SYSTEM_PROMPT_DEFAULT = """Você é o Agente Juiz e Consolidador do NexusLocal.

Você vai receber a pergunta original do usuário, as respostas de N modelos diferentes, e \
possivelmente resultados de busca web verificando fatos específicos.

Siga este processo de raciocínio internamente, mas NÃO exponha essas etapas na resposta final \
(a resposta final deve ir direto ao ponto, como se você tivesse respondido sozinho):

1. EXTRAÇÃO: para cada resposta, identifique os pontos fortes e específicos que ela traz \
   (dados, exemplos, raciocínios, ângulos) — não trate as respostas como blocos monolíticos.
2. RECONCILIAÇÃO: onde as respostas divergem entre si em fatos, números ou conclusões, decida \
   qual versão é mais provável correta. Priorize:
   a) resultados de busca web fornecidos (se houver e forem relevantes ao conflito),
   b) respostas marcadas com [CONFIANCA: alta] sobre as marcadas [CONFIANCA: baixa],
   c) consenso entre múltiplos modelos independentes sobre a posição isolada de um só.
   Se não for possível resolver a divergência com confiança, sinalize a incerteza na resposta \
   final em vez de inventar uma resposta única falsamente confiante.
3. SÍNTESE: escreva a resposta final unificada, clara e completa, incorporando o melhor de \
   cada fonte e as correções da etapa de reconciliação. Não mencione que está consolidando \
   respostas de outros modelos, nem cite "[CONFIANCA: ...]" na resposta final — isso é só \
   para seu raciocínio interno.

Retorne apenas a resposta final em Markdown, direto ao usuário."""


async def _detectar_claims_verificaveis(
    provider_juiz, judge_model_name: str, pergunta: str, respostas_validas: list
) -> list[str]:
    """Pede ao próprio Juiz que identifique até 3 afirmações factuais checáveis
    que, se erradas, mudariam a resposta. Retorna lista de queries de busca (pode ser vazia)."""

    blocos = "\n\n".join(
        f"--- {r['model_id']} ---\n{r['response'][:1500]}" for r in respostas_validas
    )
    prompt_deteccao = f"""Pergunta do usuário: "{pergunta}"

Respostas dos modelos:
{blocos}

Liste até 3 afirmações factuais VERIFICÁVEIS (datas, números, nomes, eventos, versões de \
produto, status atual de algo) presentes nas respostas acima que, se estiverem erradas, \
mudariam a qualidade da resposta final. Ignore opiniões, criatividade ou raciocínio subjetivo.

Se não houver nenhuma afirmação que valha a pena verificar (pergunta puramente criativa, \
opinativa, ou os modelos concordam claramente), responda apenas: NENHUMA

Caso contrário, responda SOMENTE com uma lista em formato JSON de strings, cada uma sendo uma \
query de busca curta e direta para verificar o fato. Exemplo:
["versão atual do FastAPI 2026", "quando foi lançado o modelo X"]"""

    try:
        resposta = ""
        async for token in provider_juiz.stream_chat(
            model=judge_model_name,
            messages=[{"role": "user", "content": prompt_deteccao}],
        ):
            resposta += str(token)

        resposta = resposta.strip()
        if resposta.upper().startswith("NENHUMA"):
            return []

        # tolera o modelo devolver texto ao redor do JSON
        start, end = resposta.find("["), resposta.rfind("]")
        if start == -1 or end == -1:
            return []
        queries = json.loads(resposta[start:end + 1])
        return [q for q in queries if isinstance(q, str) and q.strip()][:3]
    except Exception:
        logger.warning("fusion grounding: erro ao detectar claims", exc_info=True)
        return []


async def _refinar_pergunta(
    provider_juiz, judge_model_name: str, prompt: str, history: list
) -> str:
    """Refina a pergunta do usuário para remover ambiguidades antes do fan-out."""
    
    system_prompt = (
        "Você é um refinador de prompts. Seu objetivo é pegar a pergunta do usuário e reescrevê-la para que fique cristalina, "
        "resolvendo ambiguidades e completando referências implícitas (como 'ele', 'isso', 'anterior') com base no histórico da conversa.\n\n"
        "REGRAS:\n"
        "1. Clarifique sem prescrever: deixe explícito O QUE o usuário quer, mas NÃO prescreva COMO responder. Preserve a abertura para diferentes abordagens.\n"
        "2. EXTREMAMENTE IMPORTANTE: Só altere a pergunta se houver uma ambiguidade REAL dependente do histórico (ex: uso de pronomes ou continuidade de assunto). "
        "Se a pergunta já é compreensível e auto-contida, você DEVE retornar EXATAMENTE o texto original. Não tente 'melhorar', reescrever datas relativas ou adicionar colchetes didáticos à pergunta.\n"
        "3. Retorne APENAS o texto da pergunta refinada (ou original), sem comentários, aspas extras, ou explicações."
    )
    
    # Só o histórico recente — evita prompt enorme (ex.: system de projeto) no refinador
    hist_curto = []
    for m in history:
        if not isinstance(m, dict):
            continue
        role = m.get("role")
        if role not in ("user", "assistant"):
            continue
        content = m.get("content")
        if isinstance(content, list):
            text_parts = [
                str(p.get("text", "")) for p in content if isinstance(p, dict) and p.get("type") == "text"
            ]
            content = "\n".join(text_parts)
        if not isinstance(content, str) or not content.strip():
            continue
        # Cap por mensagem para não estourar free-tier no refine
        hist_curto.append({"role": role, "content": content[:2000]})
    hist_curto = hist_curto[-6:]

    mensagens = [{"role": "system", "content": system_prompt}] + hist_curto
    if not any(m.get("role") == "user" for m in hist_curto):
        mensagens.append({"role": "user", "content": prompt[:4000]})

    try:
        async def _stream_refine() -> str:
            resposta = ""
            async for token in provider_juiz.stream_chat(
                model=judge_model_name,
                messages=mensagens,
            ):
                resposta += str(token)
            return resposta

        resposta = await asyncio.wait_for(_stream_refine(), timeout=TIMEOUT_REFINAR)
        resposta_limpa = resposta.strip()

        # Se a IA encapsular com aspas, removemos
        if resposta_limpa.startswith('"') and resposta_limpa.endswith('"'):
            resposta_limpa = resposta_limpa[1:-1].strip()

        # Refino vazio ou absurdamente longo → fallback
        if not resposta_limpa or len(resposta_limpa) > max(len(prompt) * 4, 4000):
            return prompt

        return resposta_limpa
    except asyncio.TimeoutError:
        logger.warning("fusion refinement: timeout após %ss — usando pergunta original", TIMEOUT_REFINAR)
        return prompt
    except Exception:
        logger.warning("fusion refinement: erro ao refinar pergunta", exc_info=True)
        return prompt


def _precisa_refinar(prompt: str, history: list) -> bool:
    """Heurística rápida: só aciona o refinador se houver sinais de ambiguidade.
    Suporta todas as línguas de tradução ativa no sistema (PT, EN, ES, FR, DE, JA, KO)."""
    # Primeira mensagem da conversa — não há contexto anterior para desambiguar
    user_msgs = [m for m in history if isinstance(m, dict) and m.get("role") == "user"]
    if len(user_msgs) <= 1:
        return False

    # Padrões para línguas com limite de palavra (\b)
    # (Português, Inglês, Espanhol, Francês, Alemão)
    patterns_western = [
        # Português
        r'isso|isto|ele[s]?|ela[s]?|anterior|acima|aquilo|o mesmo|a mesma|o que disse|como mencionei|continue|continua|e quanto|sobre aquilo|nesse caso|desse jeito|esse tema|essa questão|do que falamos',
        # English
        r'this|that|it|he|she|they|him|her|them|above|former|latter|aforesaid|same|continue|go on|what about|about that|in this case|in that case|what I said|as I mentioned',
        # Español
        r'esto|eso|aquello|él|ella|ellos|ellas|anterior|arriba|lo mismo|la misma|continua|continúa|qué hay de|sobre eso|en este caso|en ese caso|lo que dije|como mencioné',
        # Français
        r'ceci|cela|ça|il|elle|ils|elles|le|la|les|lui|leur|précédent|ci-dessus|continuer|qu\'en est-il|à ce sujet|dans ce cas|ce que j\'ai dit|comme mentionné',
        # Deutsch
        r'dies|das|es|er|sie|ihm|ihn|ihnen|vorherige|oben|weiter|weitergehen|was ist mit|darüber|in diesem Fall|was ich gesagt habe|wie erwähnt'
    ]
    
    combined_western = r'\b(' + '|'.join(patterns_western) + r')\b'
    if re.search(combined_western, prompt, re.IGNORECASE):
        return True

    # Padrões para línguas sem limite de palavra (Japonês, Coreano)
    patterns_asian = [
        # Japanese (これ, それ, あれ, 彼, 彼女, 前の, 続き, 続けて, さっき)
        r'これ|それ|あれ|彼|彼女|前の|続き|続けて|さっき',
        # Korean (이것, 그것, 저것, 그, 그녀, 이전, 계속, 아까, 앞서)
        r'이것|그것|저것|그|그녀|이전|계속|아까|앞서'
    ]
    combined_asian = '|'.join(patterns_asian)
    if re.search(combined_asian, prompt):
        return True

    return False


async def _buscar_web(query: str, search_config: dict) -> Optional[str]:
    """Usa o motor de busca web real do NexusLocal."""
    try:
        from backend.web_search import resolve_and_execute_search, format_search_results
        from backend.database import get_db
        
        db = await get_db()
        try:
            results = await asyncio.wait_for(
                resolve_and_execute_search(query, db, search_config), 
                timeout=TIMEOUT_BUSCA_WEB
            )
            if results:
                return format_search_results(
                    results, 
                    query, 
                    template=search_config.get("injection_template")
                )
            return None
        finally:
            await db.close()
    except Exception:
        logger.warning("fusion grounding: erro na busca '%s'", query, exc_info=True)
        return None


async def executar_fusion(
    prompt: str,
    history: list,
    websocket: WebSocket,
    conversation_id: str,
    user_id: str | None = None,
    force_grounding: bool = False,
    web_search_already_done: bool = False,
    client_timezone_offset: int | None = None,
):
    db = await get_db()
    try:
        async with db.execute(
            "SELECT id, provider_id, model_id, position FROM fusion_models ORDER BY position"
        ) as cur:
            modelos_rows = await cur.fetchall()

        async with db.execute(
            "SELECT judge_provider_id, judge_model_id, judge_system_prompt, grounding_enabled "
            "FROM fusion_config WHERE id = 1"
        ) as cur:
            juiz_row = await cur.fetchone()

        from backend.web_search import get_web_search_config
        search_config = await get_web_search_config(db)
    finally:
        await db.close()

    if not modelos_rows:
        await websocket.send_json({"type": "error", "message": "Nenhum modelo paralelo configurado para o Fusion."})
        return

    if not juiz_row:
        await websocket.send_json({"type": "error", "message": "Modelo Juiz não configurado."})
        return

    judge_provider_id, judge_model_id, judge_system_prompt, config_grounding = juiz_row
    judge_system_prompt = judge_system_prompt or JUDGE_SYSTEM_PROMPT_DEFAULT
    config_grounding = True if config_grounding is None else bool(config_grounding)

    # Grounding roda se estiver habilitado na config do Fusion OU se o usuário
    # ativou a busca web nesta mensagem — sempre condicionado à busca web global.
    # Se a busca web global já foi executada para o prompt inicial, pulamos
    # a verificação factual para não repetir o trabalho e economizar tempo e quota.
    web_search_ok = bool(search_config and search_config.get("enabled"))
    grounding_enabled = (config_grounding or force_grounding) and web_search_ok and not web_search_already_done

    modelos = [
        {"id": r[0], "provider_id": r[1], "model_id": r[2], "position": r[3]}
        for r in modelos_rows
    ]

    # ── Instanciar o Juiz (necessário para refinamento e fases posteriores) ──
    conn = await get_db()
    try:
        provider_juiz = await get_provider(judge_provider_id, conn, user_id=user_id)
        judge_model_name = await get_model_name(judge_model_id, conn)
    finally:
        await conn.close()

    # ── Refinamento da Pergunta (condicional) ────────────────────────────
    # Só refina se houver sinais de ambiguidade (pronomes, referências a
    # contexto anterior). Perguntas auto-contidas pulam direto pro fan-out,
    # evitando 5-45s de latência desnecessária no free-tier.
    prompt_refinado = prompt
    if _precisa_refinar(prompt, history):
        await websocket.send_json({"type": "fusion_phase", "phase": "refining"})
        prompt_refinado = await _refinar_pergunta(provider_juiz, judge_model_name, prompt, history)

    # ── Agora sim mostra os modelos — sem espera fantasma ────────────────
    await websocket.send_json({
        "type": "fusion_start",
        "models": [m["model_id"] for m in modelos],
    })
    await websocket.send_json({"type": "fusion_phase", "phase": "proposers"})

    # Substituir no history apenas para os modelos (o bd ainda guarda o original)
    history_para_modelos = [dict(m) for m in history]
    if history_para_modelos and history_para_modelos[-1].get("role") == "user":
        original_content = history_para_modelos[-1]["content"]
        if isinstance(original_content, str):
            history_para_modelos[-1]["content"] = original_content.replace(prompt, prompt_refinado)
        elif isinstance(original_content, list):
            # Caso seja multimodal (com imagens), substituímos na parte de texto
            for part in original_content:
                if part.get("type") == "text":
                    part["text"] = part["text"].replace(prompt, prompt_refinado)

    if prompt_refinado != prompt:
        await websocket.send_json({
            "type": "fusion_refined_prompt",
            "prompt": prompt_refinado
        })

    async def chamar_modelo(modelo: dict) -> dict:
        from backend.ranking.failover import resolve_model_with_failover

        try:
            conn = await get_db()
            try:
                resolved = await resolve_model_with_failover(modelo["model_id"], conn)
                final_model_id = resolved.model_id
                final_provider_id = resolved.provider_id

                await websocket.send_json({
                    "type": "fusion_status",
                    "model_id": final_model_id,
                    "provider_id": final_provider_id,
                    "status": "running",
                    "was_fallback": resolved.was_failover,
                    "original_model_id": resolved.original_model_id if resolved.was_failover else None
                })

                provider = await get_provider(final_provider_id, conn, user_id=user_id)
                model_name = await get_model_name(final_model_id, conn)
            finally:
                await conn.close()

            # Injeta a instrução de auto-crítica na última mensagem do usuário,
            # usando o histórico já refinado (se foi).
            history_com_critica = [dict(m) for m in history_para_modelos]
            if history_com_critica and history_com_critica[-1].get("role") == "user":
                history_com_critica[-1]["content"] = (
                    history_com_critica[-1]["content"] + SELF_CRITIQUE_SUFFIX
                )

            async def _stream():
                texto = ""
                async for token in provider.stream_chat(model=model_name, messages=history_com_critica):
                    texto += str(token)
                return texto

            resposta = await asyncio.wait_for(_stream(), timeout=TIMEOUT_MODELO_PARALELO)

            # Extrai a auto-crítica [CONFIANCA: ...] — o frontend recebe o campo
            # estruturado (badge) e o texto limpo, sem a marcação crua.
            resposta_limpa, confianca, motivo_confianca = _extrair_confianca(resposta)

            await websocket.send_json({
                "type": "fusion_status",
                "model_id": final_model_id,
                "status": "done",
                "response": resposta_limpa,
                "confidence": confianca,
                "confidence_reason": motivo_confianca,
            })
            return {
                "model_id": final_model_id,
                "response": resposta_limpa,
                "confidence": confianca,
                "confidence_reason": motivo_confianca,
                "status": "done",
            }

        except asyncio.TimeoutError:
            logger.warning("fusion: timeout no modelo %s", modelo['model_id'])
            await websocket.send_json({
                "type": "fusion_status",
                "model_id": modelo["model_id"],
                "status": "error",
                "error_reason": "timeout",
            })
            return {"model_id": modelo["model_id"], "response": "", "status": "error"}

        except Exception as e:
            error_msg = str(e)
            logger.error("fusion: erro no modelo %s: %s", modelo["model_id"], error_msg)
            await check_and_deactivate_model(modelo["model_id"], error_msg)
            await websocket.send_json({
                "type": "fusion_status",
                "model_id": modelo["model_id"],
                "status": "error",
            })
            return {"model_id": modelo["model_id"], "response": "", "status": "error"}

    resultados = await asyncio.gather(*[chamar_modelo(m) for m in modelos])
    respostas_validas = [r for r in resultados if r["status"] == "done" and r["response"]]

    if not respostas_validas:
        await websocket.send_json({"type": "error", "message": "Nenhum modelo retornou resposta válida."})
        return

    # provider_juiz e judge_model_name já instanciados antes do fan-out

    # ── Grounding: detectar claims verificáveis e buscar na web ────────
    grounding_texto = ""
    if grounding_enabled:
        await websocket.send_json({"type": "fusion_grounding", "status": "checking"})
        try:
            queries = await asyncio.wait_for(
                _detectar_claims_verificaveis(
                    provider_juiz, judge_model_name, prompt, respostas_validas
                ),
                timeout=TIMEOUT_DETECCAO_CLAIMS,
            )
        except asyncio.TimeoutError:
            logger.warning("fusion grounding: timeout na detecção de claims — seguindo sem grounding")
            queries = []

        if queries:
            await websocket.send_json({
                "type": "fusion_grounding",
                "status": "searching",
                "queries": queries,
            })
            resultados_busca = await asyncio.gather(
                *[_buscar_web(q, search_config) for q in queries], return_exceptions=False
            )
            partes = [
                f"Busca: \"{q}\"\n{res}"
                for q, res in zip(queries, resultados_busca) if res
            ]
            if partes:
                grounding_texto = "\n\n".join(partes)

        await websocket.send_json({
            "type": "fusion_grounding",
            "status": "done",
            "found": bool(grounding_texto),
        })

    # ── Monta mensagens do Juiz: system separado do conteúdo ───────────
    def _cabecalho_resposta(r: dict) -> str:
        if r.get("confidence"):
            motivo = f" — {r['confidence_reason']}" if r.get("confidence_reason") else ""
            return f"--- RESPOSTA: {r['model_id']} [CONFIANCA: {r['confidence']}{motivo}] ---"
        return f"--- RESPOSTA: {r['model_id']} ---"

    blocos = "\n\n".join([
        f"{_cabecalho_resposta(r)}\n{r['response']}"
        for r in respostas_validas
    ])

    import datetime
    if client_timezone_offset is not None:
        try:
            # client_timezone_offset is in minutes (positive for west of UTC, negative for east)
            # In Python timedelta, positive is east, so we invert the sign.
            tz = datetime.timezone(datetime.timedelta(minutes=-int(client_timezone_offset)))
            current_date = datetime.datetime.now(tz).strftime("%d/%m/%Y %H:%M")
        except Exception:
            current_date = datetime.datetime.now().strftime("%d/%m/%Y %H:%M")
    else:
        current_date = datetime.datetime.now().strftime("%d/%m/%Y %H:%M")

    # O Juiz precisa do histórico da conversa para manter contexto, além
    # de receber os resultados da busca web inicial (que estão na última
    # mensagem do usuário em `history`).
    mensagens_juiz = [dict(m) for m in history]
    
    judge_system_prompt_final = (
        f"{judge_system_prompt}\n\n"
        f"[INFORMAÇÃO DO SISTEMA]\n"
        f"Data atual do sistema: {current_date}. Você deve usar esta data como referência para o tempo presente."
    )

    # Substitui a instrução de sistema padrão pela do Juiz
    if mensagens_juiz and mensagens_juiz[0].get("role") == "system":
        mensagens_juiz[0]["content"] = judge_system_prompt_final
    else:
        mensagens_juiz.insert(0, {"role": "system", "content": judge_system_prompt_final})

    # Anexa as respostas para consolidação na última mensagem do usuário
    if mensagens_juiz and mensagens_juiz[-1].get("role") == "user":
        extra_content = f"\n\n--- RESPOSTAS DOS MODELOS PARALELOS PARA CONSOLIDAÇÃO ---\n{blocos}"
        if grounding_texto:
            extra_content += (
                f"\n\n--- RESULTADOS DE BUSCA WEB (FACT-CHECKING POSTERIOR) ---\n"
                f"Priorize essas informações factuais sobre as respostas dos modelos:\n{grounding_texto}"
            )
        
        orig_content = mensagens_juiz[-1]["content"]
        if isinstance(orig_content, str):
            mensagens_juiz[-1]["content"] = orig_content + extra_content
        elif isinstance(orig_content, list):
            for part in reversed(orig_content):
                if part.get("type") == "text":
                    part["text"] += extra_content
                    break

    await websocket.send_json({
        "type": "fusion_judge_start",
        "model_id": judge_model_id,
    })

    full_response = ""
    try:
        await websocket.send_json({
            "type": "stream_start",
            "conversation_id": conversation_id,
            "from_cache": False,
        })

        async def _stream_juiz():
            nonlocal full_response
            async for token in provider_juiz.stream_chat(
                model=judge_model_name,
                messages=mensagens_juiz,
            ):
                token_str = str(token)
                full_response += token_str
                await websocket.send_json({"type": "token", "content": token_str})

        await asyncio.wait_for(_stream_juiz(), timeout=TIMEOUT_JUIZ)

    except asyncio.TimeoutError:
        await websocket.send_json({"type": "error", "message": "Timeout no modelo Juiz."})
        return
    except Exception as e:
        error_msg = str(e)
        await check_and_deactivate_model(judge_model_id, error_msg)
        await websocket.send_json({"type": "error", "message": f"Erro no modelo Juiz: {error_msg}"})
        return

    # Guarda anti-vazamento: o Juiz é instruído a não citar [CONFIANCA: ...],
    # mas removemos qualquer ocorrência residual antes de persistir.
    if CONFIDENCE_RE.search(full_response):
        full_response = CONFIDENCE_RE.sub("", full_response).strip()

    assistant_msg_id = str(uuid.uuid4())
    db = await get_db()
    try:
        await db.execute(
            """INSERT INTO messages (id, conversation_id, role, content, model_id)
               VALUES (?, ?, 'assistant', ?, ?)""",
            (assistant_msg_id, conversation_id, full_response, judge_model_id),
        )
        await db.execute(
            "UPDATE conversations SET updated_at = datetime('now') WHERE id = ?",
            (conversation_id,),
        )
        await db.commit()
    finally:
        await db.close()

    # ── Detectar e salvar múltiplos artifacts (após consolidar no Juiz) ───
    artifacts_list = []

    if full_response:
        try:
            from backend.orchestration.artifacts import detect_artifacts, save_artifact
            db = await get_db()
            try:
                detected_list = detect_artifacts(full_response)
                for detected in detected_list:
                    art_id = await save_artifact(
                        db, conversation_id, assistant_msg_id, detected
                    )
                    artifacts_list.append({
                        "id": art_id,
                        "type": detected["type"],
                        "title": detected["title"]
                    })

                    await websocket.send_json({
                        "type": "artifact",
                        "id": art_id,
                        "artifact_type": detected["type"],
                        "title": detected["title"],
                        "conv_id": conversation_id,
                        "msg_id": assistant_msg_id,
                    })
            finally:
                await db.close()
        except Exception:
            logger.exception("fusion artifact detect/save failed")

    await websocket.send_json({
        "type": "stream_end",
        "message_id": assistant_msg_id,
        "conversation_id": conversation_id,
        "from_cache": False,
        # Retrocompatibilidade
        "artifact_id": artifacts_list[0]["id"] if artifacts_list else None,
        "artifact_type": artifacts_list[0]["type"] if artifacts_list else None,
        "artifact_title": artifacts_list[0]["title"] if artifacts_list else None,
        "artifacts": artifacts_list
    })
