"""backend.proactive.accumulator — Acúmulo e convergência de tópicos em segundo plano (F9.1.2).

Permite que o Assistente Proativo / Nexus Pet funcione como um amigo silencioso:
em vez de interromper a cada pesquisa solta, acumula sinais de interesse
(ex: 'voos para Natal' -> 'praias de Natal' -> 'hotéis em Natal') e, ao atingir
a convergência (TriggerThreshold), engatilha um insight útil consolidado
(ex: 'Roteiro de Férias em Natal/RN').
"""
from __future__ import annotations

import json
import re
import unicodedata
import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any, Optional, Sequence

import aiosqlite

from backend.logging_config import get_logger

logger = get_logger(__name__)

DEFAULT_TRIGGER_THRESHOLD = 3
DEFAULT_EXPIRY_DAYS = 7


def normalize_topic_key(category: str, raw_topic: str) -> str:
    """Normaliza categoria e tópico em uma chave estável de agrupamento.

    Exemplo:
        normalize_topic_key("place", "Natal / RN - Ponta Negra")
        -> "place:natal_rn_ponta_negra"
    """
    cat = (category or "other").strip().lower()
    clean = unicodedata.normalize("NFKD", raw_topic or "")
    clean = "".join(c for c in clean if not unicodedata.combining(c))
    clean = re.sub(r"[^a-zA-Z0-9]+", "_", clean).strip("_").lower()
    return f"{cat}:{clean[:60]}" if clean else f"{cat}:geral"


@dataclass
class ProactiveMemory:
    id: str
    user_id: str
    topic_category: str
    topic_key: str
    signal_count: int
    accumulated_context: dict[str, Any]
    insight_ready_id: Optional[str]
    status: str
    last_signal_at: str
    created_at: str

    @classmethod
    def from_row(cls, row: aiosqlite.Row | Sequence[Any]) -> ProactiveMemory:
        return cls(
            id=row[0],
            user_id=row[1],
            topic_category=row[2],
            topic_key=row[3],
            signal_count=row[4],
            accumulated_context=json.loads(row[5]) if isinstance(row[5], str) else (row[5] or {}),
            insight_ready_id=row[6],
            status=row[7],
            last_signal_at=row[8],
            created_at=row[9],
        )


@dataclass
class AccumulateResult:
    memory_id: str
    triggered: bool
    signal_count: int
    status: str
    topic_key: str
    action: str
    prompt_hook: str


def generate_prompt_hook(category: str, topic_label: str) -> str:
    """Gera o gancho de fala amigável para o balão do Pet estilo Clippy."""
    label = topic_label.strip() or "este assunto"
    cat = (category or "").lower()

    if cat == "place":
        return f"Oi! Notei que você está pesquisando sobre {label}... Montei um roteiro de viagem completo. Quer dar uma olhada?"
    elif cat == "product":
        return f"Psiu! Vi que você está de olho em {label}... Reuni um comparativo com detalhes e avaliações. Quer conferir?"
    elif cat == "event":
        return f"Ei! Acompanhei seu interesse sobre {label}... Preparei um resumo das datas e principais novidades. Quer ver?"
    else:
        return f"Olá! Percebi seu interesse em {label} ultimamente... Separei um material bacana sobre isso. Quer dar uma olhada?"


