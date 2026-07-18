"""
backend/routers/families.py
FastAPI router — CRUD de famílias de modelos + assistente de sugestão de agrupamento.

Endpoints:
  Famílias:
    GET    /api/families/                        – lista todas as famílias
    GET    /api/families/{family_id}              – detalhe com membros
    POST   /api/families/                        – cria nova família
    PUT    /api/families/{family_id}              – atualiza display_name / description
    DELETE /api/families/{family_id}             – apaga família (cascata nos membros)

  Membros:
    GET    /api/families/{family_id}/members      – lista membros ordenados por fallback_order
    POST   /api/families/{family_id}/members      – adiciona modelo à família
    DELETE /api/families/{family_id}/members/{model_id} – remove modelo da família

  Sugestão (Fase 7.2):
    GET    /api/families/suggest                 – sugere agrupamentos baseado em padrões de nome
"""

from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel, Field
from typing import List, Optional
import re

from backend.database import get_db
from backend.auth import get_current_user, require_admin

router = APIRouter(prefix="/api/families", tags=["families"])


# ─── Pydantic schemas ──────────────────────────────────────────────────────────

class FamilyCreate(BaseModel):
    id: str = Field(..., description="Identificador estável, ex: 'deepseek-r1'")
    display_name: str = Field(..., description="Nome legível da família")
    description: Optional[str] = Field(None, description="Descrição opcional")


class FamilyUpdate(BaseModel):
    display_name: Optional[str] = None
    description: Optional[str] = None


class MemberCreate(BaseModel):
    model_id: str = Field(..., description="ID do modelo, ex: 'openrouter/deepseek/deepseek-r1'")
    fallback_order: int = Field(..., gt=0, description="Ordem de fallback (1 = primário)")


# ─── Helpers internos ──────────────────────────────────────────────────────────

async def _fetch_family(db, family_id: str):
    async with db.execute(
        "SELECT id, display_name, description FROM model_families WHERE id = ?",
        (family_id,),
    ) as cur:
        return await cur.fetchone()


async def _list_members(db, family_id: str):
    async with db.execute(
        """SELECT mfm.model_id, mfm.fallback_order, m.display_name
           FROM model_family_members mfm
           LEFT JOIN models m ON m.id = mfm.model_id
           WHERE mfm.family_id = ?
           ORDER BY mfm.fallback_order""",
        (family_id,),
    ) as cur:
        rows = await cur.fetchall()
    return [{"model_id": r[0], "fallback_order": r[1], "display_name": r[2]} for r in rows]


# ─── CRUD de famílias ──────────────────────────────────────────────────────────

@router.get("/", response_model=List[dict])
async def list_families(current_user: dict = Depends(get_current_user)):
    """Lista todas as famílias cadastradas."""
    db = await get_db()
    async with db.execute(
        "SELECT id, display_name, description FROM model_families ORDER BY id"
    ) as cur:
        rows = await cur.fetchall()
    await db.close()
    return [{"id": r[0], "display_name": r[1], "description": r[2]} for r in rows]


