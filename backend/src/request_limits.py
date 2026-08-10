"""ASGI security/resource guard executed before FastAPI parses request bodies."""

from __future__ import annotations

import threading

from starlette.responses import JSONResponse
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from .config import Settings
from .rate_limit import SlidingWindowRateLimiter
from .security import service_token_is_valid


MULTIPART_OVERHEAD_BYTES = 64 * 1024
MAX_STANDARD_REQUEST_BYTES = 64 * 1024
HEAVY_WORKLOAD_PATHS = frozenset(
    {
        "/api/upload",
        "/api/overview",
        "/api/data-quality",
        "/api/dashboard",
        "/api/ai-summary",
        "/api/ask",
        "/api/anomalies",
        "/api/report",
    }
)


class _RequestBodyTooLarge(Exception):
    """Internal signal raised before a parser receives excess request bytes."""


def _header_values(scope: Scope, name: bytes) -> list[bytes]:
    return [
        value
        for key, value in scope.get("headers", [])
        if key.lower() == name
    ]


def _bearer_token(scope: Scope) -> str | None:
    """Extract one unambiguous Bearer credential from raw ASGI headers."""

    values = _header_values(scope, b"authorization")
    if len(values) != 1:
        return None
    try:
        authorization = values[0].decode("latin-1")
    except UnicodeDecodeError:
        return None
    scheme, separator, token = authorization.partition(" ")
    if not separator or scheme.lower() != "bearer" or not token:
        return None
    return token


def _content_length(scope: Scope) -> int | None:
    """Parse duplicate/comma-joined Content-Length values without ambiguity."""

    raw_values = _header_values(scope, b"content-length")
    if not raw_values:
        return None
    values = [part.strip() for raw in raw_values for part in raw.split(b",")]
    if not values or any(not value.isdigit() for value in values):
        raise ValueError("Content-Length invalide.")
    parsed = {int(value) for value in values}
    if len(parsed) != 1:
        raise ValueError("Content-Length ambigu.")
    return parsed.pop()


class BusinessRequestGuardMiddleware:
    """Authenticate and bound business requests before FastAPI parses bodies.

    Uploads additionally consume a process-wide quota. A shared semaphore
    serializes upload parsing and memory-heavy analytics before multipart/JSON
    parsing. The ASGI ``receive`` counter also protects bodies sent without
    Content-Length and bodies larger than their declared length.
    """

    def __init__(
        self,
        app: ASGIApp,
        *,
        settings: Settings,
        rate_limiter: SlidingWindowRateLimiter,
        workload_gate: threading.BoundedSemaphore,
    ) -> None:
        self.app = app
        self.settings = settings
        self.rate_limiter = rate_limiter
        self.workload_gate = workload_gate
        self.max_upload_body_bytes = (
            settings.max_upload_bytes + MULTIPART_OVERHEAD_BYTES
        )

    async def _respond(
        self,
        scope: Scope,
        receive: Receive,
        send: Send,
        *,
        status_code: int,
        detail: str,
        headers: dict[str, str] | None = None,
    ) -> None:
        response = JSONResponse(
            status_code=status_code,
            content={"detail": detail},
            headers=headers,
        )
        await response(scope, receive, send)

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        path = str(scope.get("path", ""))
        if (
            scope["type"] != "http"
            or not path.startswith("/api/")
            or path == "/api/health"
        ):
            await self.app(scope, receive, send)
            return

        if not service_token_is_valid(self.settings, _bearer_token(scope)):
            await self._respond(
                scope,
                receive,
                send,
                status_code=401,
                detail="Authentification du service requise.",
                headers={"WWW-Authenticate": "Bearer"},
            )
            return

        try:
            content_length = _content_length(scope)
        except ValueError as exc:
            await self._respond(
                scope,
                receive,
                send,
                status_code=400,
                detail=str(exc),
            )
            return
        is_upload = path == "/api/upload"
        max_body_bytes = (
            self.max_upload_body_bytes
            if is_upload
            else MAX_STANDARD_REQUEST_BYTES
        )
        if content_length is not None and content_length > max_body_bytes:
            await self._respond(
                scope,
                receive,
                send,
                status_code=413,
                detail="Requête trop volumineuse pour la limite configurée.",
            )
            return

        gate_acquired = False
        if path in HEAVY_WORKLOAD_PATHS:
            gate_acquired = self.workload_gate.acquire(blocking=False)
            if not gate_acquired:
                await self._respond(
                    scope,
                    receive,
                    send,
                    status_code=429,
                    detail=(
                        "Un autre upload est déjà en cours de traitement."
                        if is_upload
                        else "Une autre analyse est déjà en cours de traitement."
                    ),
                    headers={"Retry-After": "1"},
                )
                return

        if is_upload:
            decision = self.rate_limiter.consume()
            if not decision.allowed:
                # The request obtained a workload slot but will not parse a
                # body, so make the slot available before sending the response.
                self.workload_gate.release()
                gate_acquired = False
                await self._respond(
                    scope,
                    receive,
                    send,
                    status_code=429,
                    detail="Quota global d'uploads temporairement atteint.",
                    headers={"Retry-After": str(decision.retry_after_seconds)},
                )
                return

        received_bytes = 0
        body_too_large = False
        response_started = False

        async def limited_receive() -> Message:
            nonlocal body_too_large, received_bytes
            message = await receive()
            if message["type"] == "http.request":
                received_bytes += len(message.get("body", b""))
                if received_bytes > max_body_bytes:
                    body_too_large = True
                    raise _RequestBodyTooLarge
            return message

        async def tracked_send(message: Message) -> None:
            nonlocal response_started
            # Starlette's multipart parser can translate receive errors into a
            # generic 400. Once the byte counter fired, suppress that internal
            # response so this outer guard can emit the intended 413 instead.
            if body_too_large:
                return
            if message["type"] == "http.response.start":
                response_started = True
            await send(message)

        try:
            try:
                await self.app(scope, limited_receive, tracked_send)
            except _RequestBodyTooLarge:
                pass
            if body_too_large:
                # Body parsing happens before these endpoints can start a
                # response. Still fail closed instead of emitting a second
                # response if an ASGI implementation violates that assumption.
                if response_started:
                    raise RuntimeError(
                        "Request body limit exceeded after response start."
                    )
                await self._respond(
                    scope,
                    receive,
                    send,
                    status_code=413,
                    detail="Requête trop volumineuse pour la limite configurée.",
                )
        finally:
            if gate_acquired:
                self.workload_gate.release()
