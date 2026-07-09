from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Optional
from backend.database import get_db, check_and_deactivate_model
from backend.providers.registry import get_provider, get_model_name

router = APIRouter(prefix="/api/enhancer", tags=["enhancer"])

DEFAULT_SYSTEM_PROMPT = (
    "Você é um engenheiro de prompt especialista. Seu objetivo é pegar o prompt "
    "simples enviado pelo usuário e expandi-lo, adicionando clareza, contexto "
    "implícito, estrutura lógica e removendo ambiguidades.\n\n"
    "Retorne APENAS o prompt aprimorado final, sem introduções, explicações ou aspas."
)


class EnhancerConfigOut(BaseModel):
    enhancer_provider_id: Optional[str] = None
    enhancer_model_id: Optional[str] = None
    enhancer_enabled: bool = True
    enhancer_system_prompt: str = DEFAULT_SYSTEM_PROMPT


class EnhancerConfigIn(BaseModel):
    enhancer_provider_id: Optional[str] = None
    enhancer_model_id: Optional[str] = None
    enhancer_enabled: Optional[bool] = None
    enhancer_system_prompt: Optional[str] = None


class EnhancerProcessIn(BaseModel):
    prompt: str


class EnhancerProcessOut(BaseModel):
    enhanced_prompt: str


async def _get_config() -> dict:
    db = await get_db()
    try:
        async with db.execute(
            "SELECT enhancer_provider_id, enhancer_model_id, enhancer_enabled, enhancer_system_prompt "
            "FROM enhancer_config WHERE id = 1"
        ) as cur:
            row = await cur.fetchone()
        if row:
            return {
                "enhancer_provider_id": row[0],
                "enhancer_model_id": row[1],
                "enhancer_enabled": bool(row[2]),
                "enhancer_system_prompt": row[3] or DEFAULT_SYSTEM_PROMPT,
            }
        return {
            "enhancer_provider_id": None,
            "enhancer_model_id": None,
            "enhancer_enabled": True,
            "enhancer_system_prompt": DEFAULT_SYSTEM_PROMPT,
        }
    finally:
        await db.close()


@router.get("/config", response_model=EnhancerConfigOut)
async def get_config():
    return await _get_config()


@router.post("/config", response_model=EnhancerConfigOut)
async def save_config(body: EnhancerConfigIn):
    db = await get_db()
    try:
        current = await _get_config()
        updates = {k: v for k, v in body.model_dump().items() if v is not None}
        merged = {**current, **updates}

        await db.execute(
            """INSERT INTO enhancer_config (id, enhancer_provider_id, enhancer_model_id, enhancer_enabled, enhancer_system_prompt)
               VALUES (1, ?, ?, ?, ?)
               ON CONFLICT(id) DO UPDATE SET
                   enhancer_provider_id = excluded.enhancer_provider_id,
                   enhancer_model_id = excluded.enhancer_model_id,
                   enhancer_enabled = excluded.enhancer_enabled,
                   enhancer_system_prompt = excluded.enhancer_system_prompt""",
            (
                merged["enhancer_provider_id"],
                merged["enhancer_model_id"],
                1 if merged["enhancer_enabled"] else 0,
                merged["enhancer_system_prompt"],
            ),
        )
        await db.commit()
        return await _get_config()
    finally:
        await db.close()


@router.post("/process", response_model=EnhancerProcessOut)
async def process_prompt(body: EnhancerProcessIn):
    if not body.prompt.strip():
        raise HTTPException(status_code=400, detail="Prompt vazio.")

    config = await _get_config()

    if not config["enhancer_enabled"]:
        raise HTTPException(status_code=400, detail="O Melhorador está desativado nas configurações.")

    provider_id = config["enhancer_provider_id"]
    model_id = config["enhancer_model_id"]

    if not provider_id or not model_id:
        raise HTTPException(
            status_code=400,
            detail="Configure o provedor e modelo do Melhorador nas Configurações.",
        )

    db = await get_db()
    try:
        try:
            provider = await get_provider(provider_id, db)
            model_name = await get_model_name(model_id, db)
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e))

        messages = [
            {"role": "system", "content": config["enhancer_system_prompt"]},
            {"role": "user", "content": body.prompt},
        ]

        full_response = ""
        try:
            async for token in provider.stream_chat(
                model=model_name,
                messages=messages,
                temperature=0.7,
                max_tokens=2048,
            ):
                full_response += str(token)
        except Exception as e:
            error_msg = str(e)
            await check_and_deactivate_model(model_id, error_msg, db)
            raise HTTPException(status_code=502, detail=f"Erro ao chamar o modelo: {error_msg}")

        if not full_response.strip():
            raise HTTPException(status_code=502, detail="Resposta vazia do modelo.")

        return EnhancerProcessOut(enhanced_prompt=full_response.strip())
    finally:
        await db.close()
