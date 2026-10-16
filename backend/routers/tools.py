"""backend/routers/tools.py — Rotas para execução de ferramentas (code_exec, diagrams) e administração.
"""
from __future__ import annotations

import json
from typing import Any, Optional
import aiosqlite
from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field

from backend.auth import get_current_user, require_admin
from backend.database import get_db
from backend.logging_config import get_logger
from backend.tools.base import DEFAULT_TTL, ToolResult
from backend.tools.cache import invalidate_family
from backend.tools.dispatcher import dispatch_tool
from backend.tools.failover import (
    get_tool_provider_quota_status,
    mark_tool_provider_success,
)
from backend.tools.registry import ToolRegistry, get_provider
from backend.tools.sync_public_apis import sync_public_apis

logger = get_logger(__name__)

router = APIRouter(tags=["tools"])


# ── Schemas de Entrada ──────────────────────────────────────────────

class CodeExecRequest(BaseModel):
    language: str = Field(..., description="Linguagem de programação (ex: python, javascript, java, cpp, go, rust)")
    code: str = Field(..., max_length=65536, description="Código fonte a ser executado")
    stdin: Optional[str] = Field(default="", description="Entrada padrão (stdin)")


class DiagramRequest(BaseModel):
    type: str = Field(default="mermaid", description="Tipo de diagrama (mermaid, plantuml, d2, graphviz, chart)")
    source_code: str = Field(..., max_length=65536, description="Código fonte ou especificação do diagrama")
    width: Optional[int] = Field(default=600, ge=100, le=2400)
    height: Optional[int] = Field(default=380, ge=100, le=2400)


class ToolToggleRequest(BaseModel):
    enabled: bool


class ToolConfigUpdate(BaseModel):
    global_enabled: Optional[bool] = None
    auto_detection: Optional[bool] = None
    rate_limit_per_user: Optional[int] = None
    ttls: Optional[dict[str, int]] = None


# ── Endpoints de Usuário (Artifacts Avançados) ───────────────────────

@router.post("/api/tools/execute")
async def execute_code(
    request: CodeExecRequest,
    user: dict = Depends(get_current_user),
    db: aiosqlite.Connection = Depends(get_db),
):
    """Executa código fonte remotamente via Piston/Judge0 de forma isolada."""
    try:
        result = await dispatch_tool(
            family="code_exec",
            params={
                "language": request.language,
                "code": request.code,
                "stdin": request.stdin or "",
            },
            user_id=user["id"],
            db=db,
        )
        return result.to_dict()
    finally:
        await db.close()


@router.post("/api/tools/diagram")
async def render_diagram(
    request: DiagramRequest,
    user: dict = Depends(get_current_user),
    db: aiosqlite.Connection = Depends(get_db),
):
    """Renderiza diagramas (Mermaid, PlantUML, D2) ou gráficos Chart.js em SVG sanitizado."""
    try:
        result = await dispatch_tool(
            family="diagrams",
            params={
                "type": request.type,
                "source": request.source_code,
                "width": request.width,
                "height": request.height,
            },
            user_id=user["id"],
            db=db,
        )
        return result.to_dict()
    finally:
        await db.close()


# ── Endpoints Administrativos ────────────────────────────────────────

