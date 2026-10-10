"""Focused tests for authenticated router mounting."""

from __future__ import annotations

import unittest
from typing import Optional

from fastapi import APIRouter, FastAPI, Header, HTTPException
from fastapi.testclient import TestClient

from acestep.api.http.authenticated_router import include_authenticated_router


class TestAuthenticatedRouter(unittest.TestCase):
    """Verify the shared dependency protects every mounted router endpoint."""

    def test_dependency_protects_router_without_protecting_unrelated_route(self) -> None:
        app = FastAPI()
        router = APIRouter()

        @app.get("/health")
        async def health() -> dict[str, bool]:
            return {"ok": True}

        @router.get("/v1/models")
        async def models() -> dict[str, list]:
            return {"data": []}

        async def verify_api_key(
            authorization: Optional[str] = Header(None),
        ) -> None:
            if authorization != "Bearer secret":
                raise HTTPException(status_code=401, detail="Invalid API key")

        include_authenticated_router(app, router, verify_api_key)
        client = TestClient(app)

        self.assertEqual(client.get("/health").status_code, 200)
        self.assertEqual(client.get("/v1/models").status_code, 401)
        self.assertEqual(
            client.get(
                "/v1/models",
                headers={"Authorization": "Bearer secret"},
            ).status_code,
            200,
        )


if __name__ == "__main__":
    unittest.main()