@router.get("/suggest", response_model=List[dict])
async def suggest_family_groupings(current_user: dict = Depends(get_current_user)):
    """
    Assistente de sugestão de agrupamento de modelos em famílias (Fase 7.2).

    Analisa os modelos cadastrados e detecta padrões de nomenclatura comuns
    (ex: 'deepseek-r1', 'llama-3.3', 'gemma-3') para sugerir famílias ainda
    não existentes.

    Retorna uma lista de sugestões, cada uma com:
      - suggested_id        – slug proposto para a família
      - suggested_name      – nome legível sugerido
      - matched_models      – modelos que seriam agrupados
      - already_has_family  – True se já existe uma família com esse id
    """
    db = await get_db()

    # 1. Carrega todos os modelos habilitados
    async with db.execute(
        "SELECT id, display_name FROM models WHERE enabled = 1"
    ) as cur:
        model_rows = await cur.fetchall()

    # 2. Carrega famílias já existentes
    async with db.execute("SELECT id FROM model_families") as cur:
        existing_families = {r[0] for r in await cur.fetchall()}

    await db.close()

    # 3. Padrões de nome conhecidos (nome normalizado → regex que captura variantes)
    #    A chave é o slug da família; o valor é (nome legível, regex)
    KNOWN_PATTERNS: List[tuple] = [
        # DeepSeek
        ("deepseek-r1",    "DeepSeek R1",    re.compile(r"deepseek.?r1", re.I)),
        ("deepseek-v3",    "DeepSeek V3",    re.compile(r"deepseek.?v3", re.I)),
        ("deepseek-coder", "DeepSeek Coder", re.compile(r"deepseek.?coder", re.I)),
        # Llama
        ("llama-4",        "Llama 4",        re.compile(r"llama.?4", re.I)),
        ("llama-3.3",      "Llama 3.3",      re.compile(r"llama.?3[._]?3", re.I)),
        ("llama-3.1",      "Llama 3.1",      re.compile(r"llama.?3[._]?1", re.I)),
        ("llama-3",        "Llama 3",        re.compile(r"llama.?3(?![._]?[13])", re.I)),
        # Qwen
        ("qwen3",          "Qwen 3",         re.compile(r"qwen.?3", re.I)),
        ("qwen2.5",        "Qwen 2.5",       re.compile(r"qwen.?2[._]?5", re.I)),
        ("qwen2",          "Qwen 2",         re.compile(r"qwen.?2(?![._]?5)", re.I)),
        # Gemma
        ("gemma-3",        "Gemma 3",        re.compile(r"gemma.?3", re.I)),
        ("gemma-2",        "Gemma 2",        re.compile(r"gemma.?2", re.I)),
        # Mistral / Mixtral
        ("mixtral",        "Mixtral",        re.compile(r"mixtral", re.I)),
        ("mistral-small",  "Mistral Small",  re.compile(r"mistral.?small", re.I)),
        ("mistral-large",  "Mistral Large",  re.compile(r"mistral.?large", re.I)),
        ("mistral-nemo",   "Mistral Nemo",   re.compile(r"mistral.?nemo", re.I)),
        # GPT
        ("gpt-4o",         "GPT-4o",         re.compile(r"gpt.?4o", re.I)),
        ("gpt-4-turbo",    "GPT-4 Turbo",    re.compile(r"gpt.?4.?turbo", re.I)),
        ("gpt-4",          "GPT-4",          re.compile(r"gpt.?4(?!o|.?turbo)", re.I)),
        # Claude
        ("claude-3.7",     "Claude 3.7",     re.compile(r"claude.?3[._]?7", re.I)),
        ("claude-3.5",     "Claude 3.5",     re.compile(r"claude.?3[._]?5", re.I)),
        ("claude-3",       "Claude 3",       re.compile(r"claude.?3(?![._]?[57])", re.I)),
        # Gemini
        ("gemini-2.5",     "Gemini 2.5",     re.compile(r"gemini.?2[._]?5", re.I)),
        ("gemini-2",       "Gemini 2",       re.compile(r"gemini.?2(?![._]?5)", re.I)),
        ("gemini-1.5",     "Gemini 1.5",     re.compile(r"gemini.?1[._]?5", re.I)),
        # Phi
        ("phi-4",          "Phi 4",          re.compile(r"phi.?4", re.I)),
        ("phi-3",          "Phi 3",          re.compile(r"phi.?3", re.I)),
        # WizardLM / Wizard
        ("wizardlm",       "WizardLM",       re.compile(r"wizard.?lm", re.I)),
        # Falcon
        ("falcon",         "Falcon",         re.compile(r"falcon", re.I)),
    ]

    # 4. Para cada padrão, verifica quais modelos batem
    suggestions = []
    for slug, name, pattern in KNOWN_PATTERNS:
        matched = [
            {"id": m[0], "display_name": m[1]}
            for m in model_rows
            if pattern.search(m[0]) or (m[1] and pattern.search(m[1]))
        ]
        if len(matched) >= 2:
            suggestions.append({
                "suggested_id": slug,
                "suggested_name": name,
                "matched_models": matched,
                "already_has_family": slug in existing_families,
            })

    # Ordena: primeiro as sugestões novas (sem família), depois as que já existem
    suggestions.sort(key=lambda s: (s["already_has_family"], s["suggested_id"]))
    return suggestions


@router.get("/{family_id}", response_model=dict)
async def get_family(family_id: str, current_user: dict = Depends(get_current_user)):
    """Retorna os detalhes de uma família com seus membros."""
    db = await get_db()
    family = await _fetch_family(db, family_id)
    if not family:
        await db.close()
        raise HTTPException(status_code=404, detail="Família não encontrada")
    members = await _list_members(db, family_id)
    await db.close()
    return {
        "id": family[0],
        "display_name": family[1],
        "description": family[2],
        "members": members,
    }


