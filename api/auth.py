"""Revalidação de token contra o subscription_access_api.

Não reimplementa nenhuma regra de acesso/assinatura: cada request chega com
o mesmo token de sessão emitido pelo Hub (`POST /generate-agendador-token`)
e essa camada apenas confere com a fonte da verdade existente
(`POST /validate-agendador-token`), igual ao que docksmith/app.py já faz.
"""

import httpx
from fastapi import Header, HTTPException

from . import config
from .logging_config import get_logger

logger = get_logger(__name__)


def _extract_token(authorization: str | None) -> str:
    if not authorization:
        raise HTTPException(status_code=401, detail="Token ausente. Faça login pelo Hub.")
    token = authorization.strip()
    if token.lower().startswith("bearer "):
        token = token.split(" ", 1)[1].strip()
    if not token:
        raise HTTPException(status_code=401, detail="Token ausente. Faça login pelo Hub.")
    return token


async def get_current_user(authorization: str | None = Header(default=None)) -> dict:
    try:
        token = _extract_token(authorization)
    except HTTPException:
        logger.warning("Autenticação rejeitada: token ausente")
        raise

    if config.DEV_BYPASS_AUTH and token == "dev-bypass-token":
        logger.info("Autenticação aceita: bypass de dev")
        return {"token": token, "user": {"id": "dev", "email": "dev@docksmith.local"}}

    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            resp = await client.post(
                f"{config.API_BASE}/validate-agendador-token",
                json={"token": token},
            )
    except httpx.HTTPError:
        logger.error("Falha ao contatar subscription_access_api para validar token")
        raise HTTPException(status_code=502, detail="Não foi possível validar o acesso agora. Tente novamente.")

    if resp.status_code != 200:
        logger.warning("Autenticação rejeitada: token inválido/expirado (status=%d)", resp.status_code)
        raise HTTPException(status_code=401, detail="Token inválido ou expirado. Faça login novamente pelo Hub.")

    data = resp.json()
    user = data.get("user", {})
    logger.info("Autenticação aceita: usuário id=%s", user.get("id"))
    return {"token": token, "user": user}
