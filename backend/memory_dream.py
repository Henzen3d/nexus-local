import asyncio
import inspect
import json
import re
import time
import uuid
import datetime
from typing import Optional, Literal, Callable, Awaitable, Any
from pydantic import BaseModel, Field, model_validator

import aiosqlite

from backend import database as dbmod
from backend.database import (
    get_user_memory,
    create_memory_snapshot,
    record_dream_log,
    update_dream_log,
    _try_embed_fact,
)
from backend.providers.base import ProviderHTTPError, RateLimitError
from backend.providers.registry import get_provider, get_model_name
from backend.logging_config import get_logger

logger = get_logger(__name__)

# Limites e prazos de execução do Dream Consolidator (T1.2)
DREAM_MAX_RESPONSE_CHARS = 250_000
DREAM_EXECUTION_DEADLINE_S = 180.0
DREAM_PER_CALL_TIMEOUT_S = 30.0
DREAM_MAX_CANDIDATES_PER_BATCH = 3


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

    @model_validator(mode="after")
    def _validate_action_fields(self) -> "DreamOperation":
        if self.action == "merge":
            if not self.source_fact_ids or len(self.source_fact_ids) < 1:
                raise ValueError("Operação 'merge' requer 'source_fact_ids' não vazio.")
            if self.new_fact is None:
                raise ValueError("Operação 'merge' requer 'new_fact'.")
        elif self.action == "supersede":
            if not self.old_fact_id:
                raise ValueError("Operação 'supersede' requer 'old_fact_id'.")
            if self.new_fact is None:
                raise ValueError("Operação 'supersede' requer 'new_fact'.")
        elif self.action in ("keep", "archive"):
            if not self.fact_id:
                raise ValueError(f"Operação '{self.action}' requer 'fact_id'.")
        return self


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
3. RESOLUÇÃO DE CONTRADIÇÕES: Se o usuário dizia "mora em São Paulo" e depois diz "mudou-se para Curitiba", a informação mais recente PREVALECE. A informação antiga deve ser marcada como "supersede". PROIBIDO resolver contradição de número inventando um terceiro número. Se um fato diz 46 e outro diz 10, mantenha os dois números que já estão escritos. Não calcule ano de nascimento. Não escreva "ajustado por consistência".
4. FUSÃO (MERGE): Agrupe múltiplos micro-fatos fragmentados do mesmo assunto em um único fato denso e informativo. Exemplo:
   Fato A: "Usa React no frontend"
   Fato B: "Prefere Tailwind e TypeScript"
   -> Fato Fundido: "Stack frontend: React com TypeScript e Tailwind CSS."
5. FATOS FIXADOS (PINNED) SÃO PROTEGIDOS: Fatos com Pinned: True são explicitamente prioritários. Você NUNCA pode arquivá-los isoladamente. Se um fato pinned participar de um MERGE ou SUPERSEDE, o novo fato resultante DEVE obrigatoriamente manter "is_pinned": true.
6. DISTINÇÃO TITULAR vs FAMÍLIA/DEPENDENTES: Nunca misture atributos ou preferências de dependentes/cônjuge com os do titular. Mantenha fatos familiares isolados sob categoria 'personal' e chaves com prefixo "family.*".
7. ISOLAMENTO DE PROJETOS DISTINTOS: Fatos com categoria "project" ou prefixo "project.<slug>" pertencem estritamente ao seu próprio escopo. NUNCA misture requisitos ou stacks de dois projetos diferentes.
8. ESTABILIDADE & ANTI-CHURN: Se um fato já estiver claro, denso e consolidado e não houver fatos novos ou contradições a seu respeito, MANTENHA-O com ação "keep". É proibido fazer alterações cosméticas de vocabulário, estilo ou pontuação.
9. ATENUAÇÃO TEMPORAL VS. FATOS PERMANENTES:
   - PROIBIDO ARQUIVAR FATOS BIOGRÁFICOS OU DURÁVEIS: Informações de formação acadêmica, histórico familiar, condições médicas/alergias, traços de identidade, preferências duradouras ou marcos profissionais NUNCA devem ser arquivadas por antiguidade, mesmo que tenham ocorrido há anos.
   - ARQUIVAMENTO RESTRITO A EVENTOS EFÊMEROS E TAREFAS PASSADAS: Apenas arquive fatos que representavam ações passageiras pontuais já superadas (ex: "preciso consertar a torneira", "estou gripado hoje", "viajando no fim de semana"), desde que o evento tenha ocorrido há mais de 30 dias e não tenha impacto futuro.
10. PRESERVAÇÃO DE CONDIÇÕES E CONTEXTO (ANTI-SMEAR):
    Se o usuário especificou critérios condicionais (ex: "prefere X quando Y", "usa A para frontend mas B para scripts", "gosta de café de manhã mas chá à noite"), o fato consolidado resultante DEVE OBRIGATORIAMENTE manter ambas as condições explícitas. É estritamente proibido achatar para um genérico "usa ferramenta A e B" eliminando os critérios de escolha.
11. ARQUIVAMENTO RESTRITO: Só marque ação "archive" para fatos comprovadamente efêmeros ou ruídos sem qualquer valor durável. Sempre forneça a justificativa em "reason".
12. ALIAS DE ID: Cada fato chega com um alias curto no campo ID (f1, f2, f3). Copie esse alias exatamente em fact_id, old_fact_id e source_fact_ids. Nunca invente, encurte nem reescreva o ID.
13. IDADE E NASCIMENTO: Nunca invente ano de nascimento. Nunca ajuste uma idade para bater com um ano que não estava nos fatos de origem. Se o fato diz ~46 anos, mantenha ~46. Filho não pode ser mais velho que o titular. Idade do titular não vira idade de filho.
14. ESCOPO: identity.* é só o titular. Esposa, filho e casamento ficam em family.*. Não una dois project.<slug> diferentes num merge. Não fixe (pin) um fato que não estava fixado. Não introduza nome, número, CEP ou ano que não esteja nos fatos de origem, exceto a data de hoje e a ancoragem de "ontem/semana passada".

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


