import asyncio
import json
import re
import time
import uuid
import datetime
from typing import Optional, Literal, Callable, Awaitable
from pydantic import BaseModel, Field

import aiosqlite

from backend import database as dbmod
from backend.database import (
    get_user_memory,
    create_memory_snapshot,
    record_dream_log,
    update_dream_log,
    _try_embed_fact,
)
from backend.providers.registry import get_provider, get_model_name
from backend.logging_config import get_logger

logger = get_logger(__name__)


# =========================================================
# PYDANTIC SCHEMAS
# =========================================================

class NewFactPayload(BaseModel):
    category: str = Field(..., description="Categoria do fato (tech, personal, project, preference, identity, professional)")
    fact_key: Optional[str] = Field(None, description="Chave semântica em snake_case")
    fact: str = Field(..., min_length=5, description="Texto do fato consolidado")
    confidence: float = Field(0.95, ge=0.0, le=1.0)
    is_pinned: bool = Field(False, description="Preserva status de fixado se originado de fato fixado")


class DreamOperation(BaseModel):
    action: Literal["merge", "supersede", "archive", "keep"]
    source_fact_ids: Optional[list[str]] = None
    old_fact_id: Optional[str] = None
    fact_id: Optional[str] = None
    new_fact: Optional[NewFactPayload] = None
    reason: Optional[str] = None


class DreamResponseSchema(BaseModel):
    summary_of_changes: str
    operations: list[DreamOperation]


class DreamSafetyError(Exception):
    """Exceção levantada quando a resposta do LLM viola os limiares de segurança e retenção."""
    pass


class DreamLLMError(Exception):
    """Exceção levantada em falhas de conexão ou truncamento severo do modelo."""
    pass


# =========================================================
# SYSTEM PROMPT DO CONSOLIDADOR
# =========================================================

_DREAM_SYSTEM_PROMPT = """Você é o Dream Consolidator, o agente de consolidação e higiene de memória do NexusLocal.
Sua missão é reorganizar o banco de memórias do usuário, eliminando redundâncias, resolvendo contradições e ancorando o tempo.

DATA DE REFERÊNCIA HOJE: {CURRENT_DATE}

REGRAS DE OURO:
1. PRESERVAÇÃO DA VERDADE: Nunca invente informações novas. Só sintetize ou reorganize com base no que já existe.
2. ANCORAGEM TEMPORAL: Transforme referências temporais flutuantes ("ontem", "no mês passado", "atualmente", "ano que vem") em marcos absolutos baseando-se na data original informada na linha de cada fato (ex: [CriadoEm: 2026-03-10] "comecei no novo emprego semana passada" -> "Iniciou no novo emprego em 2026-03-03").
3. RESOLUÇÃO DE CONTRADIÇÕES: Se o usuário dizia "mora em São Paulo" e depois diz "mudou-se para Curitiba", a informação mais recente PREVALECE. A informação antiga deve ser marcada como "supersede".
4. FUSÃO (MERGE): Agrupe múltiplos micro-fatos fragmentados do mesmo assunto em um único fato denso e informativo. Exemplo:
   Fato A: "Usa React no frontend"
   Fato B: "Prefere Tailwind e TypeScript"
   -> Fato Fundido: "Stack frontend: React com TypeScript e Tailwind CSS."
5. FATOS FIXADOS (PINNED) SÃO PROTEGIDOS: Fatos com Pinned: True são explicitamente prioritários. Você NUNCA pode arquivá-los isoladamente. Se um fato pinned participar de um MERGE ou SUPERSEDE, o novo fato resultante DEVE obrigatoriamente manter "is_pinned": true.
6. DISTINÇÃO TITULAR vs FAMÍLIA/DEPENDENTES: Nunca misture atributos ou preferências de dependentes/cônjuge com os do titular. Mantenha fatos familiares isolados sob categoria 'personal' e chaves com prefixo "family.*".
7. ISOLAMENTO DE PROJETOS DISTINTOS: Fatos com categoria "project" ou prefixo "project.<slug>" pertencem estritamente ao seu próprio escopo. NUNCA misture requisitos ou stacks de dois projetos diferentes.
8. ESTABILIDADE & ANTI-CHURN: Se um fato já estiver claro, denso e consolidado e não houver fatos novos ou contradições a seu respeito, MANTENHA-O com ação "keep". É proibido fazer alterações cosméticas de vocabulário, estilo ou pontuação.
9. ATENUAÇÃO TEMPORAL: Se um fato descreve um evento pontual ocorrido há mais de 90 dias em relação à data de hoje e não for fixado (pinned), marque-o como "archive" se perdeu relevância durável, ou mantenha com confiança reduzida.
10. ARQUIVAMENTO RESTRITO: Só marque ação "archive" para fatos comprovadamente efêmeros ou ruídos sem qualquer valor durável. Sempre forneça a justificativa em "reason".
11. ALIAS DE ID: Cada fato chega com um alias curto no campo ID (f1, f2, f3). Copie esse alias exatamente em fact_id, old_fact_id e source_fact_ids. Nunca invente, encurte nem reescreva o ID.

FORMATO DE RESPOSTA OBRIGATÓRIO (JSON PURO SEM MARKDOWN ADICIONAL):
{
  "summary_of_changes": "Resumo em 1 parágrafo das mudanças realizadas para o log de auditoria.",
  "operations": [
    {
      "action": "merge",
      "source_fact_ids": ["f1", "f2"],
      "new_fact": {
        "category": "tech",
        "fact_key": "tech.frontend_stack",
        "fact": "Stack frontend: React com TypeScript e Tailwind CSS",
        "confidence": 0.95,
        "is_pinned": false
      }
    },
    {
      "action": "supersede",
      "old_fact_id": "f3",
      "new_fact": {
        "category": "personal",
        "fact_key": "location.city",
        "fact": "Reside em Curitiba (mudou-se em 2026-10)",
        "confidence": 0.95,
        "is_pinned": false
      }
    },
    {
      "action": "archive",
      "fact_id": "f5",
      "reason": "Evento pontual ocorrido há mais de 90 dias sem valor contínuo"
    },
    {
      "action": "keep",
      "fact_id": "f4"
    }
  ]
}
"""


