from fastapi import APIRouter, HTTPException, Request, status
from pydantic import BaseModel, Field
from backend.database import get_db
from backend.auth import hash_password, verify_password, create_access_token
from backend.logging_config import get_logger
from backend.rate_limit import SlidingWindowLimiter, client_ip

from typing import Optional

logger = get_logger(__name__)

router = APIRouter(prefix="/api/auth", tags=["auth"])

# Anti brute-force: o /login é público (Cloudflare Tunnel) e não tinha nenhum limite.
# 10 tentativas por IP / 15 min e 5 por usuário / 15 min; sucesso zera o contador.
_ip_limiter = SlidingWindowLimiter(max_hits=10, window_seconds=15 * 60)
_user_limiter = SlidingWindowLimiter(max_hits=5, window_seconds=15 * 60)

# Hash bcrypt de uma senha aleatória usado quando o usuário não existe, para que
# o tempo de resposta seja igual ao de uma senha errada (evita enumerar logins).
_DUMMY_HASH = hash_password("nexuslocal-dummy-password-for-constant-time")

class UserAuthSchema(BaseModel):
    username: str = Field(min_length=1, max_length=128)
    password: str = Field(min_length=1, max_length=256)

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
async def login(body: UserAuthSchema, request: Request):
    username = body.username.strip().lower()
    ip = client_ip(request)

    retry_after = await _ip_limiter.hit(f"ip:{ip}")
    if not retry_after:
        retry_after = await _user_limiter.hit(f"user:{username}")
    if retry_after:
        logger.warning("Login bloqueado por rate limit (ip=%s, user=%s)", ip, username)
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Muitas tentativas de login. Tente novamente em alguns minutos.",
            headers={"Retry-After": str(retry_after)},
        )

    db = await get_db()
    try:
        async with db.execute(
            "SELECT id, password_hash, email, phone, role FROM users WHERE username = ?", 
            (username,)
        ) as cur:
            row = await cur.fetchone()

        if not row:
            # Tempo constante: executa o bcrypt mesmo sem usuário.
            verify_password(body.password, _DUMMY_HASH)
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Usuário ou senha incorretos."
            )

        user_id, pwd_hash, email, phone, role = row
        if not verify_password(body.password, pwd_hash):
            logger.info("Login falhou (ip=%s, user=%s)", ip, username)
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Usuário ou senha incorretos."
            )

        await _user_limiter.reset(f"user:{username}")
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
