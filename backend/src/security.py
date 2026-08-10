"""Small authentication boundary for the public FastAPI service.

The browser never receives this service token.  A trusted frontend proxy adds
it to server-to-server requests before they reach the backend.
"""

from __future__ import annotations

import secrets
from collections.abc import Callable, Coroutine
from typing import Any, Annotated

from fastapi import HTTPException, Security, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from .config import Settings


SERVICE_BEARER_SCHEME = HTTPBearer(
    auto_error=False,
    scheme_name="BackendServiceToken",
    description="Jeton interne utilisé par le proxy frontend de confiance.",
)
ServiceTokenDependency = Callable[..., Coroutine[Any, Any, None]]


def service_token_is_valid(settings: Settings, provided_token: str | None) -> bool:
    """Validate a raw bearer token with one shared constant-time comparison.

    The ASGI business guard calls this helper before request-body parsing,
    while the FastAPI dependency below remains the defence-in-depth check for
    routing.
    """

    if settings.backend_service_token is None:
        return True
    expected_token = settings.backend_service_token.encode("utf-8")
    candidate = (provided_token or "").encode("utf-8")
    return secrets.compare_digest(candidate, expected_token)


def build_service_token_dependency(settings: Settings) -> ServiceTokenDependency:
    """Build an application-scoped bearer-token validator.

    ``compare_digest`` operates on bytes to support every header value without
    raising on non-ASCII input and to avoid data-dependent string comparison.
    """

    async def require_service_token(
        credentials: Annotated[
            HTTPAuthorizationCredentials | None,
            Security(SERVICE_BEARER_SCHEME),
        ] = None,
    ) -> None:
        # An unprotected backend is allowed only in the explicit local/test mode.
        if settings.backend_service_token is None:
            return

        if credentials is None or not service_token_is_valid(
            settings, credentials.credentials
        ):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Authentification du service requise.",
                headers={"WWW-Authenticate": "Bearer"},
            )

    return require_service_token
