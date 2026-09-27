from __future__ import annotations
import hmac
from typing import Optional
from fastapi import Header, HTTPException, Security, Request, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from app.core.config import settings

_bearer_security = HTTPBearer(auto_error=False)


def require_admin_token(
    request: Request,
    auth: Optional[HTTPAuthorizationCredentials] = Security(_bearer_security),
    x_api_key: Optional[str] = Header(None, alias="X-API-Key"),
) -> bool:
    """
    Verifica a autenticação para endpoints administrativos e mutáveis.
    Aceita token via:
      - Header 'Authorization: Bearer <token>'
      - Header 'X-API-Key: <token>'
    
    Se AGENT_API_TOKEN não estiver configurado no ambiente e ENVIRONMENT for 'development',
    permite a requisição em modo desenvolvimento local para não interromper os fluxos do usuário.
    """
    expected_token = settings.AGENT_API_TOKEN.strip() if settings.AGENT_API_TOKEN else ""

    # Se não há token configurado no ambiente:
    if not expected_token:
        # Se estiver em desenvolvimento, permite
        if settings.ENVIRONMENT == "development":
            return True
        # Se for produção/staging sem token configurado, rejeita por segurança
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"error": {"code": "AUTH_REQUIRED", "message": "Admin API token must be configured in production."}},
        )

    # Coleta o token fornecido
    provided_token: Optional[str] = None
    if auth and auth.credentials:
        provided_token = auth.credentials.strip()
    elif x_api_key:
        provided_token = x_api_key.strip()

    if not provided_token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"error": {"code": "TOKEN_MISSING", "message": "Authentication token missing."}},
            headers={"WWW-Authenticate": "Bearer"},
        )

    if not hmac.compare_digest(provided_token, expected_token):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={"error": {"code": "FORBIDDEN", "message": "Invalid authentication token."}},
        )

    return True
