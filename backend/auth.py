import os
import time
import asyncio
from datetime import datetime, timezone, timedelta
from typing import Optional
from jose import JWTError, jwt
from passlib.context import CryptContext
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from backend.database import get_db

JWT_SECRET = os.getenv("JWT_SECRET", "")
if not JWT_SECRET:
    raise RuntimeError(
        "JWT_SECRET não definido. Configure a variável de ambiente JWT_SECRET "
        "no arquivo .env antes de iniciar o backend."
    )
if len(JWT_SECRET) < 32:
    # HS256 com segredo curto é força-bruta-ável offline a partir de um único token.
    import warnings
    warnings.warn(
        "JWT_SECRET tem menos de 32 caracteres. Gere um novo com: "
        "python -c \"import secrets; print(secrets.token_urlsafe(32))\"",
        RuntimeWarning,
        stacklevel=1,
    )
JWT_ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_DAYS = 7

# Revalidação do usuário no banco (existe? qual o role atual?) com cache curto.
# Sem isso, um usuário excluído ou rebaixado continuava válido (inclusive como
# admin) por até 7 dias — o tempo de vida do token.
_USER_STATE_TTL_SECONDS = 60
_user_state_cache: dict[str, tuple[float, Optional[str]]] = {}
_user_state_lock = asyncio.Lock()

# Contexto de criptografia de senhas
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

# Provedor do token Bearer
security = HTTPBearer()

def hash_password(password: str) -> str:
    return pwd_context.hash(password)

def verify_password(plain_password: str, hashed_password: str) -> bool:
    try:
        return pwd_context.verify(plain_password, hashed_password)
    except (ValueError, TypeError):
        # Hash corrompido/inesperado no banco não deve virar 500.
        return False

def create_access_token(user_id: str, username: str, role: str) -> str:
    now = datetime.now(timezone.utc)
    expire = now + timedelta(days=ACCESS_TOKEN_EXPIRE_DAYS)
    to_encode = {
        "sub": user_id,
        "username": username,
        "role": role,
        "iat": now,
        "exp": expire
    }
    encoded_jwt = jwt.encode(to_encode, JWT_SECRET, algorithm=JWT_ALGORITHM)
    return encoded_jwt


def invalidate_user_state_cache(user_id: Optional[str] = None) -> None:
    """Chame após alterar role/excluir usuário para o efeito ser imediato."""
    if user_id is None:
        _user_state_cache.clear()
    else:
        _user_state_cache.pop(user_id, None)


async def _current_role(user_id: str) -> Optional[str]:
    """Role atual do usuário no banco ou ``None`` se ele não existe mais."""
    now = time.monotonic()
    cached = _user_state_cache.get(user_id)
    if cached and cached[0] > now:
        return cached[1]
    async with _user_state_lock:
        cached = _user_state_cache.get(user_id)
        if cached and cached[0] > now:
            return cached[1]
        db = await get_db()
        try:
            async with db.execute("SELECT role FROM users WHERE id = ?", (user_id,)) as cur:
                row = await cur.fetchone()
        finally:
            await db.close()
        role = (row[0] or "user") if row else None
        _user_state_cache[user_id] = (now + _USER_STATE_TTL_SECONDS, role)
        return role


def _decode_claims(token: str) -> Optional[dict]:
    try:
        payload = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
    except JWTError:
        return None
    user_id = payload.get("sub")
    username = payload.get("username")
    if not user_id or not username:
        return None
    return {"id": user_id, "username": username, "role": payload.get("role", "user")}


async def get_current_user(credentials: HTTPAuthorizationCredentials = Depends(security)) -> dict:
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Token de autenticação inválido ou expirado.",
        headers={"WWW-Authenticate": "Bearer"},
    )
    user = _decode_claims(credentials.credentials)
    if not user:
        raise credentials_exception
    role = await _current_role(user["id"])
    if role is None:
        raise credentials_exception
    user["role"] = role
    return user


async def require_admin(user: dict = Depends(get_current_user)) -> dict:
    if user.get("role") != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Acesso restrito a administradores.",
        )
    return user

def decode_token(token: str) -> Optional[dict]:
    """Decodifica o token sem consultar o banco (compatibilidade). Prefira ``resolve_token_user``."""
    return _decode_claims(token)


async def resolve_token_user(token: str) -> Optional[dict]:
    """Versão assíncrona usada pelo WebSocket: valida assinatura E existência do usuário."""
    user = _decode_claims(token)
    if not user:
        return None
    role = await _current_role(user["id"])
    if role is None:
        return None
    user["role"] = role
    return user
