"""Helpers for mounting API routers behind the configured API-key check."""

from __future__ import annotations

from typing import Any, Callable

from fastapi import APIRouter, Depends, FastAPI


def include_authenticated_router(
    app: FastAPI,
    router: APIRouter,
    verify_api_key: Callable[..., Any],
) -> None:
    """Mount every route in ``router`` behind ``verify_api_key``.

    Args:
        app: FastAPI application receiving the router.
        router: Router whose endpoints require the configured API key.
        verify_api_key: FastAPI dependency that validates the request.
    """

    app.include_router(router, dependencies=[Depends(verify_api_key)])