@router.get("/api/admin/tools/status")
async def get_tools_status(
    admin: dict = Depends(require_admin),
    db: aiosqlite.Connection = Depends(get_db),
):
    """Retorna status de saúde, quotas e estatísticas de todas as famílias e provedores."""
    try:
        # Carrega famílias
        async with db.execute(
            "SELECT id, display_name, description, enabled FROM tool_families ORDER BY display_name"
        ) as cur:
            fam_rows = await cur.fetchall()

        # Carrega provedores com quota
        async with db.execute(
            """
            SELECT p.id, p.family_id, p.display_name, p.base_url, p.requires_key,
                   p.env_key_name, p.fallback_order, p.enabled,
                   q.status, q.consecutive_errors, q.exhausted_at, q.estimated_reset_at, q.last_error_message
            FROM tool_providers p
            LEFT JOIN tool_provider_quota q ON q.provider_id = p.id
            ORDER BY p.family_id, p.fallback_order
            """
        ) as cur:
            prov_rows = await cur.fetchall()

        # Estatísticas das últimas 24h por provedor e família
        async with db.execute(
            """
            SELECT provider_id, family,
                   count(*) as total_calls,
                   sum(cache_hit) as cache_hits,
                   avg(latency_ms) as avg_latency
            FROM tool_usage_log
            WHERE created_at >= datetime('now', '-24 hours')
            GROUP BY provider_id, family
            """
        ) as cur:
            stats_rows = await cur.fetchall()

        stats_by_prov = {r[0]: {"total": r[2], "hits": r[3] or 0, "latency": round(r[4] or 0, 1)} for r in stats_rows}

        # Organiza provedores por família
        prov_by_fam: dict[str, list] = {}
        active_providers = 0
        exhausted_providers = 0

        for r in prov_rows:
            pid = r[0]
            fid = r[1]
            q_status = r[8] or "available"
            if q_status == "exhausted":
                exhausted_providers += 1
            else:
                active_providers += 1

            prov_stats = stats_by_prov.get(pid, {"total": 0, "hits": 0, "latency": 0.0})
            total_calls = prov_stats["total"]
            hit_rate = round(prov_stats["hits"] / total_calls, 2) if total_calls > 0 else 0.0

            prov_data = {
                "id": pid,
                "display_name": r[2],
                "base_url": r[3],
                "requires_key": bool(r[4]),
                "env_key_name": r[5],
                "fallback_order": r[6],
                "enabled": bool(r[7]),
                "status": q_status,
                "consecutive_errors": r[9] or 0,
                "exhausted_at": r[10],
                "estimated_reset_at": r[11],
                "last_error": r[12],
                "total_calls_24h": total_calls,
                "cache_hit_rate": hit_rate,
                "avg_latency_ms": prov_stats["latency"],
            }
            if fid not in prov_by_fam:
                prov_by_fam[fid] = []
            prov_by_fam[fid].append(prov_data)

        # Monta resposta final de famílias
        families_res = []
        total_calls_24h = sum(s["total"] for s in stats_by_prov.values())
        total_hits_24h = sum(s["hits"] for s in stats_by_prov.values())
        global_hit_rate = round(total_hits_24h / total_calls_24h, 2) if total_calls_24h > 0 else 0.0

        for fid, dname, desc, en in fam_rows:
            f_providers = prov_by_fam.get(fid, [])
            families_res.append({
                "id": fid,
                "display_name": dname,
                "description": desc,
                "enabled": bool(en),
                "ttl_seconds": DEFAULT_TTL.get(fid, 900),
                "providers": f_providers,
            })

        return {
            "families": families_res,
            "global_stats": {
                "total_calls_24h": total_calls_24h,
                "cache_hit_rate": global_hit_rate,
                "active_providers": active_providers,
                "exhausted_providers": exhausted_providers,
            },
        }
    finally:
        await db.close()


@router.put("/api/admin/tools/provider/{provider_id}/toggle")
async def toggle_provider(
    provider_id: str,
    body: ToolToggleRequest,
    admin: dict = Depends(require_admin),
    db: aiosqlite.Connection = Depends(get_db),
):
    """Habilita ou desabilita um provedor de ferramenta."""
    try:
        new_val = 1 if body.enabled else 0
        await db.execute("UPDATE tool_providers SET enabled = ? WHERE id = ?", (new_val, provider_id))
        await db.commit()

        # Atualiza status em memória no ToolRegistry
        p = get_provider(provider_id)
        if p:
            p.enabled = body.enabled

        return {"provider_id": provider_id, "enabled": body.enabled}
    finally:
        await db.close()


