"""API-key authentication helpers shared across HTTP route registration."""

from __future__ import annotations

from typing import Any, Optional

from fastapi import Header, HTTPException

_api_key: Optional[str] = None


def set_api_key(key: Optional[str]) -> None:
    """Set the process-level API key used by auth verification helpers.

    Args:
        key: API key string, or ``None`` to disable auth enforcement.
    """

    global _api_key
    _api_key = key


def _authorization_token(authorization: Optional[str]) -> Optional[str]:
    if not authorization:
        return None
    return authorization[7:] if authorization.startswith("Bearer ") else authorization


def verify_token_from_request(
    body: dict[str, Any], authorization: Optional[str] = None
) -> Optional[str]:
    """Validate legacy body/header authentication.

    Authorization headers take precedence. This lets pre-body middleware
    authenticate a request without a stale or attacker-supplied ``ai_token`` in
    the subsequently parsed body overriding an already valid header.
    """

    if _api_key is None:
        return None

    header_token = _authorization_token(authorization)
    if header_token is not None:
        if header_token == _api_key:
            return header_token
        raise HTTPException(status_code=401, detail="Invalid API key")

    ai_token = body.get("ai_token") if body else None
    if ai_token:
        if ai_token == _api_key:
            return ai_token
        raise HTTPException(status_code=401, detail="Invalid ai_token")

    raise HTTPException(status_code=401, detail="Missing ai_token or Authorization header")


async def verify_api_key(authorization: Optional[str] = Header(None)) -> None:
    """Validate Authorization header before protected endpoint processing."""

    if _api_key is None:
        return

    token = _authorization_token(authorization)
    if token is None:
        raise HTTPException(status_code=401, detail="Missing Authorization header")
    if token != _api_key:
        raise HTTPException(status_code=401, detail="Invalid API key")
