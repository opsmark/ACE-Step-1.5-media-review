"""Focused tests for authentication before request-body parsing."""

from __future__ import annotations

from fastapi import FastAPI, Request
from fastapi.testclient import TestClient
from unittest import TestCase

from acestep.api.http.auth import set_api_key, verify_api_key, verify_token_from_request
from acestep.api.http.prebody_auth import install_prebody_auth_middleware


class PrebodyAuthTests(TestCase):
    def tearDown(self) -> None:
        set_api_key(None)

    @staticmethod
    def _app():
        app = FastAPI()
        state = {"route_called": False, "body_read": False}
        install_prebody_auth_middleware(app, verify_api_key)

        @app.post("/release_task")
        async def release_task(request: Request):
            state["route_called"] = True
            body = await request.json()
            state["body_read"] = True
            verify_token_from_request(body, request.headers.get("authorization"))
            return {"ok": True}

        @app.options("/release_task")
        async def preflight():
            return {"ok": True}

        return app, state

    def test_missing_header_is_rejected_before_route_or_body_read(self) -> None:
        set_api_key("secret")
        app, state = self._app()
        response = TestClient(app).post(
            "/release_task",
            json={"ai_token": "secret", "payload": "x" * 1000},
        )
        self.assertEqual(401, response.status_code)
        self.assertFalse(state["route_called"])
        self.assertFalse(state["body_read"])

    def test_wrong_header_is_rejected_before_route_or_body_read(self) -> None:
        set_api_key("secret")
        app, state = self._app()
        response = TestClient(app).post(
            "/release_task",
            headers={"Authorization": "Bearer wrong"},
            json={"payload": "x" * 1000},
        )
        self.assertEqual(401, response.status_code)
        self.assertFalse(state["route_called"])
        self.assertFalse(state["body_read"])

    def test_valid_header_allows_body_and_overrides_stale_body_token(self) -> None:
        set_api_key("secret")
        app, state = self._app()
        response = TestClient(app).post(
            "/release_task",
            headers={"Authorization": "Bearer secret"},
            json={"ai_token": "stale", "payload": "ok"},
        )
        self.assertEqual(200, response.status_code)
        self.assertTrue(state["route_called"])
        self.assertTrue(state["body_read"])

    def test_auth_disabled_preserves_local_body_route(self) -> None:
        set_api_key(None)
        app, state = self._app()
        response = TestClient(app).post("/release_task", json={"payload": "ok"})
        self.assertEqual(200, response.status_code)
        self.assertTrue(state["body_read"])

    def test_options_preflight_is_not_challenged(self) -> None:
        set_api_key("secret")
        app, state = self._app()
        response = TestClient(app).options("/release_task")
        self.assertEqual(200, response.status_code)
        self.assertFalse(state["body_read"])

    def test_unlisted_route_is_unchanged(self) -> None:
        set_api_key("secret")
        app = FastAPI()
        install_prebody_auth_middleware(app, verify_api_key)

        @app.post("/healthish")
        async def healthish(request: Request):
            return {"size": len(await request.body())}

        response = TestClient(app).post("/healthish", content=b"abc")
        self.assertEqual(200, response.status_code)
        self.assertEqual(3, response.json()["size"])
