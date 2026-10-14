"""URLs assinadas para anexos.

Os arquivos em ``storage/attachments`` eram servidos por ``StaticFiles`` sem
nenhuma autenticação: qualquer pessoa com o caminho (que aparece em payloads de
API, histórico do navegador, logs do proxy e no cache do Cloudflare — o Nginx
enviava ``Cache-Control: public``) baixava o arquivo de qualquer usuário.

Como ``<img src>`` não envia ``Authorization``, a solução é emitir URLs assinadas
(HMAC-SHA256 derivado do ``JWT_SECRET``) com expiração. Os endpoints que montam
``file_url``/``thumbnail_url`` passam por :func:`attachment_url`, e a rota
``GET /attachments/{path}`` só serve o arquivo se a assinatura conferir.
"""

from __future__ import annotations

import hashlib
import hmac
import os
import time
from urllib.parse import urlencode

# 7 dias: o payload de uma conversa é refeito a cada abertura, então URLs
# "velhas" só existem em abas abertas há muito tempo.
def _ttl_from_env() -> int:
    try:
        v = int(os.getenv("ATTACHMENTS_URL_TTL_SECONDS") or 0)
    except ValueError:
        v = 0
    return v if v > 0 else 7 * 24 * 3600


DEFAULT_TTL_SECONDS = _ttl_from_env()


def _signing_key() -> bytes:
    secret = os.getenv("ATTACHMENTS_SIGNING_SECRET") or os.getenv("JWT_SECRET") or ""
    # Deriva uma chave própria (não reutiliza o segredo cru do JWT em outro contexto).
    return hashlib.sha256(b"nexuslocal.attachments.v1:" + secret.encode("utf-8")).digest()


def normalize_rel_path(rel_path: str) -> str:
    """Normaliza separadores (linhas legadas do Windows usam ``\\``) e remove ``/`` inicial."""
    return (rel_path or "").replace("\\", "/").lstrip("/")


def sign_attachment_path(rel_path: str, expires_at: int) -> str:
    msg = f"{normalize_rel_path(rel_path)}|{int(expires_at)}".encode("utf-8")
    return hmac.new(_signing_key(), msg, hashlib.sha256).hexdigest()[:40]


def attachment_url(rel_path: str | None, ttl_seconds: int = DEFAULT_TTL_SECONDS) -> str | None:
    """Monta ``/attachments/<rel>?exp=<ts>&sig=<hmac>`` ou ``None`` se não houver caminho."""
    if not rel_path:
        return None
    rel = normalize_rel_path(rel_path)
    exp = int(time.time()) + int(ttl_seconds)
    sig = sign_attachment_path(rel, exp)
    return f"/attachments/{rel}?{urlencode({'exp': exp, 'sig': sig})}"


def verify_attachment_signature(rel_path: str, exp: str | int | None, sig: str | None) -> bool:
    try:
        exp_int = int(exp or 0)
    except (TypeError, ValueError):
        return False
    if not sig or exp_int <= 0 or exp_int < int(time.time()):
        return False
    expected = sign_attachment_path(rel_path, exp_int)
    return hmac.compare_digest(expected, str(sig))