@router.post("/api/admin/tools/provider/{provider_id}/test")
async def test_provider(
    provider_id: str,
    admin: dict = Depends(require_admin),
    db: aiosqlite.Connection = Depends(get_db),
):
    """Executa uma chamada de teste real a um provedor específico."""
    try:
        p = get_provider(provider_id)
        if not p:
            raise HTTPException(status_code=404, detail=f"Provedor '{provider_id}' não encontrado em memória")

        # Parâmetros padrão para teste de cada família
        sample_params = {
            "weather": {"city": "Brasília", "days": 1},
            "currency": {"from": "USD", "to": "BRL"},
            "brasil": {"type": "cep", "value": "01001000"},
            "knowledge": {"query": "Alan Turing"},
            "news": {"query": "tecnologia", "max_results": 2},
            "translation": {"text": "Hello world", "source": "en", "target": "pt"},
            "geo": {"query": "Brasília, Brasil"},
            "fun": {"type": "fact"},
            "code_exec": {"language": "python", "code": "print(2 + 2)"},
            "diagrams": {"type": "mermaid", "source": "graph TD; A-->B;"},
        }

        params = sample_params.get(p.family, {"query": "teste"})
        res = await p.execute(params)

        if res.success:
            await mark_tool_provider_success(provider_id, db)

        return res.to_dict()
    finally:
        await db.close()


@router.delete("/api/admin/tools/cache/{family}")
async def clear_family_cache(
    family: str,
    admin: dict = Depends(require_admin),
    db: aiosqlite.Connection = Depends(get_db),
):
    """Limpa todas as entradas de cache para uma família específica."""
    try:
        deleted = await invalidate_family(family, db)
        return {"family": family, "cleared_entries": deleted}
    finally:
        await db.close()


@router.get("/api/admin/tools/usage")
async def get_tools_usage(
    period: str = Query("24h", pattern="^(24h|7d|30d)$"),
    admin: dict = Depends(require_admin),
    db: aiosqlite.Connection = Depends(get_db),
):
    """Retorna métricas de uso agregadas com buckets para visualização."""
    time_filter = "-24 hours" if period == "24h" else ("-7 days" if period == "7d" else "-30 days")
    try:
        # 1. Total por família
        async with db.execute(
            f"""
            SELECT family, count(*) as calls, sum(cache_hit) as hits, avg(latency_ms) as latency
            FROM tool_usage_log
            WHERE created_at >= datetime('now', '{time_filter}')
            GROUP BY family
            ORDER BY calls DESC
            """
        ) as cur:
            family_stats = [
                {"family": r[0], "calls": r[1], "hits": r[2] or 0, "latency_ms": round(r[3] or 0, 1)}
                for r in await cur.fetchall()
            ]

        # 2. Total por provedor
        async with db.execute(
            f"""
            SELECT provider_id, family, count(*) as calls, status
            FROM tool_usage_log
            WHERE created_at >= datetime('now', '{time_filter}')
            GROUP BY provider_id, status
            """
        ) as cur:
            prov_stats = [
                {"provider": r[0], "family": r[1], "calls": r[2], "status": r[3]}
                for r in await cur.fetchall()
            ]

        return {
            "period": period,
            "by_family": family_stats,
            "by_provider": prov_stats,
        }
    finally:
        await db.close()


@router.post("/api/admin/tools/sync-public-apis")
async def trigger_public_apis_sync(
    admin: dict = Depends(require_admin),
    db: aiosqlite.Connection = Depends(get_db),
):
    """Dispara a sincronização manual com o repositório public-apis."""
    try:
        report = await sync_public_apis(db)
        return report
    finally:
        await db.close()