DREAM_REQUEST_TOKEN_BUDGET = 6000
_USER_PAYLOAD_PREFIX = "Fatos para Consolidação:\n"


def estimate_tokens(text: str) -> int:
    if not text:
        return 0
    return max(1, (len(text) + 3) // 4)


def _fact_scope(fact: dict) -> str:
    scope = fact.get("category") or "general"
    key = fact.get("fact_key") or ""
    if key.startswith("project."):
        parts = key.split(".")
        if len(parts) >= 2:
            return f"project:{parts[1]}"
    if key.startswith("family."):
        return "family"
    return scope


def render_facts_payload(
    facts: list[dict],
    current_date: str,
    alias_map: Optional[dict[str, str]] = None,
) -> tuple[dict[str, str], str]:
    """Monta o texto do lote usando aliases f1, f2… em vez do UUID."""
    if alias_map is None:
        alias_map = {f"f{i}": fact["id"] for i, fact in enumerate(facts, start=1)}
    id_to_alias = {real_id: alias for alias, real_id in alias_map.items()}
    lines = []
    for fact in facts:
        alias = id_to_alias[fact["id"]]
        created = fact.get("created_at") or current_date
        lines.append(
            f"[ID: {alias} | CriadoEm: {created} | "
            f"Pinned: {bool(fact.get('is_pinned'))} | Categoria: {fact.get('category')} | "
            f"Escopo: {_fact_scope(fact)}] {fact.get('fact') or ''}"
        )
    return alias_map, "\n".join(lines)


def split_facts_for_budget(
    facts: list[dict],
    system_prompt: str,
    max_tokens: int = DREAM_REQUEST_TOKEN_BUDGET,
) -> list[list[dict]]:
    """Fatia fatos para o pedido (prompt + lote) caber no teto de tokens."""
    if not facts:
        return []
    overhead = estimate_tokens(system_prompt) + estimate_tokens(_USER_PAYLOAD_PREFIX)
    chunks: list[list[dict]] = []
    current: list[dict] = []
    current_tokens = overhead
    for index, fact in enumerate(facts, start=1):
        line = (
            f"[ID: f{index} | CriadoEm: {fact.get('created_at') or ''} | "
            f"Pinned: {bool(fact.get('is_pinned'))} | Categoria: {fact.get('category')} | "
            f"Escopo: {_fact_scope(fact)}] {fact.get('fact') or ''}"
        )
        line_tokens = estimate_tokens(line) + 1
        if current and current_tokens + line_tokens > max_tokens:
            chunks.append(current)
            current = [fact]
            current_tokens = overhead + line_tokens
        else:
            current.append(fact)
            current_tokens += line_tokens
    if current:
        chunks.append(current)
    return chunks


def _resolve_fact_token(token: Optional[str], alias_map: dict[str, str], ids: list[str]) -> Optional[str]:
    if not token:
        return token
    if token in alias_map:
        return alias_map[token]
    if token in ids:
        return token
    if len(token) >= 8:
        matches = [real_id for real_id in ids if real_id.startswith(token)]
        if len(matches) == 1:
            return matches[0]
    return token


def remap_operation_ids(
    operations: list[DreamOperation],
    alias_map: dict[str, str],
    facts: list[dict],
) -> None:
    """Troca aliases (e prefixo único de UUID) pelo id real. ID inventado permanece."""
    ids = [fact["id"] for fact in facts]
    for op in operations:
        if op.fact_id:
            op.fact_id = _resolve_fact_token(op.fact_id, alias_map, ids)
        if op.old_fact_id:
            op.old_fact_id = _resolve_fact_token(op.old_fact_id, alias_map, ids)
        if op.source_fact_ids:
            op.source_fact_ids = [
                _resolve_fact_token(source_id, alias_map, ids) or source_id
                for source_id in op.source_fact_ids
            ]


def _llm_error_is_too_large(exc: Exception) -> bool:
    text = str(exc).lower()
    return "413" in text or "too large" in text or "request too large" in text


async def analyze_facts(
    facts: list[dict],
    system_prompt: str,
    caller: Callable[[str, str], Awaitable[str]],
    max_tokens: int = DREAM_REQUEST_TOKEN_BUDGET,
    current_date: Optional[str] = None,
) -> tuple[list[DreamOperation], list[str]]:
    """Chama o modelo em lotes que cabem no teto. 413 fatia de novo. Devolve IDs reais."""
    current_date = current_date or datetime.date.today().isoformat()
    alias_map, _full = render_facts_payload(facts, current_date)
    chunks = split_facts_for_budget(facts, system_prompt, max_tokens=max_tokens)
    all_ops: list[DreamOperation] = []
    notes: list[str] = []

    async def run_chunk(chunk: list[dict]) -> None:
        if not chunk:
            return
        _map, payload = render_facts_payload(chunk, current_date, alias_map)
        try:
            raw = await caller(system_prompt, payload)
        except DreamLLMError as exc:
            if _llm_error_is_too_large(exc) and len(chunk) > 1:
                mid = max(1, len(chunk) // 2)
                await run_chunk(chunk[:mid])
                await run_chunk(chunk[mid:])
                return
            raise
        data = json.loads(raw)
        schema = DreamResponseSchema(**data)
        remap_operation_ids(schema.operations, alias_map, facts)
        all_ops.extend(schema.operations)
        if schema.summary_of_changes:
            notes.append(schema.summary_of_changes)

    for chunk in chunks:
        await run_chunk(chunk)
    return all_ops, notes


_THINK_BLOCK = re.compile(r"<think>(.*?)</think>", re.DOTALL)


def _slice_json_object(text: str) -> str:
    text = (text or "").strip()
    if text.startswith("```"):
        lines = text.splitlines()
        if len(lines) >= 3 and lines[-1].strip().startswith("```"):
            text = "\n".join(lines[1:-1]).strip()
        else:
            text = re.sub(r"^```(?:json)?\s*", "", text)
            text = re.sub(r"\s*```$", "", text).strip()
    start = text.find("{")
    end = text.rfind("}")
    if start != -1 and end > start:
        return text[start:end + 1]
    return text


def extract_json_payload(raw: str) -> str:
    """Tira <think> e cerca markdown. Agnes 2.5 manda o JSON depois do raciocínio."""
    text = raw or ""
    insides = _THINK_BLOCK.findall(text)
    outside = _THINK_BLOCK.sub("", text)
    outside = re.sub(r"</?think>", "", outside)
    outside_json = _slice_json_object(outside)
    if outside_json.startswith("{") or outside_json.startswith("["):
        return outside_json
    inside_json = _slice_json_object("\n".join(insides))
    if inside_json.startswith("{") or inside_json.startswith("["):
        return inside_json
    return outside_json


async def iter_sse_events(queue: asyncio.Queue, heartbeat_s: float = 15.0):
    """Emite keepalive enquanto o modelo não manda o próximo passo."""
    while True:
        try:
            item = await asyncio.wait_for(queue.get(), timeout=heartbeat_s)
        except asyncio.TimeoutError:
            yield ": keepalive\n\n"
            continue
        if item is None:
            break
        yield f"data: {json.dumps(item, ensure_ascii=False)}\n\n"


# =========================================================
# VALIDAÇÃO DE SEGURANÇA E RETENÇÃO
# =========================================================

def verify_dream_safety(facts_before: list[dict], operations: list[DreamOperation]) -> None:
    """
    Verifica integridade das operações propostas:
    - Rejeita IDs inexistentes.
    - Garante que fatos is_pinned não sejam arquivados ou desfixados.
    - Aborta se > 60% dos fatos forem arquivados/descartados (para bancos com >= 8 fatos).
    - Aborta se o saldo total de fatos ativos cair abaixo de 20% do volume original.
    - Garante tamanho mínimo do texto consolidado.
    """
    existing_ids = {f["id"]: f for f in facts_before}
    pinned_ids = {f["id"] for f in facts_before if f.get("is_pinned")}

    archived_count = 0
    resulting_active_count = 0

    for op in operations:
        if op.action == "merge":
            if not op.source_fact_ids or len(op.source_fact_ids) < 2:
                raise DreamSafetyError("Operação de merge requer pelo menos 2 IDs de origem.")
            has_pinned_source = False
            for sid in op.source_fact_ids:
                if sid not in existing_ids:
                    raise DreamSafetyError(f"ID inexistente referenciado em merge: {sid}")
                if sid in pinned_ids:
                    has_pinned_source = True
            if not op.new_fact or not op.new_fact.fact or len(op.new_fact.fact.strip()) < 5:
                raise DreamSafetyError("Fato resultante de merge é inválido ou muito curto.")
            # Regra inegociável: herança do pin
            if has_pinned_source:
                op.new_fact.is_pinned = True
            resulting_active_count += 1

        elif op.action == "supersede":
            if not op.old_fact_id or op.old_fact_id not in existing_ids:
                raise DreamSafetyError(f"ID inexistente referenciado em supersede: {op.old_fact_id}")
            if not op.new_fact or not op.new_fact.fact or len(op.new_fact.fact.strip()) < 5:
                raise DreamSafetyError("Fato resultante de supersede é inválido ou muito curto.")
            if op.old_fact_id in pinned_ids:
                op.new_fact.is_pinned = True
            resulting_active_count += 1

        elif op.action == "archive":
            if not op.fact_id or op.fact_id not in existing_ids:
                raise DreamSafetyError(f"ID inexistente referenciado em archive: {op.fact_id}")
            if op.fact_id in pinned_ids:
                raise DreamSafetyError(f"Tentativa ilegal de arquivar fato fixado (PINNED): {op.fact_id}")
            archived_count += 1

        elif op.action == "keep":
            if not op.fact_id or op.fact_id not in existing_ids:
                raise DreamSafetyError(f"ID inexistente referenciado em keep: {op.fact_id}")
            resulting_active_count += 1

    total_before = len(facts_before)
    if total_before >= 8:
        if archived_count / total_before > 0.60:
            raise DreamSafetyError(
                f"Taxa de arquivamento perigosa ({archived_count}/{total_before} = {archived_count/total_before:.1%}). Operação abortada."
            )
        if resulting_active_count < total_before * 0.20:
            raise DreamSafetyError(
                f"Saldo projetado de fatos ({resulting_active_count}) caiu abaixo de 20% do original ({total_before}). Operação abortada."
            )


# =========================================================
# WATERFALL DE PROVEDOR E LLM
# =========================================================

async def resolve_dream_provider(user_id: str, custom_provider: str = None, custom_model: str = None):
    """
    Resolve o provedor para o Dream Memory com suporte a fallbacks:
      1. Configuração explícita do Dream (custom ou meta.dream_provider_id)
      2. Configuração do Extrator de Memória (meta.memory_extractor_*)
      3. Enhancer (tabela enhancer_config)
      4. Provedor padrão do chat
    """
    async with aiosqlite.connect(dbmod.DB_PATH) as db:
        # 1. Custom ou parâmetros dedicados do Dream em meta
        p_id = custom_provider
        m_id = custom_model
        if not p_id:
            async with db.execute("SELECT value FROM meta WHERE key = 'dream_provider_id'") as cur:
                row = await cur.fetchone()
                p_id = row[0] if row and row[0] else None
        if not m_id:
            async with db.execute("SELECT value FROM meta WHERE key = 'dream_model_id'") as cur:
                row = await cur.fetchone()
                m_id = row[0] if row and row[0] else None

        if p_id and m_id:
            try:
                prov = await get_provider(p_id, db, user_id=user_id)
                m_name = await get_model_name(m_id, db)
                return prov, m_name, p_id, m_id, "dream_dedicated"
            except Exception as e:
                logger.warning("[Dream] Provedor dedicado falhou ao resolver: %s", e)

        # 2. Extrator de memória
        async with db.execute("SELECT value FROM meta WHERE key = 'memory_extractor_provider_id'") as cur:
            row = await cur.fetchone()
            ext_p = row[0] if row and row[0] else None
        async with db.execute("SELECT value FROM meta WHERE key = 'memory_extractor_model_id'") as cur:
            row = await cur.fetchone()
            ext_m = row[0] if row and row[0] else None

        if ext_p and ext_m:
            try:
                prov = await get_provider(ext_p, db, user_id=user_id)
                m_name = await get_model_name(ext_m, db)
                return prov, m_name, ext_p, ext_m, "memory_extractor"
            except Exception:
                pass

        # 3. Enhancer config
        try:
            async with db.execute(
                "SELECT enhancer_provider_id, enhancer_model_id FROM enhancer_config WHERE id = 1"
            ) as cur:
                row = await cur.fetchone()
            if row and row[0] and row[1]:
                prov = await get_provider(row[0], db, user_id=user_id)
                m_name = await get_model_name(row[1], db)
                return prov, m_name, row[0], row[1], "enhancer"
        except Exception:
            pass

        # 4. Provedores habilitados livres (gemini, groq, etc.)
        async with db.execute(
            "SELECT id FROM providers WHERE enabled = 1 ORDER BY is_free DESC, id ASC"
        ) as cur:
            prov_rows = await cur.fetchall()

        for (cand_id,) in prov_rows:
            try:
                prov = await get_provider(cand_id, db, user_id=user_id)
                async with db.execute(
                    "SELECT id, name FROM models WHERE provider_id = ? AND enabled = 1 LIMIT 1",
                    (cand_id,),
                ) as m_cur:
                    m_row = await m_cur.fetchone()
                if m_row:
                    return prov, m_row[1], cand_id, m_row[0], "provider_fallback"
            except Exception:
                continue

    raise DreamLLMError("Nenhum provedor de IA disponível ou configurado para executar a consolidação.")


# =========================================================
# EXECUÇÃO DO LLM COM TRATAMENTO DE ERROS E RETRIES
# =========================================================

async def call_dream_llm(
    provider,
    model_name: str,
    provider_id: str,
    system_prompt: str,
    user_payload: str,
) -> str:
    """Executa a inferência LLM com 3 tentativas e sanitização de cercas de markdown."""
    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": f"Fatos para Consolidação:\n{user_payload}"},
    ]

    # Configuração explícita para Ollama local para impedir truncamento de contexto
    kwargs = {"temperature": 0.05}
    if provider_id == "ollama":
        kwargs["options"] = {"num_ctx": 8192, "temperature": 0.05}

    last_err = None
    for attempt in range(1, 4):
        full_response = ""
        try:
            if hasattr(provider, "stream_chat"):
                async for token in provider.stream_chat(model=model_name, messages=messages, **kwargs):
                    full_response += str(token)
            elif hasattr(provider, "chat"):
                resp = await provider.chat(model=model_name, messages=messages, **kwargs)
                full_response = resp if isinstance(resp, str) else str(resp)
            else:
                raise DreamLLMError(f"Provedor {provider} não suporta chat.")

            full_response = extract_json_payload(full_response)

            json.loads(full_response)
            return full_response

        except Exception as e:
            last_err = e
            logger.warning("[Dream] Tentativa %d falhou na chamada/parse do LLM: %s", attempt, e)
            kwargs["temperature"] = 0.10 + (attempt * 0.05)

    raise DreamLLMError(f"Falha ao obter resposta JSON válida do LLM após 3 tentativas: {last_err}")


# =========================================================
# APLICAÇÃO CIRÚRGICA (TRANSAÇÃO FLASH < 100MS)
# =========================================================

async def apply_dream_operations(
    user_id: str,
    dream_id: str,
    operations: list[DreamOperation],
    facts_before: list[dict],
) -> dict:
    """
    Aplica as operações validadas via transação relâmpago BEGIN IMMEDIATE.
    Retorna métricas consolidadas.
    """
    facts_merged_count = 0
    facts_superseded_count = 0
    facts_created_count = 0
    facts_archived_count = 0
    facts_kept_count = 0
    new_facts_to_embed = []

    async with aiosqlite.connect(dbmod.DB_PATH) as db:
        await db.execute("BEGIN IMMEDIATE")
        try:
            for op in operations:
                if op.action == "merge":
                    new_id = str(uuid.uuid4())
                    nf = op.new_fact
                    emb = _try_embed_fact(nf.fact)
                    await db.execute(
                        """INSERT INTO user_memory
                           (id, user_id, category, fact, fact_key, confidence, is_pinned,
                            is_active, status, source_dream_id, consolidated_at, version, embedding)
                           VALUES (?, ?, ?, ?, ?, ?, ?, 1, 'active', ?, datetime('now'), 1, ?)""",
                        (new_id, user_id, nf.category, nf.fact, nf.fact_key, nf.confidence,
                         1 if nf.is_pinned else 0, dream_id, emb),
                    )
                    facts_created_count += 1
                    if emb is None:
                        new_facts_to_embed.append((new_id, nf.fact))

                    for sid in (op.source_fact_ids or []):
                        await db.execute(
                            """UPDATE user_memory
                               SET is_active = 0, status = 'merged', superseded_by_id = ?,
                                   consolidated_at = datetime('now'), updated_at = datetime('now')
                               WHERE id = ? AND user_id = ?""",
                            (new_id, sid, user_id),
                        )
                        facts_merged_count += 1

                elif op.action == "supersede":
                    new_id = str(uuid.uuid4())
                    nf = op.new_fact
                    emb = _try_embed_fact(nf.fact)
                    await db.execute(
                        """INSERT INTO user_memory
                           (id, user_id, category, fact, fact_key, confidence, is_pinned,
                            is_active, status, source_dream_id, consolidated_at, version, embedding)
                           VALUES (?, ?, ?, ?, ?, ?, ?, 1, 'active', ?, datetime('now'), 1, ?)""",
                        (new_id, user_id, nf.category, nf.fact, nf.fact_key, nf.confidence,
                         1 if nf.is_pinned else 0, dream_id, emb),
                    )
                    facts_created_count += 1
                    if emb is None:
                        new_facts_to_embed.append((new_id, nf.fact))

                    await db.execute(
                        """UPDATE user_memory
                           SET is_active = 0, status = 'superseded', superseded_by_id = ?,
                               consolidated_at = datetime('now'), updated_at = datetime('now')
                           WHERE id = ? AND user_id = ?""",
                        (new_id, op.old_fact_id, user_id),
                    )
                    facts_superseded_count += 1

                elif op.action == "archive":
                    await db.execute(
                        """UPDATE user_memory
                           SET is_active = 0, status = 'archived',
                               consolidated_at = datetime('now'), updated_at = datetime('now')
                           WHERE id = ? AND user_id = ?""",
                        (op.fact_id, user_id),
                    )
                    facts_archived_count += 1

                elif op.action == "keep":
                    facts_kept_count += 1

            await db.commit()
        except Exception as e:
            await db.rollback()
            logger.error("[Dream] Erro durante transação de aplicação das operações:", exc_info=e)
            raise

    # Fora do Lock do Banco: FastEmbed batch para novas memórias se necessário
    if new_facts_to_embed:
        try:
            async with aiosqlite.connect(dbmod.DB_PATH) as db:
                for fid, txt in new_facts_to_embed:
                    emb = _try_embed_fact(txt)
                    if emb is not None:
                        await db.execute("UPDATE user_memory SET embedding = ? WHERE id = ?", (emb, fid))
                await db.commit()
        except Exception as e:
            logger.warning("[Dream] Erro ao gravar FastEmbed embeddings em lote: %s", e)

    # Reconciliação fora do lock: resumos rolling e cache semântico
    try:
        from backend.memory import refresh_memory_summaries, build_memory_fingerprint
        await refresh_memory_summaries(user_id, use_llm=False)
        await build_memory_fingerprint(user_id)
    except Exception as e:
        logger.warning("[Dream] Erro ao recalcular resumos pós-aplicação: %s", e)

    return {
        "facts_merged": facts_merged_count,
        "facts_superseded": facts_superseded_count,
        "facts_created": facts_created_count,
        "facts_archived": facts_archived_count,
        "facts_kept": facts_kept_count,
    }


# =========================================================
# SIMULAÇÃO (DRY-RUN / PREVIEW)
# =========================================================

async def simulate_dream_consolidation(
    user_id: str,
    custom_provider: str = None,
    custom_model: str = None,
) -> dict:
    """
    Executa a análise do Dream sem persistir nenhuma alteração no banco.
    Retorna o relatório de diff estruturado para revisão do usuário.
    """
    active_facts = await get_user_memory(user_id, limit=500, active_only=True)
    if not active_facts:
        return {
            "summary_of_changes": "Nenhum fato ativo encontrado para consolidação.",
            "operations": [],
            "facts_before": 0,
            "projected_active": 0,
            "actions_breakdown": {"merge": 0, "supersede": 0, "archive": 0, "keep": 0},
        }

    if len(active_facts) == 1:
        return {
            "summary_of_changes": "Apenas 1 fato ativo na memória. Nenhuma consolidação necessária.",
            "operations": [{"action": "keep", "fact_id": active_facts[0]["id"]}],
            "facts_before": 1,
            "projected_active": 1,
            "actions_breakdown": {"merge": 0, "supersede": 0, "archive": 0, "keep": 1},
        }

    provider, model_name, p_id, m_id, source = await resolve_dream_provider(
        user_id, custom_provider, custom_model
    )

    current_date = datetime.date.today().isoformat()
    system_prompt = _DREAM_SYSTEM_PROMPT.replace("{CURRENT_DATE}", current_date)

    async def caller(prompt: str, payload: str) -> str:
        return await call_dream_llm(provider, model_name, p_id, prompt, payload)

    operations, notes = await analyze_facts(active_facts, system_prompt, caller)
    schema = DreamResponseSchema(
        summary_of_changes=" ".join(notes) or "Simulação concluída.",
        operations=operations,
    )

    # Validação rigorosa dos limiares
    verify_dream_safety(active_facts, schema.operations)

    breakdown = {"merge": 0, "supersede": 0, "archive": 0, "keep": 0}
    for op in schema.operations:
        breakdown[op.action] = breakdown.get(op.action, 0) + 1

    projected_active = breakdown["keep"] + breakdown["merge"] + breakdown["supersede"]

    return {
        "summary_of_changes": schema.summary_of_changes,
        "operations": [op.dict() for op in schema.operations],
        "facts_before": len(active_facts),
        "projected_active": projected_active,
        "actions_breakdown": breakdown,
        "provider_id": p_id,
        "model_id": m_id,
    }


# =========================================================
# ORQUESTRADOR CENTRAL (EXECUÇÃO REAL ATÔMICA)
# =========================================================

async def execute_dream_consolidation(
    user_id: str,
    trigger_type: str = "dream_manual",
    custom_provider: str = None,
    custom_model: str = None,
    progress_cb: Optional[Callable[[str, int, str], Awaitable[None]]] = None,
) -> dict:
    """
    Executa o fluxo completo do Dream Memory:
      1. Snapshot atômico & leitura dos fatos
      2. Resolução do modelo LLM
      3. Análise semântica & geração de operações
      4. Validação de segurança anti-alucinação
      5. Aplicação relâmpago (<100ms) + FastEmbed + resumos
    """
    start_time = time.time()

    async def report(step: str, pct: int, msg: str):
        if progress_cb:
            try:
                await progress_cb(step, pct, msg)
            except Exception:
                pass

    await report("snapshot", 15, "Criando snapshot de segurança e calculando hash SHA-256...")
    snap_id, snap_hash = await create_memory_snapshot(user_id, trigger_type)

    active_facts = await get_user_memory(user_id, limit=500, active_only=True)
    if not active_facts:
        logger.info("[Dream] Usuário %s não possui fatos ativos. No-op.", user_id)
        return {"status": "no_op", "message": "Sem fatos ativos para consolidar."}

    provider, model_name, p_id, m_id, source = await resolve_dream_provider(
        user_id, custom_provider, custom_model
    )

    dream_id = await record_dream_log({
        "user_id": user_id,
        "snapshot_id": snap_id,
        "provider_id": p_id,
        "model_id": m_id,
        "facts_before": len(active_facts),
        "status": "running",
    })

    try:
        await report("connecting", 35, f"Conectado ao modelo {model_name} ({p_id}). Analisando memórias...")
        current_date = datetime.date.today().isoformat()
        system_prompt = _DREAM_SYSTEM_PROMPT.replace("{CURRENT_DATE}", current_date)

        await report("reasoning", 60, "Processando desduplicação, contradições e marcos temporais...")

        async def caller(prompt: str, payload: str) -> str:
            return await call_dream_llm(provider, model_name, p_id, prompt, payload)

        operations, notes = await analyze_facts(active_facts, system_prompt, caller, current_date=current_date)
        schema = DreamResponseSchema(
            summary_of_changes=" ".join(notes) or "Consolidação concluída.",
            operations=operations,
        )

        await report("validating", 80, "Verificando barreiras de integridade e retenção anti-ruído...")
        try:
            verify_dream_safety(active_facts, schema.operations)
        except DreamSafetyError as safety_err:
            duration_ms = int((time.time() - start_time) * 1000)
            await update_dream_log(dream_id, {
                "status": "aborted_safety",
                "error_message": str(safety_err),
                "duration_ms": duration_ms,
            })
            raise safety_err

        await report("persisting", 90, "Gravando transação flash (<100ms) e calculando embeddings FastEmbed...")
        stats = await apply_dream_operations(user_id, dream_id, schema.operations, active_facts)

        active_after = await get_user_memory(user_id, limit=500, active_only=True)
        duration_ms = int((time.time() - start_time) * 1000)

        await update_dream_log(dream_id, {
            "status": "success",
            "facts_after": len(active_after),
            "facts_merged": stats["facts_merged"],
            "facts_superseded": stats["facts_superseded"],
            "facts_created": stats["facts_created"],
            "facts_total_active": len(active_after),
            "duration_ms": duration_ms,
            "summary_notes": schema.summary_of_changes,
        })

        await report("done", 100, f"Consolidação concluída com sucesso! ({len(active_facts)} ➔ {len(active_after)} fatos).")

        return {
            "status": "success",
            "dream_id": dream_id,
            "snapshot_id": snap_id,
            "facts_before": len(active_facts),
            "facts_after": len(active_after),
            "compression_ratio": (len(active_facts) - len(active_after)) / len(active_facts) if active_facts else 0.0,
            "summary_notes": schema.summary_of_changes,
            "duration_ms": duration_ms,
            "stats": stats,
        }

    except Exception as exc:
        duration_ms = int((time.time() - start_time) * 1000)
        status_to_record = "aborted_safety" if isinstance(exc, DreamSafetyError) else "failed"
        await update_dream_log(dream_id, {
            "status": status_to_record,
            "error_message": str(exc)[:2000],
            "duration_ms": duration_ms,
            "facts_after": len(active_facts),
        })
        logger.error("[Dream] Falha na execução da consolidação: %s", exc, exc_info=exc)
        raise exc
