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
    username = body.username.strip().lower()
    email = body.email.strip().lower() if body.email else None
    phone = body.phone.strip() if body.phone else None

    if not username or not body.password:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Usuário e senha são obrigatórios."
        )

    db = await get_db()
    try:
        # Verifica se o usuário já existe
        async with db.execute("SELECT id FROM users WHERE username = ?", (username,)) as cur:
            row = await cur.fetchone()
            if row:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Este nome de usuário já está cadastrado."
                )

        if email:
            async with db.execute("SELECT id FROM users WHERE email = ?", (email,)) as cur:
                row = await cur.fetchone()
                if row:
                    raise HTTPException(
                        status_code=status.HTTP_400_BAD_REQUEST,
                        detail="Este endereço de e-mail já está cadastrado."
                    )

        # Lógica de papel automático: primeiro é Admin, próximos são User
        async with db.execute("SELECT COUNT(id) FROM users") as cur:
            count_row = await cur.fetchone()
            user_count = count_row[0] if count_row else 0

        user_role = "admin" if user_count == 0 else "user"
        user_id = str(uuid.uuid4())
        pwd_hash = hash_password(body.password)

        await db.execute(
            """INSERT INTO users (id, username, password_hash, email, phone, role) 
               VALUES (?, ?, ?, ?, ?, ?)""",
            (user_id, username, pwd_hash, email, phone, user_role)
        )
        await db.commit()
        
        token = create_access_token(user_id, username, user_role)
        return {
            "token": token,
            "user": {
                "id": user_id, 
                "username": username,
                "email": email,
                "phone": phone,
                "role": user_role
            }
        }
    finally:
        await db.close()

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
