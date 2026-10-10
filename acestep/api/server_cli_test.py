"""Focused tests for secure API CLI startup."""

from __future__ import annotations

import os
import unittest
from unittest.mock import MagicMock, patch

from acestep.api.server_cli import _is_loopback_host, run_api_server_main


class TestSecureApiServerCli(unittest.TestCase):
    """Verify authentication is configured before serving the application."""

    @staticmethod
    def _env_bool(_name: str, default: bool) -> bool:
        return default

    def test_loopback_detection(self) -> None:
        self.assertTrue(_is_loopback_host("127.0.0.1"))
        self.assertTrue(_is_loopback_host("::1"))
        self.assertTrue(_is_loopback_host("localhost"))
        self.assertFalse(_is_loopback_host("0.0.0.0"))
        self.assertFalse(_is_loopback_host("192.168.1.10"))
        self.assertFalse(_is_loopback_host("example.test"))

    @patch("acestep.api.server_cli.uvicorn.run")
    def test_remote_bind_without_key_is_rejected_before_app_creation(
        self,
        uvicorn_run: MagicMock,
    ) -> None:
        app_factory = MagicMock()

        with patch.dict(os.environ, {}, clear=True):
            with self.assertRaises(SystemExit) as raised:
                run_api_server_main(
                    self._env_bool,
                    argv=["--host", "0.0.0.0"],
                    app_factory=app_factory,
                )

        self.assertEqual(raised.exception.code, 2)
        app_factory.assert_not_called()
        uvicorn_run.assert_not_called()

    @patch("acestep.api.server_cli.uvicorn.run")
    def test_api_key_is_visible_when_fresh_app_is_created(
        self,
        uvicorn_run: MagicMock,
    ) -> None:
        application = object()
        observed = {}

        def app_factory():
            observed["api_key"] = os.getenv("ACESTEP_API_KEY")
            return application

        with patch.dict(os.environ, {}, clear=True):
            run_api_server_main(
                self._env_bool,
                argv=[
                    "--host",
                    "0.0.0.0",
                    "--port",
                    "9001",
                    "--api-key",
                    "  secret-value  ",
                ],
                app_factory=app_factory,
            )

        self.assertEqual(observed["api_key"], "secret-value")
        uvicorn_run.assert_called_once_with(
            application,
            host="0.0.0.0",
            port=9001,
            reload=False,
            workers=1,
        )

    @patch("acestep.api.server_cli.uvicorn.run")
    def test_loopback_without_key_remains_supported(
        self,
        uvicorn_run: MagicMock,
    ) -> None:
        application = object()
        app_factory = MagicMock(return_value=application)

        with patch.dict(os.environ, {"ACESTEP_API_KEY": "stale"}, clear=True):
            run_api_server_main(
                self._env_bool,
                argv=["--host", "127.0.0.1", "--api-key", ""],
                app_factory=app_factory,
            )
            self.assertNotIn("ACESTEP_API_KEY", os.environ)

        app_factory.assert_called_once_with()
        uvicorn_run.assert_called_once_with(
            application,
            host="127.0.0.1",
            port=8001,
            reload=False,
            workers=1,
        )


if __name__ == "__main__":
    unittest.main()
