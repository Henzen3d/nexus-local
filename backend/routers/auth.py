from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel
import uuid
from backend.database import get_db
from backend.auth import hash_password, verify_password, create_access_token

from typing import Optional

router = APIRouter(prefix="/api/auth", tags=["auth"])

class UserAuthSchema(BaseModel):
    username: str
    password: str

class UserRegisterSchema(BaseModel):
    username: str
    password: str
    email: Optional[str] = None
    phone: Optional[str] = None

@router.post("/register")
async def register(body: UserRegisterSchema):
    raise HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail="Cadastro público fechado. Peça ao administrador para criar a conta.",
    )


@router.post("/login")
async def login(body: UserAuthSchema):
    username = body.username.strip().lower()
    db = await get_db()
    try:
        async with db.execute(
            "SELECT id, password_hash, email, phone, role FROM users WHERE username = ?", 
            (username,)
        ) as cur:
            row = await cur.fetchone()
            if not row:
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="Usuário ou senha incorretos."
                )
            
            user_id, pwd_hash, email, phone, role = row
            if not verify_password(body.password, pwd_hash):
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="Usuário ou senha incorretos."
                )
            
            token = create_access_token(user_id, username, role)
            return {
                "token": token,
                "user": {
                    "id": user_id, 
                    "username": username,
                    "email": email,
                    "phone": phone,
                    "role": role
                }
            }
    finally:
        await db.close()