@router.get("/api/admin/tools/public-apis")
async def get_discovered_public_apis(
    relevance: Optional[str] = None,
    category: Optional[str] = None,
    search: Optional[str] = None,
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    admin: dict = Depends(require_admin),
    db: aiosqlite.Connection = Depends(get_db),
):
    """Consulta o catálogo de APIs públicas descobertas no repositório."""
    try:
        clauses = []
        args = []

        if relevance:
            clauses.append("relevance = ?")
            args.append(relevance)
        if category:
            clauses.append("category = ?")
            args.append(category)
        if search:
            clauses.append("(api_name LIKE ? OR description LIKE ?)")
            args.extend([f"%{search}%", f"%{search}%"])

        where_sql = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        query_sql = f"""
            SELECT id, api_name, description, auth, https, cors, category, url, relevance, integrated, discovered_at
            FROM public_apis_registry
            {where_sql}
            ORDER BY CASE relevance WHEN 'high' THEN 1 WHEN 'medium' THEN 2 WHEN 'low' THEN 3 ELSE 4 END, api_name
            LIMIT ? OFFSET ?
        """
        args.extend([limit, offset])

        async with db.execute(query_sql, args) as cur:
            rows = await cur.fetchall()

        apis = [
            {
                "id": r[0],
                "api_name": r[1],
                "description": r[2],
                "auth": r[3],
                "https": bool(r[4]),
                "cors": r[5],
                "category": r[6],
                "url": r[7],
                "relevance": r[8],
                "integrated": bool(r[9]),
                "discovered_at": r[10],
            }
            for r in rows
        ]

        # Total count
        count_sql = f"SELECT count(*) FROM public_apis_registry {where_sql}"
        async with db.execute(count_sql, args[:-2]) as cur:
            c_row = await cur.fetchone()
            total = c_row[0] if c_row else 0

        return {"total": total, "limit": limit, "offset": offset, "apis": apis}
    finally:
        await db.close()


@router.get("/api/admin/tools/config")
async def get_tool_configuration(
    admin: dict = Depends(require_admin),
    db: aiosqlite.Connection = Depends(get_db),
):
    """Lê todas as configurações de ferramentas persistidas na tabela meta."""
    try:
        async with db.execute("SELECT key, value FROM meta WHERE key LIKE 'tool_%'") as cur:
            rows = await cur.fetchall()
            meta_cfg = {r[0]: r[1] for r in rows}

        return {
            "global_enabled": meta_cfg.get("tool_global_enabled", "true").lower() in ("true", "1"),
            "auto_detection": meta_cfg.get("tool_auto_detection", "true").lower() in ("true", "1"),
            "rate_limit_per_user": int(meta_cfg.get("tool_rate_limit_per_user", "10")),
            "ttls": {
                fam: int(meta_cfg.get(f"tool_{fam}_ttl", str(DEFAULT_TTL.get(fam, 900))))
                for fam in DEFAULT_TTL
            },
        }
    finally:
        await db.close()


@router.put("/api/admin/tools/config")
async def update_tool_configuration(
    config: ToolConfigUpdate,
    admin: dict = Depends(require_admin),
    db: aiosqlite.Connection = Depends(get_db),
):
    """Atualiza configurações de ferramentas na tabela meta com hot-reload."""
    try:
        if config.global_enabled is not None:
            val = "true" if config.global_enabled else "false"
            await db.execute("INSERT OR REPLACE INTO meta (key, value) VALUES ('tool_global_enabled', ?)", (val,))

        if config.auto_detection is not None:
            val = "true" if config.auto_detection else "false"
            await db.execute("INSERT OR REPLACE INTO meta (key, value) VALUES ('tool_auto_detection', ?)", (val,))

        if config.rate_limit_per_user is not None:
            await db.execute(
                "INSERT OR REPLACE INTO meta (key, value) VALUES ('tool_rate_limit_per_user', ?)",
                (str(config.rate_limit_per_user),)
            )

        if config.ttls:
            for fam, ttl_val in config.ttls.items():
                await db.execute(
                    "INSERT OR REPLACE INTO meta (key, value) VALUES (?, ?)",
                    (f"tool_{fam}_ttl", str(ttl_val))
                )
                DEFAULT_TTL[fam] = ttl_val

        await db.commit()
        return {"success": True}
    finally:
        await db.close()