def cluster_facts_semantically(facts: list[dict]) -> list[list[dict]]:
    """
    Agrupamento Semântico em 2 Níveis:
    Nível 1: Segregação por escopo rígido (_fact_scope)
    Nível 2: Afinidade semântica por cosseno dos embeddings (> 0.55) ou coesão temática
    """
    if not facts:
        return []

    from collections import defaultdict
    by_scope = defaultdict(list)
    for f in facts:
        by_scope[_fact_scope(f)].append(f)

    clusters: list[list[dict]] = []

    _blob_to_embedding = _cosine_similarity = None
    try:
        from backend.cache.manager import (
            _blob_to_embedding as _b2e,
            _cosine_similarity as _cos,
        )
        _blob_to_embedding, _cosine_similarity = _b2e, _cos
    except Exception:
        pass

    for scope, scope_facts in by_scope.items():
        if len(scope_facts) <= 3 or not _blob_to_embedding or not _cosine_similarity:
            clusters.append(scope_facts)
            continue

        unassigned = list(scope_facts)
        while unassigned:
            seed = unassigned.pop(0)
            seed_emb = seed.get("embedding")
            current_cluster = [seed]
            if seed_emb:
                try:
                    seed_vec = _blob_to_embedding(seed_emb)
                    remaining = []
                    for other in unassigned:
                        other_emb = other.get("embedding")
                        if other_emb:
                            try:
                                sim = _cosine_similarity(seed_vec, _blob_to_embedding(other_emb))
                                if sim >= 0.55:
                                    current_cluster.append(other)
                                    continue
                            except Exception:
                                pass
                        remaining.append(other)
                    unassigned = remaining
                except Exception:
                    pass
            clusters.append(current_cluster)

    return clusters


def split_facts_for_budget(
    facts: list[dict],
    system_prompt: str,
    max_tokens: int = DREAM_REQUEST_TOKEN_BUDGET,
) -> list[list[dict]]:
    """Fatia fatos para o pedido (prompt + lote) caber no teto de tokens, preservando clusters semânticos."""
    if not facts:
        return []
    overhead = estimate_tokens(system_prompt) + estimate_tokens(_USER_PAYLOAD_PREFIX)
    clusters = cluster_facts_semantically(facts)

    chunks: list[list[dict]] = []
    current: list[dict] = []
    current_tokens = overhead

    def _fact_line_tokens(fact: dict, idx: int) -> int:
        line = (
            f"[ID: f{idx} | CriadoEm: {fact.get('created_at') or ''} | "
            f"Pinned: {bool(fact.get('is_pinned'))} | Categoria: {fact.get('category')} | "
            f"Escopo: {_fact_scope(fact)}] {fact.get('fact') or ''}"
        )
        return estimate_tokens(line) + 1

    fact_counter = 1
    for cluster in clusters:
        cluster_tokens = sum(_fact_line_tokens(f, fact_counter + i) for i, f in enumerate(cluster))

        if current and (current_tokens + cluster_tokens > max_tokens):
            chunks.append(current)
            current = []
            current_tokens = overhead

        if cluster_tokens <= (max_tokens - overhead):
            current.extend(cluster)
            current_tokens += cluster_tokens
            fact_counter += len(cluster)
        else:
            for f in cluster:
                f_tok = _fact_line_tokens(f, fact_counter)
                if current and (current_tokens + f_tok > max_tokens):
                    chunks.append(current)
                    current = [f]
                    current_tokens = overhead + f_tok
                else:
                    current.append(f)
                    current_tokens += f_tok
                fact_counter += 1

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


def _classify_dream_error(exc: Exception) -> tuple[str, Optional[int]]:
    """Classifica erro operacional do provedor usando tipo/status sem expor corpo cru ou segredos."""
    if isinstance(exc, asyncio.TimeoutError):
        return "timeout", None
    if isinstance(exc, RateLimitError):
        return "rate_limit", 429
    status = getattr(exc, "status_code", None)
    if isinstance(status, int):
        if status == 413:
            return "too_large", 413
        if status == 429:
            return "rate_limit", 429
        if status in (401, 403):
            return "auth_error", status
        if status == 503:
            return "http_503", 503
        if 500 <= status < 600:
            return f"http_{status}", status
        return f"http_{status}", status

    text = str(exc).lower()
    if "413" in text or "too large" in text or "request too large" in text:
        return "too_large", 413
    if "503" in text or "service unavailable" in text:
        return "http_503", 503
    if "429" in text or "rate limit" in text:
        return "rate_limit", 429
    if "timeout" in text or "timed out" in text:
        return "timeout", None
    m = re.search(r"\b(50[0-4]|40[134])\b", text)
    if m:
        code = int(m.group(1))
        return f"http_{code}", code
    return type(exc).__name__, None


def _llm_error_is_too_large(exc: Exception) -> bool:
    kind, status = _classify_dream_error(exc)
    return kind == "too_large" or status == 413


