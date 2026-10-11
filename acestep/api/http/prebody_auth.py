"""Authenticate legacy body-parsing routes before request payload consumption."""

from __future__ import annotations

from collections.abc import Awaitable, Callable, Iterable
from typing import Any

from fastapi import FastAPI, HTTPException, Request
from starlette.responses import JSONResponse, Response

DEFAULT_PREBODY_AUTH_PATHS = frozenset(
    {
        "/release_task",
        "/query_result",
        "/create_random_sample",
        "/format_input",
        "/v1/create_sample",
    }
)


def install_prebody_auth_middleware(
    app: FastAPI,
    verify_api_key: Callable[[str | None], Awaitable[Any]],
    *,
    protected_paths: Iterable[str] = DEFAULT_PREBODY_AUTH_PATHS,
) -> None:
    """Require header authentication before selected routes can read bodies.

    The middleware deliberately skips CORS preflight. When authentication is
    disabled, the shared verifier returns normally and legacy local behavior is
    preserved. When a key is configured, body-only ``ai_token`` authentication
    is no longer sufficient for these potentially large JSON/form/multipart
    routes because reading the body before authentication is the vulnerability.
    """

    paths = frozenset(protected_paths)

    @app.middleware("http")
    async def authenticate_before_body(
        request: Request,
        call_next: Callable[[Request], Awaitable[Response]],
    ) -> Response:
        if request.method != "OPTIONS" and request.url.path in paths:
            try:
                await verify_api_key(request.headers.get("authorization"))
            except HTTPException as exc:
                return JSONResponse(
                    status_code=exc.status_code,
                    content={"detail": exc.detail},
                    headers=exc.headers,
                )
        return await call_next(request)