@router.post("/", response_model=dict, status_code=201)
async def create_family(payload: FamilyCreate, current_user: dict = Depends(require_admin)):
    """Cria uma nova família de modelos."""
    db = await get_db()
    async with db.execute("SELECT 1 FROM model_families WHERE id = ?", (payload.id,)) as cur:
        if await cur.fetchone():
            await db.close()
            raise HTTPException(status_code=400, detail="Família já existe")
    await db.execute(
        "INSERT INTO model_families (id, display_name, description) VALUES (?, ?, ?)",
        (payload.id, payload.display_name, payload.description),
    )
    await db.commit()
    await db.close()
    return {"id": payload.id, "display_name": payload.display_name, "description": payload.description}


@router.put("/{family_id}", response_model=dict)
async def update_family(family_id: str, payload: FamilyUpdate, current_user: dict = Depends(require_admin)):
    """Atualiza display_name e/ou description de uma família."""
    db = await get_db()
    if not await _fetch_family(db, family_id):
        await db.close()
        raise HTTPException(status_code=404, detail="Família não encontrada")
    fields, values = [], []
    if payload.display_name is not None:
        fields.append("display_name = ?")
        values.append(payload.display_name)
    if payload.description is not None:
        fields.append("description = ?")
        values.append(payload.description)
    if not fields:
        await db.close()
        raise HTTPException(status_code=400, detail="Nenhum campo para atualizar")
    values.append(family_id)
    await db.execute(f"UPDATE model_families SET {', '.join(fields)} WHERE id = ?", tuple(values))
    await db.commit()
    await db.close()
    return {"id": family_id, "updated": True}


@router.delete("/{family_id}", response_model=dict)
async def delete_family(family_id: str, current_user: dict = Depends(require_admin)):
    """Apaga uma família e seus membros (CASCADE)."""
    db = await get_db()
    async with db.execute("SELECT 1 FROM model_families WHERE id = ?", (family_id,)) as cur:
        if not await cur.fetchone():
            await db.close()
            raise HTTPException(status_code=404, detail="Família não encontrada")
    await db.execute("DELETE FROM model_families WHERE id = ?", (family_id,))
    await db.commit()
    await db.close()
    return {"deleted": True, "id": family_id}


# ─── Gerenciamento de membros ──────────────────────────────────────────────────

@router.get("/{family_id}/members", response_model=List[dict])
async def list_family_members(family_id: str, current_user: dict = Depends(get_current_user)):
    """Lista os modelos membros de uma família, ordenados por fallback_order."""
    db = await get_db()
    if not await _fetch_family(db, family_id):
        await db.close()
        raise HTTPException(status_code=404, detail="Família não encontrada")
    members = await _list_members(db, family_id)
    await db.close()
    return members


@router.post("/{family_id}/members", response_model=dict, status_code=201)
async def add_family_member(family_id: str, payload: MemberCreate, current_user: dict = Depends(require_admin)):
    """Adiciona um modelo à família com uma posição de fallback."""
    db = await get_db()
    if not await _fetch_family(db, family_id):
        await db.close()
        raise HTTPException(status_code=404, detail="Família não encontrada")
    async with db.execute("SELECT 1 FROM models WHERE id = ?", (payload.model_id,)) as cur:
        if not await cur.fetchone():
            await db.close()
            raise HTTPException(status_code=400, detail="Modelo não existe")
    await db.execute(
        "INSERT OR REPLACE INTO model_family_members (id, family_id, model_id, fallback_order) VALUES (?, ?, ?, ?)",
        (f"{family_id}:{payload.model_id}", family_id, payload.model_id, payload.fallback_order),
    )
    await db.commit()
    await db.close()
    return {"family_id": family_id, "model_id": payload.model_id, "fallback_order": payload.fallback_order}


@router.delete("/{family_id}/members/{model_id:path}", response_model=dict)
async def remove_family_member(family_id: str, model_id: str, current_user: dict = Depends(require_admin)):
    """Remove um modelo de uma família."""
    db = await get_db()
    async with db.execute(
        "SELECT 1 FROM model_family_members WHERE family_id = ? AND model_id = ?",
        (family_id, model_id),
    ) as cur:
        if not await cur.fetchone():
            await db.close()
            raise HTTPException(status_code=404, detail="Membro não encontrado nessa família")
    await db.execute(
        "DELETE FROM model_family_members WHERE family_id = ? AND model_id = ?",
        (family_id, model_id),
    )
    await db.commit()
    await db.close()
    return {"deleted": True, "family_id": family_id, "model_id": model_id}