async def analyze_facts(
    facts: list[dict],
    system_prompt: str,
    caller: Callable[[str, str], Awaitable[str | DreamResponseSchema]],
    max_tokens: int = DREAM_REQUEST_TOKEN_BUDGET,
    current_date: Optional[str] = None,
    deadline: Optional[float] = None,
    *,
    single_fact_caller: Optional[Callable[[str, str], Awaitable[DreamResponseSchema]]] = None,
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
        if deadline is not None and time.monotonic() >= deadline:
            raise DreamLLMError("Prazo máximo global da consolidação excedido.")
        _map, payload = render_facts_payload(chunk, current_date, alias_map)
        try:
            select_caller = single_fact_caller if len(chunk) == 1 and single_fact_caller else caller
            raw = await select_caller(system_prompt, payload)
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            if _llm_error_is_too_large(exc) and len(chunk) > 1:
                mid = max(1, len(chunk) // 2)
                await run_chunk(chunk[:mid])
                await run_chunk(chunk[mid:])
                return
            if isinstance(exc, DreamLLMError):
                raise
            kind, status = _classify_dream_error(exc)
            raise DreamLLMError(f"Falha operacional no lote ({kind}, status={status}).") from None
        schema = raw if isinstance(raw, DreamResponseSchema) else parse_dream_response(raw)
        remap_operation_ids(schema.operations, alias_map, facts)
        all_ops.extend(schema.operations)
        if schema.summary_of_changes:
            notes.append(schema.summary_of_changes)

    for chunk in chunks:
        await run_chunk(chunk)
    return all_ops, notes


_THINK_BLOCK = re.compile(r"<think>(.*?)</think>", re.DOTALL | re.IGNORECASE)
_DREAM_REASONING_TAG = r"think|thinking|thought|reasoning|analysis"
_REASONING_TAGS = re.compile(
    rf"<({_DREAM_REASONING_TAG})(?=[\s>])[^>]*>.*?</\1\s*>",
    re.DOTALL | re.IGNORECASE,
)
_UNMATCHED_REASONING_TAG = re.compile(
    rf"<(?:{_DREAM_REASONING_TAG})(?=[\s>])[^>]*>.*\Z", re.DOTALL | re.IGNORECASE
)
_JSON_CONTAINER_START = re.compile(r"[\[{]")
_CODE_FENCE_BLOCK = re.compile(r"```(?:json)?\s*([\s\S]*?)```", re.IGNORECASE)


def _strip_fences_and_reasoning(text: str) -> str:
    """Return only the final answer, discarding reasoning even if its stream was cut short."""
    outside = _REASONING_TAGS.sub("\n", text)
    outside = _UNMATCHED_REASONING_TAG.sub("", outside)
    # Desembrulha cercas markdown mantendo o conteúdo interno
    outside = _CODE_FENCE_BLOCK.sub(lambda m: "\n" + m.group(1) + "\n", outside)
    outside = re.sub(r"^```(?:json)?\s*", "", outside.strip(), flags=re.IGNORECASE)
    outside = re.sub(r"\s*```$", "", outside).strip()
    return outside


def _scan_json_candidates(text: str, *, max_scan_positions: int = 64) -> tuple[list[Any], bool]:
    """
    Varre valores JSON de topo em ``text`` de forma limitada.
    Retorna ``(decoded_objects, saw_root_array)``.
    """
    decoder = json.JSONDecoder()
    decoded: list[Any] = []
    saw_root_array = False
    idx = 0
    n = len(text)
    attempts = 0
    while idx < n and attempts < max_scan_positions:
        start = _JSON_CONTAINER_START.search(text, idx)
        if start is None:
            break
        pos = start.start()
        attempts += 1
        try:
            obj, end_pos = decoder.raw_decode(text, pos)
            if isinstance(obj, dict):
                decoded.append(obj)
            else:
                saw_root_array = True
            idx = end_pos
        except json.JSONDecodeError:
            # Do not reinterpret nested JSON within a truncated plan or array
            # as the final output. Plain prose with brackets remains allowed.
            after_open = text[pos + 1:].lstrip()[:1]
            if text[pos] == "[" and after_open in ("{", "[", '"'):
                return decoded, True
            if text[pos] == "{" and after_open == '"':
                raise DreamLLMError("Objeto JSON inválido na resposta final.")
            idx = pos + 1
    return decoded, saw_root_array


def _validate_dream_candidates(candidates: list[Any]) -> list[DreamResponseSchema]:
    valid: list[DreamResponseSchema] = []
    for obj in candidates:
        if not isinstance(obj, dict):
            continue
        if "operations" not in obj or not isinstance(obj["operations"], list):
            continue
        if "summary_of_changes" not in obj or not isinstance(obj["summary_of_changes"], str):
            continue
        try:
            valid.append(DreamResponseSchema.model_validate(obj))
        except Exception:
            continue
    return valid


def parse_dream_response(raw: str, *, max_chars: int = DREAM_MAX_RESPONSE_CHARS) -> DreamResponseSchema:
    """
    Analisa e valida rigorosamente a resposta do Dream com Pydantic.
    Rejeita saídas acima do limite, raiz array, schema inválido e objetos conflitantes.
    """
    if not isinstance(raw, str):
        raise DreamLLMError("Resposta do modelo não é texto.")
    if len(raw) > max_chars:
        raise DreamLLMError(f"Resposta do modelo excedeu o limite máximo ({max_chars} chars).")
    if not raw.strip():
        raise DreamLLMError("Resposta vazia do modelo.")

    outside = _strip_fences_and_reasoning(raw)
    candidates, saw_root_array = _scan_json_candidates(outside)
    if saw_root_array:
        raise DreamLLMError("Resposta JSON inválida: raiz array não permitida.")

    valid = _validate_dream_candidates(candidates)

    if not valid:
        raise DreamLLMError("Nenhum objeto JSON compatível com DreamResponseSchema encontrado na resposta.")

    if len(valid) > 1:
        canonical = [v.model_dump(mode="json") for v in valid]
        first = canonical[0]
        if any(item != first for item in canonical[1:]):
            raise DreamLLMError("Resposta ambígua: múltiplos objetos DreamResponseSchema conflitantes.")

    return valid[0]


def _slice_first_valid_json(text: str) -> str:
    """Extrai o primeiro objeto ou array JSON válido, mesmo que haja texto extra ou cercas."""
    text = (text or "").strip()
    if text.startswith("```"):
        lines = text.splitlines()
        if len(lines) >= 3 and lines[-1].strip().startswith("```"):
            text = "\n".join(lines[1:-1]).strip()
        else:
            text = re.sub(r"^```(?:json)?\s*", "", text)
            text = re.sub(r"\s*```$", "", text).strip()

    decoder = json.JSONDecoder()
    for i, ch in enumerate(text):
        if ch in ("{", "["):
            try:
                _, end_idx = decoder.raw_decode(text[i:])
                return text[i:i + end_idx]
            except json.JSONDecodeError:
                continue

    start = text.find("{")
    end = text.rfind("}")
    if start != -1 and end > start:
        return text[start:end + 1]
    return text


def extract_json_payload(raw: str) -> str:
    """Tira <think> e cerca markdown. Suporta modelos que incluem texto extra ou pensamentos."""
    text = raw or ""
    insides = _THINK_BLOCK.findall(text)
    outside = _THINK_BLOCK.sub("", text)
    outside = re.sub(r"</?think>", "", outside)
    outside_json = _slice_first_valid_json(outside)
    if outside_json.startswith("{") or outside_json.startswith("["):
        try:
            json.loads(outside_json)
            return outside_json
        except json.JSONDecodeError:
            pass
    inside_json = _slice_first_valid_json("\n".join(insides))
    if inside_json.startswith("{") or inside_json.startswith("["):
        try:
            json.loads(inside_json)
            return inside_json
        except json.JSONDecodeError:
            pass
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

_RE_SYNTHESIS = re.compile(
    r"ajustad[oa]\s+por\s+consist[eê]ncia|anteriormente\s+registrado\s+como|calculad[oa]\s+a\s+partir",
    re.I,
)
_RE_NAME_BIGRAM = re.compile(
    r"\b([A-ZÁÉÍÓÚÂÊÔÃÕÇ][\w'’-]{2,})\s+([A-ZÁÉÍÓÚÂÊÔÃÕÇ][\w'’-]{2,})"
)
_RE_LONG_NUMBER = re.compile(r"(?<!\d)(\d{2,})(?!\d)")
_RE_RELATIVE_TIME = re.compile(
    r"\b(ontem|anteontem|hoje|amanh[aã]|semana\s+passada|m[eê]s\s+passado|"
    r"ano\s+que\s+vem|atualmente|h[aá]\s+\d+\s+dias)\b",
    re.I,
)
_NAME_BIGRAM_SKIP = {
    "filho", "filha", "esposa", "esposo", "stack", "react", "typescript",
    "tailwind", "python", "css", "html", "api",
}


def project_slug(fact_key: str | None) -> str | None:
    key = (fact_key or "").lower()
    if not key.startswith("project."):
        return None
    parts = key.split(".")
    return parts[1] if len(parts) > 1 else ""


def number_grounded(num: str, source_text: str, today: str) -> bool:
    if re.search(rf"(?<!\d){re.escape(num)}(?!\d)", source_text or ""):
        return True
    if num in set(re.findall(r"\d+", today or "")):
        return True
    if not _RE_RELATIVE_TIME.search(source_text or ""):
        return False
    year = int((today or "2000")[:4])
    if len(num) == 4 and abs(int(num) - year) <= 1:
        return True
    if len(num) <= 2 and int(num) <= 31:
        return True
    return False


def consolidation_block_reason(
    new_key: str | None,
    new_text: str,
    source_facts: list[dict],
    source_text: str,
    today: str | None = None,
) -> str | None:
    """Motivo para descartar um merge/supersede. None = pode gravar."""
    from backend.memory import identity_mixes_other_person, is_labeled_child_fact

    today = today or datetime.date.today().isoformat()
    text = new_text or ""
    if _RE_SYNTHESIS.search(text):
        return "sintese"
    if identity_mixes_other_person(new_key, text):
        return "identity_mistura_familia"
    slugs = {project_slug(s.get("fact_key")) for s in source_facts}
    slugs.discard(None)
    if len(slugs) > 1:
        return "projetos_cruzados"
    if is_labeled_child_fact(new_key, text) and source_facts and not any(
        is_labeled_child_fact(s.get("fact_key"), s.get("fact") or "") for s in source_facts
    ):
        return "papel_filho_sem_origem"
    norm_source = (source_text or "").replace("/", " ").lower()
    for first, second in _RE_NAME_BIGRAM.findall(text):
        if first.lower() in _NAME_BIGRAM_SKIP or second.lower() in _NAME_BIGRAM_SKIP:
            continue
        bigram = f"{first} {second}".lower()
        if bigram not in norm_source:
            return f"nome:{first} {second}"
    for num in _RE_LONG_NUMBER.findall(text):
        if not number_grounded(num, source_text, today):
            return f"numero:{num}"
    return None


def drop_impossible_age_rewrites(
    facts_before: list[dict],
    operations: list[DreamOperation],
) -> list[DreamOperation]:
    """Descarta merge/supersede que inventa ano de nascimento ou filho mais velho que o titular."""
    from backend.memory import (
        birth_years,
        child_age_impossible,
        holder_age_from_facts,
        is_labeled_child_fact,
        stated_ages,
    )

    by_id = {f["id"]: f for f in facts_before}
    holder_age = holder_age_from_facts(facts_before)
    kept: list[DreamOperation] = []
    for op in operations:
        nf = op.new_fact
        if op.action not in ("merge", "supersede") or nf is None:
            kept.append(op)
            continue
        source_ids = list(op.source_fact_ids or [])
        if op.old_fact_id:
            source_ids.append(op.old_fact_id)
        source_facts = [by_id[sid] for sid in source_ids if sid in by_id]
        source_text = " ".join((s.get("fact") or "") for s in source_facts)
        invented_years = [y for y in birth_years(nf.fact) if str(y) not in source_text]
        invented_ages = [
            age for age in stated_ages(nf.fact)
            if not re.search(rf"(?<!\d){age}(?!\d)", source_text or "")
        ]
        impossible_child = is_labeled_child_fact(nf.fact_key, nf.fact) and child_age_impossible(
            nf.fact, holder_age
        )
        holder_relabeled = (
            is_labeled_child_fact(nf.fact_key, nf.fact)
            and stated_ages(nf.fact)
            and source_ids
            and not any(
                is_labeled_child_fact(by_id.get(sid, {}).get("fact_key"), by_id.get(sid, {}).get("fact") or "")
                for sid in source_ids
            )
        )
        scope_reason = consolidation_block_reason(
            nf.fact_key, nf.fact, source_facts, source_text
        )
        if invented_years or invented_ages or impossible_child or holder_relabeled or scope_reason:
            logger.warning(
                "[Dream] operação descartada (ano=%s, idade=%s, filho impossível=%s, reetiqueta=%s, escopo=%s): %s",
                invented_years,
                invented_ages,
                impossible_child,
                holder_relabeled,
                scope_reason,
                (nf.fact or "")[:160],
            )
            continue
        sources_pinned = any(by_id.get(sid, {}).get("is_pinned") for sid in source_ids)
        if nf.is_pinned and not sources_pinned:
            nf.is_pinned = False
        kept.append(op)
    return kept


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

            # Barreira de nuance: preservação de densidade informativa (Plano 08 - Tarefa 3)
            source_len = sum(len(existing_ids[sid].get("fact") or "") for sid in op.source_fact_ids if sid in existing_ids)
            if len(op.source_fact_ids) >= 3 and source_len > 250 and len(op.new_fact.fact.strip()) < 65:
                raise DreamSafetyError(
                    f"Perda excessiva de nuance informativa no merge: {source_len} caracteres originais reduzidos para {len(op.new_fact.fact.strip())}."
                )

            # Barreira determinística de entidade (Plano 08 - Tarefa 4)
            has_family = any(
                (existing_ids[sid].get("fact_key") or "").startswith("family.") or existing_ids[sid].get("category") == "family"
                for sid in op.source_fact_ids if sid in existing_ids
            )
            has_identity = any(
                (existing_ids[sid].get("fact_key") or "").startswith("identity.") or existing_ids[sid].get("category") == "identity"
                for sid in op.source_fact_ids if sid in existing_ids
            )
            if has_family and has_identity:
                raise DreamSafetyError("Violação de Entidade: Fusão proibida entre fatos da família e identidade do titular.")

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
# WATERFALL / AUTO-ROUTER DE CANDIDATOS E EXECUÇÃO RESILIENTE (T1.2)
# =========================================================

def _provider_supports_response_format(provider) -> bool:
    """Envia response_format apenas quando o adaptador o declara explicitamente e o aceita."""
    if not getattr(provider, "supports_response_format", False):
        return False
    target = getattr(provider, "stream_chat", None) or getattr(provider, "chat", None)
    if target is None:
        return False
    try:
        sig = inspect.signature(target)
        return "response_format" in sig.parameters
    except (TypeError, ValueError):
        return False


async def resolve_dream_candidates(
    user_id: str,
    custom_provider: Optional[str] = None,
    custom_model: Optional[str] = None,
    *,
    excluded_ids: tuple[str, ...] | list[str] = (),
    max_candidates: int = 6,
) -> list[dict]:
    """
    Resolve lista ordenada de candidatos elegíveis para o Dream via Auto-Router,
    intersectada com regras de usuário (chaves, modelos/provedores ativos, cotas).
    """
    from backend.ranking.smart_router import route_dream_candidates

    excluded_set = {str(x) for x in (excluded_ids or ()) if x}
    preferred_pairs: list[tuple[Optional[str], Optional[str], str]] = []

    async with aiosqlite.connect(dbmod.DB_PATH, timeout=10.0) as db:
        await db.execute("PRAGMA busy_timeout = 10000;")

        # 1. Preferência explícita (override da chamada ou meta.dream_*)
        p_id = (custom_provider or "").strip() or None
        m_id = (custom_model or "").strip() or None
        if not p_id and not m_id:
            async with db.execute("SELECT value FROM meta WHERE key = 'dream_provider_id'") as cur:
                row = await cur.fetchone()
                p_id = (row[0] or "").strip() or None if row else None
            async with db.execute("SELECT value FROM meta WHERE key = 'dream_model_id'") as cur:
                row = await cur.fetchone()
                m_id = (row[0] or "").strip() or None if row else None
        if m_id:
            preferred_pairs.append((p_id, m_id, "dream_dedicated"))

        # A preferred local destination must not silently send memory to a
        # remote provider when that model is unavailable.
        local_only = False
        if p_id or m_id:
            async with db.execute(
                """SELECT is_local FROM providers
                   WHERE id = COALESCE(?, (SELECT provider_id FROM models WHERE id = ?))""",
                (p_id, m_id),
            ) as cur:
                row = await cur.fetchone()
                local_only = bool(row and row[0])

        # 2. Preferência secundária: extrator de memória
        async with db.execute("SELECT value FROM meta WHERE key = 'memory_extractor_provider_id'") as cur:
            row = await cur.fetchone()
            ext_p = (row[0] or "").strip() or None if row else None
        async with db.execute("SELECT value FROM meta WHERE key = 'memory_extractor_model_id'") as cur:
            row = await cur.fetchone()
            ext_m = (row[0] or "").strip() or None if row else None
        if ext_m:
            preferred_pairs.append((ext_p, ext_m, "memory_extractor"))

        # 3. Preferência terciária: enhancer_config
        try:
            async with db.execute(
                "SELECT enhancer_provider_id, enhancer_model_id FROM enhancer_config WHERE id = 1"
            ) as cur:
                row = await cur.fetchone()
            if row and row[1]:
                preferred_pairs.append(((row[0] or "").strip() or None, str(row[1]).strip(), "enhancer"))
        except Exception:
            pass

        # Determina primeiro modelo preferido válido para priorizar no Auto-Router
        primary_pref_model = m_id or (preferred_pairs[0][1] if not p_id and preferred_pairs else None)

        async with db.execute("SELECT value FROM meta WHERE key = 'router_policy'") as cur:
            pol_row = await cur.fetchone()
            router_policy = pol_row[0] if pol_row and pol_row[0] else "balanced_smart"

        routed = await route_dream_candidates(
            db,
            user_id,
            preferred_model_id=primary_pref_model,
            excluded_ids=tuple(excluded_set),
            policy=router_policy,
            max_candidates=max(max_candidates * 2, 12),
            local_only=local_only,
            preferred_provider_id=p_id if not m_id else None,
        )

        # Constrói lista final de specs sem duplicatas: preferidos explícitos + Auto-Router
        raw_specs: list[dict] = []
        seen_ids: set[str] = set()

        # Primeiro, verifica se o preferido explícito (ex: custom/meta) já veio no topo do Auto-Router;
        # se veio, preserva ordem do Auto-Router; se um preferido secundário está no roteamento, prioriza se válido.
        model_preferences = preferred_pairs if m_id or not p_id else ()
        for pref_p, pref_m, pref_src in model_preferences:
            if not pref_m or pref_m in excluded_set or pref_m in seen_ids:
                continue
            match = next(
                (c for c in routed if c["model_id"] == pref_m and pref_p in (None, c["provider_id"])),
                None,
            )
            if match is not None:
                entry = dict(match)
                entry["source"] = pref_src
                raw_specs.append(entry)
                seen_ids.add(pref_m)
                break  # apenas a preferência válida de maior prioridade vai ao topo

        for c in routed:
            mid = c["model_id"]
            if mid in seen_ids or mid in excluded_set:
                continue
            seen_ids.add(mid)
            raw_specs.append(dict(c))

        # Instancia adaptadores validando credenciais em tempo de execução (sem falhar toda a lista por um sem chave)
        resolved: list[dict] = []
        for spec in raw_specs:
            pid = spec["provider_id"]
            mid = spec["model_id"]
            try:
                prov = await get_provider(pid, db, user_id=user_id)
                m_name = spec.get("model_name") or await get_model_name(mid, db)
                resolved.append({
                    "provider": prov,
                    "provider_id": pid,
                    "model_id": mid,
                    "model_name": m_name,
                    "display_name": spec.get("display_name") or m_name,
                    "source": spec.get("source", "auto_router"),
                })
                if len(resolved) >= max(1, int(max_candidates)):
                    break
            except Exception:
                logger.debug(
                    "[Dream] Candidato ignorado na resolução (provider=%s, model=%s)",
                    pid,
                    mid,
                )
                continue

    if not resolved:
        raise DreamLLMError("Nenhum provedor de IA elegível disponível para executar a consolidação.")
    return resolved


async def resolve_dream_provider(user_id: str, custom_provider: str = None, custom_model: str = None):
    """Compatibilidade: retorna o candidato principal resolvido pelo Auto-Router do Dream."""
    candidates = await resolve_dream_candidates(
        user_id, custom_provider=custom_provider, custom_model=custom_model, max_candidates=1
    )
    top = candidates[0]
    return top["provider"], top["model_name"], top["provider_id"], top["model_id"], top["source"]


# =========================================================
# EXECUÇÃO DO LLM COM TIMEOUT, SCHEMA ESTRUTURADO E FALLBACK
# =========================================================

async def _invoke_dream_candidate(
    provider,
    model_name: str,
    provider_id: str,
    system_prompt: str,
    user_payload: str,
    *,
    timeout_s: float = DREAM_PER_CALL_TIMEOUT_S,
) -> DreamResponseSchema:
    """Executa uma chamada única a um candidato dentro de ``timeout_s`` e valida com Pydantic."""
    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": f"Fatos para Consolidação:\n{user_payload}"},
    ]

    kwargs: dict[str, Any] = {"temperature": 0.05}
    if _provider_supports_response_format(provider):
        kwargs["response_format"] = {"type": "json_object"}

    async def _collect_response(call_kwargs: dict[str, Any]) -> str:
        full_response = ""
        if hasattr(provider, "stream_chat"):
            async for token in provider.stream_chat(model=model_name, messages=messages, **call_kwargs):
                full_response += str(token)
                if len(full_response) > DREAM_MAX_RESPONSE_CHARS:
                    raise DreamLLMError(
                        f"Resposta do modelo excedeu o limite máximo ({DREAM_MAX_RESPONSE_CHARS} chars)."
                    )
            return full_response
        if hasattr(provider, "chat"):
            resp = await provider.chat(model=model_name, messages=messages, **call_kwargs)
            return resp if isinstance(resp, str) else str(resp)
        raise DreamLLMError(f"Provedor '{provider_id}' não suporta chat.")

    async def _run_call() -> str:
        try:
            return await _collect_response(kwargs)
        except Exception as exc:
            _, status = _classify_dream_error(exc)
            format_rejected = re.search(r"response[_ ]format|json[_ ]object", str(exc), re.IGNORECASE)
            if "response_format" not in kwargs or status not in (400, 422) or not format_rejected:
                raise
        # Compatible APIs can expose the argument but reject it for this model.
        # Retry with the JSON prompt within the same timeout.
        return await _collect_response({"temperature": kwargs["temperature"]})

    if timeout_s <= 0:
        raise asyncio.TimeoutError("Prazo da chamada esgotado.")

    raw_response = await asyncio.wait_for(_run_call(), timeout=timeout_s)
    return parse_dream_response(raw_response)


async def call_dream_llm(
    provider,
    model_name: str,
    provider_id: str,
    system_prompt: str,
    user_payload: str,
    *,
    timeout_s: float = DREAM_PER_CALL_TIMEOUT_S,
) -> str:
    """Executa uma inferência única validada por ``parse_dream_response`` e devolve JSON canônico."""
    try:
        schema = await _invoke_dream_candidate(
            provider,
            model_name,
            provider_id,
            system_prompt,
            user_payload,
            timeout_s=timeout_s,
        )
        return schema.model_dump_json()
    except asyncio.CancelledError:
        raise
    except DreamLLMError:
        raise
    except Exception as exc:
        kind, status = _classify_dream_error(exc)
        raise DreamLLMError(
            f"Falha na chamada ao modelo {model_name} ({provider_id}): {kind}"
            + (f" [{status}]" if status else "")
        ) from None


def _format_models_usage_summary(model_batch_counts: dict[tuple[str, str], int]) -> str:
    """Gera resumo sanitizado dos modelos usados em múltiplos lotes (sem texto de memória)."""
    if len(model_batch_counts) <= 1:
        return ""
    parts = [
        f"{pid}/{mid} ({cnt} {'lote' if cnt == 1 else 'lotes'})"
        for (pid, mid), cnt in model_batch_counts.items()
    ]
    return "Modelos utilizados: " + ", ".join(parts) + "."


async def run_dream_analysis(
    active_facts: list[dict],
    candidates: list[dict],
    *,
    current_date: Optional[str] = None,
    max_tokens: int = DREAM_REQUEST_TOKEN_BUDGET,
    execution_deadline_s: float = DREAM_EXECUTION_DEADLINE_S,
    per_call_timeout_s: float = DREAM_PER_CALL_TIMEOUT_S,
    max_candidates_per_batch: int = DREAM_MAX_CANDIDATES_PER_BATCH,
    progress_cb: Optional[Callable[[str, int, str], Awaitable[None]]] = None,
) -> dict:
    """
    Executor unificado (usado em preview e consolidação real):
    - Deadline monotônico absoluto por execução (padrão 180s) e limite por chamada (30s)
    - Até 3 candidatos por lote; avança para próximo candidato em 503, timeout ou saída/schema inválido
    - Reaproveita candidato vencedor entre lotes mantendo fallback disponível
    - Divide lote em 413 dentro do mesmo deadline
    - Propaga asyncio.CancelledError sem engolir
    """
    if not candidates:
        raise DreamLLMError("Nenhum candidato disponível para análise do Dream.")

    current_date = current_date or datetime.date.today().isoformat()
    system_prompt = _DREAM_SYSTEM_PROMPT.replace("{CURRENT_DATE}", current_date)
    deadline = time.monotonic() + max(0.05, float(execution_deadline_s))

    sticky_model_id: Optional[str] = candidates[0]["model_id"]
    demoted_ids: list[str] = []
    model_batch_counts: dict[tuple[str, str], int] = {}
    last_effective: dict = candidates[0]

    async def _report_model(cand: dict):
        if progress_cb:
            try:
                await progress_cb(
                    "connecting",
                    45,
                    f"Modelo ativo: {cand['model_name']} ({cand['provider_id']})",
                )
            except Exception:
                pass

    def _ordered_candidates_for_batch() -> list[dict]:
        primary = [c for c in candidates if c["model_id"] == sticky_model_id and c["model_id"] not in demoted_ids]
        healthy = [c for c in candidates if c["model_id"] != sticky_model_id and c["model_id"] not in demoted_ids]
        fallback_demoted = [c for c in candidates if c["model_id"] in demoted_ids]
        ordered = primary + healthy + fallback_demoted
        return ordered[: max(1, int(max_candidates_per_batch))]

    async def routed_caller(prompt: str, payload: str, *, can_split: bool = True) -> DreamResponseSchema:
        nonlocal sticky_model_id, last_effective
        batch_candidates = _ordered_candidates_for_batch()
        last_kind = "unknown"
        last_status: Optional[int] = None

        for cand in batch_candidates:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise DreamLLMError("Prazo máximo global da consolidação excedido.")
            call_timeout = min(float(per_call_timeout_s), remaining)
            pid = cand["provider_id"]
            mid = cand["model_id"]
            mname = cand["model_name"]

            try:
                schema = await _invoke_dream_candidate(
                    cand["provider"],
                    mname,
                    pid,
                    prompt,
                    payload,
                    timeout_s=call_timeout,
                )
                sticky_model_id = mid
                if mid in demoted_ids:
                    demoted_ids.remove(mid)
                if last_effective.get("model_id") != mid:
                    await _report_model(cand)
                last_effective = cand
                key = (pid, mid)
                model_batch_counts[key] = model_batch_counts.get(key, 0) + 1
                return schema
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                kind, status = _classify_dream_error(exc)
                # 413 deve subir para analyze_facts dividir o lote mantendo o mesmo deadline
                if can_split and (kind == "too_large" or status == 413):
                    logger.warning(
                        "[Dream] Lote excedeu limite do modelo (provider=%s, model=%s, status=413); dividindo lote",
                        pid,
                        mid,
                    )
                    raise ProviderHTTPError(413, "Payload excedeu o limite do modelo (413).", provider=pid) from None

                last_kind, last_status = kind, status
                if mid not in demoted_ids:
                    demoted_ids.append(mid)
                logger.warning(
                    "[Dream] Candidato falhou (provider=%s, model=%s, error_kind=%s, status=%s); tentando próximo candidato",
                    pid,
                    mid,
                    kind,
                    status,
                )
                continue

        raise DreamLLMError(
            f"Todos os candidatos falharam na consolidação (último erro: {last_kind}"
            + (f", status={last_status}" if last_status else "")
            + ")."
        )

    async def call_for_single_fact(prompt: str, payload: str) -> DreamResponseSchema:
        return await routed_caller(prompt, payload, can_split=False)

    operations, notes = await analyze_facts(
        active_facts,
        system_prompt,
        routed_caller,
        max_tokens=max_tokens,
        current_date=current_date,
        deadline=deadline,
        single_fact_caller=call_for_single_fact,
    )
    operations = drop_impossible_age_rewrites(active_facts, operations)
    model_summary = _format_models_usage_summary(model_batch_counts)

    return {
        "operations": operations,
        "notes": notes,
        "effective_provider_id": last_effective["provider_id"],
        "effective_model_id": last_effective["model_id"],
        "effective_model_name": last_effective["model_name"],
        "models_used": [
            {"provider_id": pid, "model_id": mid, "batches": cnt}
            for (pid, mid), cnt in model_batch_counts.items()
        ],
        "model_summary": model_summary,
    }


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
        await db.execute("PRAGMA busy_timeout = 10000;")
        await db.execute("BEGIN IMMEDIATE")
        from backend.memory_sanitize import sanitize_memory_text
        try:
            for op in operations:
                if op.action == "merge":
                    nf = op.new_fact
                    clean_fact, drop_sec = sanitize_memory_text(nf.fact)
                    if drop_sec or not clean_fact.strip():
                        continue
                    nf.fact = clean_fact
                    new_id = str(uuid.uuid4())
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
                               WHERE id = ? AND user_id = ? AND is_active = 1""",
                            (new_id, sid, user_id),
                        )
                        facts_merged_count += 1

                elif op.action == "supersede":
                    nf = op.new_fact
                    clean_fact, drop_sec = sanitize_memory_text(nf.fact)
                    if drop_sec or not clean_fact.strip():
                        continue
                    nf.fact = clean_fact
                    new_id = str(uuid.uuid4())
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
                           WHERE id = ? AND user_id = ? AND is_active = 1""",
                        (new_id, op.old_fact_id, user_id),
                    )
                    facts_superseded_count += 1

                elif op.action == "archive":
                    await db.execute(
                        """UPDATE user_memory
                           SET is_active = 0, status = 'archived',
                               consolidated_at = datetime('now'), updated_at = datetime('now')
                           WHERE id = ? AND user_id = ? AND is_active = 1""",
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
                await db.execute("PRAGMA busy_timeout = 10000;")
                for fid, txt in new_facts_to_embed:
                    emb = _try_embed_fact(txt)
                    if emb is not None:
                        await db.execute("UPDATE user_memory SET embedding = ? WHERE id = ?", (emb, fid))
                await db.commit()
        except Exception as e:
            logger.warning("[Dream] Erro ao gravar FastEmbed embeddings em lote: %s", e)

    # Reconciliação fora do lock: resumos rolling
    try:
        from backend.memory import refresh_memory_summaries
        await refresh_memory_summaries(user_id, use_llm=False)
    except Exception as e:
        logger.warning("[Dream] Erro ao recalcular resumos pós-aplicação (user=%s): %s", user_id, e)

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
    *,
    candidates: Optional[list[dict]] = None,
    execution_deadline_s: float = DREAM_EXECUTION_DEADLINE_S,
    per_call_timeout_s: float = DREAM_PER_CALL_TIMEOUT_S,
    max_tokens: int = DREAM_REQUEST_TOKEN_BUDGET,
) -> dict:
    """
    Executa a análise do Dream sem persistir nenhuma alteração no banco.
    Usa o mesmo executor roteado de ``execute_dream_consolidation``.
    """
    active_facts = await get_user_memory(user_id, limit=5000, active_only=True)
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

    resolved_candidates = (
        candidates
        if candidates is not None
        else await resolve_dream_candidates(user_id, custom_provider, custom_model)
    )

    current_date = datetime.date.today().isoformat()
    analysis = await run_dream_analysis(
        active_facts,
        resolved_candidates,
        current_date=current_date,
        max_tokens=max_tokens,
        execution_deadline_s=execution_deadline_s,
        per_call_timeout_s=per_call_timeout_s,
    )

    summary_text = " ".join(analysis["notes"]) or "Simulação concluída."
    if analysis["model_summary"]:
        summary_text = f"{summary_text} ({analysis['model_summary']})"

    schema = DreamResponseSchema(
        summary_of_changes=summary_text,
        operations=analysis["operations"],
    )

    # Validação rigorosa dos limiares
    verify_dream_safety(active_facts, schema.operations)

    breakdown = {"merge": 0, "supersede": 0, "archive": 0, "keep": 0}
    for op in schema.operations:
        breakdown[op.action] = breakdown.get(op.action, 0) + 1

    projected_active = breakdown["keep"] + breakdown["merge"] + breakdown["supersede"]
    clusters = cluster_facts_semantically(active_facts)

    return {
        "summary_of_changes": schema.summary_of_changes,
        "operations": [op.model_dump() for op in schema.operations],
        "facts_before": len(active_facts),
        "projected_active": projected_active,
        "actions_breakdown": breakdown,
        "clusters_count": len(clusters),
        "provider_id": analysis["effective_provider_id"],
        "model_id": analysis["effective_model_id"],
        "models_used": analysis["models_used"],
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
    *,
    candidates: Optional[list[dict]] = None,
    execution_deadline_s: float = DREAM_EXECUTION_DEADLINE_S,
    per_call_timeout_s: float = DREAM_PER_CALL_TIMEOUT_S,
    max_tokens: int = DREAM_REQUEST_TOKEN_BUDGET,
) -> dict:
    """
    Executa o fluxo completo do Dream Memory:
      1. Snapshot atômico & leitura dos fatos
      2. Resolução de candidatos pelo Auto-Router (com fallback)
      3. Análise semântica & validação estrita por lote (sem mutação parcial)
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

    active_facts = await get_user_memory(user_id, limit=5000, active_only=True)
    if not active_facts:
        logger.info("[Dream] Usuário %s não possui fatos ativos. No-op.", user_id)
        return {"status": "no_op", "message": "Sem fatos ativos para consolidar."}

    try:
        resolved_candidates = (
            candidates
            if candidates is not None
            else await resolve_dream_candidates(user_id, custom_provider, custom_model)
        )
    except asyncio.CancelledError:
        raise
    except Exception as res_err:
        duration_ms = int((time.time() - start_time) * 1000)
        await record_dream_log({
            "user_id": user_id,
            "snapshot_id": snap_id,
            "provider_id": custom_provider or "auto",
            "model_id": custom_model or "unresolved",
            "facts_before": len(active_facts),
            "facts_after": len(active_facts),
            "facts_total_active": len(active_facts),
            "duration_ms": duration_ms,
            "status": "failed",
            "error_message": str(res_err)[:500],
        })
        raise

    primary = resolved_candidates[0]
    dream_id = await record_dream_log({
        "user_id": user_id,
        "snapshot_id": snap_id,
        "provider_id": primary["provider_id"],
        "model_id": primary["model_id"],
        "facts_before": len(active_facts),
        "status": "running",
    })

    try:
        await report(
            "connecting",
            35,
            f"Conectado ao modelo {primary['model_name']} ({primary['provider_id']}). Analisando memórias...",
        )
        current_date = datetime.date.today().isoformat()

        await report("reasoning", 60, "Processando desduplicação, contradições e marcos temporais...")
        analysis = await run_dream_analysis(
            active_facts,
            resolved_candidates,
            current_date=current_date,
            max_tokens=max_tokens,
            execution_deadline_s=execution_deadline_s,
            per_call_timeout_s=per_call_timeout_s,
            progress_cb=report,
        )

        eff_provider_id = analysis["effective_provider_id"]
        eff_model_id = analysis["effective_model_id"]
        summary_text = " ".join(analysis["notes"]) or "Consolidação concluída."
        if analysis["model_summary"]:
            summary_text = f"{summary_text} ({analysis['model_summary']})"

        schema = DreamResponseSchema(
            summary_of_changes=summary_text,
            operations=analysis["operations"],
        )

        await report("validating", 80, "Verificando barreiras de integridade e retenção anti-ruído...")
        try:
            verify_dream_safety(active_facts, schema.operations)
        except DreamSafetyError as safety_err:
            duration_ms = int((time.time() - start_time) * 1000)
            await update_dream_log(dream_id, {
                "status": "aborted_safety",
                "provider_id": eff_provider_id,
                "model_id": eff_model_id,
                "error_message": str(safety_err)[:500],
                "duration_ms": duration_ms,
                "facts_after": len(active_facts),
            })
            raise safety_err

        await report("persisting", 90, "Gravando transação flash (<100ms) e calculando embeddings FastEmbed...")
        stats = await apply_dream_operations(user_id, dream_id, schema.operations, active_facts)

        active_after = await get_user_memory(user_id, limit=5000, active_only=True)
        duration_ms = int((time.time() - start_time) * 1000)

        await update_dream_log(dream_id, {
            "status": "success",
            "provider_id": eff_provider_id,
            "model_id": eff_model_id,
            "facts_after": len(active_after),
            "facts_merged": stats["facts_merged"],
            "facts_superseded": stats["facts_superseded"],
            "facts_created": stats["facts_created"],
            "facts_total_active": len(active_after),
            "duration_ms": duration_ms,
            "summary_notes": schema.summary_of_changes,
        })

        await report(
            "done",
            100,
            f"Consolidação concluída com sucesso ({eff_model_id})! ({len(active_facts)} ➔ {len(active_after)} fatos).",
        )

        return {
            "status": "success",
            "dream_id": dream_id,
            "snapshot_id": snap_id,
            "provider_id": eff_provider_id,
            "model_id": eff_model_id,
            "models_used": analysis["models_used"],
            "facts_before": len(active_facts),
            "facts_after": len(active_after),
            "compression_ratio": (len(active_facts) - len(active_after)) / len(active_facts) if active_facts else 0.0,
            "summary_notes": schema.summary_of_changes,
            "duration_ms": duration_ms,
            "stats": stats,
        }

    except asyncio.CancelledError:
        duration_ms = int((time.time() - start_time) * 1000)
        await update_dream_log(dream_id, {
            "status": "failed",
            "error_message": "Consolidação cancelada.",
            "duration_ms": duration_ms,
            "facts_after": len(active_facts),
        })
        raise
    except DreamSafetyError:
        raise
    except Exception as exc:
        duration_ms = int((time.time() - start_time) * 1000)
        kind, status = _classify_dream_error(exc)
        safe_msg = str(exc) if isinstance(exc, DreamLLMError) else f"Erro operacional ({kind}, status={status})."
        await update_dream_log(dream_id, {
            "status": "failed",
            "error_message": safe_msg[:500],
            "duration_ms": duration_ms,
            "facts_after": len(active_facts),
        })
        logger.error(
            "[Dream] Falha na execução da consolidação (user=%s, error_kind=%s, status=%s)",
            user_id,
            kind,
            status,
        )
        raise exc


async def run_dream_with_breaker(
    user_id: str,
    *,
    trigger_type: str = "dream_manual",
    custom_provider: Optional[str] = None,
    custom_model: Optional[str] = None,
    progress_cb: Optional[Callable[[str, int, str], Awaitable[None]]] = None,
    respect_breaker: bool = False,
    cooldown_minutes: Optional[int] = None,
    consolidator: Optional[Callable[..., Awaitable[dict]]] = None,
    now_fn: Optional[Callable[[], datetime.datetime]] = None,
    already_locked: bool = False,
) -> dict:
    """
    Shared service entry point for both background worker and manual Dream runs.
    Enforces `memory_pipeline_lock`, atomic half-open probe reservation, generation fencing,
    and operational failure accounting (ignoring no_op, safety aborts, and cancellations).
    """
    from contextlib import nullcontext
    from backend.memory_lock import memory_pipeline_lock

    now_getter = now_fn or (lambda: datetime.datetime.now(datetime.timezone.utc))
    exec_fn = consolidator or execute_dream_consolidation

    lock_cm = nullcontext() if already_locked else memory_pipeline_lock
    async with lock_cm:
        # Read the current breaker after reaching the head of the queue.
        # Keep the lock until the attempt has updated its breaker state.
        probe = await dbmod.try_acquire_dream_probe(
            user_id,
            now=now_getter(),
            cooldown_minutes=cooldown_minutes,
            allow_open=not respect_breaker,
        )
        if not probe.get("allowed"):
            return {"status": "skipped_breaker", "breaker": probe}
        generation = probe["generation"]

        outcome = "failure"
        try:
            result = await exec_fn(
                user_id=user_id,
                trigger_type=trigger_type,
                custom_provider=custom_provider,
                custom_model=custom_model,
                progress_cb=progress_cb,
            )
            outcome = "no_op" if result.get("status") == "no_op" else "success"
            return result
        except DreamSafetyError:
            outcome = "aborted_safety"
            raise
        except asyncio.CancelledError:
            outcome = "cancelled"
            raise
        finally:
            try:
                breaker_res = await dbmod.record_dream_attempt(
                    user_id,
                    generation,
                    outcome,
                    now=now_getter(),
                    cooldown_minutes=cooldown_minutes,
                )
                if breaker_res.get("transitioned_to_open"):
                    logger.warning(
                        "[Dream Circuit Breaker] Pausando consolidação para usuário %s após %d falhas consecutivas (próxima tentativa em %s)",
                        user_id,
                        breaker_res["consecutive_failures"],
                        breaker_res.get("retry_at"),
                    )
            except Exception as exc:
                logger.error("[Dream Circuit Breaker] Erro ao registrar resultado (%s).", type(exc).__name__)