class MemoryTopicAccumulator:
    """Gerencia o acúmulo de memórias temporais e gatilhos de convergência."""

    def __init__(self, db: aiosqlite.Connection, threshold: int = DEFAULT_TRIGGER_THRESHOLD):
        self.db = db
        self.threshold = max(2, threshold)

    async def record_signal(
        self,
        user_id: str,
        category: str,
        topic: str,
        entities: Optional[list[str]] = None,
        query: Optional[str] = None,
        context_snippet: Optional[str] = None,
    ) -> AccumulateResult:
        """Registra um sinal de interesse em segundo plano.

        Se o sinal atingir o threshold de convergência, muda status para
        'ready_to_prompt' e indica que um insight consolidado pode ser disparado.
        """
        topic_key = normalize_topic_key(category, topic)
        now_iso = datetime.now(timezone.utc).isoformat()

        # Buscar memória existente em status 'accumulating'
        async with self.db.execute(
            """
            SELECT id, user_id, topic_category, topic_key, signal_count,
                   accumulated_context, insight_ready_id, status, last_signal_at, created_at
            FROM proactive_memories
            WHERE user_id = ? AND topic_category = ? AND topic_key = ? AND status = 'accumulating'
            LIMIT 1
            """,
            (user_id, category, topic_key),
        ) as cur:
            row = await cur.fetchone()

        if row:
            existing = ProactiveMemory.from_row(row)
            new_count = existing.signal_count + 1
            ctx = existing.accumulated_context

            # Merge de entidades
            existing_entities = set(ctx.get("entities", []))
            if entities:
                existing_entities.update(entities)
            ctx["entities"] = sorted(list(existing_entities))

            # Histórico de termos pesquisados
            queries = ctx.get("queries", [])
            if query and query not in queries:
                queries.append(query)
            ctx["queries"] = queries[-10:]  # limitar histórico

            if context_snippet:
                snippets = ctx.get("snippets", [])
                snippets.append(context_snippet[:200])
                ctx["snippets"] = snippets[-5:]

            ctx["topic_label"] = topic

            triggered = new_count >= self.threshold
            new_status = "ready_to_prompt" if triggered else "accumulating"

            await self.db.execute(
                """
                UPDATE proactive_memories
                SET signal_count = ?,
                    accumulated_context = ?,
                    status = ?,
                    last_signal_at = ?
                WHERE id = ?
                """,
                (new_count, json.dumps(ctx), new_status, now_iso, existing.id),
            )
            await self.db.commit()

            hook = generate_prompt_hook(category, topic)
            action = "trigger_synthesis" if triggered else "accumulating"
            logger.info(
                "[proactive_accumulator] Sinal atualizado: user=%s topic_key=%s count=%d triggered=%s",
                user_id,
                topic_key,
                new_count,
                triggered,
            )
            return AccumulateResult(
                memory_id=existing.id,
                triggered=triggered,
                signal_count=new_count,
                status=new_status,
                topic_key=topic_key,
                action=action,
                prompt_hook=hook,
            )

        # Nova memória
        mem_id = str(uuid.uuid4())
        initial_ctx = {
            "topic_label": topic,
            "entities": sorted(list(set(entities or []))),
            "queries": [query] if query else [],
            "snippets": [context_snippet[:200]] if context_snippet else [],
        }

        await self.db.execute(
            """
            INSERT INTO proactive_memories (
                id, user_id, topic_category, topic_key, signal_count,
                accumulated_context, status, last_signal_at, created_at
            ) VALUES (?, ?, ?, ?, 1, ?, 'accumulating', ?, ?)
            """,
            (mem_id, user_id, category, topic_key, json.dumps(initial_ctx), now_iso, now_iso),
        )
        await self.db.commit()

        hook = generate_prompt_hook(category, topic)
        logger.info(
            "[proactive_accumulator] Nova memória criada: user=%s topic_key=%s count=1",
            user_id,
            topic_key,
        )
        return AccumulateResult(
            memory_id=mem_id,
            triggered=False,
            signal_count=1,
            status="accumulating",
            topic_key=topic_key,
            action="accumulating",
            prompt_hook=hook,
        )

    async def get_ready_memories(self, user_id: str) -> list[ProactiveMemory]:
        """Retorna memórias que atingiram o gatilho e aguardam exibição no balão."""
        async with self.db.execute(
            """
            SELECT id, user_id, topic_category, topic_key, signal_count,
                   accumulated_context, insight_ready_id, status, last_signal_at, created_at
            FROM proactive_memories
            WHERE user_id = ? AND status = 'ready_to_prompt'
            ORDER BY last_signal_at DESC
            """,
            (user_id,),
        ) as cur:
            rows = await cur.fetchall()
        return [ProactiveMemory.from_row(r) for r in rows]

    async def attach_insight(self, memory_id: str, insight_id: str) -> bool:
        """Vincula o insight gerado à memória consolidada."""
        res = await self.db.execute(
            """
            UPDATE proactive_memories
            SET insight_ready_id = ?
            WHERE id = ?
            """,
            (insight_id, memory_id),
        )
        await self.db.commit()
        return res.rowcount > 0

    async def mark_delivered(self, memory_id: str) -> bool:
        """Marca como entregue ao usuário (balão exibido e respondido)."""
        res = await self.db.execute(
            """
            UPDATE proactive_memories
            SET status = 'delivered'
            WHERE id = ?
            """,
            (memory_id,),
        )
        await self.db.commit()
        return res.rowcount > 0

    async def mark_archived(self, memory_id: str) -> bool:
        """Arquiva memória dispensada ou obsoleta."""
        res = await self.db.execute(
            """
            UPDATE proactive_memories
            SET status = 'archived'
            WHERE id = ?
            """,
            (memory_id,),
        )
        await self.db.commit()
        return res.rowcount > 0
