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


def build_service_token_dependency(settings: Settings) -> ServiceTokenDependency:
    """Build an application-scoped bearer-token validator.

    ``compare_digest`` operates on bytes to support every header value without
    raising on non-ASCII input and to avoid data-dependent string comparison.
    """

    expected_token = (
        settings.backend_service_token.encode("utf-8")
        if settings.backend_service_token is not None
        else None
    )

    async def require_service_token(
        credentials: Annotated[
            HTTPAuthorizationCredentials | None,
            Security(SERVICE_BEARER_SCHEME),
        ] = None,
    ) -> None:
        # An unprotected backend is allowed only in the explicit local/test mode.
        if expected_token is None:
            return

        provided_token = (
            credentials.credentials.encode("utf-8")
            if credentials is not None
            else b""
        )
        if credentials is None or not secrets.compare_digest(
            provided_token, expected_token
        ):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Authentification du service requise.",
                headers={"WWW-Authenticate": "Bearer"},
            )

    return require_service_token
